"""
Dorm Dashboard

One page: current weather, today's classes, a to-do list, and upcoming
assignments with a countdown. Same JSON-file pattern as the other two
projects.

Run:
    pip install -r requirements.txt
    python3 app.py

Then visit http://<server-ip>:5002

Configuration (environment variables, all optional):
    DASHBOARD_PORT   port to serve on (default: 5002)
"""

import json
import os
import uuid
from datetime import datetime

import requests
from flask import Flask, render_template, request, redirect, url_for, flash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
SCHEDULE_FILE = os.path.join(APP_DIR, "schedule.json")
TODOS_FILE = os.path.join(APP_DIR, "todos.json")
ASSIGNMENTS_FILE = os.path.join(APP_DIR, "assignments.json")
PORT = int(os.environ.get("DASHBOARD_PORT", "5002"))

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# WMO weather codes -> plain-English description (used by Open-Meteo)
WEATHER_CODES = {
    0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers",
    85: "Light snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm",
}

app = Flask(__name__)
app.secret_key = os.environ.get("DASHBOARD_SECRET_KEY", os.urandom(24))


# =========================================================================
# STORAGE HELPERS
# =========================================================================
def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def load_config():
    return load_json(CONFIG_FILE, {"city_display": "", "lat": None, "lon": None})


def load_schedule():
    return load_json(SCHEDULE_FILE, [])


def load_todos():
    return load_json(TODOS_FILE, [])


def load_assignments():
    return load_json(ASSIGNMENTS_FILE, [])


# =========================================================================
# WEATHER
# =========================================================================
def get_weather(lat, lon):
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
            timeout=5,
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
def humanize_countdown(due_dt):
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
    if hours > 0:
        return f"in {hours}h {minutes}m", False
    return f"in {minutes}m", False


# =========================================================================
# DASHBOARD
# =========================================================================
@app.route("/")
def dashboard():
    config = load_config()
    weather = get_weather(config["lat"], config["lon"]) if config.get("lat") else None

    today_name = datetime.now().strftime("%A")
    schedule = load_schedule()
    todays_classes = sorted(
        [c for c in schedule if c["day"] == today_name],
        key=lambda c: c["start_time"],
    )

    todos = load_todos()
    todos_sorted = sorted(todos, key=lambda t: t["done"])

    assignments = load_assignments()
    enriched = []
    for a in assignments:
        try:
            due_dt = datetime.fromisoformat(a["due_date"])
            countdown_text, is_overdue = humanize_countdown(due_dt)
            enriched.append({**a, "due_dt": due_dt, "countdown_text": countdown_text, "is_overdue": is_overdue})
        except Exception:
            continue
    enriched.sort(key=lambda a: a["due_dt"])

    return render_template(
        "dashboard.html",
        config=config,
        weather=weather,
        today_name=today_name,
        todays_classes=todays_classes,
        todos=todos_sorted,
        assignments=enriched,
    )


# =========================================================================
# SETTINGS (location for weather)
# =========================================================================
@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        city = request.form.get("city", "").strip()
        if not city:
            flash("Enter a city name.", "error")
            return redirect(url_for("settings"))

        try:
            resp = requests.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1},
                timeout=5,
            )
            resp.raise_for_status()
            results = resp.json().get("results")
        except Exception:
            flash("Couldn't reach the weather service. Try again in a moment.", "error")
            return redirect(url_for("settings"))

        if not results:
            flash("City not found — try adding a state or country (e.g. 'State College, PA').", "error")
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
    text = request.form.get("text", "").strip()
    if text:
        todos = load_todos()
        todos.append({"id": uuid.uuid4().hex[:8], "text": text, "done": False})
        save_json(TODOS_FILE, todos)
    return redirect(url_for("dashboard"))


@app.route("/todos/toggle/<todo_id>", methods=["POST"])
def toggle_todo(todo_id):
    todos = load_todos()
    for t in todos:
        if t["id"] == todo_id:
            t["done"] = not t["done"]
    save_json(TODOS_FILE, todos)
    return redirect(url_for("dashboard"))


@app.route("/todos/delete/<todo_id>", methods=["POST"])
def delete_todo(todo_id):
    todos = [t for t in load_todos() if t["id"] != todo_id]
    save_json(TODOS_FILE, todos)
    return redirect(url_for("dashboard"))


# =========================================================================
# SCHEDULE
# =========================================================================
@app.route("/schedule", methods=["GET", "POST"])
def schedule_page():
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
    schedule = [c for c in load_schedule() if c["id"] != class_id]
    save_json(SCHEDULE_FILE, schedule)
    return redirect(url_for("schedule_page"))


# =========================================================================
# ASSIGNMENTS
# =========================================================================
@app.route("/assignments", methods=["GET", "POST"])
def assignments_page():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        due_date = request.form.get("due_date", "")
        class_name = request.form.get("class_name", "").strip()

        if not name or not due_date:
            flash("Fill in the assignment name and due date.", "error")
        else:
            try:
                datetime.fromisoformat(due_date)
            except ValueError:
                flash("Something went wrong with that date — try again.", "error")
                return redirect(url_for("assignments_page"))

            assignments = load_assignments()
            assignments.append({
                "id": uuid.uuid4().hex[:8],
                "name": name,
                "due_date": due_date,
                "class_name": class_name,
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
            enriched.append({**a, "due_dt": due_dt, "countdown_text": countdown_text, "is_overdue": is_overdue})
        except Exception:
            continue
    enriched.sort(key=lambda a: a["due_dt"])

    return render_template("assignments.html", assignments=enriched)


@app.route("/assignments/delete/<assignment_id>", methods=["POST"])
def delete_assignment(assignment_id):
    assignments = [a for a in load_assignments() if a["id"] != assignment_id]
    save_json(ASSIGNMENTS_FILE, assignments)
    return redirect(url_for("assignments_page"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
