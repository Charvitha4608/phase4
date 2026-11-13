"""All read queries, written as raw SQL with %s parameters.

Labels such as 3.1.1 and 3.2.4 refer to the Phase 1 functional requirements.
"""
from db import fetch_all, fetch_one

# Shared fragments ------------------------------------------------------------
COUNTRY_OF_PAIR = """(SELECT GROUP_CONCAT(co.name ORDER BY co.name SEPARATOR ' / ')
                        FROM REPRESENTS rp JOIN COUNTRY co ON co.country_code = rp.country_code
                       WHERE rp.carrier_id = rr.carrier_id AND rp.carried_id = rr.carried_id)"""


def like_pattern(text):
    """Escape LIKE wildcards so user input is matched literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


# Results ---------------------------------------------------------------------
def race_results(year, cat_code):
    """3.1.1 Selection: every result of a championship category."""
    sql = f"""
        SELECT rh.heat_number, rh.round_type, reg.bib_number, rk.rank_in_category,
               CONCAT_WS(' ', ca.first_name, ca.last_name) AS carrier,
               CONCAT_WS(' ', cr.first_name, cr.last_name) AS carried,
               {COUNTRY_OF_PAIR} AS country,
               rr.finish_time_ms, rr.finish_status, rr.rank_in_heat,
               rr.diff_to_leader_ms, rr.drop_count, rr.composition_changed,
               EXISTS (SELECT 1 FROM PROTEST p
                        WHERE p.champ_id = rr.champ_id
                          AND p.heat_cat_code = rr.cat_code
                          AND p.heat_number = rr.heat_number
                          AND p.against_carrier_id = rr.carrier_id
                          AND p.against_carried_id = rr.carried_id
                          AND p.status IN ('PENDING', 'UNDER_REVIEW')) AS under_protest
          FROM RACE_RESULT rr
          JOIN CHAMPIONSHIP ch ON ch.champ_id = rr.champ_id
          JOIN RACE_HEAT rh ON rh.champ_id = rr.champ_id AND rh.cat_code = rr.cat_code
                           AND rh.heat_number = rr.heat_number
          JOIN PERSON ca ON ca.person_id = rr.carrier_id
          JOIN PERSON cr ON cr.person_id = rr.carried_id
          LEFT JOIN REGISTRATION reg ON reg.champ_id = rr.champ_id AND reg.cat_code = rr.cat_code
                                    AND reg.carrier_id = rr.carrier_id AND reg.carried_id = rr.carried_id
          LEFT JOIN CATEGORY_RANKING rk ON rk.champ_id = rr.champ_id AND rk.cat_code = rr.cat_code
                                       AND rk.carrier_id = rr.carrier_id AND rk.carried_id = rr.carried_id
         WHERE ch.year = %s AND rr.cat_code = %s
         ORDER BY rh.heat_number, rr.rank_in_heat IS NULL, rr.rank_in_heat, reg.bib_number"""
    return fetch_all(sql, (year, cat_code))


def race_statistics(year, cat_code):
    """3.1.3 Aggregate: slowest, fastest and average time, and pairs with no drop."""
    sql = """
        SELECT MAX(rr.finish_time_ms) AS slowest_ms,
               MIN(rr.finish_time_ms) AS fastest_ms,
               AVG(rr.finish_time_ms) AS average_ms,
               COUNT(rr.finish_time_ms) AS finishers,
               COUNT(CASE WHEN rr.drop_count = 0 THEN 1 END) AS no_drop_pairs,
               COUNT(rr.drop_count) AS drops_recorded
          FROM RACE_RESULT rr
          JOIN CHAMPIONSHIP ch ON ch.champ_id = rr.champ_id
         WHERE ch.year = %s AND rr.cat_code = %s AND rr.finish_status = 'COMPLETED'"""
    return fetch_one(sql, (year, cat_code))


def team_results(year):
    """The Team series: results and that year's roster (three carriers, one carried)."""
    sql = """
        SELECT tr.heat_number, tr.rank_in_heat, tr.bib_number, t.name AS team, co.name AS country,
               tr.finish_time_ms, tr.diff_to_leader_ms, tr.penalty_ms, tr.finish_status,
               (SELECT GROUP_CONCAT(CONCAT(CONCAT_WS(' ', p.first_name, p.last_name),
                                           IF(ro.team_role = 'CARRIED', ' (carried)', ''))
                                    ORDER BY ro.team_role = 'CARRIED', p.last_name SEPARATOR ', ')
                  FROM TEAM_ROSTER ro JOIN PERSON p ON p.person_id = ro.competitor_id
                 WHERE ro.champ_id = tr.champ_id AND ro.team_id = tr.team_id) AS members
          FROM TEAM_RESULT tr
          JOIN CHAMPIONSHIP ch ON ch.champ_id = tr.champ_id
          JOIN TEAM t ON t.team_id = tr.team_id
          LEFT JOIN COUNTRY co ON co.country_code = t.home_country_code
         WHERE ch.year = %s AND tr.cat_code = 'TEAM'
         ORDER BY tr.heat_number, tr.rank_in_heat IS NULL, tr.rank_in_heat, t.name"""
    return fetch_all(sql, (year,))


def categories():
    return fetch_all("SELECT cat_code, name, distance_m, min_weight_carried_kg, has_water_obstacle, "
                     "has_dry_obstacles, max_team_size, min_age_carrier, min_age_carried "
                     "FROM RACE_CATEGORY ORDER BY FIELD(cat_code, 'MAIN', 'WOMEN', 'M40', 'SPRINT', 'TEAM')")


def years_with_results(cat_code):
    if cat_code == "TEAM":
        sql = """SELECT DISTINCT ch.year FROM TEAM_RESULT tr
                   JOIN CHAMPIONSHIP ch ON ch.champ_id = tr.champ_id ORDER BY ch.year DESC"""
        return [r["year"] for r in fetch_all(sql)]
    sql = """SELECT DISTINCT ch.year FROM RACE_RESULT rr
               JOIN CHAMPIONSHIP ch ON ch.champ_id = rr.champ_id
              WHERE rr.cat_code = %s ORDER BY ch.year DESC"""
    return [r["year"] for r in fetch_all(sql, (cat_code,))]


def winners_of_year(year):
    """Front page: the winner of each pair series in a year."""
    sql = f"""
        SELECT cat.name AS series, CONCAT_WS(' ', ca.first_name, ca.last_name) AS carrier,
               CONCAT_WS(' ', cr.first_name, cr.last_name) AS carried,
               {COUNTRY_OF_PAIR} AS country, rr.finish_time_ms
          FROM RACE_RESULT rr
          JOIN CHAMPIONSHIP ch ON ch.champ_id = rr.champ_id
          JOIN RACE_CATEGORY cat ON cat.cat_code = rr.cat_code
          JOIN RACE_HEAT rh ON rh.champ_id = rr.champ_id AND rh.cat_code = rr.cat_code
                           AND rh.heat_number = rr.heat_number
          JOIN PERSON ca ON ca.person_id = rr.carrier_id
          JOIN PERSON cr ON cr.person_id = rr.carried_id
         WHERE ch.year = %s AND rh.round_type = 'FINAL' AND rr.rank_in_heat = 1
         ORDER BY FIELD(rr.cat_code, 'MAIN', 'WOMEN', 'M40', 'SPRINT')"""
    return fetch_all(sql, (year,))


def partners(year):
    sql = """SELECT s.name FROM SPONSORS sp
               JOIN SPONSOR s ON s.sponsor_id = sp.sponsor_id
               JOIN CHAMPIONSHIP ch ON ch.champ_id = sp.champ_id
              WHERE ch.year = %s ORDER BY s.name"""
    return [r["name"] for r in fetch_all(sql, (year,))]


# Competitors and teams -------------------------------------------------------
def carriers_in_category(year, cat_code):
    """3.1.2 Projection: names and countries of the carriers in a category."""
    sql = """
        SELECT DISTINCT CONCAT_WS(' ', p.first_name, p.last_name) AS carrier, co.name AS country
          FROM PERSON p
          JOIN COMPETITOR c ON c.person_id = p.person_id
          JOIN PAIR pr ON pr.carrier_id = c.person_id
          JOIN PARTICIPATES_IN pi ON pi.carrier_id = pr.carrier_id AND pi.carried_id = pr.carried_id
          JOIN RACE_HEAT rh ON rh.champ_id = pi.champ_id AND rh.cat_code = pi.cat_code
                           AND rh.heat_number = pi.heat_number
          JOIN CHAMPIONSHIP ch ON ch.champ_id = rh.champ_id
          JOIN RACE_CATEGORY cat ON cat.cat_code = rh.cat_code
          JOIN REPRESENTS rp ON rp.carrier_id = pr.carrier_id AND rp.carried_id = pr.carried_id
          JOIN COUNTRY co ON co.country_code = rp.country_code
         WHERE cat.cat_code = %s AND ch.year = %s
         ORDER BY carrier, country"""
    return fetch_all(sql, (cat_code, year))


def search_athletes(term):
    """3.1.4 Search: competitors whose last name contains the term."""
    sql = """
        SELECT CONCAT_WS(' ', p.first_name, p.last_name) AS name, co.name AS nationality,
               (SELECT COUNT(*) FROM RACE_RESULT rr
                 WHERE rr.carrier_id = p.person_id OR rr.carried_id = p.person_id) AS races,
               (SELECT MIN(cr.rank_in_category) FROM CATEGORY_RANKING cr
                 WHERE cr.carrier_id = p.person_id OR cr.carried_id = p.person_id) AS best_rank
          FROM PERSON p
          JOIN COMPETITOR c ON c.person_id = p.person_id
          LEFT JOIN COUNTRY co ON co.country_code = p.nationality_code
         WHERE p.last_name LIKE %s
         ORDER BY p.last_name, p.first_name"""
    return fetch_all(sql, (like_pattern(term),))


def search_teams(term):
    """3.1.5 Search: teams whose name contains the term."""
    sql = """
        SELECT t.name, co.name AS home_country,
               (SELECT COUNT(DISTINCT ro.competitor_id) FROM TEAM_ROSTER ro
                 WHERE ro.team_id = t.team_id) AS listed_members,
               (SELECT COUNT(*) FROM TEAM_RESULT tr WHERE tr.team_id = t.team_id) AS races,
               (SELECT COUNT(*) FROM TEAM_RESULT tr WHERE tr.team_id = t.team_id AND tr.rank_in_heat = 1) AS wins
          FROM TEAM t
          LEFT JOIN COUNTRY co ON co.country_code = t.home_country_code
         WHERE t.name LIKE %s
         ORDER BY t.name"""
    return fetch_all(sql, (like_pattern(term),))


def registered_pairs(year):
    """Registered competitors page: confirmed registrations of a championship."""
    sql = """
        SELECT cat.name AS series, reg.bib_number,
               CONCAT_WS(' ', ca.first_name, ca.last_name) AS carrier,
               CONCAT_WS(' ', cr.first_name, cr.last_name) AS carried,
               (SELECT GROUP_CONCAT(co.name ORDER BY co.name SEPARATOR ' / ')
                  FROM REPRESENTS rp JOIN COUNTRY co ON co.country_code = rp.country_code
                 WHERE rp.carrier_id = reg.carrier_id AND rp.carried_id = reg.carried_id) AS country
          FROM REGISTRATION reg
          JOIN CHAMPIONSHIP ch ON ch.champ_id = reg.champ_id
          JOIN RACE_CATEGORY cat ON cat.cat_code = reg.cat_code
          JOIN PERSON ca ON ca.person_id = reg.carrier_id
          JOIN PERSON cr ON cr.person_id = reg.carried_id
         WHERE ch.year = %s AND reg.status = 'CONFIRMED'
         ORDER BY FIELD(reg.cat_code, 'MAIN', 'WOMEN', 'M40', 'SPRINT', 'TEAM'), carrier"""
    return fetch_all(sql, (year,))


# Analysis reports ------------------------------------------------------------
def medal_table():
    """3.2.1 Main Race medals by country since 1996.

    REPRESENTS has one row per country, so a same-country pair counts once and
    a mixed pair counts once for each country it represents.
    """
    sql = """
        SELECT co.name AS country,
               SUM(rr.rank_in_heat = 1) AS gold,
               SUM(rr.rank_in_heat = 2) AS silver,
               SUM(rr.rank_in_heat = 3) AS bronze,
               COUNT(*) AS total
          FROM RACE_RESULT rr
          JOIN RACE_HEAT rh ON rh.champ_id = rr.champ_id AND rh.cat_code = rr.cat_code
                           AND rh.heat_number = rr.heat_number
          JOIN CHAMPIONSHIP ch ON ch.champ_id = rr.champ_id
          JOIN REPRESENTS rp ON rp.carrier_id = rr.carrier_id AND rp.carried_id = rr.carried_id
          JOIN COUNTRY co ON co.country_code = rp.country_code
         WHERE rr.cat_code = 'MAIN' AND rh.round_type = 'FINAL' AND ch.year >= 1996
           AND rr.finish_status = 'COMPLETED' AND rr.composition_changed = FALSE
           AND rr.rank_in_heat BETWEEN 1 AND 3
         GROUP BY co.country_code, co.name
         ORDER BY gold DESC, silver DESC, bronze DESC, country"""
    return fetch_all(sql)


def sprint_vs_main():
    """3.2.2 Pairs in both Sprint and Main Race of one championship, since 2015.

    Both ranks are rank_in_category from the CATEGORY_RANKING view: a Sprint
    pair's place comes from the final if it reached the final, and otherwise
    from its qualifying time behind all finalists.
    """
    sql = """
        WITH sprint AS (
            SELECT carrier_id, carried_id, champ_id, rank_in_category AS sprint_rank
              FROM CATEGORY_RANKING WHERE cat_code = 'SPRINT'
        ), main_race AS (
            SELECT carrier_id, carried_id, champ_id, rank_in_category AS main_rank
              FROM CATEGORY_RANKING WHERE cat_code = 'MAIN'
        )
        SELECT ch.year, CONCAT_WS(' ', ca.first_name, ca.last_name) AS carrier,
               CONCAT_WS(' ', cr.first_name, cr.last_name) AS carried,
               s.sprint_rank, m.main_rank,
               CAST(m.main_rank AS SIGNED) - CAST(s.sprint_rank AS SIGNED) AS differential
          FROM sprint s
          JOIN main_race m ON m.carrier_id = s.carrier_id AND m.carried_id = s.carried_id
                          AND m.champ_id = s.champ_id
          JOIN CHAMPIONSHIP ch ON ch.champ_id = s.champ_id
          JOIN PERSON ca ON ca.person_id = s.carrier_id
          JOIN PERSON cr ON cr.person_id = s.carried_id
         WHERE ch.year >= 2015
         ORDER BY ch.year DESC, m.main_rank"""
    return fetch_all(sql)


def busiest_officials():
    """3.2.3 Officials who judged at least 3 championships."""
    sql = """
        SELECT CONCAT_WS(' ', p.first_name, p.last_name) AS official, o.official_role,
               COUNT(DISTINCT j.champ_id) AS championships,
               COUNT(*) AS assignments,
               GROUP_CONCAT(CONCAT(ch.year, ' ', cat.name)
                            ORDER BY ch.year DESC, cat.name SEPARATOR ', ') AS judged,
               (SELECT COUNT(*) FROM PROTEST_DECISION d WHERE d.decided_by = o.person_id) AS protests_decided
          FROM OFFICIAL o
          JOIN PERSON p ON p.person_id = o.person_id
          JOIN JUDGES j ON j.official_id = o.person_id
          JOIN CHAMPIONSHIP ch ON ch.champ_id = j.champ_id
          JOIN RACE_CATEGORY cat ON cat.cat_code = j.cat_code
         GROUP BY o.person_id, p.first_name, p.last_name, o.official_role
        HAVING championships >= 3
         ORDER BY assignments DESC, official"""
    return fetch_all(sql)


def finish_time_trend():
    """3.2.4 Main Race average and spread per championship since 1996."""
    sql = """
        WITH per_year AS (
            SELECT ch.year, COUNT(rr.finish_time_ms) AS timed,
                   AVG(rr.finish_time_ms) AS average_ms,
                   STDDEV(rr.finish_time_ms) AS spread_ms
              FROM CHAMPIONSHIP ch
              JOIN RACE_RESULT rr ON rr.champ_id = ch.champ_id
              JOIN RACE_HEAT rh ON rh.champ_id = rr.champ_id AND rh.cat_code = rr.cat_code
                               AND rh.heat_number = rr.heat_number
             WHERE rr.cat_code = 'MAIN' AND rh.round_type = 'FINAL'
               AND rr.finish_status = 'COMPLETED' AND ch.year >= 1996
             GROUP BY ch.year
        )
        SELECT year, timed, average_ms,
               CASE WHEN timed >= 2 THEN spread_ms END AS spread_ms,
               timed >= 2 AND average_ms = MIN(CASE WHEN timed >= 2 THEN average_ms END) OVER () AS is_fastest,
               timed >= 2 AND spread_ms = MIN(CASE WHEN timed >= 2 THEN spread_ms END) OVER () AS is_tightest
          FROM per_year
         ORDER BY year DESC"""
    return fetch_all(sql)


def world_records():
    """Records page: the fastest stored time in each series."""
    sql = """
        WITH all_times AS (
            SELECT cat.name AS series, rr.finish_time_ms, ch.year,
                   CONCAT(CONCAT_WS(' ', ca.first_name, ca.last_name), ' / ',
                          CONCAT_WS(' ', cr.first_name, cr.last_name)) AS holders
              FROM RACE_RESULT rr
              JOIN CHAMPIONSHIP ch ON ch.champ_id = rr.champ_id
              JOIN RACE_CATEGORY cat ON cat.cat_code = rr.cat_code
              JOIN PERSON ca ON ca.person_id = rr.carrier_id
              JOIN PERSON cr ON cr.person_id = rr.carried_id
             WHERE rr.finish_status = 'COMPLETED' AND rr.finish_time_ms IS NOT NULL
            UNION ALL
            SELECT 'Team Competition', tr.finish_time_ms, ch.year, t.name
              FROM TEAM_RESULT tr
              JOIN CHAMPIONSHIP ch ON ch.champ_id = tr.champ_id
              JOIN TEAM t ON t.team_id = tr.team_id
             WHERE tr.finish_status = 'COMPLETED' AND tr.finish_time_ms IS NOT NULL
        ), ordered AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY series ORDER BY finish_time_ms, year) AS position_in_series
              FROM all_times
        )
        SELECT series, holders, finish_time_ms, year FROM ordered
         WHERE position_in_series = 1 ORDER BY series"""
    return fetch_all(sql)


def gold_medalists(cat_code):
    """Champions page: winners of a series, newest first."""
    sql = f"""
        SELECT ch.year, CONCAT_WS(' ', ca.first_name, ca.last_name) AS carrier,
               CONCAT_WS(' ', cr.first_name, cr.last_name) AS carried,
               {COUNTRY_OF_PAIR} AS country
          FROM RACE_RESULT rr
          JOIN RACE_HEAT rh ON rh.champ_id = rr.champ_id AND rh.cat_code = rr.cat_code
                           AND rh.heat_number = rr.heat_number
          JOIN CHAMPIONSHIP ch ON ch.champ_id = rr.champ_id
          JOIN PERSON ca ON ca.person_id = rr.carrier_id
          JOIN PERSON cr ON cr.person_id = rr.carried_id
         WHERE rr.cat_code = %s AND rh.round_type = 'FINAL' AND rr.rank_in_heat = 1
           AND rr.finish_status = 'COMPLETED'
         ORDER BY ch.year DESC, carrier"""
    return fetch_all(sql, (cat_code,))


# Lookups for the forms -------------------------------------------------------
def championship_by_year(year):
    return fetch_one("SELECT champ_id, year, start_date, end_date FROM CHAMPIONSHIP WHERE year = %s", (year,))


def countries():
    return fetch_all("SELECT country_code, name FROM COUNTRY ORDER BY name")


def categories_of_championship(year):
    sql = """SELECT cat.cat_code, cat.name FROM HAS_CATEGORY hc
               JOIN RACE_CATEGORY cat ON cat.cat_code = hc.cat_code
               JOIN CHAMPIONSHIP ch ON ch.champ_id = hc.champ_id
              WHERE ch.year = %s AND cat.max_team_size = 2
              ORDER BY FIELD(cat.cat_code, 'MAIN', 'WOMEN', 'M40', 'SPRINT')"""
    return fetch_all(sql, (year,))


def protestable_heats():
    sql = """SELECT rh.champ_id, rh.cat_code, rh.heat_number, rh.round_type, rh.heat_completed_at, ch.year,
                    cat.name AS category
               FROM RACE_HEAT rh
               JOIN CHAMPIONSHIP ch ON ch.champ_id = rh.champ_id
               JOIN RACE_CATEGORY cat ON cat.cat_code = rh.cat_code
              WHERE rh.heat_completed_at IS NOT NULL
              ORDER BY ch.year DESC, FIELD(rh.cat_code, 'MAIN', 'WOMEN', 'M40', 'SPRINT'), rh.heat_number"""
    return fetch_all(sql)


def protestable_heat(champ_id, cat_code, heat_number):
    sql = """SELECT rh.champ_id, rh.cat_code, rh.heat_number, rh.round_type, rh.heat_completed_at, ch.year,
                    cat.name AS category
               FROM RACE_HEAT rh
               JOIN CHAMPIONSHIP ch ON ch.champ_id = rh.champ_id
               JOIN RACE_CATEGORY cat ON cat.cat_code = rh.cat_code
              WHERE rh.champ_id = %s AND rh.cat_code = %s AND rh.heat_number = %s
                AND rh.heat_completed_at IS NOT NULL"""
    return fetch_one(sql, (champ_id, cat_code, heat_number))


def heat_entries(champ_id, cat_code, heat_number):
    """Result rows of one heat, with the identifiers the forms post back."""
    sql = f"""
        SELECT rr.carrier_id, rr.carried_id, reg.bib_number, rr.rank_in_heat, rr.finish_time_ms,
               rr.diff_to_leader_ms, rr.drop_count, rr.finish_status,
               CONCAT_WS(' ', ca.first_name, ca.last_name) AS carrier,
               CONCAT_WS(' ', cr.first_name, cr.last_name) AS carried,
               {COUNTRY_OF_PAIR} AS country
          FROM RACE_RESULT rr
          JOIN PERSON ca ON ca.person_id = rr.carrier_id
          JOIN PERSON cr ON cr.person_id = rr.carried_id
          LEFT JOIN REGISTRATION reg ON reg.champ_id = rr.champ_id AND reg.cat_code = rr.cat_code
                                    AND reg.carrier_id = rr.carrier_id AND reg.carried_id = rr.carried_id
         WHERE rr.champ_id = %s AND rr.cat_code = %s AND rr.heat_number = %s
         ORDER BY rr.rank_in_heat IS NULL, rr.rank_in_heat, reg.bib_number, carrier"""
    return fetch_all(sql, (champ_id, cat_code, heat_number))


def protests_list(open_only=False):
    """All protests, or only those still waiting for a decision."""
    sql = """
        SELECT p.champ_id, p.protest_seq, ch.year, p.filed_at, p.fee_paid, p.status, p.description,
               p.heat_cat_code, p.heat_number, cat.name AS category,
               CONCAT(CONCAT_WS(' ', fa.first_name, fa.last_name), ' / ', CONCAT_WS(' ', fb.first_name, fb.last_name)) AS filer,
               CONCAT(CONCAT_WS(' ', aa.first_name, aa.last_name), ' / ', CONCAT_WS(' ', ab.first_name, ab.last_name)) AS against_pair,
               (SELECT d.decision_text FROM PROTEST_DECISION d
                 WHERE d.champ_id = p.champ_id AND d.protest_seq = p.protest_seq
                 ORDER BY d.decision_seq DESC LIMIT 1) AS decision
          FROM PROTEST p
          JOIN CHAMPIONSHIP ch ON ch.champ_id = p.champ_id
          JOIN RACE_CATEGORY cat ON cat.cat_code = p.heat_cat_code
          JOIN PERSON fa ON fa.person_id = p.filer_carrier_id
          JOIN PERSON fb ON fb.person_id = p.filer_carried_id
          JOIN PERSON aa ON aa.person_id = p.against_carrier_id
          JOIN PERSON ab ON ab.person_id = p.against_carried_id
         WHERE %s = 0 OR p.status IN ('PENDING', 'UNDER_REVIEW')
         ORDER BY p.filed_at DESC, p.protest_seq DESC"""
    return fetch_all(sql, (1 if open_only else 0,))


def jury_officials():
    sql = """SELECT o.person_id, CONCAT_WS(' ', p.first_name, p.last_name) AS name, o.official_role
               FROM OFFICIAL o JOIN PERSON p ON p.person_id = o.person_id
              ORDER BY o.official_role = 'JURY' DESC, name"""
    return fetch_all(sql)


def registrations_for_year(year):
    sql = """
        SELECT reg.champ_id, reg.cat_code, reg.carrier_id, reg.carried_id, reg.bib_number, reg.status,
               reg.carrier_weigh_in_kg, reg.carried_weigh_in_kg, reg.backpack_weight_kg, cat.name AS series,
               CONCAT_WS(' ', ca.first_name, ca.last_name) AS carrier,
               CONCAT_WS(' ', cr.first_name, cr.last_name) AS carried
          FROM REGISTRATION reg
          JOIN CHAMPIONSHIP ch ON ch.champ_id = reg.champ_id
          JOIN RACE_CATEGORY cat ON cat.cat_code = reg.cat_code
          JOIN PERSON ca ON ca.person_id = reg.carrier_id
          JOIN PERSON cr ON cr.person_id = reg.carried_id
         WHERE ch.year = %s
         ORDER BY FIELD(reg.cat_code, 'MAIN', 'WOMEN', 'M40', 'SPRINT'), reg.status, reg.bib_number IS NULL, reg.bib_number"""
    return fetch_all(sql, (year,))


def registration(champ_id, cat_code, carrier_id, carried_id):
    sql = """
        SELECT reg.champ_id, reg.cat_code, reg.carrier_id, reg.carried_id, reg.bib_number, reg.status,
               cat.name AS series, ch.year,
               CONCAT_WS(' ', ca.first_name, ca.last_name) AS carrier,
               CONCAT_WS(' ', cr.first_name, cr.last_name) AS carried
          FROM REGISTRATION reg
          JOIN CHAMPIONSHIP ch ON ch.champ_id = reg.champ_id
          JOIN RACE_CATEGORY cat ON cat.cat_code = reg.cat_code
          JOIN PERSON ca ON ca.person_id = reg.carrier_id
          JOIN PERSON cr ON cr.person_id = reg.carried_id
         WHERE reg.champ_id = %s AND reg.cat_code = %s AND reg.carrier_id = %s AND reg.carried_id = %s"""
    return fetch_one(sql, (champ_id, cat_code, carrier_id, carried_id))


def replacement_carriers(champ_id, injured_id):
    """Competitors registered in the same championship, other than the injured one."""
    sql = """
        SELECT DISTINCT p.person_id, CONCAT_WS(' ', p.first_name, p.last_name) AS name
          FROM REGISTRATION reg
          JOIN PERSON p ON p.person_id IN (reg.carrier_id, reg.carried_id)
         WHERE reg.champ_id = %s AND reg.status = 'CONFIRMED' AND p.person_id <> %s
         ORDER BY name"""
    return fetch_all(sql, (champ_id, injured_id))


def next_free_bib(champ_id, cat_code):
    sql = "SELECT COALESCE(MAX(bib_number), 0) + 1 AS bib FROM REGISTRATION WHERE champ_id = %s AND cat_code = %s"
    return fetch_one(sql, (champ_id, cat_code))["bib"]


def championships_overview():
    """D-1 page: each championship with the records that would block deletion."""
    sql = """
        SELECT ch.champ_id, ch.year, ch.edition_number,
               (SELECT COUNT(*) FROM RACE_HEAT x WHERE x.champ_id = ch.champ_id) AS heats,
               (SELECT COUNT(*) FROM PROTEST x WHERE x.champ_id = ch.champ_id) AS protests,
               (SELECT COUNT(*) FROM SPONSORS x WHERE x.champ_id = ch.champ_id) AS sponsors,
               (SELECT COUNT(*) FROM ACCREDITS x WHERE x.champ_id = ch.champ_id) AS accreditations,
               (SELECT COUNT(*) FROM REGISTRATION x WHERE x.champ_id = ch.champ_id) AS registrations,
               (SELECT COUNT(*) FROM TEAM_RESULT x WHERE x.champ_id = ch.champ_id) AS team_results,
               (SELECT COUNT(*) FROM TEAM_ROSTER x WHERE x.champ_id = ch.champ_id) AS team_roster
          FROM CHAMPIONSHIP ch ORDER BY ch.year DESC"""
    return fetch_all(sql)


def deletion_log():
    return fetch_all("SELECT champ_id, year, deleted_by, deleted_at, reason "
                     "FROM CHAMPIONSHIP_DELETION_LOG ORDER BY deleted_at DESC, log_id DESC")
