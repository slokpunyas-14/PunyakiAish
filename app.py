"""
Wedding RSVP backend.

Receives a guest name via POST /api/rsvp and appends it as a new row
(name + timestamp) to a Google Sheet, using a Google Service Account
for authentication.

Setup required before running (see SETUP.md for full step-by-step):
  1. Create a Google Cloud project + enable Google Sheets API & Google Drive API.
  2. Create a Service Account, download its JSON key as `service_account.json`
     and place it in this folder (NEVER commit this file to a public repo).
  3. Create a Google Sheet, share it with the service account's email
     (found inside service_account.json as "client_email") with Editor access.
  4. Copy the Sheet ID from its URL and set it as SHEET_ID below or via
     the SHEET_ID environment variable.
"""

import os
from datetime import datetime

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
CORS(app)

# ---- CONFIG ----
SHEET_ID = os.environ.get("SHEET_ID", "1OK2TqtSBurJz3kQycl0KUrJEwG6lAn7lfrOeK_BkQ4o")
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
    return render_template("rsvp.html")


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
    """
    Admin-only endpoint to check the total RSVP count.
    Not linked anywhere on the guest-facing page.
    """
    try:
        sheet = get_sheet()
        # minus 1 for the header row
        count = max(len(sheet.get_all_values()) - 1, 0)
    except Exception as exc:
        app.logger.error(f"Failed to read Google Sheet: {exc}")
        return jsonify({"error": "Could not fetch count"}), 500

    return jsonify({"count": count})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
