# Support Ticket Hub (Web Edition)

A small self-hosted help desk. Anyone on your network opens the site and
files a ticket. You log into `/admin` — from anywhere — to triage and
resolve them.

## 1. Run it on your home server

```bash
pip install -r requirements.txt
python3 app.py
```

By default it listens on port 5000 and is reachable from any device on
your home network at:

- `http://<server-ip>:5000/` — the ticket submission form
- `http://<server-ip>:5000/admin` — the admin dashboard

Find `<server-ip>` with `ip addr` (Linux) or `hostname -I`.

**Before you go live, set a real admin password** — the default is
`admin123`:

```bash
export TICKET_ADMIN_PASSWORD="something-only-you-know"
export TICKET_SECRET_KEY="a-long-random-string"   # keeps you logged in across restarts
python3 app.py
```

Put those two lines in a `.env`-style startup script, or in the systemd
unit below, so you don't have to retype them.

## 2. Keep it running

The simplest way is a systemd service so it survives reboots and crashes.
Create `/etc/systemd/system/ticket-hub.service`:

```ini
[Unit]
Description=Support Ticket Hub
After=network.target

[Service]
WorkingDirectory=/path/to/ticket_hub
Environment=TICKET_ADMIN_PASSWORD=something-only-you-know
Environment=TICKET_SECRET_KEY=a-long-random-string
ExecStart=/usr/bin/python3 app.py
Restart=always
User=youruser

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl enable --now ticket-hub
```

## 3. Reaching it from college (the important part)

`app.run(host="0.0.0.0")` only makes it reachable on your **local**
network. To resolve tickets while you're away, you need a way in from
outside. Two realistic options, easiest first:

**Option A — Tailscale (recommended).** Install Tailscale on the home
server and on your laptop/phone at college, sign into the same account on
both. You get a private, encrypted address for your server
(`http://home-server:5000`) that works from anywhere, with no ports opened
to the public internet and no extra HTTPS setup needed. This is the
option most people in your situation should use.

**Option B — Port forward + reverse proxy.** Forward a port on your
router to the server, and put Nginx or Caddy in front of Flask with a
free HTTPS certificate (e.g. via Let's Encrypt or Caddy's automatic TLS).
This exposes the ticket form to the whole internet, so it needs a real
password (see above) and ideally a firewall/fail2ban in front of it.
Only do this if Tailscale isn't an option for you.

Avoid exposing port 5000 directly to the internet without TLS — the
admin password would travel in plain text.

## Files

```
app.py                    Flask application and routes
templates/                HTML pages (Jinja2)
static/style.css          Styling
requirements.txt          Python dependencies
tickets_database.json     Created automatically on first ticket (JSON storage, same as before)
```
