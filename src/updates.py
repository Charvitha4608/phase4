"""All write operations, as raw parameterised SQL inside transactions.

I-1, I-2, U-1, U-2, U-3 and D-1 refer to the Phase 1 functional requirements.
Any exception rolls the whole operation back (see db.transaction).
"""
import logging
from datetime import date, datetime, timedelta
from db import transaction

logger = logging.getLogger(__name__)

# In-memory notification queue and email outbox for tracking external events
NOTIFICATION_QUEUE = []
EMAIL_OUTBOX = []


class FormError(ValueError):
    """Invalid user input, shown to the user as a message."""


def send_confirmation_email(to_email, recipient_name, championship_year, series_name, bib_number):
    """Dispatch or queue a confirmation email for external notification."""
    message = {
        "to": to_email,
        "recipient_name": recipient_name,
        "subject": f"Registration Confirmation - Wife Carrying World Championships {championship_year}",
        "body": (
            f"Dear {recipient_name},\n\n"
            f"Your registration for {series_name} in the {championship_year} World Championships "
            f"has been confirmed.\n"
            f"Your bib number is {bib_number}.\n\n"
            f"Best of luck!"
        ),
        "sent_at": datetime.now().isoformat(),
    }
    EMAIL_OUTBOX.append(message)
    logger.info("Confirmation email sent to %s for bib %s", to_email, bib_number)
    return message


def queue_notification(recipient, message_text, event_type, details=None):
    """Queues an external notification (displaced pair, promoted pair, etc.)."""
    item = {
        "recipient": recipient,
        "message": message_text,
        "event_type": event_type,
        "details": details or {},
        "queued_at": datetime.now().isoformat(),
    }
    NOTIFICATION_QUEUE.append(item)
    logger.info("Notification queued for %s [%s]: %s", recipient, event_type, message_text)
    return item


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
    cur.execute("INSERT IGNORE INTO COMPETITOR (person_id) VALUES (%s)", (person_id,))
    if person.get("phone"):
        cur.execute("""
            INSERT INTO PERSON_PHONE (person_id, phone_number) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE phone_number = VALUES(phone_number)""", (person_id, person["phone"]))
    return person_id


def _category_fee(cur, cat_code, max_team_size=None):
    """C6: the entry fee of a category, as RACE_CATEGORY publishes it.

    The fee is never passed in from a form, so a registration cannot be booked at
    the wrong price. max_team_size, when given, is the size the caller is
    registering for, which keeps a team out of a pair category and the reverse.
    """
    cur.execute("SELECT entry_fee_eur, max_team_size FROM RACE_CATEGORY WHERE cat_code = %s", (cat_code,))
    row = cur.fetchone()
    if row is None:
        raise FormError("That series does not exist.")
    if max_team_size == 2 and row["max_team_size"] > 2:
        raise FormError("That is a team series. Please use the team registration form.")
    if max_team_size and max_team_size > 2 and row["max_team_size"] <= 2:
        raise FormError("That is a pair series. Please use the pair registration form.")
    return row["entry_fee_eur"]


def register_pair(champ_id, cat_code, carrier, carried):
    """I-1: register a pair. Returns the backpack weight set by the trigger.

    Weigh-ins are stored on the registration, not on the person, so each
    championship keeps its own weights (DC-1, DC-2). The fee comes from the
    category (C6), not from the form. The bib number is automatically assigned
    as the next unused number within the championship and category.
    """
    with transaction() as cur:
        # Check C12: Country codes must exist in COUNTRY
        for code in {carrier["country"], carried["country"]}:
            cur.execute("SELECT 1 FROM COUNTRY WHERE country_code = %s", (code,))
            if not cur.fetchone():
                raise FormError(f"Country code '{code}' does not exist.")

        # Check C1: Carrier age must be at least 18 on championship start date
        cur.execute("SELECT year, start_date FROM CHAMPIONSHIP WHERE champ_id = %s", (champ_id,))
        ch_row = cur.fetchone()
        champ_year = ch_row["year"] if ch_row else 2027
        if ch_row and ch_row.get("start_date") and carrier.get("date_of_birth"):
            start = ch_row["start_date"]
            dob_carrier = carrier["date_of_birth"]
            carrier_age = start.year - dob_carrier.year - ((start.month, start.day) < (dob_carrier.month, dob_carrier.day))
            if carrier_age < 18:
                raise FormError("Carrier is younger than the minimum age for this category on the start date.")
            if carried.get("date_of_birth"):
                dob_carried = carried["date_of_birth"]
                carried_age = start.year - dob_carried.year - ((start.month, start.day) < (dob_carried.month, dob_carried.day))
                if carried_age < 17:
                    raise FormError("Carried competitor is younger than the minimum age for this category on the start date.")

        fee = _category_fee(cur, cat_code, max_team_size=2)
        carrier_id = _find_or_create_competitor(cur, carrier)
        carried_id = _find_or_create_competitor(cur, carried)

        if carrier_id == carried_id:
            raise FormError("The carrier and the carried competitor must be two different people.")

        cur.execute("""
            INSERT INTO PAIR (carrier_id, carried_id, formed_year, is_active) VALUES (%s, %s, YEAR(CURDATE()), TRUE)
            ON DUPLICATE KEY UPDATE is_active = TRUE""", (carrier_id, carried_id))
        for code in {carrier["country"], carried["country"]}:
            cur.execute("""
                INSERT INTO REPRESENTS (carrier_id, carried_id, country_code) VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE country_code = VALUES(country_code)""", (carrier_id, carried_id, code))

        # Auto-assign the next available unique bib number for this championship/category (C4)
        cur.execute("""
            SELECT COALESCE(MAX(bib_number), 0) + 1 AS next_bib
              FROM REGISTRATION WHERE champ_id = %s AND cat_code = %s FOR UPDATE""",
                    (champ_id, cat_code))
        bib_number = cur.fetchone()["next_bib"]

        cur.execute("""
            INSERT INTO REGISTRATION (champ_id, cat_code, carrier_id, carried_id, bib_number,
                                      carrier_weigh_in_kg, carried_weigh_in_kg, fee_paid, status, registered_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'CONFIRMED', NOW())""",
                    (champ_id, cat_code, carrier_id, carried_id, bib_number,
                     carrier["weight_kg"], carried["weight_kg"], fee))

        cur.execute("""
            SELECT backpack_weight_kg FROM REGISTRATION
             WHERE champ_id = %s AND cat_code = %s AND carrier_id = %s AND carried_id = %s""",
                    (champ_id, cat_code, carrier_id, carried_id))
        backpack = cur.fetchone()["backpack_weight_kg"]

    # Send confirmation email after successful registration (external action)
    send_confirmation_email(
        to_email=carrier["email"],
        recipient_name=f"{carrier['first_name']} {carrier['last_name']}",
        championship_year=champ_year,
        series_name=cat_code,
        bib_number=bib_number
    )
    return backpack


def register_team(champ_id, cat_code, team_name, home_country, carriers, carried):
    """I-1 (team): register a team of four in a team category.

    C10 wants exactly three carriers and one carried competitor, so TEAM_ROSTER
    gets four rows and the roster triggers enforce the shape. The entry itself
    goes in REGISTRATION like any other, under the pair of the first carrier and
    the carried competitor: that is the pair that holds the bib (C4), the
    weigh-ins and the team fee (C6). The other two carriers are on the roster.

    Returns (team_id, backpack_weight_kg, fee).
    """
    if len(carriers) != 3:
        raise FormError("A team needs exactly three carriers.")
    with transaction() as cur:
        # Check C12: Country codes
        all_countries = {home_country, carried["country"], *(p["country"] for p in carriers)}
        for code in all_countries:
            if code:
                cur.execute("SELECT 1 FROM COUNTRY WHERE country_code = %s", (code,))
                if not cur.fetchone():
                    raise FormError(f"Country code '{code}' does not exist.")

        cur.execute("SELECT year, start_date FROM CHAMPIONSHIP WHERE champ_id = %s", (champ_id,))
        ch_row = cur.fetchone()
        champ_year = ch_row["year"] if ch_row else 2027

        fee = _category_fee(cur, cat_code, max_team_size=4)

        cur.execute("SELECT team_id, home_country_code FROM TEAM WHERE name = %s FOR UPDATE", (team_name,))
        team = cur.fetchone()
        if team is None:
            cur.execute("""
                INSERT INTO TEAM (name, founded_year, home_country_code) VALUES (%s, YEAR(CURDATE()), %s)""",
                        (team_name, home_country))
            team_id = cur.lastrowid
        else:
            team_id = team["team_id"]
            cur.execute("""
                SELECT 1 FROM TEAM_ROSTER WHERE champ_id = %s AND team_id = %s""", (champ_id, team_id))
            if cur.fetchone():
                raise FormError(f'"{team_name}" already has a roster for this championship.')
            if team["home_country_code"] is None and home_country:
                cur.execute("UPDATE TEAM SET home_country_code = %s WHERE team_id = %s", (home_country, team_id))

        carrier_ids = [_find_or_create_competitor(cur, person) for person in carriers]
        carried_id = _find_or_create_competitor(cur, carried)
        if len(set(carrier_ids + [carried_id])) != 4:
            raise FormError("A team needs four different people.")

        for person_id in carrier_ids:
            cur.execute("""
                INSERT INTO TEAM_ROSTER (champ_id, team_id, competitor_id, team_role)
                VALUES (%s, %s, %s, 'CARRIER')""", (champ_id, team_id, person_id))
        cur.execute("""
            INSERT INTO TEAM_ROSTER (champ_id, team_id, competitor_id, team_role)
            VALUES (%s, %s, %s, 'CARRIED')""", (champ_id, team_id, carried_id))

        lead_carrier_id = carrier_ids[0]
        cur.execute("""
            INSERT INTO PAIR (carrier_id, carried_id, formed_year, is_active) VALUES (%s, %s, YEAR(CURDATE()), TRUE)
            ON DUPLICATE KEY UPDATE is_active = TRUE""", (lead_carrier_id, carried_id))
        for code in all_countries:
            if code:
                cur.execute("""
                    INSERT INTO REPRESENTS (carrier_id, carried_id, country_code) VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE country_code = VALUES(country_code)""",
                            (lead_carrier_id, carried_id, code))

        # Auto-assign the next available bib number for this championship/category (C4)
        cur.execute("""
            SELECT COALESCE(MAX(bib_number), 0) + 1 AS next_bib
              FROM REGISTRATION WHERE champ_id = %s AND cat_code = %s FOR UPDATE""",
                    (champ_id, cat_code))
        bib_number = cur.fetchone()["next_bib"]

        cur.execute("""
            INSERT INTO REGISTRATION (champ_id, cat_code, carrier_id, carried_id, bib_number,
                                      carrier_weigh_in_kg, carried_weigh_in_kg, fee_paid, status, registered_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'CONFIRMED', NOW())""",
                    (champ_id, cat_code, lead_carrier_id, carried_id, bib_number,
                     carriers[0]["weight_kg"], carried["weight_kg"], fee))
        cur.execute("""
            SELECT backpack_weight_kg FROM REGISTRATION
             WHERE champ_id = %s AND cat_code = %s AND carrier_id = %s AND carried_id = %s""",
                    (champ_id, cat_code, lead_carrier_id, carried_id))
        backpack = cur.fetchone()["backpack_weight_kg"]

    # Send confirmation email
    send_confirmation_email(
        to_email=carriers[0]["email"],
        recipient_name=f"{carriers[0]['first_name']} {carriers[0]['last_name']}",
        championship_year=champ_year,
        series_name=f"Team {team_name}",
        bib_number=bib_number
    )
    return team_id, backpack, fee


def file_protest(champ_id, cat_code, heat_number, filed_at, filer, against, description):
    """I-2: file a protest against a race result.

    Checks:
    - C5: within 15 minutes of max heat finish time. Rejects with PROTEST_WINDOW_EXPIRED.
    - C6: fee must be exactly 150 EUR and non-refundable.
    - C13: both pairs participated in the protested heat.
    - C12: both pairs exist in PAIR.
    - Flags the result as under protest with status PENDING.
    """
    with transaction() as cur:
        # Check C12: pair existence
        cur.execute("SELECT 1 FROM PAIR WHERE carrier_id = %s AND carried_id = %s", filer)
        if not cur.fetchone():
            raise FormError("The filing pair does not exist.")
        cur.execute("SELECT 1 FROM PAIR WHERE carrier_id = %s AND carried_id = %s", against)
        if not cur.fetchone():
            raise FormError("The protested pair does not exist.")

        if filer == against:
            raise FormError("A pair cannot file a protest against itself.")

        # Check C5: 15-minute protest window from maximum heat finish time
        cur.execute("""
            SELECT heat_completed_at FROM RACE_HEAT
             WHERE champ_id = %s AND cat_code = %s AND heat_number = %s""",
                    (champ_id, cat_code, heat_number))
        heat = cur.fetchone()
        if not heat or not heat["heat_completed_at"]:
            raise FormError("No finish time is recorded for this heat, so a protest cannot be accepted.")

        heat_end = heat["heat_completed_at"]
        if filed_at < heat_end or filed_at > heat_end + timedelta(minutes=15):
            raise FormError("PROTEST_WINDOW_EXPIRED: a protest must be filed within 15 minutes of the last finish in the heat.")

        # Check C13: both pairs took part in the heat
        cur.execute("""
            SELECT 1 FROM PARTICIPATES_IN
             WHERE champ_id = %s AND cat_code = %s AND heat_number = %s
               AND carrier_id = %s AND carried_id = %s""",
                    (champ_id, cat_code, heat_number, *filer))
        if not cur.fetchone():
            raise FormError("The filing pair did not participate in this heat.")

        cur.execute("""
            SELECT 1 FROM PARTICIPATES_IN
             WHERE champ_id = %s AND cat_code = %s AND heat_number = %s
               AND carrier_id = %s AND carried_id = %s""",
                    (champ_id, cat_code, heat_number, *against))
        if not cur.fetchone():
            raise FormError("The protested pair did not participate in this heat.")

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
    """U-1: correct a finish time, recalculate the heat, flag pending protests.

    - Recalculates rank_in_heat and diff_to_leader for the heat.
    - rank_in_category is dynamically recalculated via CATEGORY_RANKING view.
    - Updates Sprint Final qualifiers if qualification is affected and queues
      notification to displaced pairs.
    - Re-evaluates pending protests if the corrected result affects them.
    - Checks C12 and C5.
    """
    if new_time_ms <= 0:
        raise FormError("Finish time must be greater than zero.")

    with transaction() as cur:
        # Check C12: result must exist
        cur.execute("""
            SELECT finish_time_ms, finish_status FROM RACE_RESULT
             WHERE champ_id = %s AND cat_code = %s AND heat_number = %s
               AND carrier_id = %s AND carried_id = %s""",
                    (champ_id, cat_code, heat_number, carrier_id, carried_id))
        existing_result = cur.fetchone()
        if existing_result is None or existing_result["finish_status"] != 'COMPLETED':
            raise FormError("That result does not exist, or the pair did not finish.")

        # Capture Sprint qualifying top 4 before correction if SPRINT
        old_qualifiers = set()
        if cat_code == "SPRINT":
            cur.execute("""
                SELECT rr.carrier_id, rr.carried_id
                  FROM RACE_RESULT rr
                  JOIN RACE_HEAT rh ON rh.champ_id = rr.champ_id AND rh.cat_code = rr.cat_code
                                   AND rh.heat_number = rr.heat_number
                 WHERE rr.champ_id = %s AND rr.cat_code = 'SPRINT' AND rh.round_type = 'QUALIFYING'
                   AND rr.finish_status = 'COMPLETED' AND rr.finish_time_ms IS NOT NULL
                 ORDER BY rr.finish_time_ms ASC
                 LIMIT 4""", (champ_id,))
            old_qualifiers = set((r["carrier_id"], r["carried_id"]) for r in cur.fetchall())

        cur.execute("""
            UPDATE RACE_RESULT SET finish_time_ms = %s, drop_count = %s
             WHERE champ_id = %s AND cat_code = %s AND heat_number = %s
               AND carrier_id = %s AND carried_id = %s AND finish_status = 'COMPLETED'""",
                    (new_time_ms, drop_count, champ_id, cat_code, heat_number, carrier_id, carried_id))

        # Recalculate rank_in_heat and diff_to_leader_ms for all heat rows
        _recompute_heat(cur, champ_id, cat_code, heat_number)

        # Check and update Sprint Final qualifiers if affected
        if cat_code == "SPRINT":
            cur.execute("""
                SELECT rr.carrier_id, rr.carried_id
                  FROM RACE_RESULT rr
                  JOIN RACE_HEAT rh ON rh.champ_id = rr.champ_id AND rh.cat_code = rr.cat_code
                                   AND rh.heat_number = rr.heat_number
                 WHERE rr.champ_id = %s AND rr.cat_code = 'SPRINT' AND rh.round_type = 'QUALIFYING'
                   AND rr.finish_status = 'COMPLETED' AND rr.finish_time_ms IS NOT NULL
                 ORDER BY rr.finish_time_ms ASC
                 LIMIT 4""", (champ_id,))
            new_qualifiers = set((r["carrier_id"], r["carried_id"]) for r in cur.fetchall())

            # Detect displaced pairs
            displaced = old_qualifiers - new_qualifiers
            for dis_carrier, dis_carried in displaced:
                queue_notification(
                    recipient=f"{dis_carrier}-{dis_carried}",
                    message_text=(
                        f"Pair {dis_carrier}-{dis_carried} has been displaced from Sprint Final "
                        f"qualification following a timing correction in Heat {heat_number}."
                    ),
                    event_type="DISPLACED_FROM_FINAL",
                    details={"champ_id": champ_id, "heat_number": heat_number}
                )

        # Re-evaluate pending protests
        cur.execute("""
            UPDATE PROTEST SET status = 'UNDER_REVIEW'
             WHERE champ_id = %s AND heat_cat_code = %s AND heat_number = %s AND status = 'PENDING'
               AND ((filer_carrier_id = %s AND filer_carried_id = %s)
                 OR (against_carrier_id = %s AND against_carried_id = %s))""",
                    (champ_id, cat_code, heat_number, carrier_id, carried_id, carrier_id, carried_id))

        cur.execute("""
            SELECT rank_in_heat FROM RACE_RESULT
             WHERE champ_id = %s AND cat_code = %s AND heat_number = %s
               AND carrier_id = %s AND carried_id = %s""",
                    (champ_id, cat_code, heat_number, carrier_id, carried_id))
        return cur.fetchone()["rank_in_heat"]


def change_carrier(champ_id, cat_code, carrier_id, carried_id, new_carrier_id, new_bib):
    """U-2: the registered carrier becomes the carried competitor of a new pair.

    - Invalidates old pair (is_active = FALSE).
    - Sets old registration status to REPLACED.
    - Creates new PAIR with replacement carrier.
    - Flags existing RACE_RESULT of invalidated pairs with composition_changed = TRUE,
      keeping them visible but excluding them from medal aggregation.
    - Rechecks C3: carried competitor weight must be at least 49 kg; automatically
      creates backpack weight record if violated.
    - Checks C2, C3, C9, and C10 (team composition: 3 carriers + 1 carried).
    """
    if new_carrier_id == carrier_id:
        raise FormError("The carrier and the carried competitor must be two different people.")

    with transaction() as cur:
        cur.execute("""
            SELECT fee_paid, status, carrier_weigh_in_kg FROM REGISTRATION
             WHERE champ_id = %s AND cat_code = %s AND carrier_id = %s AND carried_id = %s FOR UPDATE""",
                    (champ_id, cat_code, carrier_id, carried_id))
        old = cur.fetchone()
        if old is None:
            raise FormError("That registration does not exist.")
        if old["status"] != "CONFIRMED":
            raise FormError("Only a confirmed registration can be changed.")

        # Check C1/C2 age constraints on new carrier and former carrier
        cur.execute("SELECT start_date FROM CHAMPIONSHIP WHERE champ_id = %s", (champ_id,))
        ch = cur.fetchone()
        if ch and ch["start_date"]:
            start = ch["start_date"]
            cur.execute("SELECT date_of_birth FROM PERSON WHERE person_id = %s", (new_carrier_id,))
            p_new = cur.fetchone()
            if p_new and p_new["date_of_birth"]:
                age_new = start.year - p_new["date_of_birth"].year - (
                    (start.month, start.day) < (p_new["date_of_birth"].month, p_new["date_of_birth"].day)
                )
                if age_new < 18:
                    raise FormError("New carrier must be at least 18 years old on the championship start date.")

        # Invalidate old pair
        cur.execute("UPDATE PAIR SET is_active = FALSE WHERE carrier_id = %s AND carried_id = %s",
                    (carrier_id, carried_id))

        # Create new pair
        cur.execute("""
            INSERT INTO PAIR (carrier_id, carried_id, formed_year, is_active) VALUES (%s, %s, YEAR(CURDATE()), TRUE)
            ON DUPLICATE KEY UPDATE is_active = TRUE""", (new_carrier_id, carrier_id))

        cur.execute("""
            INSERT INTO REPRESENTS (carrier_id, carried_id, country_code)
            SELECT %s, %s, country_code FROM REPRESENTS WHERE carrier_id = %s AND carried_id = %s
            ON DUPLICATE KEY UPDATE country_code = VALUES(country_code)""",
                    (new_carrier_id, carrier_id, carrier_id, carried_id))

        # Mark old registration as REPLACED
        cur.execute("""
            UPDATE REGISTRATION SET status = 'REPLACED'
             WHERE champ_id = %s AND cat_code = %s AND carrier_id = %s AND carried_id = %s""",
                    (champ_id, cat_code, carrier_id, carried_id))

        # Re-check C10 if this championship has team rosters involving the old carrier
        cur.execute("""
            SELECT team_id FROM TEAM_ROSTER
             WHERE champ_id = %s AND competitor_id = %s AND team_role = 'CARRIER'""",
                    (champ_id, carrier_id))
        team_row = cur.fetchone()
        if team_row:
            team_id = team_row["team_id"]
            cur.execute("""
                UPDATE TEAM_ROSTER SET competitor_id = %s
                 WHERE champ_id = %s AND team_id = %s AND competitor_id = %s AND team_role = 'CARRIER'""",
                        (new_carrier_id, champ_id, team_id, carrier_id))

        # Auto-assign bib if not provided
        if not new_bib:
            cur.execute("""
                SELECT COALESCE(MAX(bib_number), 0) + 1 AS next_bib
                  FROM REGISTRATION WHERE champ_id = %s AND cat_code = %s FOR UPDATE""",
                        (champ_id, cat_code))
            new_bib = cur.fetchone()["next_bib"]

        # Insert new registration.
        # The former carrier's weigh_in becomes the carried_weigh_in_kg.
        # Trigger trg_registration_rules calculates backpack_weight_kg = GREATEST(49 - weight, 0).
        cur.execute("""
            INSERT INTO REGISTRATION (champ_id, cat_code, carrier_id, carried_id, bib_number,
                                      carried_weigh_in_kg, fee_paid, status, registered_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'CONFIRMED', NOW())""",
                    (champ_id, cat_code, new_carrier_id, carrier_id, new_bib,
                     old["carrier_weigh_in_kg"], old["fee_paid"]))

        # Flag existing results as composition_changed
        cur.execute("""
            UPDATE RACE_RESULT SET composition_changed = TRUE
             WHERE champ_id = %s AND carrier_id = %s AND carried_id = %s""",
                    (champ_id, carrier_id, carried_id))
        return cur.rowcount


def decide_protest(champ_id, protest_seq, official_id, outcome, decision_text):
    """U-3: record the jury's decision. An upheld protest disqualifies the pair.

    - Updates PROTEST.status to outcome ('UPHELD' or 'REJECTED').
    - Inserts PROTEST_DECISION record (decision text, official, timestamp).
    - Checks C13 (decided by JURY official).
    - Checks C5 (logs warning if 60-minute SLA exceeded).
    - Checks C12 (referential integrity).
    - When UPHELD:
      - Sets RACE_RESULT.finish_status = 'DQ'.
      - Recalculates rank_in_heat and diff_to_leader.
      - rank_in_category derived dynamically from view.
      - Queues notifications to newly promoted pairs.
      - Keeps the 150 EUR protest fee non-refundable.
    """
    with transaction() as cur:
        # Check C12 & C13
        cur.execute("""
            SELECT status, heat_cat_code, heat_number, against_carrier_id, against_carried_id, filed_at
              FROM PROTEST WHERE champ_id = %s AND protest_seq = %s FOR UPDATE""", (champ_id, protest_seq))
        protest = cur.fetchone()
        if protest is None:
            raise FormError("That protest does not exist.")
        if protest["status"] not in ("PENDING", "UNDER_REVIEW"):
            raise FormError("That protest has already been decided.")

        cur.execute("SELECT official_role FROM OFFICIAL WHERE person_id = %s", (official_id,))
        off = cur.fetchone()
        if not off or off["official_role"] != 'JURY':
            raise FormError("Only an official with the JURY role may decide a protest.")

        # C5: check 60-minute SLA
        if protest.get("filed_at"):
            duration = datetime.now() - protest["filed_at"]
            if duration.total_seconds() > 3600:
                logger.warning("Protest %s-%s decision exceeded 60-minute SLA (%s)",
                               champ_id, protest_seq, duration)

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
            # Record previous ranks before disqualification to detect promoted pairs
            cur.execute("""
                SELECT carrier_id, carried_id, rank_in_heat
                  FROM RACE_RESULT
                 WHERE champ_id = %s AND cat_code = %s AND heat_number = %s
                   AND finish_status = 'COMPLETED'""",
                        (champ_id, protest["heat_cat_code"], protest["heat_number"]))
            prev_ranks = {(r["carrier_id"], r["carried_id"]): r["rank_in_heat"] for r in cur.fetchall()}

            # Set finish_status = 'DQ'
            cur.execute("""
                UPDATE RACE_RESULT SET finish_status = 'DQ'
                 WHERE champ_id = %s AND cat_code = %s AND heat_number = %s
                   AND carrier_id = %s AND carried_id = %s""",
                        (champ_id, protest["heat_cat_code"], protest["heat_number"],
                         protest["against_carrier_id"], protest["against_carried_id"]))

            _recompute_heat(cur, champ_id, protest["heat_cat_code"], protest["heat_number"])

            # Find newly promoted pairs and queue notifications
            cur.execute("""
                SELECT carrier_id, carried_id, rank_in_heat
                  FROM RACE_RESULT
                 WHERE champ_id = %s AND cat_code = %s AND heat_number = %s
                   AND finish_status = 'COMPLETED'""",
                        (champ_id, protest["heat_cat_code"], protest["heat_number"]))
            new_ranks = {(r["carrier_id"], r["carried_id"]): r["rank_in_heat"] for r in cur.fetchall()}

            for pair, new_rank in new_ranks.items():
                old_rank = prev_ranks.get(pair)
                if old_rank is not None and new_rank < old_rank:
                    queue_notification(
                        recipient=f"{pair[0]}-{pair[1]}",
                        message_text=(
                            f"Pair {pair[0]}-{pair[1]} has been promoted from rank {old_rank} to rank {new_rank} "
                            f"in Heat {protest['heat_number']} following upheld protest decision."
                        ),
                        event_type="PROMOTED_IN_HEAT",
                        details={
                            "champ_id": champ_id,
                            "cat_code": protest["heat_cat_code"],
                            "heat_number": protest["heat_number"],
                            "old_rank": old_rank,
                            "new_rank": new_rank
                        }
                    )


def delete_championship(champ_id, deleted_by, reason):
    """D-1: delete a cancelled championship only when it has no dependent records.

    - Rejects deletion if RACE_HEAT, PROTEST, REGISTRATION, TEAM_ROSTER,
      TEAM_RESULT, SPONSORS, or ACCREDITS exist.
    - Allows deletion if only the placeholder CHAMPIONSHIP record exists.
    - Sets nullable foreign key references to NULL if any exist.
    - Logs deletion in CHAMPIONSHIP_DELETION_LOG (champ_id, year, deleted_by, deleted_at, reason).
    """
    with transaction() as cur:
        cur.execute("SELECT year FROM CHAMPIONSHIP WHERE champ_id = %s FOR UPDATE", (champ_id,))
        row = cur.fetchone()
        if row is None:
            raise FormError("That championship does not exist.")

        # Reject if dependent records exist
        cur.execute("SELECT COUNT(*) AS cnt FROM RACE_HEAT WHERE champ_id = %s", (champ_id,))
        if cur.fetchone()["cnt"] > 0:
            raise FormError("This championship cannot be deleted: race heats still refer to it. Archive it instead.")

        cur.execute("SELECT COUNT(*) AS cnt FROM PROTEST WHERE champ_id = %s", (champ_id,))
        if cur.fetchone()["cnt"] > 0:
            raise FormError("This championship cannot be deleted: protests still refer to it. Archive it instead.")

        cur.execute("SELECT COUNT(*) AS cnt FROM REGISTRATION WHERE champ_id = %s", (champ_id,))
        if cur.fetchone()["cnt"] > 0:
            raise FormError("This championship cannot be deleted: registrations still refer to it. Archive it instead.")

        cur.execute("SELECT COUNT(*) AS cnt FROM SPONSORS WHERE champ_id = %s", (champ_id,))
        if cur.fetchone()["cnt"] > 0:
            raise FormError("This championship cannot be deleted: sponsorships still refer to it. Archive them first.")

        cur.execute("SELECT COUNT(*) AS cnt FROM ACCREDITS WHERE champ_id = %s", (champ_id,))
        if cur.fetchone()["cnt"] > 0:
            raise FormError("This championship cannot be deleted: press accreditations still refer to it. Archive them first.")

        cur.execute("SELECT COUNT(*) AS cnt FROM TEAM_ROSTER WHERE champ_id = %s", (champ_id,))
        if cur.fetchone()["cnt"] > 0:
            raise FormError("This championship cannot be deleted: team rosters still refer to it. Archive it instead.")

        cur.execute("DELETE FROM CHAMPIONSHIP WHERE champ_id = %s", (champ_id,))
        cur.execute("""
            INSERT INTO CHAMPIONSHIP_DELETION_LOG (champ_id, year, deleted_by, deleted_at, reason)
            VALUES (%s, %s, %s, NOW(), %s)""", (champ_id, row["year"], deleted_by, reason))
        return row["year"]
