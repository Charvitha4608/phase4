"""Generate populate.sql from saved copies of eukonkanto.fi pages.

Usage: python3 tools/build_populate.py <snapshot_dir> > populate.sql

<snapshot_dir> holds results.html, results_champions-and-records.html and
participating-competitors-and-countries.html. This script only builds the SQL
file: the application never runs it, and populate.sql is the submitted script.
"""
import re
import sys
from collections import OrderedDict
from html.parser import HTMLParser
from pathlib import Path


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.table, self.row, self.cell = [], None, None, None
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "table":
            self.table = []
            self.tables.append(self.table)
        elif tag == "tr" and self.table is not None:
            self.row = []
            self.table.append(self.row)
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr":
            self.row = None
        elif tag == "table":
            self.table = None

    def handle_data(self, data):
        if self.cell is not None and not self.skip:
            self.cell.append(data)


def tables_of(path):
    parser = TableParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser.tables


def page_lines(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", text)
    text = re.sub(r"(?i)<(/p|br\s*/?|/li|/h\d|/tr|/td)>", "\n", text)
    import html
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


# Countries used by the site, with the codes the site uses where it shows one.
COUNTRIES = {
    "FIN": ("Finland", "Europe"), "EST": ("Estonia", "Europe"),
    "LTU": ("Lithuania", "Europe"), "GBR": ("United Kingdom", "Europe"),
    "SGP": ("Singapore", "Asia"), "USA": ("United States", "North America"),
    "SWE": ("Sweden", "Europe"), "IRL": ("Ireland", "Europe"),
    "CZE": ("Czech Republic", "Europe"), "PHL": ("Philippines", "Asia"),
    "FRA": ("France", "Europe"), "SVK": ("Slovakia", "Europe"),
    "CAN": ("Canada", "North America"), "RUS": ("Russia", "Europe"),
    "UKR": ("Ukraine", "Europe"), "BRA": ("Brazil", "South America"),
    "GER": ("Germany", "Europe"), "AUT": ("Austria", "Europe"),
    "SRB": ("Serbia", "Europe"), "ITA": ("Italy", "Europe"),
    "AUS": ("Australia", "Australia"), "SUI": ("Switzerland", "Europe"),
    # No competitors yet: the country of the Phase 1 I-1 scenario.
    "IND": ("India", "Asia"),
}
COUNTRY_ALIASES = {name.lower(): code for code, (name, _) in COUNTRIES.items()}
COUNTRY_ALIASES.update({
    "usa": "USA", "singabore": "SGP", "rus": "RUS", "fin": "FIN", "ukr": "UKR",
})

# Spelling variants of one person on the site, and surname-first entries.
NAME_FIXES = {
    "Helmi-RiinaKangas": "Helmi-Riina Kangas", "Helmiriina Kangas": "Helmi-Riina Kangas",
    "Viltrop Kristi": "Kristi Viltrop", "Allar Voogla": "Alar Voogla",
    "Inga Klauso": "Inga Klauson", "Spiess Philipp": "Philipp Spiess",
    "Müller Kim Stella": "Kim Stella Müller",
}

HISTORIC_TEAM_WINNERS = {
    1996: ["Ylä-Savon kihlakunnan poliisit"], 1997: ["Ylä-Savon kihlakunnan poliisit"],
    1998: ["Ylä-Savon kihlakunnan poliisit"], 1999: ["Iisalmen Putkiasennus Oy"],
    2000: ["Ylä-Savon kihlakunnan poliisit"], 2001: ["Väike-Maarja Vald"],
    2002: ["Iisalmen Putkiasennus Oy", "Äntu Farm"], 2003: ["Äntu Farm"], 2004: ["Äntu Farm"],
    2005: ["Sõbrad"], 2006: ["Sõbrad"], 2007: ["Sõbrad"], 2008: ["Sõbrad"], 2009: ["Sõbrad"],
    2010: ["Konkurendid"], 2011: ["Sonkarun"], 2012: ["Sonkarun"], 2013: ["Sonkarun"],
    2014: ["Sonkarun"], 2015: ["Sonkarun"], 2016: ["Serti"], 2017: ["Serti"], 2018: ["Serti"],
    2019: ["Serti"], 2022: ["Serti"], 2023: ["Maailmanmestaruuden metsästäjät"],
    2024: ["Team Australia"], 2025: ["Team Big Beef"],
}
HISTORIC_TEAM_COUNTRY = {
    "Väike-Maarja Vald": "EST", "Äntu Farm": "EST", "Sõbrad": "EST",
    "Konkurendid": "EST", "Team Australia": "AUS",
}
# "World records" block of the champions page: (category, year) -> time in ms.
RECORD_TIMES = {("MAIN", 2006): 56900, ("SPRINT", 2012): 31340}
TEAM_RECORD = ("Sõbrad", 2008, 84600)
WOMEN_RECORD = ("Janita Riekkinen", "Sanna Jäntti", 2025, 99510)

PARTNERS = ["DNA", "Rebekan hoitokoti", "IPA.fi", "Levin LVI.fi", "Savon LVItalo.fi", "Olvi",
            "Ylä-Savon Jätehuolto", "Omatalo", "Sonkajärven kunta", "OP Kaskimaa"]

HELD_YEARS = [y for y in range(1996, 2027) if y not in (2020, 2021)]


def q(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def insert(table, columns, rows):
    if not rows:
        return ""
    head = f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n"
    body = ",\n".join("  (" + ", ".join(q(v) for v in row) + ")" for row in rows)
    return head + body + ";\n\n"


def parse_time(text):
    text = text.strip().lstrip("+")
    if not text or not re.search(r"\d", text):
        return None
    minutes = 0
    if ":" in text:
        m, text = text.split(":", 1)
        minutes = int(m)
    return minutes * 60000 + round(float(text) * 1000)


def parse_countries(text):
    parts = [p.strip() for p in re.split(r"[/()]", text) if p.strip()]
    return [COUNTRY_ALIASES[p.lower()] for p in parts]


class Store:
    def __init__(self):
        self.people = OrderedDict()   # name -> person dict
        self.pairs = OrderedDict()    # (carrier_id, carried_id) -> set of countries
        self.teams = OrderedDict()    # name -> team dict

    def person(self, raw):
        name = NAME_FIXES.get(raw.strip(), raw.strip())
        if name not in self.people:
            self.people[name] = {"id": len(self.people) + 1, "name": name, "nat": None}
        return self.people[name]

    def pair(self, carrier, carried, countries):
        a, b = self.person(carrier), self.person(carried)
        key = (a["id"], b["id"])
        self.pairs.setdefault(key, set()).update(countries)
        if len(countries) == 1:
            a["nat"] = a["nat"] or countries[0]
            b["nat"] = b["nat"] or countries[0]
        return key

    def team(self, name, country=None):
        if name not in self.teams:
            self.teams[name] = {"id": len(self.teams) + 1, "name": name, "country": country}
        return self.teams[name]


def main(snapshot):
    store = Store()
    results = tables_of(snapshot / "results.html")
    series_rows = [t for t in results if t and t[0] and "Kilpailun sarjat" in t[0][0]]
    sprint_table, saturday_table = series_rows

    # Each block: code row, header rows, result rows, ended by Sarjaluettelo.
    blocks = {}
    current = None
    for row in sprint_table + saturday_table:
        if len(row) == 2 and row[0] in ("SPRINTTI", "SPR_A1", "SPR_A2", "SPR_A3", "SPR_FIN",
                                        "JOUKKUE", "W", "M40", "M/W"):
            current = row[0]
            blocks[current] = []
            continue
        if row and row[0] == "Sarjaluettelo":
            current = None
            continue
        if current and len(row) >= 6 and re.match(r"^(\d+\.|DNS|DNF|DQ)$", row[0]):
            blocks[current].append(row)

    registrations = {}  # (year, cat, pair) -> bib
    heats, participations, race_results, team_results, roster = [], [], [], [], []
    y2026 = 2026

    def add_heat(year, cat, number, round_name):
        heats.append((year, cat, number, round_name))

    # 2026 Sprint: three heats and the final.
    for code, number, round_name in [("SPR_A1", 1, "QUALIFYING"), ("SPR_A2", 2, "QUALIFYING"),
                                     ("SPR_A3", 3, "QUALIFYING"), ("SPR_FIN", 4, "FINAL")]:
        add_heat(y2026, "SPRINT", number, round_name)
        for row in blocks[code]:
            rank, bib, names, country, time, diff = row[:6]
            carrier, carried = names.split("/", 1)
            pair = store.pair(carrier, carried, parse_countries(country))
            registrations[(y2026, "SPRINT", pair)] = int(bib)
            participations.append((pair, y2026, "SPRINT", number))
            race_results.append((pair, y2026, "SPRINT", number, parse_time(time), "COMPLETED",
                                 int(rank.rstrip(".")), parse_time(diff) or 0))

    # 2026 Women, Men 40+ and Main series.
    for code, cat in [("W", "WOMEN"), ("M40", "M40"), ("M/W", "MAIN")]:
        add_heat(y2026, cat, 1, "FINAL")
        for row in blocks[code]:
            rank, bib, names, full_carried, country, _, time, diff = row[:8]
            carrier, carried = names.split("/", 1)
            if full_carried:   # the site truncates long names and gives the full one here
                carried = full_carried
            pair = store.pair(carrier, carried, parse_countries(country))
            registrations[(y2026, cat, pair)] = int(bib)
            participations.append((pair, y2026, cat, 1))
            if rank in ("DNS", "DNF", "DQ"):
                race_results.append((pair, y2026, cat, 1, None, rank, None, None))
            else:
                race_results.append((pair, y2026, cat, 1, parse_time(time), "COMPLETED",
                                     int(rank.rstrip(".")), parse_time(diff) or 0))

    # 2026 Team competition, one race. Row format: carrier/carried, carrier/carrier.
    add_heat(y2026, "TEAM", 1, "FINAL")
    for row in blocks["JOUKKUE"]:
        rank, bib, first, second, name, codes, time, diff = row[:8]
        code_list = [c for c in codes.split("/") if c]
        team = store.team(name, code_list[0] if len(code_list) == 1 else None)
        first_carrier, carried = first.split("/")
        for person, role in [(first_carrier, "CARRIER"), (carried, "CARRIED")] + \
                            [(p, "CARRIER") for p in second.split("/")]:
            roster.append((y2026, team["id"], store.person(person)["id"], role))
        penalty = 15000 if bib == "105" else 0   # "Aikasakko +15 sek" row on the site
        team_results.append((y2026, team["id"], int(bib), parse_time(time), penalty, "COMPLETED",
                             int(rank.rstrip(".")), parse_time(diff) or 0))

    # History from the champions page.
    lines = page_lines(snapshot / "results_champions-and-records.html")
    world = lines.index("World Championships")
    sprint = lines.index("Sprint", world)
    team_heading = lines.index("Team", sprint)

    def winner_entries(chunk):
        for line in chunk:
            match = re.match(r"^(\d{4}): (.+)$", line)
            if not match:
                continue
            year, text = int(match[1]), match[2].rstrip(".")
            body, country = text.rsplit(",", 1)
            body = body.split(",")[0] if "," in body else body
            codes = parse_countries(country.strip())
            for one in body.split(" / "):
                left, right = one.split(" and ", 1)
                if " " not in left.strip():    # "Jouni and Tiina Jussila"
                    left = f"{left.strip()} {right.split()[-1]}"
                yield year, left.strip(), right.strip(), codes

    for cat, chunk in [("MAIN", lines[world + 1:sprint]), ("SPRINT", lines[sprint + 1:team_heading])]:
        seen = set()
        for year, carrier, carried, codes in winner_entries(chunk):
            if year == y2026:
                continue
            pair = store.pair(carrier, carried, codes)
            if year not in seen:
                add_heat(year, cat, 1, "FINAL")
                seen.add(year)
            participations.append((pair, year, cat, 1))
            race_results.append((pair, year, cat, 1, RECORD_TIMES.get((cat, year)), "COMPLETED", 1, None))

    carrier, carried, year, millis = WOMEN_RECORD
    pair = store.pair(carrier, carried, ["FIN"])
    add_heat(year, "WOMEN", 1, "FINAL")
    participations.append((pair, year, "WOMEN", 1))
    race_results.append((pair, year, "WOMEN", 1, millis, "COMPLETED", None, None))

    for year, names in HISTORIC_TEAM_WINNERS.items():
        add_heat(year, "TEAM", 1, "FINAL")
        for name in names:
            team = store.team(name, HISTORIC_TEAM_COUNTRY.get(name))
            millis = TEAM_RECORD[2] if (name, year) == TEAM_RECORD[:2] else None
            team_results.append((year, team["id"], None, millis, 0, "COMPLETED", 1, None))

    # 2027 registered competitors. Rows with withheld names are not imported.
    registered = tables_of(snapshot / "participating-competitors-and-countries.html")
    registered = [t for t in registered if t and t[0] and t[0][0] in ("Carrier", "Team")]
    for table, cat in zip(registered, ["MAIN", "SPRINT", "M40", "TEAM"]):
        for row in table[1:]:
            if cat == "TEAM":   # columns: team, carriers, carried, country
                team = store.team(row[0], parse_countries(row[3])[0])
                carriers = [c.strip() for c in row[1].split(",") if c.strip() != "To be determined"]
                for person, role in [(c, "CARRIER") for c in carriers] + [(row[2], "CARRIED")]:
                    roster.append((2027, team["id"], store.person(person)["id"], role))
                continue
            if "Name not published" in (row[0], row[2]):
                continue
            pair = store.pair(row[0], row[2], parse_countries(row[1]) + parse_countries(row[3]))
            registrations[(2027, cat, pair)] = None

    # Identifiers of championships: held editions, the two cancelled years, 2027.
    years = sorted(HELD_YEARS + [2020, 2021, 2027])
    champ_id = {year: index + 1 for index, year in enumerate(years)}
    edition, next_edition = {}, 1
    for year in years:
        if year not in (2020, 2021):
            edition[year] = next_edition
            next_edition += 1

    categories_of = {}
    for year in years:
        if year in (2020, 2021):
            categories_of[year] = []
            continue
        cats = ["MAIN", "TEAM"]
        if year >= 2006:
            cats.append("SPRINT")
        if year >= 2025:
            cats.append("WOMEN")
        if year >= 2026:
            cats.append("M40")
        categories_of[year] = cats

    # Output -----------------------------------------------------------------
    out = ["-- Wife Carrying World Championships: population script.",
           "-- Generated by tools/build_populate.py from eukonkanto.fi.",
           "-- Rows that the site does not publish are marked DEMO and listed in README.md.",
           "-- Run with: mysql -u <user> -p < populate.sql",
           "", "SET NAMES utf8mb4;", "USE wife_carrying_db;", ""]
    w = out.append

    w(insert("COUNTRY", ["country_code", "name", "continent"],
             [(c, n, cont) for c, (n, cont) in COUNTRIES.items()]))
    w(insert("VENUE", ["venue_id", "name", "street", "city", "postal_code", "country_code", "capacity", "track_length_m"],
             [(1, "Wife Carrying Arena", "Urheilutie 1", "Sonkajärvi", None, "FIN", None, 253.5)]))
    w(insert("ORGANISER", ["organiser_id", "name", "legal_form", "founded_year"],
             [(1, "Sonkajärven Eukonkanto Oy", "Oy", None)]))
    w(insert("RACE_CATEGORY",
             ["cat_code", "name", "distance_m", "min_weight_carried_kg", "has_water_obstacle",
              "has_dry_obstacles", "max_team_size", "min_age_carrier", "min_age_carried"],
             [("MAIN", "Main Series", 253.5, 49, True, True, 2, 18, 17),
              ("SPRINT", "Sprint", 120, 49, True, False, 2, 18, 17),
              ("WOMEN", "Women's Main Series", 253.5, 49, True, True, 2, 18, 17),
              ("M40", "Senior Series 40+", 253.5, 49, True, True, 2, 40, 17),
              ("TEAM", "Team Competition", 253.5, 49, True, True, 4, 18, 17)]))

    def split_name(name):
        parts = name.split()
        return (" ".join(parts[:-1]), parts[-1]) if len(parts) > 1 else (name, None)

    person_rows, competitor_rows = [], []
    for person in store.people.values():
        first, last = split_name(person["name"])
        person_rows.append((person["id"], first, last, None, None, None, "COMPETITOR", person["nat"]))
        competitor_rows.append((person["id"], None))
    next_person = len(person_rows) + 1

    # DEMO officials: the site names no officials, jury members or protests.
    demo_officials = [("Demo", "Jury Chair", 3, "JURY"), ("Demo", "Jury Member", 3, "JURY"),
                      ("Demo", "Jury Deputy", 3, "JURY"), ("Demo", "Timekeeper", 2, "TIMEKEEPER"),
                      ("Demo", "Equipment Inspector", 2, "EQUIPMENT_INSPECTOR"), ("Demo", "Starter", 1, "STARTER")]
    official_ids = {}
    official_rows = []
    for offset, (first, last, level, role) in enumerate(demo_officials):
        pid = next_person + offset
        official_ids[last] = pid
        person_rows.append((pid, first, last, None, None, None, "OFFICIAL", None))
        official_rows.append((pid, level, role))

    person_columns = ["person_id", "first_name", "last_name", "email", "gender", "date_of_birth",
                      "role_type", "nationality_code"]
    w(insert("PERSON", person_columns, person_rows))
    w(insert("COMPETITOR", ["person_id", "career_start_year"], competitor_rows))
    w("-- DEMO: officials (not published on the site).\n")
    w(insert("OFFICIAL", ["person_id", "certification_level", "official_role"], official_rows))
    w(insert("PERSON_PHONE", ["person_id", "phone_number"],
             [(official_ids["Jury Chair"], "+358 00 000 0001"), (official_ids["Jury Chair"], "+358 00 000 0002"),
              (official_ids["Jury Member"], "+358 00 000 0003")]))

    w(insert("TEAM", ["team_id", "name", "founded_year", "home_country_code", "parent_team_id"],
             [(t["id"], t["name"], None, t["country"], None) for t in store.teams.values()]))
    w(insert("PAIR", ["carrier_id", "carried_id", "formed_year", "is_active"],
             [(a, b, None, True) for a, b in store.pairs]))
    w(insert("REPRESENTS", ["carrier_id", "carried_id", "country_code"],
             [(a, b, c) for (a, b), codes in store.pairs.items() for c in sorted(codes)]))

    def dates(year):
        return {2026: ("2026-07-03", "2026-07-04"), 2027: ("2027-07-02", "2027-07-03")}.get(year, (None, None))

    w(insert("CHAMPIONSHIP",
             ["champ_id", "year", "edition_number", "start_date", "end_date", "is_grand_prix",
              "spectator_count", "venue_id", "organiser_id"],
             [(champ_id[y], y, edition.get(y), *dates(y), False, None, 1, 1) for y in years]))
    w(insert("CHAMP_HOST_LANGUAGE", ["champ_id", "host_language"],
             [(champ_id[y], lang) for y in (2026, 2027) for lang in ("Finnish", "English")]))
    w(insert("HAS_CATEGORY", ["champ_id", "cat_code"],
             [(champ_id[y], c) for y in years for c in categories_of[y]]))
    w(insert("TEAM_ROSTER", ["champ_id", "team_id", "competitor_id", "team_role"],
             [(champ_id[y], t, p, r) for y, t, p, r in roster]))

    # DEMO clock times: the site publishes only elapsed times, and C5 needs a clock time.
    finish = {("SPRINT", 1): "2026-07-03 19:08:00", ("SPRINT", 2): "2026-07-03 19:12:00",
              ("SPRINT", 3): "2026-07-03 19:16:00", ("SPRINT", 4): "2026-07-03 19:24:00",
              ("WOMEN", 1): "2026-07-04 14:30:00", ("M40", 1): "2026-07-04 14:45:00",
              ("MAIN", 1): "2026-07-04 16:30:00"}
    scheduled = {("SPRINT", n): "2026-07-03 19:00:00" for n in (1, 2, 3, 4)}
    scheduled[("MAIN", 1)] = "2026-07-04 15:00:00"
    w("-- heat_completed_at on 2026 heats is DEMO (the site publishes elapsed times only).\n")
    w(insert("RACE_HEAT",
             ["champ_id", "cat_code", "heat_number", "round_type", "scheduled_time", "heat_completed_at", "status"],
             [(champ_id[y], c, n, r,
               scheduled.get((c, n)) if y == 2026 else None,
               finish.get((c, n)) if y == 2026 else None, "COMPLETED")
              for y, c, n, r in heats]))
    w(insert("PARTICIPATES_IN", ["carrier_id", "carried_id", "champ_id", "cat_code", "heat_number"],
             [(p[0], p[1], champ_id[y], c, n) for p, y, c, n in participations]))
    w(insert("RACE_RESULT",
             ["carrier_id", "carried_id", "champ_id", "cat_code", "heat_number", "finish_time_ms",
              "finish_status", "rank_in_heat", "diff_to_leader_ms", "drop_count", "composition_changed"],
             [(p[0], p[1], champ_id[y], c, n, t, s, r, d, None, False)
              for p, y, c, n, t, s, r, d in race_results]))
    w(insert("REGISTRATION", ["champ_id", "cat_code", "carrier_id", "carried_id", "bib_number", "status"],
             [(champ_id[y], c, p[0], p[1], bib, "CONFIRMED") for (y, c, p), bib in registrations.items()]))
    w(insert("TEAM_PARTICIPATES_IN", ["champ_id", "cat_code", "heat_number", "team_id"],
             [(champ_id[y], "TEAM", 1, t) for y, t, *_ in team_results]))
    w(insert("TEAM_RESULT",
             ["champ_id", "cat_code", "heat_number", "team_id", "bib_number", "finish_time_ms", "penalty_ms",
              "finish_status", "rank_in_heat", "diff_to_leader_ms", "drop_count"],
             [(champ_id[y], "TEAM", 1, t, b, ms, pen, s, r, d, None) for y, t, b, ms, pen, s, r, d in team_results]))

    partner_rows = [(i + 1, name, None, None, None, None) for i, name in enumerate(PARTNERS)]
    w(insert("SPONSOR", ["sponsor_id", "name", "country", "contact_email", "contact_phone", "contact_address"], partner_rows))
    w(insert("SPONSOR_CATEGORY", ["sponsor_id", "sponsorship_category"],
             [(r[0], "Cooperation partner") for r in partner_rows]))
    w(insert("SPONSORS", ["champ_id", "sponsor_id", "tier", "contract_start", "contract_end"],
             [(champ_id[2026], r[0], "Cooperation partner", None, None) for r in partner_rows]))

    w("-- DEMO: the site lists no press outlets, judging assignments or protests.\n")
    w(insert("PRESS_OUTLET", ["outlet_id", "name", "country"],
             [(1, "Demo Press Outlet A", "Finland"), (2, "Demo Press Outlet B", "Estonia")]))
    w(insert("ACCREDITS", ["champ_id", "outlet_id", "drone_permission"],
             [(champ_id[2026], 1, True), (champ_id[2026], 2, False)]))

    judging = [("Jury Chair", y, c) for y in (2023, 2024, 2025, 2026) for c in ("MAIN", "SPRINT")]
    judging += [("Jury Deputy", y, "MAIN") for y in (2024, 2025, 2026)]
    judging += [("Jury Member", y, "SPRINT") for y in (2025, 2026)]   # fewer than 3: excluded from 3.2.3
    judging += [("Timekeeper", 2026, "MAIN")]
    w(insert("JUDGES", ["official_id", "champ_id", "cat_code"],
             [(official_ids[o], champ_id[y], c) for o, y, c in judging]))

    by_bib = {(c, bib): p for (y, c, p), bib in registrations.items() if y == y2026}
    main_a, main_b = by_bib[("MAIN", 58)], by_bib[("MAIN", 50)]
    sprint_a, sprint_b = by_bib[("SPRINT", 74)], by_bib[("SPRINT", 76)]
    w(insert("PROTEST",
             ["champ_id", "protest_seq", "filed_at", "fee_paid", "status", "description", "heat_cat_code",
              "heat_number", "filer_carrier_id", "filer_carried_id", "against_carrier_id", "against_carried_id"],
             [(champ_id[2026], 1, "2026-07-04 16:35:00", 150, "REJECTED", "DEMO protest: alleged lane obstruction.",
               "MAIN", 1, *main_a, *main_b),
              (champ_id[2026], 2, "2026-07-03 19:20:00", 150, "REJECTED", "DEMO protest: alleged false start.",
               "SPRINT", 2, *sprint_a, *sprint_b)]))
    w(insert("PROTEST_DECISION",
             ["champ_id", "protest_seq", "decision_seq", "decision_text", "decided_at", "decision_outcome", "decided_by"],
             [(champ_id[2026], 1, 1, "DEMO decision: no infringement found.", "2026-07-04 17:00:00", "REJECTED", official_ids["Jury Chair"]),
              (champ_id[2026], 2, 1, "DEMO decision: start was valid.", "2026-07-03 19:50:00", "REJECTED", official_ids["Jury Chair"])]))

    sys.stdout.write("".join(part if part.endswith("\n") else part + "\n" for part in out))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
