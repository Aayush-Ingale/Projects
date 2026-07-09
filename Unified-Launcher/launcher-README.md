# Service Launcher

One page to start, stop, or restart every app on Capriccio, and jump
straight to each one once it's running. Wraps `systemctl` — doesn't
duplicate any of the health-check logic the status page already does,
just adds the controls the status page doesn't have (start/stop), plus
one-click links into each app.

## What it does

- Shows each service's current state (active/inactive) via `systemctl is-active`
- Start / Restart / Stop buttons per service, calling `systemctl` directly
- "Open" link to each app's real Tailscale HTTPS address
- Auto-refreshes every 15 seconds so the status stays current without reloading

## 1. Run it on your Debian server

```bash
cd Launcher
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Set your Tailscale hostname** so the "Open" links point somewhere real:

```bash
export LAUNCHER_TAILSCALE_HOST="your-server.your-tailnet.ts.net"
python3 app.py
```

By default it serves on port **5005**. Visit:
```
http://<server-ip>:5005
```

## 2. Permissions note (important)

Starting, stopping, and restarting systemd units all require root.
Run this the same way as your other services — as `root`, matching your
existing systemd units — or every button will silently fail with a
permissions error instead of actually doing anything.

## 3. Before you rely on this, check the service names

Open `app.py` and look at the `SERVICES` list near the top. The
`systemd` value for each entry must match your actual unit name exactly
— the same string you'd type after `systemctl status`. Verify with:

```bash
systemctl list-units --type=service --all | grep -iE "dashboard|ticket|photo|status|notif"
```

If any name doesn't match what's actually installed, edit the list:

```python
SERVICES = [
    {"name": "College Dashboard", "systemd": "dorm-dashboard", "public_url": f"https://{TAILSCALE_HOST}:8443/"},
    {"name": "Ticket Hub", "systemd": "ticket-hub", "public_url": f"https://{TAILSCALE_HOST}:8444/"},
    {"name": "Photo Drop", "systemd": "photo-drop", "public_url": f"https://{TAILSCALE_HOST}:8445/"},
    {"name": "Status Page", "systemd": "status-page", "public_url": f"https://{TAILSCALE_HOST}:8446/"},
    {"name": "Notification Hub", "systemd": "notification-hub", "public_url": f"https://{TAILSCALE_HOST}:8447/"},
]
```

Don't add this launcher's own systemd unit to that list if you ever
create one — hitting "Stop" on itself will kill the process serving the
button you just clicked.

## 4. Run it permanently with systemd

```bash
sudo nano /etc/systemd/system/launcher.service
```
```ini
[Unit]
Description=Service Launcher
After=network.target

[Service]
WorkingDirectory=/root/Projects/Launcher
Environment=LAUNCHER_TAILSCALE_HOST=your-server.your-tailnet.ts.net
ExecStart=/root/Projects/Launcher/venv/bin/python3 app.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now launcher
```

## 5. On exposing this over Tailscale — read before you do it

Your other apps follow a "no login, Tailscale is the security boundary"
model, which is reasonable for read-only or personal-convenience tools
(a photo gallery, a status page). This app is different: it can **stop
and restart services**, not just read data. Anyone who can reach it can
take down your whole stack with a single request.

Recommended for now: **don't** run `tailscale serve` on this one. Reach
it only via SSH tunnel or your server's private Tailscale IP directly,
not a public HTTPS port:

```bash
ssh -L 5005:127.0.0.1:5005 aayush-personal@100.79.31.19
```
then visit `http://127.0.0.1:5005` on your own machine.

If you later want it reachable the same way as your other apps, add a
login screen first (see Ticket Hub's `/admin` for the pattern already in
this repo) before exposing it through `tailscale serve`.

## Files

```
app.py                  Flask app: systemctl status checks + start/stop/restart
templates/               HTML pages
static/style.css         Styling
requirements.txt         Python dependencies
```
