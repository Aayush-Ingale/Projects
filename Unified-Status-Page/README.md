# Server Status

One page showing whether everything on your home server is actually
healthy — no clicking through three separate systemd checks or SSHing in
just to see if something crashed.

Checks (all run live, nothing stored):
- **Each Flask app** — HTTP reachability + response time, and its systemd
  service state (active/failed/inactive)
- **ZFS pool health** — `storagepool`'s status (ONLINE/DEGRADED/etc.),
  size, and free space
- **Disk usage** — root filesystem and your ZFS mountpoint
- **Server uptime**

## 1. Run it on your Debian server

```bash
cd status_page
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

By default it serves on port **5006**. Visit:
```
http://<server-ip>:5006
```

Set your own Tailscale hostname so the "Open" and admin links point
somewhere real instead of a placeholder:
```bash
export STATUS_PAGE_TAILSCALE_HOST="your-server.your-tailnet.ts.net"
python3 app.py
```
(find yours by running `tailscale status` on your server, or checking
the machine detail page in the Tailscale admin console)

The page auto-refreshes every 30 seconds, so you can leave it open on a
second monitor or a spare tab.

## 2. Permissions note

Checking systemd service state and ZFS pool health both typically
require root privileges on Debian. Run this the same way as your other
services (as `root`, matching your existing systemd units) or those
specific checks will just show "unknown" instead of the real state —
not a crash, just incomplete info.

## 3. Run it permanently with systemd

```bash
sudo nano /etc/systemd/system/status-page.service
```
```ini
[Unit]
Description=Server Status Page
After=network.target

[Service]
WorkingDirectory=/root/Projects/status_page
Environment=STATUS_PAGE_TAILSCALE_HOST=your-server.your-tailnet.ts.net
ExecStart=/root/Projects/status_page/venv/bin/python3 app.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now status-page
```

## 4. Add it to your Tailscale Serve setup

Same pattern as your other three apps:
```bash
sudo tailscale serve --bg --https=8446 http://127.0.0.1:5006
```
Then reach it from anywhere on your tailnet at:
```
https://capriccio.taild96475.ts.net:8446/
```

## Customizing what's monitored

Open `app.py` and edit the `SERVICES` list near the top to add/remove
services, or `DISK_PATHS` to change which filesystems get checked:

```python
SERVICES = [
    {"name": "Dorm Dashboard", "systemd": "dorm-dashboard", "url": "http://127.0.0.1:5001/"},
    {"name": "Ticket Hub", "systemd": "ticket-hub", "url": "http://127.0.0.1:5000/"},
    {"name": "Photo Drop", "systemd": "Photo-DropOff.service", "url": "http://127.0.0.1:5003/"},
]
```

## Files

```
app.py                  Flask app: all health checks + rendering
templates/               HTML pages
static/style.css         Styling
requirements.txt         Python dependencies
```
