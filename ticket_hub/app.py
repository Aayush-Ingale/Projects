"""
Support Ticket Hub - Web Edition

A small self-hosted ticket desk. Anyone on the network can open the site
and file a ticket. You log into /admin from anywhere (including over a
VPN like Tailscale while you're away) to triage and resolve them.

Run:
    pip install -r requirements.txt
    python app.py

Then visit http://<server-ip>:5000  (submit form)
       and http://<server-ip>:5000/admin  (admin dashboard)

Configuration (environment variables, all optional):
    TICKET_ADMIN_PASSWORD   password for the admin dashboard (default: admin123 - CHANGE THIS)
    TICKET_SECRET_KEY       Flask session secret (default: a random key generated on each restart,
                             which logs everyone out on restart - set a fixed one for persistent sessions)
    TICKET_DB_FILE          path to the JSON database file (default: tickets_database.json)
"""

import datetime
import json
import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
import uuid
from werkzeug.utils import secure_filename
from flask import send_from_directory

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.environ.get("TICKET_DB_FILE", os.path.join(APP_DIR, "tickets_database.json"))
ADMIN_PASSWORD = os.environ.get("TICKET_ADMIN_PASSWORD", "admin123")
PRIORITY_WEIGHTS = {"High": 1, "Medium": 2, "Low": 3}

app = Flask(__name__)
app.secret_key = os.environ.get("TICKET_SECRET_KEY", os.urandom(24))

UPLOAD_FOLDER = os.path.join(APP_DIR, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB max upload


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# =========================================================================
# STORAGE
# =========================================================================
def load_tickets() -> dict:
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_tickets(tickets: dict) -> None:
    with open(DB_FILE, "w") as f:
        json.dump(tickets, f, indent=4)


def next_ticket_id(tickets: dict) -> int:
    if not tickets:
        return 1001
    return max(int(k) for k in tickets.keys()) + 1


# =========================================================================
# AUTH
# =========================================================================
def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


# =========================================================================
# CUSTOMER-FACING ROUTES
# =========================================================================
@app.route("/", methods=["GET", "POST"])
def submit_ticket():
    if request.method == "POST":
        name = request.form.get("customer_name", "").strip()
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", "Medium")
        if priority not in PRIORITY_WEIGHTS:
            priority = "Medium"

        if not name or not description:
            flash("Please fill in your name and a description of the issue.", "error")
            return render_template("submit.html", name=name, description=description, priority=priority)

        attachment_filename = ""
        file = request.files.get("attachment")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Attachments must be an image (png, jpg, jpeg, gif, or webp).", "error")
                return render_template("submit.html", name=name, description=description, priority=priority)
            safe_name = secure_filename(file.filename)
            attachment_filename = f"{uuid.uuid4().hex}_{safe_name}"
            file.save(os.path.join(UPLOAD_FOLDER, attachment_filename))

        tickets = load_tickets()
        ticket_id = next_ticket_id(tickets)
        tickets[str(ticket_id)] = {
            "id": ticket_id,
            "customer_name": name,
            "description": description,
            "priority": priority,
            "status": "Open",
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "resolution_notes": "",
            "attachment": attachment_filename,
        }
        save_tickets(tickets)
        return render_template("submit.html", success_id=ticket_id, had_attachment=bool(attachment_filename))

    return render_template("submit.html")

@app.route("/status", methods=["GET", "POST"])
def check_status():
    ticket = None
    error = None

    if request.method == "POST":
        ticket_id = request.form.get("ticket_id", "").strip()
        name = request.form.get("customer_name", "").strip()

        tickets = load_tickets()
        found = tickets.get(ticket_id)

        if found and found["customer_name"].strip().lower() == name.lower():
            ticket = found
        else:
            error = "No matching ticket found. Double check your ticket number and the name you used."

    return render_template("status.html", ticket=ticket, error=error)

# =========================================================================
# ADMIN ROUTES
# =========================================================================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    tickets = load_tickets()
    sort_priority = request.args.get("sort", "1") == "1"

    items = list(tickets.values())
    if sort_priority:
        active = [t for t in items if t["status"] != "Resolved"]
        active.sort(key=lambda t: PRIORITY_WEIGHTS.get(t["priority"], 2))
        resolved = [t for t in items if t["status"] == "Resolved"]
        items = active + resolved
    else:
        items.sort(key=lambda t: t["id"], reverse=True)

    total = len(tickets)
    closed = sum(1 for t in tickets.values() if t["status"] == "Resolved")
    rate = round((closed / total) * 100, 1) if total else 0.0

    return render_template(
        "admin_dashboard.html",
        tickets=items,
        total=total,
        rate=rate,
        sort_priority=sort_priority,
    )


@app.route("/admin/ticket/<int:ticket_id>/update", methods=["POST"])
@admin_required
def update_ticket(ticket_id):
    tickets = load_tickets()
    key = str(ticket_id)
    if key in tickets:
        tickets[key]["status"] = request.form.get("status", tickets[key]["status"])
        tickets[key]["resolution_notes"] = request.form.get("resolution_notes", "").strip()
        save_tickets(tickets)
        flash(f"Ticket #{ticket_id} updated.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/uploads/<path:filename>")
@admin_required
def view_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == "__main__":
    # host="0.0.0.0" makes it reachable from other devices on your network,
    # not just from the server itself.
    app.run(host="0.0.0.0", port=5000, debug=False)
