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

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.environ.get("TICKET_DB_FILE", os.path.join(APP_DIR, "tickets_database.json"))
ADMIN_PASSWORD = os.environ.get("TICKET_ADMIN_PASSWORD", "admin123")
PRIORITY_WEIGHTS = {"High": 1, "Medium": 2, "Low": 3}

app = Flask(__name__)
app.secret_key = os.environ.get("TICKET_SECRET_KEY", os.urandom(24))


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
        }
        save_tickets(tickets)
        return render_template("submit.html", success_id=ticket_id)

    return render_template("submit.html")


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


if __name__ == "__main__":
    # host="0.0.0.0" makes it reachable from other devices on your network,
    # not just from the server itself.
    app.run(host="0.0.0.0", port=5000, debug=False)
