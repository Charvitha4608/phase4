# Video script (under 10 minutes)

For recording only. This file does not go in the zip.

**Before recording:** reload the data so results match the site, then log in to the shell and start the app. Open the browser and the terminal side by side.

```bash
mysql -u root -p < src/schema.sql
mysql -u root -p < src/populate.sql
mysql -u root -p wife_carrying_db
```

If a take goes wrong, run the first two commands again and restart from that point.

## Opening (45 s)

Say: "This is the Wife Carrying World Championships database, modelled on eukonkanto.fi." Click Programme, then open the Competitors, Results and Contact menus and visit one or two pages from each.

## Queries, features 1 to 13 (about 3 min)

| # | Do this |
|---|---|
| 1 | Front page: point at the 2026 winners and partners |
| 2 | Results: show Main Series, then the Sprint tab (qualifying heats, final, and the Category rank column) |
| 3 | Back on Main Series: point at the four statistics boxes |
| 4 | Team Competition tab: point at the roster (3 carriers + "(carried)") and the +15 s penalty on Team 2 SPOLK |
| 5 | Competitors menu, Registered Competitors: Series = Sprint, press Show |
| 6 | Search last name `Miettinen`, then `zzz` to show the no-match message |
| 7 | Competitors menu, Teams: search `Beer` |
| 8 | Competitors: scroll to Registered for 2027 |
| 9, 10, 11 | Results menu, Champions and Records: world records, medal table, trend table |
| 12, 13 | Results menu: Sprint and Main Race, then Officials Report |

## Updates, features 14 to 19 (about 5 min)

For each one: run the query, do the action in the browser, run the **same** query again.

### 14. Register a pair

```sql
SELECT p.first_name, p.last_name, r.bib_number, r.carrier_weigh_in_kg, r.carried_weigh_in_kg, r.backpack_weight_kg, r.fee_paid, r.status FROM REGISTRATION r JOIN PERSON p ON p.person_id = r.carrier_id JOIN CHAMPIONSHIP c ON c.champ_id = r.champ_id WHERE c.year = 2027 AND r.bib_number = 500;
```

Competitors menu, Register. Series Main Series, bib `500`.
Carrier: Arjun Rao, arjun@example.com, 1990-01-01, 75 kg, India.
Carried: Meera Rao, meera@example.com, 1992-01-01, **45** kg, India.
Press Register. The message shows a 4 kg backpack. The query now shows both weigh-ins stored on the registration, not on the competitor.

### 15. File a protest

```sql
SELECT protest_seq, status, filed_at, description FROM PROTEST ORDER BY protest_seq;
```

Competitors menu, Protests, File a protest. Choose heat "2026 Main Series, final" and press Choose heat.
Protesting pair: 4. Teemu Tuovinen. Protested pair: 3. Jonatan Wasenius. Reason: `Unrecovered drop at the water obstacle.`
First set Filed at to **2026-07-04 17:00** and submit to show the rejection. Then set it to **16:35** and submit.

### 16. Correct a finish time

```sql
SELECT r.bib_number, x.finish_time_ms, x.rank_in_heat, x.diff_to_leader_ms FROM RACE_RESULT x JOIN REGISTRATION r ON r.champ_id = x.champ_id AND r.cat_code = x.cat_code AND r.carrier_id = x.carrier_id AND r.carried_id = x.carried_id JOIN CHAMPIONSHIP c ON c.champ_id = x.champ_id WHERE c.year = 2026 AND x.cat_code = 'SPRINT' AND x.heat_number = 3 ORDER BY x.rank_in_heat;
```

Officials, Correct a finish time. The page opens on Sprint heat 3. On bib 80, enter `35.00` and press Save. Bib 80 moves to rank 1 and bib 78 to rank 2.

### 17. Decide a protest

```sql
SELECT r.bib_number, x.finish_status, x.rank_in_heat FROM RACE_RESULT x JOIN REGISTRATION r ON r.champ_id = x.champ_id AND r.cat_code = x.cat_code AND r.carrier_id = x.carrier_id AND r.carried_id = x.carried_id JOIN CHAMPIONSHIP c ON c.champ_id = x.champ_id WHERE c.year = 2026 AND x.cat_code = 'MAIN' AND r.bib_number IN (62, 49, 42, 47, 44) ORDER BY x.rank_in_heat IS NULL, x.rank_in_heat;
```

Officials, Decide protests. First choose **Demo Timekeeper** and submit to show that only the jury can decide. Then choose **Demo Jury Chair**, Uphold, text `DQ for unrecovered drop`, and submit. Bib 42 becomes DQ and bib 47 moves up to 3.

### 18. Change a carrier

```sql
SELECT r.bib_number, r.status, pr.is_active, x.composition_changed FROM REGISTRATION r JOIN PAIR pr ON pr.carrier_id = r.carrier_id AND pr.carried_id = r.carried_id LEFT JOIN RACE_RESULT x ON x.champ_id = r.champ_id AND x.cat_code = r.cat_code AND x.carrier_id = r.carrier_id AND x.carried_id = r.carried_id JOIN CHAMPIONSHIP c ON c.champ_id = r.champ_id WHERE c.year = 2026 AND r.cat_code = 'MAIN' AND r.bib_number IN (49, 900);
```

Officials, Change a carrier, 2026. Press Change on bib 49. New carrier: Perttu Saarinen. Bib: `900`. Press Replace pair. Then open Results menu, Champions and Records: Lithuania's silver is gone.

### 19. Delete a championship

```sql
SELECT c.year, c.edition_number, (SELECT COUNT(*) FROM RACE_HEAT h WHERE h.champ_id = c.champ_id) AS heats FROM CHAMPIONSHIP c WHERE c.year IN (2020, 2026);
SELECT year, deleted_by, reason FROM CHAMPIONSHIP_DELETION_LOG;
```

Officials, Delete a championship. Try **2026** first to show the rejection. Then delete **2020** with reason `Cancelled: COVID-19`.

## After recording

Save the video as `41.mp4` in this folder, then run `./package.sh`.
