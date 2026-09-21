import os
import re
import csv
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import gspread
from google.oauth2.service_account import Credentials
import traceback

import urllib.request
import datetime
import email.utils
import google.auth._helpers

# Lazy cached time-sync: applied once on first API call, not at import time
_time_sync_applied = False

def _ensure_time_sync():
    """Measures clock drift against Google servers and patches google.auth._helpers.utcnow
    so that JWT tokens have correct timestamps even when the local clock is wrong.
    Safe to call multiple times — only applies the patch once.
    """
    global _time_sync_applied
    if _time_sync_applied:
        return
    _time_sync_applied = True
    try:
        if hasattr(google.auth._helpers.utcnow, "_is_patched"):
            return  # already patched by another import
        response = urllib.request.urlopen("https://www.google.com", timeout=5)
        date_str = response.info().get('Date')
        if not date_str:
            return
        google_date = email.utils.parsedate_to_datetime(date_str)
        google_utc = google_date.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        local_utc = datetime.datetime.utcnow()
        offset_seconds = (local_utc - google_utc).total_seconds()
        if abs(offset_seconds) > 30:
            print(f"[GoogleSheets][TimeSync] Clock drift detected ({offset_seconds:.0f}s). Applying offset patch...")
            _original_utcnow = google.auth._helpers.utcnow
            def _patched_utcnow(_orig=_original_utcnow, _off=offset_seconds):
                return _orig() - datetime.timedelta(seconds=_off)
            _patched_utcnow._is_patched = True
            google.auth._helpers.utcnow = _patched_utcnow
    except Exception as e:
        print(f"[GoogleSheets][TimeSync] Warning: could not measure time offset: {e}")


def get_csv_url(sheet_url: str) -> str:
    """Extracts the spreadsheet ID and returns a public CSV export URL."""
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
    if match:
        spreadsheet_id = match.group(1)
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv"
    return sheet_url

def normalize_sheet_url(sheet_url: str) -> str:
    """Ensures sheet_url is a full Google Sheets URL. Converts bare spreadsheet IDs."""
    sheet_url = sheet_url.strip()
    if not sheet_url.startswith("http://") and not sheet_url.startswith("https://"):
        if "/" not in sheet_url:
            sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_url}/edit"
    return sheet_url


def find_credentials_file() -> str:
    """Finds credentials.json in the current working directory or parent app/workspace folders."""
    env_cred = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if env_cred:
        env_path = Path(env_cred)
        if env_path.exists():
            return str(env_path)

    candidates = [
        Path(os.getcwd()) / "credentials.json",
        Path(__file__).resolve().parents[1] / "credentials.json",
        Path(__file__).resolve().parents[2] / "credentials.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(Path(os.getcwd()) / "credentials.json")


def normalize_headers(headers: List[str]) -> Dict[str, str]:
    """
    Normalizes sheet headers and maps them to standard fields ('name', 'phone', 'language', 'status').
    Returns a dictionary mapping standardized fields to the actual sheet header strings.
    """
    mapping = {}
    for h in headers:
        clean = h.strip().lower().replace(".", "").replace(" ", "").replace("_", "").replace("-", "")
        if clean in ["name", "customername", "username"]:
            mapping["name"] = h
        elif clean in ["phone", "phno", "phoneno", "phonenumber", "phnumber", "phone_no", "phone-no", "mobile", "mobileno", "mobilenumber", "contactno", "contactnumber"]:
            mapping["phone"] = h
        elif clean in ["language", "lang", "preferredlanguage", "pref_lang", "pref-lang"]:
            mapping["language"] = h
        elif clean in ["callstatus", "status"]:
            mapping["status"] = h
        elif clean in ["investigatedcoursename", "investigatedcourse", "course", "coursename", "subject", "investigatedcourses", "enquiredcoursename", "enquiredcourse"]:
            mapping["investigated_course"] = h
        elif clean in ["internshiporcourse", "type", "category", "internship_or_course", "internorcourse"]:
            mapping["internship_or_course"] = h
        elif clean in ["courseduration", "duration", "length"]:
            mapping["course_duration"] = h
    return mapping

def find_header_row(records: List[List[str]]) -> Tuple[int, List[str], Dict[str, str]]:
    """
    Scans list of rows to find the first row that matches name or phone headers.
    Returns (1-based header_row_index, header_row_values, normalized_header_map).
    If no match is found, defaults to row index 1 (0-based index 0), the first row.
    """
    for idx, row in enumerate(records):
        mapping = normalize_headers(row)
        if mapping and ("name" in mapping or "phone" in mapping):
            return idx + 1, row, mapping
    if records:
        return 1, records[0], normalize_headers(records[0])
    return 1, [], {}

def read_sheet_data(sheet_url: str) -> List[Dict[str, Any]]:
    """
    Reads the Google Sheet data.
    Attempts to authenticate with credentials.json in the workspace root first.
    Falls back to a public HTTP CSV export request if credentials are not found.
    Returns a list of dictionaries, where keys are normalized to ('name', 'phone', 'language')
    and includes the 'row_number' (1-indexed starting at 1, but header is row 1, so first data row is 2).
    """
    sheet_url = normalize_sheet_url(sheet_url)
    _ensure_time_sync()
    # 1. Try Credentials-based reading via gspread
    cred_file = find_credentials_file()
    auth_error = None
    if os.path.exists(cred_file):
        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_file(cred_file, scopes=scope)
            client = gspread.authorize(creds)
            
            # Extract spreadsheet ID or name
            match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
            if match:
                spreadsheet = client.open_by_key(match.group(1))
            else:
                # Fallback to opening by title
                spreadsheet = client.open(sheet_url)
                
            sheet = spreadsheet.get_worksheet(0)
            records = sheet.get_all_values()
            
            if not records:
                return []
                
            header_row_index, headers, header_map = find_header_row(records)
            
            results = []
            # Start from the row after the header row
            for idx, row in enumerate(records[header_row_index:], start=header_row_index + 1):
                if len(row) < len(headers):
                    # Pad row if shorter than headers
                    row += [""] * (len(headers) - len(row))
                    
                row_dict = {headers[i]: row[i] for i in range(len(headers))}
                
                normalized = {"row_number": idx}
                if "name" in header_map:
                    normalized["name"] = row_dict.get(header_map["name"], "").strip()
                if "phone" in header_map:
                    normalized["phone"] = row_dict.get(header_map["phone"], "").strip()
                if "language" in header_map:
                    normalized["language"] = row_dict.get(header_map["language"], "").strip()
                if "status" in header_map:
                    normalized["status"] = row_dict.get(header_map["status"], "").strip()
                if "investigated_course" in header_map:
                    normalized["investigated_course"] = row_dict.get(header_map["investigated_course"], "").strip()
                if "internship_or_course" in header_map:
                    normalized["internship_or_course"] = row_dict.get(header_map["internship_or_course"], "").strip()
                if "course_duration" in header_map:
                    normalized["course_duration"] = row_dict.get(header_map["course_duration"], "").strip()
                    
                results.append(normalized)
            return results
        except Exception as e:
            auth_error = str(e)
            print(f"Authenticated Sheet reading failed: {auth_error}. Falling back to public CSV...")

    # 2. Fallback to Public CSV export download
    csv_url = get_csv_url(sheet_url)
    try:
        response = requests.get(csv_url, timeout=10)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP GET returned status code {response.status_code}")
            
        decoded = response.content.decode("utf-8")
        reader = csv.reader(decoded.splitlines())
        records = list(reader)
        
        if not records:
            return []
            
        header_row_index, headers, header_map = find_header_row(records)
        
        results = []
        for idx, row in enumerate(records[header_row_index:], start=header_row_index + 1):
            if len(row) < len(headers):
                row += [""] * (len(headers) - len(row))
                
            row_dict = {headers[i]: row[i] for i in range(len(headers))}
            
            normalized = {"row_number": idx}
            if "name" in header_map:
                normalized["name"] = row_dict.get(header_map["name"], "").strip()
            if "phone" in header_map:
                normalized["phone"] = row_dict.get(header_map["phone"], "").strip()
            if "language" in header_map:
                normalized["language"] = row_dict.get(header_map["language"], "").strip()
            if "status" in header_map:
                normalized["status"] = row_dict.get(header_map["status"], "").strip()
            if "investigated_course" in header_map:
                normalized["investigated_course"] = row_dict.get(header_map["investigated_course"], "").strip()
            if "internship_or_course" in header_map:
                normalized["internship_or_course"] = row_dict.get(header_map["internship_or_course"], "").strip()
            if "course_duration" in header_map:
                normalized["course_duration"] = row_dict.get(header_map["course_duration"], "").strip()
                
            results.append(normalized)
        return results
    except Exception as e:
        fallback_error = str(e)
        print(f"Failed to read public Google Sheet: {fallback_error}")
        if auth_error:
            raise RuntimeError(
                f"Unable to read spreadsheet: authenticated access failed: {auth_error}; public fallback failed: {fallback_error}"
            )
        raise RuntimeError(f"Unable to read spreadsheet: {fallback_error}")

def update_sheet_feedback(sheet_url: str, row_number: int, feedback_data: Dict[str, Any]) -> None:
    """
    Updates the Google Sheet at row_number with the provided feedback data.
    Automatically checks and appends tracking columns ('Call Status', 'Duration (sec)', 'Summary', 'Transcript')
    if they do not already exist as headers.
    """
    sheet_url = normalize_sheet_url(sheet_url)
    _ensure_time_sync()
    cred_file = find_credentials_file()
    print(f"[GoogleSheets] Using credentials file: {cred_file}")
    if not os.path.exists(cred_file):
        msg = (f"credentials.json not found. Tried: {cred_file}. "
               f"Cannot update Google Sheet dynamically. Row: {row_number}, URL: {sheet_url}")
        print(f"[GoogleSheets][ERROR] {msg}")
        raise RuntimeError(msg)

    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        try:
            creds = Credentials.from_service_account_file(cred_file, scopes=scope)
        except Exception as e:
            print(f"[GoogleSheets][ERROR] Failed to load service account credentials from {cred_file}: {e}")
            print(traceback.format_exc())
            raise

        client = gspread.authorize(creds)

        # Extract spreadsheet ID or name
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
        spreadsheet_id = match.group(1) if match else None
        print(f"[GoogleSheets] Opening spreadsheet: {spreadsheet_id or sheet_url}")
        if spreadsheet_id:
            spreadsheet = client.open_by_key(spreadsheet_id)
        else:
            spreadsheet = client.open(sheet_url)

        sheet = spreadsheet.get_worksheet(0)
        records = sheet.get_all_values()
        print(f"[GoogleSheets] Retrieved {len(records)} rows from sheet (including headers).")
        
        # Find header row dynamically
        header_row_index, headers, _ = find_header_row(records)
        if not headers:
            headers = sheet.row_values(1)
            header_row_index = 1
            
        # Ensure feedback columns exist
        target_columns = [
            "Call Status", "Duration (sec)", "Summary", "Transcript", "Conversation",
            "Follow Up Date", "Joining Date", "Reminder Consent", "Reminder Call Date"
        ]
        col_indices = {}
        for col_name in target_columns:
            clean_target = col_name.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
            found_idx = None
            for idx, h in enumerate(headers):
                clean_h = h.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
                if clean_h == clean_target:
                    found_idx = idx + 1
                    break
                # Special fallback for Call Status: if they just have "Status"
                if clean_target == "callstatus" and clean_h == "status":
                    found_idx = idx + 1
                    break
                    
            if found_idx is not None:
                col_indices[col_name] = found_idx
            else:
                sheet.update_cell(header_row_index, len(headers) + 1, col_name)
                headers.append(col_name)
                col_indices[col_name] = len(headers)
        
        # Perform updates in a single batch to avoid API quota limits
        cells_to_update = []
        mapping = {
            "Call Status": "status",
            "Duration (sec)": "duration",
            "Summary": "summary",
            "Transcript": "transcript",
            "Conversation": "conversation",
            "Follow Up Date": "followup_date",
            "Joining Date": "joining_date",
            "Reminder Consent": "reminder_consent",
            "Reminder Call Date": "reminder_call_date",
        }
        
        for col_name, data_key in mapping.items():
            if col_name in col_indices and data_key in feedback_data:
                cells_to_update.append({
                    'range': gspread.utils.rowcol_to_a1(row_number, col_indices[col_name]),
                    'values': [[feedback_data[data_key]]]
                })
                
        if cells_to_update:
            sheet.batch_update(cells_to_update)
            
        print(f"Successfully updated Google Sheet row {row_number} with call details.")
    except Exception as e:
        print(f"Failed to write feedback back to Google Sheet: {repr(e)}")
        traceback.print_exc()
        print(f"[Fallback Outcome Log] Row: {row_number} | Data: {feedback_data}")


def update_sheet_status(sheet_url: str, row_number: int, status: str) -> None:
    """Update just the Status/Call Status column for one sheet row.

    Thin wrapper around update_sheet_feedback, matching the same "status"
    key already used successfully by the /calls/run-sheet queue-marking
    logic (e.g. "queue", "ongoing", "calling", "do_not_call").
    """
    update_sheet_feedback(sheet_url, row_number, {"status": status})

