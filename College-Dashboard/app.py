"""
Dorm Dashboard

One page: current weather, today's classes, a to-do list, and upcoming
assignments with a countdown. Same JSON-file pattern as the ticket-hub project.

New in this version:
    - Weight/grade tracking per assignment, with a weighted current-grade
      calculation per class (see /grades).
    - File attachments: upload an actual file (PDF, doc, image, etc.) to
      an assignment and download it back later.

Run:
    pip install -r requirements.txt
    python3 app.py

Then visit http://<server-ip>:5001

Configuration (environment variables, all optional)
    DASHBOARD_PORT port to serve on (default: 5001)
    DASHBOARD_SECRET_KEY flask session secret (default: random each restart)
"""

import json
import os
import uuid
from datetime import datetime, timedelta

import requests
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from werkzeug.utils import secure_filename

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
SCHEDULE_FILE = os.path.join(APP_DIR, "schedule.json")
TODOS_FILE = os.path.join(APP_DIR, "todos.json")
ASSIGNMENTS_FILE = os.path.join(APP_DIR, "assignments.json")
ARCHIVED_ASSIGNMENTS_FILE = os.path.join(APP_DIR, "archived_assignments.json")
ATTACHMENTS_DIR = os.path.join(APP_DIR, "attachments")
PORT = int(os.environ.get("DASHBOARD_PORT", "5001"))

os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

ALLOWED_ATTACHMENT_EXTENSIONS = {
    "pdf", "doc", "docx", "txt", "png", "jpg", "jpeg", "gif", "ppt", "pptx", "xls", "xlsx"
}

# An assignment counts as "due soon" if it's within this many hours and
# not already overdue. Used to highlight it in the template.
DUE_SOON_HOURS = 24

# A class counts as "starting soon" (for the dashboard notification
# banner) if it's within this many minutes.
CLASS_NOTIFY_MINUTES = 30

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

WEATHER_CODES = {
    0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers",
    85: "Light snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm",
}

app = Flask(__name__)
app.secret_key = os.environ.get("DASHBOARD_SECRET_KEY", os.urandom(24))
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload limit

# =========================================================================
# STORAGE HELPERS
# =========================================================================

def load_json(path, default):
    """
    -> dict OR list
    Reads a JSON file off disk and hands back whatever was in it
    (a dict or a list, depending on the file). If the file doesn't
    exist yet or is broken, hands back 'default' instead of crashing.
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data) -> None:
    """
    -> None
    Writes data to disk as JSON. Doesn't need to return anything -
    its whole job is the side effect of writing the file.
    """
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def load_config() -> dict:
    """-> dict - your saved city name + coordinates, or blank defaults."""
    return load_json(CONFIG_FILE, {"city_display": "", "lat": None, "lon": None})


def load_schedule() -> list:
    """-> list - every class you've added, or an empty list."""
    return load_json(SCHEDULE_FILE, [])


def load_todos() -> list:
    """-> list - every to-do item, or an empty list"""
    return load_json(TODOS_FILE, [])


def load_assignments() -> list:
    """-> list - every assignment, or an empty list."""
    return load_json(ASSIGNMENTS_FILE, [])


def load_archived_assignments() -> list:
    """-> list - every archived assignment, or an empty list."""
    return load_json(ARCHIVED_ASSIGNMENTS_FILE, [])


def allowed_attachment(filename) -> bool:
    """-> bool - whether the uploaded file's extension is on the allow-list."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_ATTACHMENT_EXTENSIONS
    )


# =========================================================================
# WEATHER
# =========================================================================

def get_weather(lat, lon):
    """
    -> dict OR None
    Calls the weather API and hands back a dict like
    {"temp": 72, "wind": 5, "description": "Clear sky"}.
    If the API call fails for any reason, returns None instead of
    crashing the page -- the template checks for that and shows a
    friendly message.
    """
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": "auto",
            },
            timeout=5
        )
        resp.raise_for_status()
        current = resp.json().get("current", {})
        code = current.get("weather_code")
        return {
            "temp": round(current.get("temperature_2m")) if current.get("temperature_2m") is not None else None,
            "wind": current.get("wind_speed_10m"),
            "description": WEATHER_CODES.get(code, "Unknown"),
        }
    except Exception:
        return None


# =========================================================================
# COUNTDOWN HELPER
# =========================================================================

def humanize_countdown(due_dt) -> tuple:
    """
    -> tuple of (str, bool)
    Turns a due-date into human text and a flag for whether it's overdue.
    Example return value: ("in 2d 4h", False) or ("Overdue by 1d 3h", True).
    Returning two things at once like this is why the type hint is 'tuple'.
    """
    delta = due_dt - datetime.now()
    seconds = delta.total_seconds()

    if seconds < 0:
        overdue = -delta
        days, hours = overdue.days, overdue.seconds // 3600
        if days > 0:
            return f"Overdue by {days}d {hours}h", True
        return f"Overdue by {hours}h", True

    days, hours = delta.days, delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    if days > 0:
        return f"in {days}d {hours}h", False
    return f"in {minutes}m", False


# =========================================================================
# NEXT CLASS / NOTIFICATION HELPER
# =========================================================================

def get_next_class(schedule):
    """
    -> dict OR None
    Finds the next class coming up from right now -- checks the rest of
    today first, then wraps into the following days if nothing's left
    today (looks up to a week ahead). Returns the class dict plus two
    extra keys: "minutes_until" and "is_starting_soon" (True if it starts
    within CLASS_NOTIFY_MINUTES, which the dashboard uses to decide
    whether to show the notification banner).
    """
    now = datetime.now()
    current_time_str = now.strftime("%H:%M")
    today_idx = now.weekday()  # Monday == 0

    for offset in range(8):
        day_idx = (today_idx + offset) % 7
        day_name = WEEKDAYS[day_idx]
        day_classes = sorted(
            [c for c in schedule if c["day"] == day_name],
            key=lambda c: c["start_time"],
        )

        for c in day_classes:
            if offset == 0 and c["start_time"] <= current_time_str:
                continue  # already started or already passed today

            try:
                hour, minute = map(int, c["start_time"].split(":"))
            except Exception:
                continue

            target_date = (now + timedelta(days=offset)).date()
            class_dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute)
            minutes_until = int((class_dt - now).total_seconds() // 60)

            return {
                **c,
                "minutes_until": minutes_until,
                "is_starting_soon": minutes_until <= CLASS_NOTIFY_MINUTES,
            }

    return None


# =========================================================================
# GRADE / WEIGHT CALCULATION
# =========================================================================

def calculate_grades(assignments) -> dict:
    """
    -> dict
    Groups assignments by class_name and computes a weighted current grade
    for each class, using only assignments that have BOTH a weight and a
    grade recorded. Assignments without a grade yet (not graded) are still
    counted toward "total_count" so you can see how much of the class is
    still outstanding, but they don't affect current_grade.

    Example return value:
        {
            "CS 101": {
                "current_grade": 91.5,
                "graded_count": 2,
                "total_count": 5,
                "assignments": [...]
            },
            ...
        }
    """
    by_class = {}
    for a in assignments:
        cls = a.get("class_name") or "Unassigned"
        by_class.setdefault(cls, []).append(a)

    summary = {}
    for cls, items in by_class.items():
        graded = [
            a for a in items
            if a.get("weight") not in (None, "") and a.get("grade") not in (None, "")
        ]
        total_weight = sum(float(a["weight"]) for a in graded)
        if total_weight > 0:
            weighted_sum = sum(float(a["weight"]) * float(a["grade"]) for a in graded)
            current_grade = weighted_sum / total_weight
        else:
            current_grade = None

        summary[cls] = {
            "current_grade": round(current_grade, 2) if current_grade is not None else None,
            "graded_count": len(graded),
            "total_count": len(items),
            "assignments": items,
        }
    return summary


# =========================================================================
# DASHBOARD
# =========================================================================


@app.route("/")
def dashboard():
    """
    -> str (HTML)
    Every Flask route function that returns render_template(...) is
    actually returning a finished HTML page as text. Flask sends that
    text to the browser, which draws it as the page you see.
    """
    config = load_config()
    weather = get_weather(config["lat"], config["lon"]) if config.get("lat") else None

    today_name = datetime.now().strftime("%A")
    schedule = load_schedule()
    todays_classes = sorted(
        [c for c in schedule if c["day"] == today_name],
        key=lambda c: c["start_time"],
    )

    next_class = get_next_class(schedule)

    todos = load_todos()
    todos_sorted = sorted(todos, key=lambda t: t["done"])

    assignments = load_assignments()
    enriched = []
    for a in assignments:
        try:
            due_dt = datetime.fromisoformat(a["due_date"])
            countdown_text, is_overdue = humanize_countdown(due_dt)
            is_due_soon = (not is_overdue) and (due_dt - datetime.now() <= timedelta(hours=DUE_SOON_HOURS))
            enriched.append({
                **a,
                "due_dt": due_dt,
                "countdown_text": countdown_text,
                "is_overdue": is_overdue,
                "is_due_soon": is_due_soon,
            })
        except Exception:
            continue
    enriched.sort(key=lambda a: a["due_dt"])

    return render_template(
        "dashboard.html",
        config=config,
        weather=weather,
        today_name=today_name,
        todays_classes=todays_classes,
        next_class=next_class,
        todos=todos_sorted,
        assignments=enriched,
    )


# =========================================================================
# SETTINGS (location for weather)
# =========================================================================


@app.route("/settings", methods=["GET", "POST"])
def settings():
    """
    -> str (HTML) OR a redirect
    On GET: returns the setting page HTML.
    On POST: either returns a redirect (send the browser to a new URL --
    that's what redirect(url_for(...)) produces) or, if something's
    wrong, redirects back to itself so the person can try again.
    """
    if request.method == "POST":
        city = request.form.get("city", "").rstrip()
        if not city:
            flash("Enter a city name.", "error")
            return redirect(url_for("settings"))

        try:
            resp = requests.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1},
                timeout=5
            )
            resp.raise_for_status()
            results = resp.json().get("results")
        except Exception:
            flash("Couldn't reach the weather service. Try again in a moment.", "error")
            return redirect(url_for("settings"))

        if not results:
            flash("City not found -- try adding a state or country (e.g. 'State College, PA').", "error")
            return redirect(url_for("settings"))

        r = results[0]
        display = r["name"]
        if r.get("admin1"):
            display += f", {r['admin1']}"
        save_json(CONFIG_FILE, {"city_display": display, "lat": r["latitude"], "lon": r["longitude"]})
        flash(f"Location set to {display}.", "success")
        return redirect(url_for("dashboard"))

    return render_template("settings.html", config=load_config())


# =========================================================================
# TO-DOS
# =========================================================================


@app.route("/todos/add", methods=["POST"])
def add_todo():
    """-> redirect. Saves the new to-do, then sends the browser back to '/'."""
    text = request.form.get("text", "").strip()
    if text:
        todos = load_todos()
        todos.append({"id": uuid.uuid4().hex[:8], "text": text, "done": False})
        save_json(TODOS_FILE, todos)
    return redirect(url_for("dashboard"))


@app.route("/todos/toggle/<todo_id>", methods=["POST"])
def toggle_todo(todo_id):
    """-> redirect. Flips done/not-done for one to-do, then goes back to '/'."""
    todos = load_todos()
    for t in todos:
        if t["id"] == todo_id:
            t["done"] = not t["done"]
    save_json(TODOS_FILE, todos)
    return redirect(url_for("dashboard"))


@app.route("/todos/delete/<todo_id>", methods=["POST"])
def delete_todo(todo_id):
    """-> redirect. Removes one to-do, then goes back to '/'."""
    todos = [t for t in load_todos() if t["id"] != todo_id]
    save_json(TODOS_FILE, todos)
    return redirect(url_for("dashboard"))


# =========================================================================
# SCHEDULE
# =========================================================================


@app.route("/schedule", methods=["GET", "POST"])
def schedule_page():
    """-> str (HTML) OR redirect -- same GET/POST pattern as settings()."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        day = request.form.get("day", "")
        start_time = request.form.get("start_time", "")
        end_time = request.form.get("end_time", "")
        location = request.form.get("location", "").strip()

        if not name or day not in WEEKDAYS or not start_time or not end_time:
            flash("Fill in the class name, day, and start/end times.", "error")
        else:
            schedule = load_schedule()
            schedule.append({
                "id": uuid.uuid4().hex[:8],
                "name": name,
                "day": day,
                "start_time": start_time,
                "end_time": end_time,
                "location": location,
            })
            save_json(SCHEDULE_FILE, schedule)
            flash(f'"{name}" added to your schedule.', "success")
        return redirect(url_for("schedule_page"))

    schedule = load_schedule()
    by_day = {day: sorted([c for c in schedule if c["day"] == day], key=lambda c: c["start_time"]) for day in WEEKDAYS}
    return render_template("schedule.html", by_day=by_day, weekdays=WEEKDAYS)


@app.route("/schedule/delete/<class_id>", methods=["POST"])
def delete_class(class_id):
    """-> redirect. Removes one class, then goes back to /schedule."""
    schedule = [c for c in load_schedule() if c["id"] != class_id]
    save_json(SCHEDULE_FILE, schedule)
    return redirect(url_for("schedule_page"))


# =========================================================================
# ASSIGNMENTS
# =========================================================================


@app.route("/assignments", methods=["GET", "POST"])
def assignments_page():
    """
    -> str (HTML) OR redirect -- same GET/POST pattern as settings().

    Assignment form now accepts (all optional except name/due_date):
        weight       - how much this assignment counts toward the class
                       grade (e.g. 15 for "15%"). Any consistent unit works
                       as long as you're consistent within a class.
        grade        - score earned, in the same scale as weight implies
                       (e.g. 92 for "92%"). Usually left blank until graded,
                       then set later via /assignments/grade/<id>.
        attachment   - an uploaded file (syllabus, rubric, your submission,
                       etc.), stored under ATTACHMENTS_DIR.

    NOTE: because this route now accepts file uploads, the HTML form for
    adding an assignment must include enctype="multipart/form-data".
    """
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        due_date = request.form.get("due_date", "")
        class_name = request.form.get("class_name", "").strip()
        weight = request.form.get("weight", "").strip()
        grade = request.form.get("grade", "").strip()

        if not name or not due_date:
            flash("Fill in the assignment name and due date.", "error")
            return redirect(url_for("assignments_page"))

        try:
            datetime.fromisoformat(due_date)
        except ValueError:
            flash("Something went wrong with that date -- try again.", "error")
            return redirect(url_for("assignments_page"))

        if weight:
            try:
                weight = float(weight)
            except ValueError:
                flash("Weight must be a number (e.g. 15 for 15%).", "error")
                return redirect(url_for("assignments_page"))
        else:
            weight = None

        if grade:
            try:
                grade = float(grade)
            except ValueError:
                flash("Grade must be a number (e.g. 92 for 92%).", "error")
                return redirect(url_for("assignments_page"))
        else:
            grade = None

        assignment_id = uuid.uuid4().hex[:8]

        # Handle optional file upload
        attachment_filename = None
        attachment_original_name = None
        uploaded_file = request.files.get("attachment")
        if uploaded_file and uploaded_file.filename:
            if not allowed_attachment(uploaded_file.filename):
                flash(
                    f"That file type isn't allowed. Allowed: {', '.join(sorted(ALLOWED_ATTACHMENT_EXTENSIONS))}.",
                    "error",
                )
                return redirect(url_for("assignments_page"))
            original_name = secure_filename(uploaded_file.filename)
            ext = original_name.rsplit(".", 1)[1].lower()
            attachment_filename = f"{assignment_id}.{ext}"
            uploaded_file.save(os.path.join(ATTACHMENTS_DIR, attachment_filename))
            attachment_original_name = original_name

        assignments = load_assignments()
        assignments.append({
            "id": assignment_id,
            "name": name,
            "due_date": due_date,
            "class_name": class_name,
            "weight": weight,
            "grade": grade,
            "attachment_filename": attachment_filename,
            "attachment_original_name": attachment_original_name,
            "subtasks": [],
        })
        save_json(ASSIGNMENTS_FILE, assignments)
        flash(f'"{name}" added.', "success")
        return redirect(url_for("assignments_page"))

    assignments = load_assignments()
    enriched = []
    for a in assignments:
        try:
            due_dt = datetime.fromisoformat(a["due_date"])
            countdown_text, is_overdue = humanize_countdown(due_dt)
            is_due_soon = (not is_overdue) and (due_dt - datetime.now() <= timedelta(hours=DUE_SOON_HOURS))
            enriched.append({
                **a,
                "due_dt": due_dt,
                "countdown_text": countdown_text,
                "is_overdue": is_overdue,
                "is_due_soon": is_due_soon,
            })
        except Exception:
            continue
    enriched.sort(key=lambda a: a["due_dt"])

    return render_template("assignments.html", assignments=enriched)


@app.route("/assignments/grade/<assignment_id>", methods=["POST"])
def set_grade(assignment_id):
    """
    -> redirect
    Sets (or clears, if left blank) the grade and/or weight on an existing
    assignment. This is the route your "enter grade" form on the assignment
    list should POST to once you get a score back.
    """
    grade_raw = request.form.get("grade", "").strip()
    weight_raw = request.form.get("weight", "").strip()

    assignments = load_assignments()
    found = False
    for a in assignments:
        if a["id"] == assignment_id:
            found = True
            if grade_raw == "":
                a["grade"] = None
            else:
                try:
                    a["grade"] = float(grade_raw)
                except ValueError:
                    flash("Grade must be a number.", "error")
                    return redirect(url_for("assignments_page"))
            if weight_raw == "":
                a["weight"] = None
            else:
                try:
                    a["weight"] = float(weight_raw)
                except ValueError:
                    flash("Weight must be a number.", "error")
                    return redirect(url_for("assignments_page"))

    if not found:
        flash("Couldn't find that assignment.", "error")
        return redirect(url_for("assignments_page"))

    save_json(ASSIGNMENTS_FILE, assignments)
    flash("Grade updated.", "success")
    return redirect(url_for("assignments_page"))


# =========================================================================
# SUBTASKS (checklist items within an assignment)
# =========================================================================


@app.route("/assignments/<assignment_id>/subtasks/add", methods=["POST"])
def add_subtask(assignment_id):
    """-> redirect. Adds one checklist item to an assignment's subtasks list."""
    text = request.form.get("text", "").strip()
    if text:
        assignments = load_assignments()
        for a in assignments:
            if a["id"] == assignment_id:
                a.setdefault("subtasks", []).append({
                    "id": uuid.uuid4().hex[:8],
                    "text": text,
                    "done": False,
                })
        save_json(ASSIGNMENTS_FILE, assignments)
    return redirect(url_for("assignments_page"))


@app.route("/assignments/<assignment_id>/subtasks/toggle/<subtask_id>", methods=["POST"])
def toggle_subtask(assignment_id, subtask_id):
    """-> redirect. Flips done/not-done for one subtask."""
    assignments = load_assignments()
    for a in assignments:
        if a["id"] == assignment_id:
            for s in a.get("subtasks", []):
                if s["id"] == subtask_id:
                    s["done"] = not s["done"]
    save_json(ASSIGNMENTS_FILE, assignments)
    return redirect(url_for("assignments_page"))


@app.route("/assignments/<assignment_id>/subtasks/delete/<subtask_id>", methods=["POST"])
def delete_subtask(assignment_id, subtask_id):
    """-> redirect. Removes one subtask from an assignment's checklist."""
    assignments = load_assignments()
    for a in assignments:
        if a["id"] == assignment_id:
            a["subtasks"] = [s for s in a.get("subtasks", []) if s["id"] != subtask_id]
    save_json(ASSIGNMENTS_FILE, assignments)
    return redirect(url_for("assignments_page"))


# =========================================================================
# ARCHIVE (instead of permanent delete)
# =========================================================================


@app.route("/assignments/archive/<assignment_id>", methods=["POST"])
def archive_assignment(assignment_id):
    """
    -> redirect
    Moves an assignment out of assignments.json and into
    archived_assignments.json, instead of deleting it outright. Its
    attachment file (if any) is left on disk untouched -- only the
    record moves, so you can still download it from the archive page
    or restore the assignment later.
    """
    assignments = load_assignments()
    match = next((a for a in assignments if a["id"] == assignment_id), None)
    if not match:
        flash("Couldn't find that assignment.", "error")
        return redirect(url_for("assignments_page"))

    remaining = [a for a in assignments if a["id"] != assignment_id]
    save_json(ASSIGNMENTS_FILE, remaining)

    archived = load_archived_assignments()
    match["archived_at"] = datetime.now().isoformat()
    archived.append(match)
    save_json(ARCHIVED_ASSIGNMENTS_FILE, archived)

    flash(f'"{match["name"]}" archived.', "success")
    return redirect(url_for("assignments_page"))


@app.route("/assignments/archived")
def archived_assignments_page():
    """-> str (HTML). Shows everything you've archived, most recent first."""
    archived = load_archived_assignments()
    enriched = []
    for a in archived:
        try:
            due_dt = datetime.fromisoformat(a["due_date"])
        except Exception:
            due_dt = None
        enriched.append({**a, "due_dt": due_dt})
    enriched.sort(key=lambda a: a.get("archived_at", ""), reverse=True)
    return render_template("archived.html", assignments=enriched)


@app.route("/assignments/restore/<assignment_id>", methods=["POST"])
def restore_assignment(assignment_id):
    """-> redirect. Moves an archived assignment back into the active list."""
    archived = load_archived_assignments()
    match = next((a for a in archived if a["id"] == assignment_id), None)
    if not match:
        flash("Couldn't find that archived assignment.", "error")
        return redirect(url_for("archived_assignments_page"))

    remaining = [a for a in archived if a["id"] != assignment_id]
    save_json(ARCHIVED_ASSIGNMENTS_FILE, remaining)

    match.pop("archived_at", None)
    assignments = load_assignments()
    assignments.append(match)
    save_json(ASSIGNMENTS_FILE, assignments)

    flash(f'"{match["name"]}" restored.', "success")
    return redirect(url_for("assignments_page"))


@app.route("/assignments/archived/delete/<assignment_id>", methods=["POST"])
def delete_archived_assignment(assignment_id):
    """
    -> redirect
    Permanently deletes an archived assignment, including its attachment
    file if it had one. This is the only truly destructive route left --
    everything reachable from the main assignments page just archives.
    """
    archived = load_archived_assignments()
    remaining = []
    for a in archived:
        if a["id"] == assignment_id:
            if a.get("attachment_filename"):
                path = os.path.join(ATTACHMENTS_DIR, a["attachment_filename"])
                if os.path.exists(path):
                    os.remove(path)
            continue
        remaining.append(a)
    save_json(ARCHIVED_ASSIGNMENTS_FILE, remaining)
    flash("Assignment permanently deleted.", "success")
    return redirect(url_for("archived_assignments_page"))


@app.route("/assignments/delete/<assignment_id>", methods=["POST"])
def delete_assignment(assignment_id):
    """
    -> redirect. Removes one assignment, then goes back to /assignments.
    Also deletes its attachment file off disk, if it had one, so files
    don't pile up in ATTACHMENTS_DIR forever.

    NOTE: this is kept around for direct/permanent deletion, but the
    assignments.html template should now point its main "remove" button
    at /assignments/archive/<id> instead, so nothing is lost by accident.
    """
    assignments = load_assignments()
    remaining = []
    for a in assignments:
        if a["id"] == assignment_id:
            if a.get("attachment_filename"):
                path = os.path.join(ATTACHMENTS_DIR, a["attachment_filename"])
                if os.path.exists(path):
                    os.remove(path)
            continue
        remaining.append(a)
    save_json(ASSIGNMENTS_FILE, remaining)
    return redirect(url_for("assignments_page"))


@app.route("/attachments/<assignment_id>")
def download_attachment(assignment_id):
    """
    -> file download
    Serves the uploaded file back for a given assignment, using its
    original filename so the download looks right to the person opening it.
    """
    assignments = load_assignments()
    match = next((a for a in assignments if a["id"] == assignment_id), None)
    if not match or not match.get("attachment_filename"):
        flash("No attachment found for that assignment.", "error")
        return redirect(url_for("assignments_page"))

    return send_from_directory(
        ATTACHMENTS_DIR,
        match["attachment_filename"],
        as_attachment=True,
        download_name=match.get("attachment_original_name") or match["attachment_filename"],
    )


# =========================================================================
# GRADES OVERVIEW
# =========================================================================


@app.route("/grades")
def grades_page():
    """-> str (HTML). Shows a per-class weighted grade breakdown."""
    assignments = load_assignments()
    summary = calculate_grades(assignments)
    return render_template("grades.html", summary=summary)


if __name__ == "__main__":
    """
    This block has no -> arrow because it's not a function - it's the
    "only run this if the file is executed directly" guard. app.run(...)
    itself doesn't return anything meaningful either; it just starts
    the server and keeps running until you stop it.
    """
    app.run(host="0.0.0.0", port=PORT, debug=False)
