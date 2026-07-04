# Projects

Code and projects I've built for my home server. Everything follows the
same basic pattern: Python + Flask, JSON files for storage, run as a
systemd service, reached remotely over Tailscale instead of exposing
anything to the public internet.

## What's in here

| Project | What it does | Default port |
|---|---|---|
| [`College-Dashboard/`](./College-Dashboard) | Weather, class schedule, to-dos, assignments (with grade/weight tracking, file attachments, subtasks, due-soon alerts, and an archive) | 5001 |
| [`ticket_hub/`](./ticket_hub) | Self-hosted help desk — anyone can file a support ticket, admin dashboard to triage/resolve them, plus a dedicated resolved-tickets view | 5000 |
| [`photo_upload/`](./photo_upload) | Photo/video upload spot for iPhones — upload via Safari's native Photos picker, or straight from the Photos app's Share Sheet using an iOS Shortcut | 5003 |

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

Each keeps its data in flat JSON files sitting next to `app.py` (e.g.
`assignments.json`, `tickets_database.json`, `photos.json`) — no database
server to install or maintain. Simple, but back these up manually since
nothing does it automatically yet.

## Running everything at once

Since each app defaults to a different port, they can all run
simultaneously on the same Debian server without conflicting:

- `http://<server>:5000` — ticket hub
- `http://<server>:5001` — dorm dashboard
- `http://<server>:5003` — photo drop

Each one should be set up as its own systemd service so it survives
reboots and crashes — see the individual project READMEs for the exact
service file to use.

## Accessing it all remotely — Tailscale

None of these apps have real authentication (aside from ticket hub's
admin password) — they're designed to be reached over a private
Tailscale network, not the open internet.

Quick setup on the Debian server:
```bash
sudo apt update
sudo apt install curl -y
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```
Then install Tailscale on your phone/laptop and log into the same
account. From there, every app above is reachable from anywhere using:
```
http://<server-tailscale-name>:<port>
```
Find `<server-tailscale-name>` by running `tailscale status` on the
server — it's the hostname listed next to your server's `100.x.x.x` IP.

**Don't port-forward these to the public internet** — none of them are
hardened for that, and a couple (dashboard, photo drop) have no login at
all.

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
├── photo_upload/
│   ├── app.py
│   ├── templates/
│   ├── static/
│   ├── requirements.txt
│   └── README.md
└── README.md   ← you are here
```
