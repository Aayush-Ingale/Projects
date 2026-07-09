"""
Photo Drop - Web Edition

A tiny self-hosted photo upload spot. Point Safari at it on your iPhone and
tap "Choose Photos" -- iOS opens your native Photos library picker directly,
no separate app needed. There's also a "/upload" API endpoint you can wire
up to an iOS Shortcut so you can hit Share -> [your shortcut] right from
inside the Photos app itself, without opening a browser at all (see
SHORTCUT_SETUP.md for that part).

Run:
    pip install -r requirements.txt
    python3 app.py

Then visit http://<server-ip>:5003

Configuration (environment variables, all optional):
    PHOTO_DROP_PORT           port to serve on (default: 5003)
    PHOTO_DROP_UPLOAD_TOKEN   if set, uploads must include this token
                              (via ?token=... or a "token" form field) --
                              recommended once you wire up the Shortcut,
                              so random people on your tailnet can't spam
                              your gallery. Leave unset to allow anyone
                              reachable to upload with no token.
"""

import mimetypes
import os
import uuid
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_from_directory, jsonify,
)
from werkzeug.utils import secure_filename

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PHOTOS_DIR = "/storagepool/media"
METADATA_FILE = os.path.join(APP_DIR, "photos.json")
PORT = int(os.environ.get("PHOTO_DROP_PORT", "5003"))
UPLOAD_TOKEN = os.environ.get("PHOTO_DROP_UPLOAD_TOKEN", "")

os.makedirs(PHOTOS_DIR, exist_ok=True)

# iPhones commonly send HEIC/HEIF for photos and MOV for videos, alongside
# the usual jpg/png -- all allowed here so nothing gets silently rejected.
ALLOWED_EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "webp", "heic", "heif", "mp4", "mov"
}

app = Flask(__name__)
app.secret_key = os.environ.get("PHOTO_DROP_SECRET_KEY", os.urandom(24))
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB per request


# =========================================================================
# STORAGE HELPERS
# =========================================================================

import json


def load_photos() -> list:
    """-> list - every uploaded photo's metadata, or an empty list."""
    if not os.path.exists(METADATA_FILE):
        return []
    try:
        with open(METADATA_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_photos(photos: list) -> None:
    """-> None. Writes the photo metadata list back to disk."""
    with open(METADATA_FILE, "w") as f:
        json.dump(photos, f, indent=4)


def allowed_file(filename) -> bool:
    """-> bool - whether the uploaded file's extension is on the allow-list."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def is_authorized(req) -> bool:
    """
    -> bool
    If PHOTO_DROP_UPLOAD_TOKEN is unset, everyone reachable is allowed to
    upload (fine on a private tailnet). If it IS set, the request must
    include the matching token, either as a query string (?token=...) or
    a form field -- both are supported so a Shortcut can pass it either
    way.
    """
    if not UPLOAD_TOKEN:
        return True
    supplied = req.args.get("token") or req.form.get("token")
    return supplied == UPLOAD_TOKEN


# =========================================================================
# ROUTES
# =========================================================================

@app.route("/")
def gallery():
    """
    -> str (HTML)
    Shows the upload form plus a grid of everything uploaded so far,
    newest first.
    """
    photos = load_photos()
    photos.sort(key=lambda p: p["uploaded_at"], reverse=True)
    return render_template("gallery.html", photos=photos, token_required=bool(UPLOAD_TOKEN))


@app.route("/upload", methods=["POST"])
def upload():
    """
    -> redirect OR JSON
    Handles two kinds of callers with one endpoint:
      1. The web form on "/" -- sends multiple files under the field
         name "photos", expects a redirect back to the gallery.
      2. An iOS Shortcut hitting this directly from the Share Sheet --
         typically sends a single file under the field name "file",
         expects a small JSON response instead of an HTML redirect.
    """
    if not is_authorized(request):
        if request.files.get("file"):
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        flash("Upload token missing or incorrect.", "error")
        return redirect(url_for("gallery"))

    incoming = request.files.getlist("photos") or request.files.getlist("file")
    if not incoming:
        if request.files.get("file") is not None:
            return jsonify({"ok": False, "error": "No file received"}), 400
        flash("No files selected.", "error")
        return redirect(url_for("gallery"))

    uploader = request.form.get("uploader", "").strip()
    photos = load_photos()
    saved_count = 0

    for f in incoming:
        if not f or not f.filename:
            continue
        if not allowed_file(f.filename):
            continue  # silently skip disallowed types rather than failing the whole batch

        original_name = secure_filename(f.filename)
        ext = original_name.rsplit(".", 1)[1].lower()
        stored_name = f"{uuid.uuid4().hex}.{ext}"
        f.save(os.path.join(PHOTOS_DIR, stored_name))

        photos.append({
            "id": uuid.uuid4().hex[:8],
            "filename": stored_name,
            "original_name": original_name,
            "uploader": uploader,
            "uploaded_at": datetime.now().isoformat(),
        })
        saved_count += 1

    save_photos(photos)

    # Shortcut-style callers (single "file" field) get JSON back so the
    # Shortcut can show a quiet confirmation instead of trying to render HTML.
    if request.files.get("file") is not None and not request.files.getlist("photos"):
        return jsonify({"ok": True, "saved": saved_count})

    if saved_count:
        flash(f"Uploaded {saved_count} photo(s).", "success")
    else:
        flash("Nothing uploaded -- check the file type.", "error")
    return redirect(url_for("gallery"))


@app.route("/photos/<filename>")
def serve_photo(filename):
    """
    -> file
    Serves a photo's raw bytes so <img> tags in the gallery can display
    it directly. HEIC files won't render in most browsers -- that's a
    browser limitation, not a bug here (see note in gallery.html).
    """
    return send_from_directory(PHOTOS_DIR, filename)


@app.route("/photos/<photo_id>/delete", methods=["POST"])
def delete_photo(photo_id):
    """-> redirect. Removes one photo's file and its metadata entry."""
    photos = load_photos()
    remaining = []
    for p in photos:
        if p["id"] == photo_id:
            path = os.path.join(PHOTOS_DIR, p["filename"])
            if os.path.exists(path):
                os.remove(path)
            continue
        remaining.append(p)
    save_photos(remaining)
    return redirect(url_for("gallery"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
