"""All write operations, as raw parameterised SQL inside transactions.

I-1, I-2, U-1, U-2, U-3 and D-1 refer to the Phase 1 functional requirements.
Any exception rolls the whole operation back (see db.transaction).
"""
from db import transaction


class FormError(ValueError):
    """Invalid user input, shown to the user as a message."""


def _recompute_heat(cur, champ_id, cat_code, heat_number):
    """Recalculate the stored rank_in_heat and diff_to_leader_ms of one heat.

    The previous rank breaks exact ties, which keeps the order the site
    published for pairs with equal times.
    """
    heat = (champ_id, cat_code, heat_number)
    cur.execute("""
        UPDATE RACE_RESULT SET rank_in_heat = NULL, diff_to_leader_ms = NULL
         WHERE champ_id = %s AND cat_code = %s AND heat_number = %s
           AND finish_status <> 'COMPLETED'""", heat)
    cur.execute("""
        UPDATE RACE_RESULT rr
          JOIN (SELECT carrier_id, carried_id,
                       ROW_NUMBER() OVER (ORDER BY finish_time_ms, rank_in_heat) AS new_rank,
                       finish_time_ms - MIN(finish_time_ms) OVER () AS new_diff
                  FROM RACE_RESULT
                 WHERE champ_id = %s AND cat_code = %s AND heat_number = %s
                   AND finish_status = 'COMPLETED') ranked
            ON ranked.carrier_id = rr.carrier_id AND ranked.carried_id = rr.carried_id
           SET rr.rank_in_heat = ranked.new_rank, rr.diff_to_leader_ms = ranked.new_diff
         WHERE rr.champ_id = %s AND rr.cat_code = %s AND rr.heat_number = %s""", heat + heat)


def _find_or_create_competitor(cur, person):
    cur.execute("SELECT person_id FROM PERSON WHERE email = %s", (person["email"],))
    row = cur.fetchone()
    if row:
        person_id = row["person_id"]
    else:
        cur.execute("""
            INSERT INTO PERSON (first_name, last_name, email, gender, date_of_birth, role_type, nationality_code)
            VALUES (%s, %s, %s, %s, %s, 'COMPETITOR', %s)""",
                    (person["first_name"], person["last_name"], person["email"], person["gender"],
                     person["date_of_birth"], person["country"]))
        person_id = cur.lastrowid
    cur.execute("""
        INSERT INTO COMPETITOR (person_id, weight_kg) VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE weight_kg = VALUES(weight_kg)""", (person_id, person["weight_kg"]))
    if person.get("phone"):
        cur.execute("""
            INSERT INTO PERSON_PHONE (person_id, phone_number) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE phone_number = VALUES(phone_number)""", (person_id, person["phone"]))
    return person_id


def register_pair(champ_id, cat_code, bib_number, carrier, carried):
    """I-1: register a pair. Returns the backpack weight set by the trigger."""
    with transaction() as cur:
        carrier_id = _find_or_create_competitor(cur, carrier)
        carried_id = _find_or_create_competitor(cur, carried)
        cur.execute("""
            INSERT INTO PAIR (carrier_id, carried_id, formed_year, is_active) VALUES (%s, %s, YEAR(CURDATE()), TRUE)
            ON DUPLICATE KEY UPDATE is_active = TRUE""", (carrier_id, carried_id))
        for code in {carrier["country"], carried["country"]}:
            cur.execute("""
                INSERT INTO REPRESENTS (carrier_id, carried_id, country_code) VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE country_code = VALUES(country_code)""", (carrier_id, carried_id, code))
        cur.execute("""
            INSERT INTO REGISTRATION (champ_id, cat_code, carrier_id, carried_id, bib_number, fee_paid, status, registered_at)
            VALUES (%s, %s, %s, %s, %s, 55, 'CONFIRMED', NOW())""",
                    (champ_id, cat_code, carrier_id, carried_id, bib_number))
        cur.execute("""
            SELECT backpack_weight_kg FROM REGISTRATION
             WHERE champ_id = %s AND cat_code = %s AND carrier_id = %s AND carried_id = %s""",
                    (champ_id, cat_code, carrier_id, carried_id))
        return cur.fetchone()["backpack_weight_kg"]


def file_protest(champ_id, cat_code, heat_number, filed_at, filer, against, description):
    """I-2: file a protest. The trigger checks the time window and both pairs."""
    with transaction() as cur:
        cur.execute("""
            SELECT COALESCE(MAX(protest_seq), 0) + 1 AS next_seq
              FROM PROTEST WHERE champ_id = %s FOR UPDATE""", (champ_id,))
        seq = cur.fetchone()["next_seq"]
        cur.execute("""
            INSERT INTO PROTEST (champ_id, protest_seq, filed_at, fee_paid, status, description, heat_cat_code,
                                 heat_number, filer_carrier_id, filer_carried_id, against_carrier_id, against_carried_id)
            VALUES (%s, %s, %s, 150, 'PENDING', %s, %s, %s, %s, %s, %s, %s)""",
                    (champ_id, seq, filed_at, description, cat_code, heat_number, *filer, *against))
        return seq


def correct_finish_time(champ_id, cat_code, heat_number, carrier_id, carried_id, new_time_ms, drop_count):
    """U-1: correct a finish time, recalculate the heat, flag pending protests."""
    with transaction() as cur:
        cur.execute("""
            UPDATE RACE_RESULT SET finish_time_ms = %s, drop_count = %s
             WHERE champ_id = %s AND cat_code = %s AND heat_number = %s
               AND carrier_id = %s AND carried_id = %s AND finish_status = 'COMPLETED'""",
                    (new_time_ms, drop_count, champ_id, cat_code, heat_number, carrier_id, carried_id))
        cur.execute("""
            SELECT 1 FROM RACE_RESULT
             WHERE champ_id = %s AND cat_code = %s AND heat_number = %s
               AND carrier_id = %s AND carried_id = %s AND finish_status = 'COMPLETED'""",
                    (champ_id, cat_code, heat_number, carrier_id, carried_id))
        if cur.fetchone() is None:
            raise FormError("That result does not exist, or the pair did not finish.")
        _recompute_heat(cur, champ_id, cat_code, heat_number)
        cur.execute("""
            UPDATE PROTEST SET status = 'UNDER_REVIEW'
             WHERE champ_id = %s AND heat_cat_code = %s AND heat_number = %s AND status = 'PENDING'
               AND ((filer_carrier_id = %s AND filer_carried_id = %s)
                 OR (against_carrier_id = %s AND against_carried_id = %s))""",
                    (champ_id, cat_code, heat_number, carrier_id, carried_id, carrier_id, carried_id))
        cur.execute("""
            SELECT rank_in_heat FROM RACE_RESULT
             WHERE champ_id = %s AND cat_code = %s AND heat_number = %s AND carrier_id = %s AND carried_id = %s""",
                    (champ_id, cat_code, heat_number, carrier_id, carried_id))
        return cur.fetchone()["rank_in_heat"]


def change_carrier(champ_id, cat_code, carrier_id, carried_id, new_carrier_id, new_bib):
    """U-2: the registered carrier becomes the carried competitor of a new pair."""
    with transaction() as cur:
        cur.execute("""
            SELECT fee_paid, status FROM REGISTRATION
             WHERE champ_id = %s AND cat_code = %s AND carrier_id = %s AND carried_id = %s FOR UPDATE""",
                    (champ_id, cat_code, carrier_id, carried_id))
        old = cur.fetchone()
        if old is None:
            raise FormError("That registration does not exist.")
        if old["status"] != "CONFIRMED":
            raise FormError("Only a confirmed registration can be changed.")

        cur.execute("""
            INSERT INTO PAIR (carrier_id, carried_id, formed_year, is_active) VALUES (%s, %s, YEAR(CURDATE()), TRUE)
            ON DUPLICATE KEY UPDATE is_active = TRUE""", (new_carrier_id, carrier_id))
        cur.execute("""
            INSERT INTO REPRESENTS (carrier_id, carried_id, country_code)
            SELECT %s, %s, country_code FROM REPRESENTS WHERE carrier_id = %s AND carried_id = %s
            ON DUPLICATE KEY UPDATE country_code = VALUES(country_code)""",
                    (new_carrier_id, carrier_id, carrier_id, carried_id))
        cur.execute("UPDATE PAIR SET is_active = FALSE WHERE carrier_id = %s AND carried_id = %s",
                    (carrier_id, carried_id))
        cur.execute("""
            UPDATE REGISTRATION SET status = 'REPLACED'
             WHERE champ_id = %s AND cat_code = %s AND carrier_id = %s AND carried_id = %s""",
                    (champ_id, cat_code, carrier_id, carried_id))
        # The insert trigger re-checks age (C1, C2) and sets the backpack weight (C3).
        cur.execute("""
            INSERT INTO REGISTRATION (champ_id, cat_code, carrier_id, carried_id, bib_number, fee_paid, status, registered_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'CONFIRMED', NOW())""",
                    (champ_id, cat_code, new_carrier_id, carrier_id, new_bib, old["fee_paid"]))
        cur.execute("""
            UPDATE RACE_RESULT SET composition_changed = TRUE
             WHERE champ_id = %s AND carrier_id = %s AND carried_id = %s""",
                    (champ_id, carrier_id, carried_id))
        return cur.rowcount


def decide_protest(champ_id, protest_seq, official_id, outcome, decision_text):
    """U-3: record the jury's decision. An upheld protest disqualifies the pair."""
    with transaction() as cur:
        cur.execute("""
            SELECT status, heat_cat_code, heat_number, against_carrier_id, against_carried_id
              FROM PROTEST WHERE champ_id = %s AND protest_seq = %s FOR UPDATE""", (champ_id, protest_seq))
        protest = cur.fetchone()
        if protest is None:
            raise FormError("That protest does not exist.")
        if protest["status"] not in ("PENDING", "UNDER_REVIEW"):
            raise FormError("That protest has already been decided.")

        cur.execute("""
            SELECT COALESCE(MAX(decision_seq), 0) + 1 AS next_seq FROM PROTEST_DECISION
             WHERE champ_id = %s AND protest_seq = %s""", (champ_id, protest_seq))
        decision_seq = cur.fetchone()["next_seq"]
        cur.execute("""
            INSERT INTO PROTEST_DECISION (champ_id, protest_seq, decision_seq, decision_text, decided_at,
                                          decision_outcome, decided_by)
            VALUES (%s, %s, %s, %s, NOW(), %s, %s)""",
                    (champ_id, protest_seq, decision_seq, decision_text, outcome, official_id))
        cur.execute("UPDATE PROTEST SET status = %s WHERE champ_id = %s AND protest_seq = %s",
                    (outcome, champ_id, protest_seq))
        if outcome == "UPHELD":
            cur.execute("""
                UPDATE RACE_RESULT SET finish_status = 'DQ'
                 WHERE champ_id = %s AND cat_code = %s AND heat_number = %s
                   AND carrier_id = %s AND carried_id = %s""",
                        (champ_id, protest["heat_cat_code"], protest["heat_number"],
                         protest["against_carrier_id"], protest["against_carried_id"]))
            _recompute_heat(cur, champ_id, protest["heat_cat_code"], protest["heat_number"])


def delete_championship(champ_id, deleted_by, reason):
    """D-1: delete a championship with no dependent records, and log it."""
    with transaction() as cur:
        cur.execute("SELECT year FROM CHAMPIONSHIP WHERE champ_id = %s FOR UPDATE", (champ_id,))
        row = cur.fetchone()
        if row is None:
            raise FormError("That championship does not exist.")
        cur.execute("DELETE FROM CHAMPIONSHIP WHERE champ_id = %s", (champ_id,))
        cur.execute("""
            INSERT INTO CHAMPIONSHIP_DELETION_LOG (champ_id, year, deleted_by, deleted_at, reason)
            VALUES (%s, %s, %s, NOW(), %s)""", (champ_id, row["year"], deleted_by, reason))
        return row["year"]
