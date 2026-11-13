# Please Confirm: Open Decisions and Checks

Working notes, not part of the submission. Everything here needs a person, not more automated work. Check items off as you go; cross out and write a note if you disagree with something.

Anything I find later that doesn't block me gets added under section 0, newest first, instead of chat. If something *does* block me, I'll ask directly in chat instead of writing it here.

## 0. Schema-revision choices: confirmed

The schema revisions from the "Phase 4 schema revisions" note (points 1–4) are now in `src/schema.sql`, `src/populate.sql` and the app, and are listed in [README.md](README.md#design-changes) as DC-1 to DC-13. These are the choices I made where the note left room. The team confirmed all five on 13 Nov:

- [x] **Point 1, one table, not two.** As asked, entry data goes straight into `REGISTRATION`, not into separate `COMPETITOR_ENTRY` and `PAIR_REGISTRATION` tables. `REGISTRATION` now holds bib, `carrier_weigh_in_kg`, `carried_weigh_in_kg`, backpack weight, fee, status, `cancelled_at` and refund. The table keeps its name `REGISTRATION`; it is not renamed to `PAIR_REGISTRATION`.
- [x] **Point 1, fee per pair.** `fee_paid` is stored once per pair entry (€55, or €160 for a team), as before, not once per person.
- [x] **Point 2, teams with no roster.** The site publishes team rosters only for 2026 (complete) and 2027 (Team USA: one carrier and the carried person so far). Winners from 1996–2025 have no roster. C10 therefore blocks an incomplete roster from racing, but lets a team with no roster rows at all race. Otherwise the historical team winners could not be loaded.
- [x] **Point 2, extra team result columns.** `TEAM_RESULT` uses the note's key (`champ_id, cat_code, heat_number, team_id`) and also keeps `bib_number` and `penalty_ms`, because the 2026 results show team bibs and a +15 s penalty.
- [x] **Point 4, view rather than triggers.** `rank_in_category` is computed by the view `CATEGORY_RANKING` instead of being stored and kept up to date by triggers, so U-1 and U-3 can never leave it stale. A Sprint pair that didn't reach the final ranks behind all finalists, ordered by qualifying time.

## 1. Demo data: decided

- [x] **Use demo data.** Decided: no officials, jury members, protests or press outlets are published on eukonkanto.fi, but U-3 (decide a protest) and the officials report (3.2.3) need them. The six officials, two protests and two press outlets stay, labelled `DEMO` in `src/populate.sql` and listed in the README under Data sources. The same goes for the 2026 heat completion clock times that the 15-minute protest rule needs.

Optional: tell the TA so it isn't a surprise at grading. The decision no longer depends on the reply.

> Hi, for Phase 4 our Mini World is eukonkanto.fi. The site publishes results but doesn't name any officials, jury members or protests, or list press outlets, and our Phase 1 functional requirements need them (the officials report and the protest decision operation). We've added a small number of rows clearly labelled DEMO for these and listed them in the README. All competitor, result and event data comes from the site.

- [ ] Sent to TA (optional)

## 2. Design changes: signed off

Full reasons are in [README.md](README.md#design-changes).

- [x] **DC-1 (`REGISTRATION` table):** event data is stored per championship and category: bib, both weigh-ins, backpack, fee, status, cancellation time and refund.
- [x] **DC-2 (event columns removed from COMPETITOR):** `bib_number`, `role` and `weight_kg` are gone from `COMPETITOR`. Bib and weigh-ins are on `REGISTRATION`; role comes from `PAIR` or `TEAM_ROSTER`.
- [x] **DC-10 (more than 2 nationalities):** `REPRESENTS` allows any number of countries per pair. Bib 21 in the 2026 Main Series has three. A mixed pair's medal counts once for each country.
- [x] **DC-12, DC-4 (team rosters and team results, point 2):** `COMPETES_FOR` is replaced by `TEAM_ROSTER (champ_id, team_id, competitor_id, team_role)`. `TEAM_PARTICIPATES_IN` was added, and `TEAM_RESULT` is now keyed by heat. All 7 teams of 2026 load with 3 carriers and 1 carried each.
- [x] **DC-3, DC-5 (Sprint rounds and heat completion time, point 3):** `RACE_HEAT.round_type` is `QUALIFYING` or `FINAL`, and `RACE_HEAT.heat_completed_at` is the clock time that C5 checks protests against.
- [x] **DC-13 and constraints (point 4):** `rank_in_category` comes from the view `CATEGORY_RANKING` and is shown on the Sprint results page. New `CHECK`s cover weigh-ins (20–300 kg), backpack (0–49 kg), refund (0 or more) and `cancelled_at`. New triggers enforce C10. Each violation is shown in the page as a plain message.
- [x] **Demo officials/protests:** see section 1.

## 3. Things only you can verify

I tested against a private MySQL 8.4.9 server with no password, and against saved copies of the site pages. After these changes the original 124 end-to-end checks pass, and so do 29 new checks for points 1–4. I could not test:

- [ ] **Your own MySQL.** The schema changed, so run both setup commands in the README again (`schema.sql`, then `populate.sql`). If you get an error, paste it here or in chat.
- [ ] **A few results by eye.** Open eukonkanto.fi/en/results/ next to the app's `/results` page and compare 3–4 rows per series. For the Team Competition, also check the four names per team and which one is marked "(carried)".
- [ ] **All 20 features**, clicking through yourself rather than reading my test output. Feature 14 (Register a pair) now rejects weigh-ins outside 20–300 kg. Feature 15 (Register a team) is new: it needs three carriers and one carried competitor, and books the €160 team fee.
- [ ] **The video timing.** Do one full timed run-through using [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md). Features 2, 4 and 14 have small additions. Tell me if it runs over 10 minutes.

## 4. Known gaps (no action needed, just be ready to explain them)

- Medal table counts gold only before 2026 (the site doesn't publish silver/bronze for older years).
- Finish-time trend has a real average for 2026 only; other years show one record time or nothing.
- C10 cannot be checked for team winners from 1996–2025, because their rosters aren't published (confirmed in section 0).
- C8 (footwear inspection) and the 60-minute decision target in U-3 are not enforced in SQL. The reasons are in the README's Constraint enforcement section.
