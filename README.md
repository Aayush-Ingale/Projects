# Photo Drop

A tiny self-hosted photo upload spot for your home server. Two ways to get
photos in from an iPhone:

1. **Safari, no extra app** — visit the site, tap "Choose photos," and iOS
   opens your native Photos library picker directly.
2. **Share Sheet, no browser at all** — set up the iOS Shortcut below once,
   then from inside the Photos app: select photo(s) → Share → your
   shortcut → done.

## 1. Run it on your Debian server

```bash
cd photo_upload
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

By default it serves on port **5003**. Visit:
```
http://<server-ip>:5003
```

## 2. (Recommended) Set an upload token

Since this endpoint will be reachable from your Tailscale network, anyone
on your tailnet could otherwise upload/spam it. Set a token so uploads
need a shared secret:

```bash
export PHOTO_DROP_UPLOAD_TOKEN="something-only-you-and-your-shortcut-know"
python3 app.py
```

The web form will then show an "Upload code" field automatically. If you
skip this, uploads are open to anyone who can reach the URL — fine on a
private tailnet, but worth knowing.

## 3. Run it permanently with systemd

```bash
sudo nano /etc/systemd/system/photo-drop.service
```
```ini
[Unit]
Description=Photo Drop
After=network.target

[Service]
WorkingDirectory=/path/to/photo_upload
Environment=PHOTO_DROP_UPLOAD_TOKEN=something-only-you-and-your-shortcut-know
ExecStart=/path/to/photo_upload/venv/bin/python3 app.py
Restart=always
User=youruser

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now photo-drop
```

## 4. Set up the iOS Shortcut (Share Sheet upload)

This is what lets you upload straight from inside the Photos app, no
Safari required.

1. Open the **Shortcuts** app on your iPhone → tap **+** to create a new shortcut
2. Tap **Add Action** → search for **"Get Contents of URL"** → add it
3. Tap the URL field, enter:
   ```
   http://<server-tailscale-name>:5003/upload?token=something-only-you-and-your-shortcut-know
   ```
   (skip the `?token=...` part if you didn't set `PHOTO_DROP_UPLOAD_TOKEN`)
4. Tap **Show More** under that action, and set:
   - **Method:** POST
   - **Request Body:** Form
   - Add a new field: key = `file`, type = **File**, value = **Shortcut Input**
5. Tap the shortcut's settings (ⓘ icon) → turn on **"Use with Share Sheet"** → under "Share Sheet Types," select **Images** (and Videos, if you want those too)
6. Name it something like "Upload to Photo Drop" and save

**To use it:** open Photos on your iPhone → select one or more photos → tap **Share** → scroll to find your shortcut → tap it. It uploads in the background with no browser involved.

## Files

```
app.py                  Flask app: upload + gallery
templates/               HTML pages
static/style.css         Styling
requirements.txt          Python dependencies
photos/                   Uploaded files, created on first upload
photos.json               Metadata (uploader, filename, timestamp) for each photo
```

## Notes

- **HEIC photos** (iPhone's default format) can't be previewed inline by
  most browsers — they show as a download link in the gallery instead of
  a thumbnail. Two ways around this:
  - Set your iPhone to **Settings → Camera → Formats → Most Compatible**
    before uploading (saves as JPEG instead of HEIC going forward)
  - Or convert HEIC → JPEG server-side on upload using `pillow-heif` —
    ask if you want this added; it's a small addition to `app.py`.
- **No login system** — like your other home server apps, this relies on
  Tailscale for access control, not a password. The optional upload token
  is a lightweight extra layer, not real authentication.
- **Storage**: photos are saved under `photos/`, and nothing is ever
  auto-deleted — keep an eye on disk usage if you're uploading a lot of
  video.
