# Please Confirm: Open Decisions and Checks

Working notes, not part of the submission. Everything here needs a person, not more automated work. Check items off as you go; cross out and write a note if you disagree with something.

Anything I find later that doesn't block me gets added under **New items** below, newest first, instead of chat. If something *does* block me, I'll ask directly in chat instead of writing it here.

## 0. TO CONFIRM 

## 1. Message to send the TA

The site names no officials, jury members or protests, but two required operations and a report need them. Send this before you rely on the demo rows being acceptable:

> Hi, for Phase 4 our Mini World is eukonkanto.fi. The site publishes results but doesn't name any officials, jury members or protests, or list press outlets, and our Phase 1 functional requirements need them (the officials report and the protest decision operation). We've added a small number of rows clearly labelled DEMO for these and listed them in the README. All competitor, result and event data comes from the site. Is that acceptable?

- [ ] Sent to TA
- [ ] Reply received: ________________________

## 2. Design changes to sign off on

Full reasons are in [README.md](README.md#design-changes). These are the ones most likely to need your team's agreement rather than mine, because they go beyond a direct fix:

- [ ] **DC-1 (added REGISTRATION table):** bib numbers and fees moved out of COMPETITOR into a new table. Changes how Team 28's schema reads.
- [ ] **DC-2 (removed bib_number/role from COMPETITOR):** needed because the 2026 results show one person as carrier in one pair and carried in another. Confirm your team agrees this was a real gap, not a misreading of Team 28's design.
- [ ] **DC-10 (REPRESENTS allows more than 2 countries):** bib 21 in the 2026 results lists three nationalities for one pair. Confirm this is how you want mixed-nationality pairs handled, since it affects the medal count (a pair can win medals for more than one country).
- [ ] **Demo officials/protests (not a DC, but a data decision):** six invented officials and two invented protests. If your TA says no, I'll need to redesign the two features that depend on them (U-3 and the officials report).

## 3. Things only you can verify

I tested against a private MySQL server with no password and the same version (8.4.9) as described, and against saved copies of the site pages. I could not test:

- [ ] **Your own MySQL.** Run the setup commands in the README. If you get an error, paste it here or in chat.
- [ ] **A few results by eye.** Open eukonkanto.fi/en/results/ next to the app's `/results` page and compare 3–4 rows per series.
- [ ] **All 19 features**, clicking through yourself rather than reading my test output.
- [ ] **The video timing.** One full timed run-through using [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md). Tell me if it runs over 10 minutes.

## 4. Known gaps (no action needed, just be ready to explain them)

- Medal table counts gold only before 2026 (the site doesn't publish silver/bronze for older years).
- Finish-time trend has a real average for 2026 only; other years show one record time or nothing.
- C8 (footwear inspection), C10 (team roster of exactly 3+1), and the 60-minute decision target in U-3 are not enforced in SQL — reasons are in the README's Constraint Enforcement table.
