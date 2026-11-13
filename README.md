# Wife Carrying World Championships: Database and Web Application

Project Phase 4, Team 41. Mini World: the Wife Carrying World Championships, modelled on <https://eukonkanto.fi/en/front-page/>.

## Technology

| Part | Choice |
|---|---|
| Paradigm and DBMS | Relational, MySQL 8.4.9 |
| Query language | SQL, written as raw parameterised strings |
| Python driver | PyMySQL 1.2.4 (no ORM or query builder) |
| Backend | Python 3.14, Flask 3.1.3 |
| Frontend | Server-rendered Jinja2 templates, plain CSS |

## Setup and run

Run these from the folder that contains this README, with MySQL running.

```bash
# 1. Load the schema, then the data. Both ask for your MySQL password.
mysql -u root -p < src/schema.sql
mysql -u root -p < src/populate.sql

# 2. Install dependencies
cd src
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Start the application
export DB_USER=root
read -s -p "MySQL password: " DB_PASS; export DB_PASS; echo
python app.py
```

Open <http://localhost:5000>. Optional settings are `DB_HOST`, `DB_PORT` and `DB_NAME`, which default to `localhost`, `3306` and `wife_carrying_db`. Re-running the two scripts rebuilds the database exactly.

## Design Changes

Phase 2 was done by **Team 37** and Phase 3 by **Team 28**. The baseline is Team 28's schema of 26 relations. One of them, `COMPETES_FOR`, is replaced by `TEAM_ROSTER` (DC-12). Four more tables and one view are added, giving 30 tables. Each change below is marked with its `DC-n` number in `src/schema.sql`.

| # | Change | Reason |
|---|---|---|
| DC-1 | Added `REGISTRATION`: one pair's entry in one championship category, with bib, carrier and carried weigh-ins, backpack weight, fee, status, cancellation time and refund | Phase 1 needs event-scoped registrations for I-1, U-2, C3, C4, C6, C7 and C15, and they were lost in Phase 2. Keeping them per championship preserves each year's bib and weigh-in. |
| DC-2 | Removed `bib_number`, `role` and `weight_kg` from `COMPETITOR` | All three belong to one event, not to the person. Bib and weigh-ins moved to `REGISTRATION`, and role comes from `PAIR` or `TEAM_ROSTER`. The 2026 results show the same person as carrier in one pair and carried in another. |
| DC-3 | Added `RACE_HEAT.round_type` (QUALIFYING or FINAL) | The Sprint has qualifying heats and a final. Ranking them together counts a pair twice, and U-1 must tell them apart. |
| DC-4 | Added `TEAM_PARTICIPATES_IN` and `TEAM_RESULT`, keyed by heat like `PARTICIPATES_IN` and `RACE_RESULT` | A team race has four people, so the pair tables cannot store it. |
| DC-5 | Added `RACE_HEAT.heat_completed_at` | C5 needs a clock time, and `finish_time_ms` is an elapsed duration. |
| DC-6 | Added `RACE_RESULT.composition_changed` | U-2 must keep the results visible while removing them from the medal table. |
| DC-7 | `RACE_RESULT.finish_time_ms` and `drop_count` allow NULL | Non-starters have no time, past winners have no published time, and the site does not publish drops. |
| DC-8 | Added `CHAMPIONSHIP_DELETION_LOG` | D-1 requires an audit record of each deletion. |
| DC-9 | `PERSON.last_name`, `email`, `date_of_birth`, `nationality_code` and the `REGISTRATION` weigh-ins allow NULL | The site does not publish these and some names are single words. The registration form requires them for new entries. |
| DC-10 | `REPRESENTS` allows any number of countries per pair | Bib 21 in the 2026 Main Series represents three countries. A mixed pair's medal counts once for each country it represents. |
| DC-11 | Added foreign keys `RACE_RESULT` to `PARTICIPATES_IN`, and `JUDGES` and `RACE_HEAT` to `HAS_CATEGORY` | They enforce three rules Team 37 list as notational deviations, without triggers. |
| DC-12 | Replaced `COMPETES_FOR` with `TEAM_ROSTER` (championship, team, competitor, role) | Team line-ups change between years. Andrew Lee and Devon Lee raced for Team Beer for my Horses in 2026 and are registered for Team USA in 2027. The role is needed for C10. |
| DC-14 | Added `RACE_CATEGORY.entry_fee_eur`, with `CHECK (entry_fee_eur IN (55, 160))` | C6 has two prices, and which one applies depends on the category: €55 for a pair series, €160 for the team series. Holding the price on the category means the registration pages read it instead of a fee being typed into a form, and a new category cannot be added without a price. `trg_registration_rules` now rejects a `REGISTRATION.fee_paid` that does not match its category. |
| DC-15 | Added team registration (`/register/team`), which writes `TEAM`, four `TEAM_ROSTER` rows and one `REGISTRATION` | I-1 covers registration, and the €160 team fee in C6 only means something if a team can be registered. The entry goes in `REGISTRATION` under the pair of the first carrier and the carried competitor, which is what holds the bib (C4), the weigh-ins and the fee; the other two carriers are on the roster, where C10 counts them. |
| DC-13 | Added view `CATEGORY_RANKING`, which derives `rank_in_category` with `RANK() OVER (PARTITION BY champ_id, cat_code ...)` | Phase 1 has `rank_in_category`. Storing it would go out of date after U-1 and U-3, so it is computed on read. A Sprint pair ranks by the final if it reached it, otherwise by its qualifying time. |

## Constraint enforcement

| Rule | Where it is enforced |
|---|---|
| C1, C2 minimum ages | Trigger `trg_registration_rules` |
| C3 backpack weight | Trigger `trg_registration_rules` sets it from the carried weigh-in. `CHECK` keeps it between 0 and 49 kg |
| C4 unique bib per championship and category | `UNIQUE` on `REGISTRATION` |
| C5 15-minute protest window; C13 both pairs in the heat | Trigger `trg_protest_rules`, comparing the protest's `filed_at` with the heat's `heat_completed_at` |
| C6 fees (€55 or €160 registration, €150 protest) | `CHECK` on `REGISTRATION` and `PROTEST`. The applicable registration fee is `RACE_CATEGORY.entry_fee_eur` (DC-14); `trg_registration_rules` rejects a fee that does not match the category, and the register pages read the price from there rather than accepting one from the form |
| C7, C15 cancellation refund | Trigger `trg_registration_cancel` sets `cancelled_at` and the refund. `CHECK`s keep the refund at 0 or more and allow `cancelled_at` only on a cancelled entry |
| Weigh-in bounds | `CHECK` on `REGISTRATION` (20–300 kg), also checked by the form |
| C9 two different people in a pair | `CHECK` on `PAIR` |
| C10 team of three carriers and one carried | Triggers `trg_team_roster_insert` and `trg_team_roster_update` stop a fourth carrier or a second carried person. Trigger `trg_team_participation_rules` lets a team race only with a complete roster, and only in a team category |
| C11 judge certification | Trigger `trg_judges_certification` |
| C12 referential integrity | Foreign keys. Championship links are `ON DELETE RESTRICT` |
| C13 jury-only decisions | Trigger `trg_decision_jury` |

Every trigger and `CHECK` failure is shown in the web page as a plain sentence (see `database_message` in `src/app.py`), not as a raw error.

**Not enforced, with reasons.** C8 (footwear inspection) has no inspection records in the schema. The site publishes no rosters for team winners before 2026, so C10 lets a team with no roster rows at all race, as with the other unpublished values in DC-9. The 60-minute decision target in U-3 is described in Phase 1 as a soft target. Notifications and emails in Phase 1 are outside the database.

**Changes from Phase 1 behaviour.** The U-1, U-2 and U-3 cascades run in one application transaction rather than in triggers. U-2 flags results only in the affected championship, as Team 37 pointed out that a later role change must not invalidate earlier medals. A pending protest is represented by `PROTEST.status`, because a `PROTEST_DECISION` row requires a deciding official.

## Data sources

Real data, taken from eukonkanto.fi: full 2026 results for every series including Sprint heats, the 2026 team rosters with each member's role, World Championship and Sprint winners, team winners, world-record times, 2027 registered competitors, rules, venue, organiser and partners. Spelling variants of one person's name were merged, and entries the site withholds (such as "Name not published") were not imported.

**Demo rows, which are not on the site.** They are labelled `DEMO` in `src/populate.sql`. The site names none of these, but two operations and one report cannot run without them, so the team decided to use clearly labelled demo rows.

- Six officials and their phone numbers, judging assignments, two protests, their decisions and two press outlets. U-3 (decide a protest) needs jury officials and open protests, and the officials report (3.2.3) needs judging assignments.
- `heat_completed_at` clock times on 2026 heats, needed to test the 15-minute protest rule (C5, I-2).

**Limits caused by what the site publishes.** Silver and bronze exist for 2026 only, so earlier years of the medal table count gold only. Finish times exist for 2026 and for record-setting runs only, so the trend report shows all 29 championships but calculates a meaningful average for 2026 only. The Senior Series record shows 1:13.4, as in the 2026 results table, while the site's records block gives 1.13.49. No personal birth dates, weigh-ins or emails were invented for real competitors, which is why the Teams page shows "Not published" rather than 0 for the member count of a team winner from before 2026. Every team does now carry a `home_country_code`: for the 2026 teams it is the country of the roster, and for the earlier winners the country the team is named for (a Finnish police district, a Finnish firm, an Estonian club). `src/tools/build_populate.py` is the script that generated `populate.sql` from saved copies of the site.

## Features

Numbers match the order of the video. Phase 1 requirement numbers are in brackets.

**Queries**

1. **Front page winners.** `/`. Open the front page. Shows the 2026 winner of each pair series and the partners.
2. **Race results** (3.1.1). `/results`. Open Results, then choose a series tab and year. Shows every result: rank, bib, carrier, carried, country, time, gap, drops and status. Sprint is split into qualifying heats and the final, with each pair's overall category rank.
3. **Race statistics** (3.1.3). `/results`, the four boxes above the table. Changes with the series and year. Shows fastest, average and slowest time, and pairs with no drop.
4. **Team results.** `/results?series=TEAM`. Open the Team Competition tab. Shows teams, that year's roster (three carriers and the carried competitor), time, gap and penalties.
5. **Carriers by series** (3.1.2). `/competitors`, "Carriers in the 2026 championship". Choose a series and press Show. Lists carrier names and countries once each.
6. **Athlete search** (3.1.4). `/competitors?q=...`. Type part of a last name and press Search. Shows matching athletes, nationality, races and best rank.
7. **Team search** (3.1.5). `/teams?q=...`. Type part of a team name and press Search. Shows matching teams, country, members, results and wins.
8. **2027 registered competitors.** `/competitors#registered`. Lists confirmed registrations by series.
9. **World records.** `/results/champions-and-records`. Shows the fastest stored time in each series.
10. **Medal table** (3.2.1). Same page. Shows Main Race medals by country, ordered by gold, silver and bronze.
11. **Finish-time trend** (3.2.4). Same page. Shows the average and standard deviation per championship, and labels the fastest and tightest.
12. **Sprint and Main Race report** (3.2.2). `/reports/sprint-vs-main`, in the Results menu. Shows pairs in both races, their ranks and the differential.
13. **Officials report** (3.2.3). `/reports/officials`, in the Results menu. Shows officials with at least 3 championships, what they judged and protests decided.

Programme, Track and Rules, Official Grand Prix, Contact and Media and Accreditation are information pages.

**Updates**

14. **Register a pair** (I-1, create). `/register`. Fill in the form and press Register. Creates the people, the pair and the 2027 registration with both weigh-ins, and sets a backpack weight if the carried competitor weighs under 49 kg.
15. **Register a team** (I-1, create). `/register/team`, or the "Team of four" tab on the register page. Fill in the team name, home country, bib and four people, and press Register team. Creates or reuses the team, writes the roster of three carriers and one carried competitor (C10) and the 2027 team registration at the €160 team fee (C6, DC-14, DC-15). Both register pages show the fee per category and no longer state the fee in the confirmation message.
16. **File a protest** (I-2, create). `/protests/new`. Choose a heat and press Choose heat, complete the form and press File protest. Rejected outside the 15-minute window.
17. **Correct a finish time** (U-1, update). `/officials/results`. Choose a heat, enter a new time on a row and press Save. Recalculates rank and gap for the heat and puts the pair's pending protests under review.
18. **Decide a protest** (U-3, update). `/officials/protests`. Choose a jury official and outcome, and press Record decision. Upholding disqualifies the pair and recalculates the heat.
19. **Change a carrier** (U-2, update). `/officials/registrations`. Press Change on a row, choose the new carrier and press Replace pair. Replaces the pair and removes its results in that championship from the medal table.
20. **Delete a championship** (D-1, delete). `/officials/championships`. Enter a name and reason and press Delete. Rejected if records still refer to the championship, and logged on success.

The officials' area has no login, since accounts are not part of the functional requirements.

## Use of Generative AI

Generative AI (Claude) was used to extract website data and to draft the schema, queries, application and this README, as the course permits. The team reviewed the results.
