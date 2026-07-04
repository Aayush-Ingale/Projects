# Dorm Dashboard

One page: current weather, today's classes, a to-do list, and upcoming
assignments with a live countdown. Same pattern as the other two projects —
Flask + JSON files + systemd.

## 1. Set up on your Debian server

```bash
cd ~
git clone <your-repo-url> dorm_dashboard    # or upload the files the way you did before
cd dorm_dashboard
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

By default it serves on port **5001** (ticket hub is 5000). Note: when you
build the uptime monitor, give it a port other than 5001/5000 (e.g. 5002)
so it doesn't collide with this one. Visit:

```
http://<server-ip>:5001
```

## 2. Set your location for weather

Click **Settings** and enter your city (add a state/country if it's a
common name, e.g. "State College, PA"). Weather comes from Open-Meteo,
which is free and needs no API key. If the lookup fails, double check the
server has internet access — this call happens server-side.

## 3. Add your schedule and assignments

- **Schedule** — add each class once with its day and time; it'll
  automatically show up under "Today's classes" on whichever days it's
  scheduled.
- **Assignments** — add a name, optional class, and due date/time. The
  dashboard shows a live countdown, and flags anything overdue in red.
  You can also add an optional weight/grade and attach a file (syllabus,
  rubric, your submission, etc.) to each assignment.
- **Grades** — see a weighted current-grade estimate per class, based on
  whichever assignments have both a weight and a grade entered.
- **To-do** — quick add/check-off list, right on the main dashboard.

## 4. Run it permanently with systemd

```bash
sudo nano /etc/systemd/system/dorm-dashboard.service
```

```ini
[Unit]
Description=Dorm Dashboard
After=network.target

[Service]
WorkingDirectory=/root/dorm_dashboard
ExecStart=/root/dorm_dashboard/venv/bin/python3 app.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now dorm-dashboard
systemctl status dorm-dashboard
```

## 5. Reach it from anywhere

Same as the other two apps — once your laptop is on the same Tailscale
network as the server:

```
http://<tailscale-name>:5001
```

## Note on privacy/access

Like the uptime monitor, this app has **no login** — it's meant to be a
convenience page just for you, reachable over your home network or
Tailscale, not exposed publicly. Don't port-forward this one either.

## Files

```
app.py                       Flask app: weather, schedule, todos, assignments
templates/                    HTML pages
static/style.css              Styling
requirements.txt              Python dependencies (Flask + requests)
config.json                   Created after you set your location
schedule.json                 Created after you add your first class
todos.json                    Created after you add your first to-do
assignments.json              Created after you add your first assignment
attachments/                   Uploaded assignment files, created on first upload
```
