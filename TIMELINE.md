# Timeline: 4-Person Plan to Submit by 12 Nov, 11:00 PM

Written 11 Nov, 15:32. About 31.5 hours left. Split into 4 tracks so all of you have something concrete to do in parallel rather than one person doing everything.

## What I expect from the team

- **One person owns `team_review.md`.** They collect everyone's results into it as each track finishes, so it's the single place showing what's done.
- **Everyone reads the Features list in `README.md`** before their track, so you know what each page is supposed to do.
- **Report problems to me as you find them**, don't fix them yourselves in the code and don't wait until a milestone ends to mention something broken. The earlier I know, the more time I have to fix it before the next step depends on it.
- **No one touches `src/` code directly** without telling me first — if two people edit the same file at once I can't merge that, and I can't verify a change I didn't make or see.

## Track 1 — Real environment (whoever has MySQL set up)

1. Run the setup commands in `README.md` on your own machine, with your own MySQL password.
2. Confirm the app starts and `/` loads in a browser.
3. Click through all 19 numbered features in the README's Feature list, in order, confirming each does what it says.
4. Check off `team_review.md` section 3's first and third items.

**Report back:** any error message, exactly as shown, plus which step it happened on.

## Track 2 — Data accuracy (whoever is comfortable comparing tables)

1. Open eukonkanto.fi/en/results/ in one tab and the app's `/results` page in another.
2. Compare 3–4 rows per series (Main, Women, 40+, Sprint, Team) — names, country, time.
3. Open eukonkanto.fi/en/results/champions-and-records/ next to the app's Champions and Records page, and spot-check 3–4 years.
4. Check off `team_review.md` section 3's second item.

**Report back:** any row that doesn't match, with the bib number or year.

## Track 3 — Design sign-off and the TA

1. Read the Design Changes table in `README.md` (DC-1 through DC-11).
2. As a team, agree or disagree with the four flagged items in `team_review.md` section 2.
3. Send the TA message in `team_review.md` section 1, today if possible — a late reply is a real risk otherwise.
4. Read `src/queries.py` and `src/updates.py` enough that any of you could explain one query if asked.

**Report back:** TA's reply when it arrives, and any design change your team disagrees with.

## Track 4 — Video rehearsal (whoever will present or run the terminal)

1. Do one **unrecorded** full run-through of `VIDEO_SCRIPT.md` tonight, start to finish, timed.
2. Note which section ran long.
3. Decide who talks and who drives the browser/terminal for the real recording.

**Report back:** total time, and whether anything in the script was confusing or wrong.

## Milestones

| By | What's done if you've hit it |
|---|---|
| **Today, 19:00** | Tracks 1–3 finished. `team_review.md` sections 1–3 fully checked off, except the TA's reply. You know the app works on real infrastructure, matches the site, and the team has agreed on every design choice. |
| **Today, 22:00** | Track 4 finished. You know the real recording will fit in 10 minutes and who does what on camera. |
| **Tomorrow, 11:00** | `41.mp4` recorded and saved in the `phase 4` folder, following the (now-rehearsed) script. |
| **Tomorrow, 15:00** | `./package.sh` run, `41.zip` produced, its file listing checked against the structure in `README.md`. |
| **Tomorrow, 19:00** | `41.zip` uploaded. Four hours of slack left before the 23:00 deadline, in case the submission portal is slow or something needs a last fix. |

If you fall behind one milestone, tell me which one — I'll adjust what's realistic for the rest rather than you guessing.
