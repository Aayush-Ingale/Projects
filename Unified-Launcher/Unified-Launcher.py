"""
Service Launcher

One page to start, stop, or restart every app on Capriccio, and jump
straight to each one's page once it's running. Wraps `systemctl` --
doesn't duplicate any of the health-check logic the status page already
does, just gives you the controls the status page doesn't (start/stop),
plus one-click links to actually open each app.

Password-protected: unlike the other apps in this repo, this one can
stop and restart services, not just display data, so it requires a
login before showing anything or acting on any button. Same pattern as
Ticket Hub's /admin.

Run:
    pip install -r requirements.txt
    python3 Unified-Launcher.py

Then visit http://<server-ip>:5005

NOTE: starting/stopping/restarting systemd units requires root. Run this
under the same user as your other services (root, matching your existing
systemd units) or every action below will silently fail with a
permissions error instead of doing anything.

Configuration (environment variables, all optional):
    LAUNCHER_PORT             port to serve on (default: 5005)
    LAUNCHER_TAILSCALE_HOST   your tailnet hostname, used to build the
                              "Open" links below (falls back to a
                              placeholder if unset -- links will be
                              broken but the app still starts)
    LAUNCHER_PASSWORD         password required to log in (default:
                              admin123 -- CHANGE THIS before exposing
                              this app over Tailscale)
    LAUNCHER_SECRET_KEY       Flask session secret (default: a random
                              key generated on each restart, which logs
                              everyone out on restart -- set a fixed one
                              for persistent sessions)
"""

import os
import subprocess
from functools import wraps

from flask import Flask, render_template, redirect, url_for, flash, request, session

PORT = int(os.environ.get("LAUNCHER_PORT", "5005"))
TAILSCALE_HOST = os.environ.get("LAUNCHER_TAILSCALE_HOST", "your-server.your-tailnet.ts.net")
LAUNCHER_PASSWORD = os.environ.get("LAUNCHER_PASSWORD", "admin123")

app = Flask(__name__)
app.secret_key = os.environ.get("LAUNCHER_SECRET_KEY", os.urandom(24))

# Edit this list to match your actual systemd unit names and ports.
# "systemd" must match exactly what you'd type after `systemctl status`.
# "public_url" is the Tailscale HTTPS address you'd actually open in a
# browser -- separate from the internal port, same pattern as the
# status page.
SERVICES = [
    {"name": "College Dashboard", "systemd": "dorm-dashboard", "public_url": f"https://{TAILSCALE_HOST}:8443/"},
    {"name": "Ticket Hub", "systemd": "ticket-hub", "public_url": f"https://{TAILSCALE_HOST}:8444/"},
    {"name": "Photo Drop", "systemd": "photo-drop", "public_url": f"https://{TAILSCALE_HOST}:8445/"},
    {"name": "Status Page", "systemd": "status-page", "public_url": f"https://{TAILSCALE_HOST}:8446/"},
    {"name": "Notification Hub", "systemd": "notification-hub", "public_url": f"https://{TAILSCALE_HOST}:8447/"},
]

VALID_ACTIONS = {"start", "stop", "restart"}


# =========================================================================
# AUTH
# =========================================================================
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == LAUNCHER_PASSWORD:
            session["is_logged_in"] = True
            return redirect(url_for("dashboard"))
        flash("Incorrect password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("is_logged_in", None)
    return redirect(url_for("login"))


# =========================================================================
# SYSTEMD HELPERS
# =========================================================================

def check_status(unit_name) -> str:
    """-> str. 'active', 'inactive', 'failed', or 'unknown'."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit_name],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def run_action(unit_name, action) -> tuple:
    """
    -> (bool, str)
    Runs `systemctl <action> <unit_name>`. Returns (success, message).
    Never raises -- a failure just gets flashed to the page instead of
    crashing the launcher itself.
    """
    if action not in VALID_ACTIONS:
        return False, f"'{action}' isn't a valid action."
    try:
        result = subprocess.run(
            ["systemctl", action, unit_name],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return True, f"{unit_name}: {action} succeeded."
        return False, f"{unit_name}: {action} failed -- {result.stderr.strip() or 'no error output'}"
    except Exception as e:
        return False, f"{unit_name}: {action} failed -- {e}"


# =========================================================================
# ROUTES
# =========================================================================

@app.route("/")
@login_required
def dashboard():
    services = []
    for svc in SERVICES:
        services.append({
            **svc,
            "status": check_status(svc["systemd"]),
        })
    return render_template("dashboard.html", services=services)


@app.route("/service/<systemd_name>/<action>", methods=["POST"])
@login_required
def service_action(systemd_name, action):
    # Only allow actions on units we actually know about -- this
    # endpoint takes systemd_name straight from a URL, and without
    # this check it'd happily run `systemctl stop <anything>` on any
    # unit name typed into the address bar.
    known_units = {svc["systemd"] for svc in SERVICES}
    if systemd_name not in known_units:
        flash(f"Unknown service '{systemd_name}'.", "error")
        return redirect(url_for("dashboard"))

    success, message = run_action(systemd_name, action)
    flash(message, "success" if success else "error")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
