"""
Wedding RSVP backend — SINGLE FILE VERSION.

The guest-facing HTML page is embedded directly in this file, so there is
NO separate templates folder and nothing else to upload. Just this app.py,
requirements.txt, and Procfile.

Receives a guest name via POST /api/rsvp and appends it as a new row
(name + timestamp) to a Google Sheet, using a Google Service Account.

Setup required (one time):
  1. Google Cloud project with Google Sheets API + Google Drive API enabled.
  2. A Service Account; download its JSON key. On Render, paste that JSON
     into Secret Files with the filename `service_account.json`.
  3. Create a Google Sheet, share it with the service account's client_email
     (found in the JSON) as Editor.
  4. Set the SHEET_ID environment variable to your Sheet's ID.
"""

import os
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
CORS(app)

# ---- CONFIG ----
SHEET_ID = os.environ.get("SHEET_ID", "PASTE_YOUR_GOOGLE_SHEET_ID_HERE")
SERVICE_ACCOUNT_FILE = os.environ.get(
    "SERVICE_ACCOUNT_FILE", "service_account.json"
)
WORKSHEET_NAME = os.environ.get("WORKSHEET_NAME", "RSVPs")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
# ----------------

_sheet = None

PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RSVP</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Georgia', 'Times New Roman', serif;
    background: linear-gradient(135deg, #faf6f0 0%, #f0e6d8 100%);
    min-height: 100vh; display: flex; align-items: center;
    justify-content: center; padding: 20px;
  }
  .card {
    background: #ffffff; border-radius: 16px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.1);
    padding: 48px 36px; max-width: 420px; width: 100%; text-align: center;
  }
  .card h1 {
    font-size: 28px; color: #4a3b32; margin-bottom: 8px;
    font-weight: 400; letter-spacing: 1px;
  }
  .card p.subtitle {
    color: #9a8a7a; font-size: 14px; margin-bottom: 32px; letter-spacing: 0.5px;
  }
  input[type="text"] {
    width: 100%; padding: 14px 16px; border: 1px solid #ddd0c0;
    border-radius: 8px; font-size: 16px; font-family: Arial, sans-serif;
    margin-bottom: 16px; outline: none; transition: border-color 0.2s;
  }
  input[type="text"]:focus { border-color: #b8860b; }
  button {
    width: 100%; padding: 14px; background: #b8860b; color: white;
    border: none; border-radius: 8px; font-size: 16px;
    font-family: Arial, sans-serif; cursor: pointer; transition: background 0.2s;
  }
  button:hover { background: #9c7209; }
  button:disabled { background: #ccc; cursor: not-allowed; }
  .message {
    margin-top: 16px; font-size: 14px; font-family: Arial, sans-serif;
    min-height: 20px;
  }
  .message.success { color: #2e7d32; }
  .message.error { color: #c62828; }
</style>
</head>
<body>
<div class="card">
  <h1>You're Invited &#128141;</h1>
  <p class="subtitle">Kindly RSVP below</p>
  <form id="rsvpForm">
    <input type="text" id="nameInput" placeholder="Enter your full name" required autocomplete="off">
    <button type="submit" id="submitBtn">Confirm RSVP</button>
  </form>
  <div class="message" id="message"></div>
</div>
<script>
  const API_URL = '/api/rsvp';
  const form = document.getElementById('rsvpForm');
  const nameInput = document.getElementById('nameInput');
  const submitBtn = document.getElementById('submitBtn');
  const messageEl = document.getElementById('message');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = nameInput.value.trim();
    if (!name) return;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Submitting...';
    messageEl.textContent = '';
    messageEl.className = 'message';
    try {
      const res = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name })
      });
      const data = await res.json();
      if (!res.ok) { throw new Error(data.error || 'Submission failed'); }
      messageEl.textContent = data.message || ('Thank you, ' + name + '!');
      messageEl.className = 'message success';
      nameInput.value = '';
    } catch (err) {
      console.error(err);
      messageEl.textContent = err.message || 'Something went wrong. Please try again.';
      messageEl.className = 'message error';
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Confirm RSVP';
    }
  });
</script>
</body>
</html>"""


def get_sheet():
    """Lazily connect to the Google Sheet and cache the connection."""
    global _sheet
    if _sheet is not None:
        return _sheet

    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SHEET_ID)

    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=WORKSHEET_NAME, rows=1000, cols=3
        )
        worksheet.append_row(["Name", "Timestamp"])

    _sheet = worksheet
    return _sheet


@app.route("/")
def index():
    # The page always loads, even before Google is configured.
    return PAGE_HTML


@app.route("/api/rsvp", methods=["POST"])
def rsvp():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()

    if not name:
        return jsonify({"error": "Name is required"}), 400
    if len(name) > 100:
        return jsonify({"error": "Name is too long"}), 400

    try:
        sheet = get_sheet()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([name, timestamp])
    except Exception as exc:
        app.logger.error(f"Failed to write to Google Sheet: {exc}")
        return jsonify({"error": "Could not save RSVP. Please try again."}), 500

    return jsonify({"success": True, "message": f"Thank you, {name}!"})


@app.route("/api/rsvp/count", methods=["GET"])
def rsvp_count():
    """Admin-only count check. Not linked anywhere on the guest page."""
    try:
        sheet = get_sheet()
        count = max(len(sheet.get_all_values()) - 1, 0)
    except Exception as exc:
        app.logger.error(f"Failed to read Google Sheet: {exc}")
        return jsonify({"error": "Could not fetch count"}), 500

    return jsonify({"count": count})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
