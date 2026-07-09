"""
Server Status - Unified Health Dashboard

One page showing whether everything on your home server is actually
healthy: each Flask app's HTTP status + response time, its systemd
service state, your ZFS pool health, disk usage, and how long the
server's been up. No stored data, no database -- every check runs live
each time you load the page.

Run:
    pip install -r requirements.txt
    python3 Unified-Status-Page.py

Then visit http://<server-ip>:5002

Configuration (environment variables, all optional):
    STATUS_PAGE_PORT   port to serve on (default: 5002)

NOTE: checking systemd service status and zpool health both typically
require root privileges on Debian. Run this under the same user as your
other services (root, based on your existing systemd units) or the
checks below will silently show as "unknown" instead of their real state.
"""

import os
import shutil
import subprocess
import time

import requests
from flask import Flask, render_template

PORT = int(os.environ.get("STATUS_PAGE_PORT", "5002"))

app = Flask(__name__)

# Each service you want monitored: its display name, systemd unit name
# (exactly as used in 'systemctl status <name>'), and the local URL to
# HTTP-check. All checks hit 127.0.0.1 directly since this page runs on
# the same server as everything else -- no need to go through
# Tailscale for these internal checks
#
# "public_url" is separate -- that's the link shown to YOU to click
# through and actually open the app, so it uses your real Tailscale
# HTTPS address instead of localhost. "extra_link" adds any additional
# pages worth linking directly, like Ticket Hub's admin dashboard.
#
# TAILSCALE_HOST comes from an environment variable so this repo works
# for anyone who clones it -- just set you own tailnet hostname before
# running, instead of editing this file. Falls back to a placeholder so
# the app still starts (with broken links) if you forget to set it.
TAILSCALE_HOST = os.environ.get("STATUS_PAGE_TAILSCALE_HOST", "your-server.your-tailnet.ts.net")

SERVICES = [
    {
        "name": "College Dashboard",
        "systemd": "College-Dashboard",
        "url": "http://127.0.0.1:5001/",
        "public_url": f"https://{TAILSCALE_HOST}:8444/",
        "extra links": [],
    },
    {
        "name": "Ticket Hub",
        "systemd": "ticket-hub",
        "url": "http://127.0.0.1:5000/",
        "public_url": f"https://{TAILSCALE_HOST}:8444/",
        "extra_links": [
            {"label": "Admin dashboard", "url": f"https://{TAILSCALE_HOST}:8444/admin"},
            {"label": "Resolved tickets", "url": f"https://{TAILSCALE_HOST}:8444/admin/resolved"},
        ],
    },
    {
        "name": "Photo-DropOff",
        "systemd": "Photo-DropOff.service",
        "url": "http://127.0.0.1:5003/",
        "public_url": f"https://{TAILSCALE_HOST}:8445/",
        "extra_links": [],
    },
    {
        "name": "Notification Hub",
        "systemd": "notification-hub",
        "url": "http://127.0.0.1:5004/",
        "public_url": f"https://{TAILSCALE_HOST}:8447/",
        "extra_links": [],
    },
]

# Paths to report disk usage for. "/" covers your root filesystem;
# add your ZFS mountpoint too since that's likely a separate volume.
DISK_PATHS = ["/", "/storagepool"]


# =========================================================================
# HEALTH CHECK HELPERS
# =========================================================================

def check_systemd(unit_name) -> str:
    """
    -> str
    Returns "active", "inactive", "failed", or "unknown" for a given
    systemd unit, using 'systemctl is-active'.
    """
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit_name],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def check_http(url) -> dict:
    """
    -> dict
    Hits a URL and reports whether it responded, its status code, amd
    how long it took in milliseconds. Never raises -- a connection
    failure just shows up as ok=False instead of crashing the page.
    """
    start = time.time()
    try:
        resp = requests.get(url, timeout=5)
        latency_ms = round((time.time() - start) * 1000)
        return {"ok": resp.status_code < 500, "status_code": resp.status_code, "latency_ms": latency_ms}
    except Exception as e:
        return {"ok": False, "status_code": None, "latency_ms": None, "error": str(e)}

def check_zpools() -> list:
    """
    -> list
    Returns one dict per ZFS pool with its name, size, allocated space,
    free space, and health status (ONLINE/DEGRADED/FAULTED/ETC.). Empty
    list if ZFS isn't installed or no pools exist -- not an error.
    """
    try:
        result = subprocess.run(
            ["zpool", "list", "-H", "-o", "name,size,alooc,free,health"],
            capture_output=True, text=True, timeout=5,
        )
        pools = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) == 5:
                pools.append({
                    "name": parts[0], "size": parts[1], "alloc": parts[2],
                    "free": parts[3], "health": parts[4],
                })
        return pools
    except Exception:
        return []
def check_zpools() -> list:
    env = os.environ.copy()
    env["PATH"] = env.get("PATH", "") + os.pathsep + "/sbin" + os.pathsep + "/usr/sbin"
    try:
        result = subprocess.run(
            ["zpool", "list", "-H", "-o", "name,size,alloc,free,health"],
            capture_output=True, text=True, timeout=5, env=env,
        )
        pools = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) == 5:
                pools.append({
                    "name": parts[0], "size": parts[1], "alloc": parts[2],
                    "free": parts[3], "health": parts[4],
                })
        return pools
    except Exception:
        return []

def check_disk_usage(path) -> dict:
    """
    -> dict OR None
    Reports total/used/free space (in GB) and percent used for a given
    path. Returns None if the path doesn't exist on this server, so the
    template can skip it cleanly instead of showing a broken row.
    """
    if not os.path.exists(path):
        return None
    try:
        total, used, free = shutil.disk_usage(path)
        return {
            "path": path,
            "total_gb": round(total / (1024 ** 3), 1),
            "used_gb": round(used / (1024 ** 3), 1),
            "free_gb": round(free / (1024 ** 3), 1),
            "percent_used": round(used / total * 100, 1) if total else 0,
        }
    except Exception:
        return None


def get_uptime() -> str:
    """-> str. Human-readable server uptime, e.g. "3d $h 12m"."""
    try:
        with open("/proc/uptime") as f:
            seconds = float(f.readline().split()[0])
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    except Exception:
        return "unknown"


# =========================================================================
# ROUTES
# =========================================================================

@app.route("/")
def satus():
    """
    -> str (HTML)
    Runs every health check fresh on each page load and renders them.
    Nothing here is cached or stored -- refreshing the page re-checks
    everything from scratch.
    """
    services = []
    for svc in SERVICES:
        http_result = check_http(svc["url"])
        systemd_state = check_systemd(svc["systemd"])
        services.append({
            "name": svc["name"],
            "http": http_result,
            "systemd_state": systemd_state,
            "public_url": svc.get("public_url", "#"),
            "extra_links": svc.get("extra_links", []),
            # "healthy" requires BOTH the HTTP check succeeding AND
            # systemd reporting active -- either one failing flags it.
            "healthy": http_result["ok"] and systemd_state == "active",
        })

    zpools = check_zpools()
    disks = [d for d in (check_disk_usage(p) for p in DISK_PATHS) if d is not None]
    uptime = get_uptime()

    return render_template(
        "status.html",
        services=services,
        zpools=zpools,
        disks=disks,
        uptime=uptime,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
