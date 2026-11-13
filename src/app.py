"""Web application for the Wife Carrying World Championships database."""
import os
import re
from datetime import date, datetime, timedelta

import pymysql
from flask import Flask, abort, flash, redirect, render_template, request, url_for

import queries
import updates
from updates import FormError

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "phase-4-local-only")

LATEST_YEAR = 2026
NEXT_YEAR = 2027
PAIR_SERIES = ("MAIN", "WOMEN", "M40", "SPRINT")
ALL_SERIES = PAIR_SERIES + ("TEAM",)


# ---------- display helpers ----------
def format_time(ms):
    if ms is None:
        return "–"
    ms = int(round(float(ms)))
    minutes, rest = divmod(ms, 60000)
    if minutes:
        seconds = f"{rest / 1000:04.1f}" if rest % 100 == 0 else f"{rest / 1000:05.2f}"
        return f"{minutes}:{seconds}"
    return f"{rest / 1000:.2f}"


def format_diff(ms, series=None):
    """Gap to the leader, in the style the site uses for each series."""
    if ms is None:
        return "–"
    ms = int(ms)
    if ms == 0:
        return ""
    if ms >= 60000 or series == "SPRINT":
        return "+" + format_time(ms)
    return f"+{ms / 1000:.1f}" if ms % 100 == 0 else f"+{ms / 1000:.2f}"


app.jinja_env.filters["time"] = format_time
app.jinja_env.filters["diff"] = format_diff


@app.context_processor
def page_context():
    return {"latest_year": LATEST_YEAR, "next_year": NEXT_YEAR}


# ---------- input parsing ----------
def required(form, name, label):
    value = form.get(name, "").strip()
    if not value:
        raise FormError(f"{label} is required.")
    return value


def to_int(value, label, minimum=None, maximum=None):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise FormError(f"{label} must be a whole number.")
    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        raise FormError(f"{label} is out of range.")
    return number


def to_weight(value, label):
    """Event weigh-in in kg. Same bounds as chk_reg_weigh_in in schema.sql."""
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        raise FormError(f"{label} must be a number.")
    if not 20 <= number <= 300:
        raise FormError(f"{label} must be between 20 and 300 kg.")
    return number


def to_date(value, label):
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        raise FormError(f"{label} must be a valid date.")


def to_datetime(value, label):
    try:
        return datetime.fromisoformat(str(value).strip())
    except ValueError:
        raise FormError(f"{label} must be a valid date and time.")


def to_time_ms(value):
    match = re.fullmatch(r"(?:(\d{1,2}):)?(\d{1,2}(?:\.\d{1,3})?)", str(value).strip())
    if not match:
        raise FormError("Finish time must look like 35.80 or 1:04.4.")
    total = int(match[1] or 0) * 60000 + round(float(match[2]) * 1000)
    if total <= 0:
        raise FormError("Finish time must be greater than zero.")
    return total


def to_pair(value, label):
    match = re.fullmatch(r"(\d+)-(\d+)", str(value).strip())
    if not match:
        raise FormError(f"Please choose a {label}.")
    return int(match[1]), int(match[2])


def to_heat(value):
    match = re.fullmatch(r"(\d+)\|([A-Z0-9]+)\|(\d+)", str(value).strip())
    if not match:
        return None
    return int(match[1]), match[2], int(match[3])


CHECK_MESSAGES = {
    "chk_pair_distinct": "The carrier and the carried competitor must be two different people.",
    "chk_reg_fee": "A registration fee must be €55 (individual) or €160 (team).",
    "chk_protest_fee": "The protest fee must be exactly €150.",
    "chk_reg_weigh_in": "A weigh-in must be between 20 and 300 kg.",
    "chk_reg_backpack": "A backpack weight must be between 0 and 49 kg.",
    "chk_reg_refund": "A refund cannot be negative.",
    "chk_reg_cancelled": "Only a cancelled registration can have a cancellation time.",
}


def database_message(error):
    """Turn a MySQL error into a sentence for the user."""
    code = error.args[0] if error.args else 0
    detail = error.args[1] if len(error.args) > 1 else str(error)
    if code == 1644:      # raised by our triggers
        return detail
    if code == 1062:
        if "uq_reg_bib" in detail:
            return "That bib number is already taken in this series."
        if "REGISTRATION.PRIMARY" in detail or "registration.PRIMARY" in detail:
            return "This pair is already registered in this series."
        return f"That record already exists: {detail}"
    if code == 1451:
        return ("This championship cannot be deleted: heats, protests, registrations, team rosters, "
                "team results, sponsors or accreditations still refer to it. Archive it instead.")
    if code == 1452:
        return "A referenced record does not exist."
    if code == 3819:     # CHECK constraint
        for name, text in CHECK_MESSAGES.items():
            if name in detail:
                return text
        return f"The data breaks a database rule: {detail}"
    if code in (2002, 2003):
        return "The database server cannot be reached. Check that MySQL is running."
    return f"Database error {code}: {detail}"


@app.errorhandler(pymysql.MySQLError)
def handle_database_error(error):
    return render_template("message.html", title="Database error", message=database_message(error)), 500


@app.errorhandler(404)
def handle_not_found(_error):
    return render_template("message.html", title="Page not found",
                           message="That page or record does not exist."), 404


def run_write(action, success_message):
    """Run a write. Show the outcome as a message. Returns True on success."""
    try:
        result = action()
    except FormError as error:
        flash(str(error), "error")
    except pymysql.MySQLError as error:
        flash(database_message(error), "error")
    else:
        flash(success_message(result), "success")
        return True
    return False


# ---------- public pages ----------
@app.route("/")
def home():
    return render_template("home.html", winners=queries.winners_of_year(LATEST_YEAR),
                           partners=queries.partners(LATEST_YEAR))


@app.route("/programme")
def programme():
    return render_template("programme.html", venue=queries.venue_for_year(LATEST_YEAR))


@app.route("/track-and-rules")
def rules():
    return render_template("rules.html", categories=queries.categories())


@app.route("/contact")
def contact():
    return render_template("contact.html", organiser=queries.organiser_info())


@app.route("/official-grand-prix")
def grand_prix():
    return render_template("grand_prix.html")


@app.route("/accreditation-press")
def press():
    return render_template("press.html", outlets=queries.accredited_media(LATEST_YEAR), year=LATEST_YEAR)


@app.route("/results")
def results():
    cat_code = request.args.get("series", "MAIN")
    if cat_code not in ALL_SERIES:
        abort(404)
    years = queries.years_with_results(cat_code)
    year = request.args.get("year", type=int, default=LATEST_YEAR)
    if year not in years:
        flash(f"No {cat_code} results are stored for {year}. Showing the latest year.", "error")
        year = years[0]
    context = {"series": cat_code, "year": year, "years": years, "categories": queries.categories()}
    if cat_code == "TEAM":
        return render_template("results.html", teams=queries.team_results(year), **context)
    return render_template("results.html", rows=queries.race_results(year, cat_code),
                           stats=queries.race_statistics(year, cat_code), **context)


@app.route("/results/champions-and-records")
def champions():
    return render_template("champions.html", records=queries.world_records(), medals=queries.medal_table(),
                           trend=queries.finish_time_trend(), main_gold=queries.gold_medalists("MAIN"),
                           sprint_gold=queries.gold_medalists("SPRINT"))


@app.route("/competitors")
def competitors():
    term = request.args.get("q", "").strip()
    cat_code = request.args.get("series", "SPRINT")
    if cat_code not in PAIR_SERIES:
        abort(404)
    return render_template("competitors.html", term=term, series=cat_code, categories=queries.categories(),
                           athletes=queries.search_athletes(term) if term else None,
                           carriers=queries.carriers_in_category(LATEST_YEAR, cat_code),
                           registered=queries.registered_pairs(NEXT_YEAR))


@app.route("/teams")
def teams():
    term = request.args.get("q", "").strip()
    return render_template("teams.html", term=term, found=queries.search_teams(term) if term else None)


@app.route("/reports/sprint-vs-main")
def report_sprint_vs_main():
    return render_template("report_sprint_main.html", rows=queries.sprint_vs_main())


@app.route("/reports/officials")
def report_officials():
    return render_template("report_officials.html", rows=queries.busiest_officials())


# ---------- I-1: registration ----------
def person_from_form(form, prefix, label):
    return {
        "first_name": required(form, f"{prefix}_first_name", f"{label} first name"),
        "last_name": required(form, f"{prefix}_last_name", f"{label} last name"),
        "email": required(form, f"{prefix}_email", f"{label} email"),
        "gender": form.get(f"{prefix}_gender") if form.get(f"{prefix}_gender") in ("F", "M", "X") else None,
        "date_of_birth": to_date(required(form, f"{prefix}_dob", f"{label} date of birth"), f"{label} date of birth"),
        "country": required(form, f"{prefix}_country", f"{label} country"),
        "weight_kg": to_weight(required(form, f"{prefix}_weight", f"{label} weight"), f"{label} weight"),
        "phone": form.get(f"{prefix}_phone", "").strip() or None,
    }


@app.route("/register", methods=["GET", "POST"])
def register():
    championship = queries.championship_by_year(NEXT_YEAR)
    if request.method == "POST":
        def action():
            cat_code = required(request.form, "series", "Series")
            if cat_code not in PAIR_SERIES:
                raise FormError("Please choose a series.")
            carrier = person_from_form(request.form, "carrier", "Carrier")
            carried = person_from_form(request.form, "carried", "Carried competitor")
            return updates.register_pair(championship["champ_id"], cat_code, carrier, carried)

        def message(backpack):
            text = f"Registered for {NEXT_YEAR}."
            return text + (f" The carried competitor must wear a {backpack} kg backpack." if backpack else "")

        if run_write(action, message):
            return redirect(url_for("competitors") + "#registered")
    return render_template("register.html", championship=championship, countries=queries.countries(),
                           series=queries.categories_of_championship(NEXT_YEAR), fees=queries.entry_fees(),
                           form=request.form)


@app.route("/register/team", methods=["GET", "POST"])
def register_team():
    """I-1 for the team category: three carriers and one carried competitor (C10)."""
    championship = queries.championship_by_year(NEXT_YEAR)
    series = queries.categories_of_championship(NEXT_YEAR, team=True)
    if request.method == "POST":
        def action():
            cat_code = required(request.form, "series", "Series")
            if cat_code not in [s["cat_code"] for s in series]:
                raise FormError("Please choose a team series.")
            team_name = required(request.form, "team_name", "Team name")
            home_country = request.form.get("home_country", "").strip() or None
            carriers = [person_from_form(request.form, f"carrier{n}", f"Carrier {n}") for n in (1, 2, 3)]
            carried = person_from_form(request.form, "carried", "Carried competitor")
            return updates.register_team(championship["champ_id"], cat_code, team_name, home_country,
                                         carriers, carried)

        def message(result):
            _, backpack, _fee = result
            text = f"Team registered for {NEXT_YEAR}."
            return text + (f" The carried competitor must wear a {backpack} kg backpack." if backpack else "")

        if run_write(action, message):
            return redirect(url_for("teams", q=request.form.get("team_name", "").strip()))
    return render_template("register_team.html", championship=championship, countries=queries.countries(),
                           series=series, fees=queries.entry_fees(), form=request.form)


# ---------- I-2: protests ----------
@app.route("/protests")
def protests():
    return render_template("protests.html", protests=queries.protests_list())


@app.route("/protests/new", methods=["GET", "POST"])
def new_protest():
    heats = queries.protestable_heats()
    selected = to_heat(request.values.get("heat", ""))
    heat = queries.protestable_heat(*selected) if selected else None
    if request.method == "POST":
        if heat is None:
            flash("Please choose a heat.", "error")
        else:
            def action():
                filer = to_pair(request.form.get("filer", ""), "protesting pair")
                against = to_pair(request.form.get("against", ""), "protested pair")
                filed_at = to_datetime(required(request.form, "filed_at", "Filing time"), "Filing time")
                description = required(request.form, "description", "Description")
                return updates.file_protest(*selected, filed_at, filer, against, description)

            if run_write(action, lambda seq: f"Protest {heat['year']}-{seq:02d} filed. Fee paid: €150 (non-refundable)."):
                return redirect(url_for("protests"))
    entries = queries.heat_entries(*selected) if heat else []
    default_time = (heat["heat_completed_at"] + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M") if heat else ""
    return render_template("protest_new.html", heats=heats, heat=heat, entries=entries,
                           default_time=default_time, form=request.form)


# ---------- officials' area: U-1, U-2, U-3, D-1 ----------
@app.route("/officials")
def officials():
    return render_template("officials.html")


@app.route("/officials/results", methods=["GET", "POST"])
def officials_results():
    heats = queries.protestable_heats()
    selected = to_heat(request.values.get("heat", "")) or (heats[0]["champ_id"], "SPRINT", 3)
    heat = queries.protestable_heat(*selected)
    if heat is None:
        abort(404)
    if request.method == "POST":
        def action():
            carrier_id, carried_id = to_pair(request.form.get("pair", ""), "pair")
            new_time = to_time_ms(required(request.form, "finish_time", "Finish time"))
            raw_drops = request.form.get("drop_count", "").strip()
            drops = to_int(raw_drops, "Drop count", 0, 50) if raw_drops else None
            return updates.correct_finish_time(*selected, carrier_id, carried_id, new_time, drops)

        run_write(action, lambda rank: f"Finish time corrected. The heat was recalculated and this pair is now rank {rank}.")
        return redirect(url_for("officials_results", heat=f"{selected[0]}|{selected[1]}|{selected[2]}"))
    return render_template("officials_results.html", heats=heats, heat=heat, entries=queries.heat_entries(*selected))


@app.route("/officials/registrations")
def officials_registrations():
    year = request.args.get("year", type=int, default=LATEST_YEAR)
    if year not in (LATEST_YEAR, NEXT_YEAR):
        abort(404)
    return render_template("officials_registrations.html", year=year, rows=queries.registrations_for_year(year))


@app.route("/officials/registrations/<int:champ_id>/<cat_code>/<int:carrier_id>/<int:carried_id>",
           methods=["GET", "POST"])
def officials_change_role(champ_id, cat_code, carrier_id, carried_id):
    entry = queries.registration(champ_id, cat_code, carrier_id, carried_id)
    if entry is None:
        abort(404)
    if request.method == "POST":
        def action():
            new_carrier = to_int(required(request.form, "new_carrier", "New carrier"), "New carrier", 1)
            new_bib = to_int(required(request.form, "new_bib", "New bib"), "New bib", 1, 9999)
            return updates.change_carrier(champ_id, cat_code, carrier_id, carried_id, new_carrier, new_bib)

        if run_write(action, lambda flagged: f"Pair replaced. {flagged} result(s) flagged and excluded from the medal table."):
            return redirect(url_for("officials_registrations", year=entry["year"]))
    return render_template("officials_change_role.html", entry=entry,
                           candidates=queries.replacement_carriers(champ_id, carrier_id),
                           next_bib=queries.next_free_bib(champ_id, cat_code))


@app.route("/officials/protests", methods=["GET", "POST"])
def officials_protests():
    if request.method == "POST":
        def action():
            champ_id = to_int(request.form.get("champ_id"), "Championship", 1)
            protest_seq = to_int(request.form.get("protest_seq"), "Protest", 1)
            official_id = to_int(required(request.form, "official", "Deciding official"), "Deciding official", 1)
            outcome = request.form.get("outcome")
            if outcome not in ("UPHELD", "REJECTED"):
                raise FormError("Please choose an outcome.")
            text = required(request.form, "decision_text", "Decision text")
            return updates.decide_protest(champ_id, protest_seq, official_id, outcome, text)

        run_write(action, lambda _: "Decision recorded. Any change to the result has been applied.")
        return redirect(url_for("officials_protests"))
    return render_template("officials_protests.html", protests=queries.protests_list(open_only=True),
                           officials=queries.jury_officials())


@app.route("/officials/championships", methods=["GET", "POST"])
def officials_championships():
    if request.method == "POST":
        def action():
            champ_id = to_int(request.form.get("champ_id"), "Championship", 1)
            deleted_by = required(request.form, "deleted_by", "Your name")
            reason = required(request.form, "reason", "Reason")
            return updates.delete_championship(champ_id, deleted_by, reason)

        run_write(action, lambda year: f"Championship {year} deleted and logged.")
        return redirect(url_for("officials_championships"))
    return render_template("officials_championships.html", rows=queries.championships_overview(),
                           log=queries.deletion_log())



@app.route("/officials/registrations/<int:champ_id>/<cat_code>/<int:carrier_id>/<int:carried_id>/cancel",
           methods=["POST"])
def officials_cancel_registration(champ_id, cat_code, carrier_id, carried_id):
    def action():
        return updates.cancel_registration(champ_id, cat_code, carrier_id, carried_id)

    run_write(action, lambda refund: f"Registration cancelled. Refund due: €{refund:.2f}" if refund else "Registration cancelled. No refund due (<30 days before event).")
    year = request.form.get("year", LATEST_YEAR)
    return redirect(url_for("officials_registrations", year=year))


if __name__ == "__main__":
    app.run(debug=True)
