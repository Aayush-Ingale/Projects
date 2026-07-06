# Notification Hub

One feed pulling together everything that needs your attention across your
home server: assignments due soon, open support tickets, and recently
uploaded photos. Reads directly from the same JSON files your other apps
already write to — no duplicated data, no syncing needed.

Runs on **port 5007**.

## What it shows

- **Assignments** — overdue or due within `NOTIFY_DUE_SOON_HOURS` (default 24h)
- **Tickets** — anything not marked Resolved; High priority tickets are flagged urgent
- **Photos** — anything uploaded in the last 48 hours

Everything is sorted urgent-first, then newest-first. The page auto-refreshes
every 60 seconds.

## Setup

```bash
cd notification_hub
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Set the real paths to your other projects' data files** before running —
these are almost certainly different from the placeholders in the code:

```bash
export NOTIFY_ASSIGNMENTS_FILE="/path/to/College-Dashboard/assignments.json"
export NOTIFY_TICKETS_FILE="/path/to/ticket_hub/tickets_database.json"
export NOTIFY_PHOTOS_FILE="/path/to/Photo-DropOff/photos.json"
python3 Unified-Notification-Hub.py
```

Visit `http://<server-ip>:5007`.

## Configuration

All environment variables are optional:

| Variable | Default | Purpose |
|---|---|---|
| `NOTIFY_ASSIGNMENTS_FILE` | `/root/Projects/College-Dashboard/assignments.json` | Path to dorm-dashboard's data file |
| `NOTIFY_TICKETS_FILE` | `/root/Projects/ticket_hub/tickets_database.json` | Path to ticket-hub's data file |
| `NOTIFY_PHOTOS_FILE` | `/root/Projects/Photo-DropOff/photos.json` | Path to photo-drop's data file |
| `NOTIFY_DUE_SOON_HOURS` | `24` | Hours-out threshold for "due soon" |
| `NOTIFY_PORT` | `5007` | Port to serve on |

## systemd service

```ini
[Unit]
Description=Notification Hub
After=network.target

[Service]
WorkingDirectory=/root/Projects/notification_hub
Environment=NOTIFY_ASSIGNMENTS_FILE=/root/Projects/College-Dashboard/assignments.json
Environment=NOTIFY_TICKETS_FILE=/root/Projects/ticket_hub/tickets_database.json
Environment=NOTIFY_PHOTOS_FILE=/root/Projects/Photo-DropOff/photos.json
ExecStart=/root/Projects/notification_hub/venv/bin/python3 app.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now notification-hub
sudo systemctl status notification-hub
```

## Exposing it over Tailscale

```bash
sudo tailscale serve --bg --https=8447 http://127.0.0.1:5007
```

Then reach it from anywhere on your tailnet at:

```
https://<server-tailscale-name>:8447/
```

Find `<server-tailscale-name>` by running `tailscale status` on the server.

## Notes

- This app is **read-only** — it never writes to any of the source JSON files,
  so there's no risk of it corrupting data owned by your other apps.
- If a source file is missing or malformed, that section just shows nothing
  rather than crashing the whole page.
- No authentication — keep this behind Tailscale, not exposed to the public
  internet.
