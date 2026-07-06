# Projects

Code and projects I've built for my home server. Everything follows the
same basic pattern: Python + Flask, JSON files for storage, run as a
systemd service, reached remotely over Tailscale instead of exposing
anything to the public internet.

## What's in here

| Project | What it does | Flask port |
|---|---|---|
| [`College-Dashboard/`](./College-Dashboard) | Weather, class schedule, to-dos, assignments (with grade/weight tracking, file attachments, subtasks, due-soon alerts, and an archive) | 5001 |
| [`ticket_hub/`](./ticket_hub) | Self-hosted help desk — anyone can file a support ticket, admin dashboard to triage/resolve them, plus a dedicated resolved-tickets view | 5000 |
| [`Photo-DropOff/`](./Photo-DropOff) | Photo/video upload spot for iPhones — upload via Safari's native Photos picker, or straight from the Photos app's Share Sheet using an iOS Shortcut | 5003 |
| [`Unified-Status-Page/`](./Unified-Status-Page) | One page showing whether everything's actually healthy — HTTP + systemd status for each app, ZFS pool health, disk usage, uptime | 5002 |
| [`notification_hub/`](./notification_hub) | Aggregates due-soon assignments, open tickets, and recent photo uploads into a single feed | 5007 |
| [`wiki/`](./wiki) | Self-hosted markdown wiki for documenting the server itself — pages are plain `.md` files on disk | 5008 |
| [`key_expiry_watcher/`](./key_expiry_watcher) | Shows how many days until each Tailscale device's key expires, so nothing silently loses access | 5009 |

Each project has its own `README.md` with full setup steps — this file is
just the overview and the shared conventions across all of them.

## Shared setup pattern

Every project here is a standalone Flask app you run the same way:

```bash
cd <project-folder>
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Most keep their data in flat JSON files sitting next to `app.py` (e.g.
`assignments.json`, `tickets_database.json`, `photos.json`) — no database
server to install or maintain. Simple, but back these up manually since
nothing does it automatically yet. The wiki is the exception — its data
is plain `.md` files in a `pages/` folder, which is arguably even easier
to back up.

## Running everything at once

Since each app defaults to a different port, all seven can run
simultaneously on the same Debian server without conflicting. Each one
is set up as its own systemd service so it survives reboots and crashes —
see the individual project READMEs for the exact service file to use.

## Accessing it all remotely — Tailscale + HTTPS

None of these apps have real authentication (aside from ticket hub's
admin password) — they're designed to be reached over a private
Tailscale network, not the open internet.

### One-time Tailscale setup on the server
```bash
sudo apt update
sudo apt install curl -y
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```
Then install Tailscale on every phone/laptop you want access from, and
log into the **same account** on each. Enable HTTPS certificates for the
tailnet once, in the admin console:
```
https://login.tailscale.com/admin/dns
```
(under "HTTPS Certificates" → Enable)

### Real HTTPS access via Tailscale Serve
Each Flask app is mapped to its own HTTPS port using `tailscale serve`,
so pages render fully styled (avoids a subpath/static-file bug we hit
early on) and get a real, browser-trusted padlock — no certificate
warnings:

```bash
sudo tailscale serve --bg --https=8443 http://127.0.0.1:5001   # dashboard
sudo tailscale serve --bg --https=8444 http://127.0.0.1:5000   # ticket hub
sudo tailscale serve --bg --https=8445 http://127.0.0.1:5003   # photo drop
sudo tailscale serve --bg --https=8446 http://127.0.0.1:5002   # status page
sudo tailscale serve --bg --https=8447 http://127.0.0.1:5007   # notification hub
sudo tailscale serve --bg --https=8448 http://127.0.0.1:5008   # wiki
sudo tailscale serve --bg --https=8449 http://127.0.0.1:5009   # key expiry watcher
```

Check current mappings any time with:
```bash
sudo tailscale serve status
```

### URLs (from any device logged into the same tailnet)
```
https://<server-tailscale-name>:8443/   → dashboard
https://<server-tailscale-name>:8444/   → ticket hub
https://<server-tailscale-name>:8444/admin   → ticket hub admin
https://<server-tailscale-name>:8445/   → photo drop
https://<server-tailscale-name>:8446/   → status page
https://<server-tailscale-name>:8447/   → notification hub
https://<server-tailscale-name>:8448/   → wiki
https://<server-tailscale-name>:8449/   → key expiry watcher
```
Find `<server-tailscale-name>` by running `tailscale status` on the
server, or checking the machine's detail page in the Tailscale admin
console (its full form looks like `capriccio.tailXXXXX.ts.net`).

**Don't port-forward these to the public internet** — none of them are
hardened for that, and most have no login at all.

## Repo structure

```
Projects/
├── College-Dashboard/
│   ├── app.py
│   ├── templates/
│   ├── static/
│   ├── requirements.txt
│   └── README.md
├── ticket_hub/
│   ├── app.py
│   ├── templates/
│   ├── static/
│   ├── requirements.txt
│   └── README.md
├── Photo-DropOff/
│   ├── app.py
│   ├── templates/
│   ├── static/
│   ├── requirements.txt
│   └── README.md
├── Unified-Status-Page/
│   ├── app.py
│   ├── templates/
│   ├── static/
│   ├── requirements.txt
│   └── README.md
├── notification_hub/
│   ├── app.py
│   ├── templates/
│   ├── static/
│   └── requirements.txt
├── wiki/
│   ├── app.py
│   ├── templates/
│   ├── static/
│   ├── pages/
│   └── requirements.txt
├── key_expiry_watcher/
│   ├── app.py
│   ├── templates/
│   ├── static/
│   └── requirements.txt
└── README.md   ← you are here
```
