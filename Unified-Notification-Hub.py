"""
Notification Hub

One feed pulling together everything that needs your attention across
your home server: assignments due soon, open support tickets, and
recently uploaded photos. Reads directly from the same JSON files your
other apps already write to -- no duplicated data, no syncing needed.

Run:
    pip install -r requirements.txt
    cp .env.example .env
    # edit .env with your real file paths
    python3 Unified-Notification-Hub.py

Then visit http://<server-ip>:5004

Configuration lives in a ".env" file (see .env.example) so your real
server paths never get committed to GitHub:
    NOTIFY_ASSIGNMENTS_FILE   path to College-Dashboard's assignments.json
    NOTIFY_TICKETS_FILE       path to ticket-hub's tickets_database.json
    NOTIFY_PHOTOS_FILE        path to Photo-DropOff's photos.json
    NOTIFY_DUE_SOON_HOURS     assignments due within this many hours count
                              as "due soon" (default: 24)
    NOTIFY_PORT               port to serve on (default: 5002)
"""

import json
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, render_template

# Loads variables from a ".env" file sitting next to this script, if one
#exists. This is where your REAL file paths live-- ".env" is listed in
# .gitignore so it never gets committed/pushed to GitHub, keeping your
# server's actual folder structure out of a public repo. See
# .env.example for the format; copy it to ".env" and fill in your real
# paths.
load_dotenv()

PORT = int(os.environ.get("NOTIFY_PORT", "5002"))
DUE_SOON_HOURS = int(os.environ.get("NOTIFY_DUE_SOON_HOURS", "24"))

# Falls back to placeholder paths if .env is missing, so the app still
# starts (just won't find real data_ instead of crashing on import.
ASSIGNMENTS_FILE = os.environ.get(
    "NOTIFY_ASSIGNMENTS_FILE", "/path/to/College-Dashboard/assignments.json"
)
TICKETS_FILE = os.environ.get(
    "NOTIFY_TICKETS_FILE", "/path/to/ticket_hub/tickets_database.json"
)
PHOTOS_FILE = os.environ.get(
    "NOTIFY_PHOTOS_FILE", "/path/to/Photo-DropOff/photos.json"
)

app = Flask(__name__)


# =========================================================================
# DATA LOADING HELPERS
# =========================================================================

def load_json(path, default):
    """
    -> dict OR list
    Reads a JSON file off disk. Returns 'default' if the file doesn't
    exist yet (e.g. no tickets filed yet) or can't be parsed -- never
    crashes the page over a missing/malformed source file.
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


# =========================================================================
# NOTIFICATION BUILDERS
# =========================================================================

def get_assignment_notifications() -> list:
    """
    -> list of dicts
    One notification per assignment due within NOTIFY_DUE_SOON_HOURS
    ( and not already overdue-and-ignored -- overdue ones still show,
    flagged as overdue, since those need attention most of all).
    """
    assignments = load_json(ASSIGNMENTS_FILE, [])
    notifications = []
    now = datetime.now()

    for a in assignments:
        try:
            due_dt = datetime.fromisoformat(a["due_date"])
        except Exception:
            continue

        is_overdue = due_dt < now
        is_due_soon = (not is_overdue) and (due_dt - now <= timedelta(hours=DUE_SOON_HOURS))

        if is_overdue or is_due_soon:
            notifications.append({
                "type": "assignment",
                "urgent": is_overdue,
                "title": a.get("name", "Untitled assignment"),
                "detail": f"{'Overdue' if is_overdue else 'Due soon'}"
                          f"{' . ' + a['class_name'] if a.get('class_name') else ''}",
                "timestamp": due_dt,
                "link_label": "Open dashboard",
            })

    return notifications


def get_ticket_notifications() -> list:
    """
    -> list of dicts
    One notification per ticket that isn't Resolved yet -- Open and In
    Progress tickets both count as needing attention, High priority
    ones flagged as urgent.
    """
    tickets = load_json(TICKETS_FILE, {})
    notifications = []

    for t in tickets.values():
        if t.get("status") == "Resolved":
            continue
        try:
            created_dt = datetime.strptime(t["created_at"], "%Y-%m-%d %H:%M")
        except Exception:
            created_dt = datetime.now()

        notifications.append({
            "type": "ticket",
            "urgent": t.get("priority") == "High",
            "title": f"#{t['id']} - {t.get('customer_name', 'Unknown')}",
            "detail": f"{t.get('priority', 'Medium')} priority . {t.get('status', 'Open')}",
            "timestamp": created_dt,
            "link_label": "Open ticket hub",
        })

    return notifications


def get_photo_notifications(recent_hours=48) -> list:
    """
    -> list of dicts
    One notification per photo/video uploaded within the last
    'recent_hours' -- older uploads don't need a fresh notification
    everytime you load this page.
    """
    photos = load_json(PHOTOS_FILE, [])
    notifications = []
    now = datetime.now()

    for p in photos:
        try:
            uploaded_dt = datetime.fromisoformat(p["uploaded_at"])
        except Exception:
            continue

        if now - uploaded_dt <= timedelta(hours=recent_hours):
            uploader = p.get("uploader") or "Someone"
            notifications.append({
                "type": "photo",
                "urgent": False,
                "title": f"{uploader} uploaded {p.get('original_name', 'a file')}",
                "detail": "New upload",
                "timestamp": uploaded_dt,
                "link_label": "Open photo drop",
            })

    return notifications


# =========================================================================
# ROUTES
# =========================================================================

@app.route("/")
def feed():
    """
    -> str (HTML)
    Combines all three notification sources into one list, sorted
    newest/most-urgent first. Runs fresh on every page load -- nothing
    cached or stored by this app itself.
    """
    all_notifications = (
        get_assignment_notifications()
        + get_ticket_notifications()
        + get_photo_notifications()
    )

    # Urgent items first, then newest within each group
    all_notifications.sort(key=lambda n: (not n["Urgent"], -n["timestamp"].timestamp()))

    counts = {
        "assignment": sum(1 for n in all_notifications if n["type"] == "assignment"),
        "ticket": sum(1 for n in all_notifications if n["type"] == "ticket"),
        "photo": sum(1 for n in all_notifications if n["type"] == "photo"),
    }

    return render_template("feed.html", notifications=all_notifications, counts=counts)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)