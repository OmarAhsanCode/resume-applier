import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Credentials configuration
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token.json")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")

_drive_service = None
_sheets_service = None

def get_google_credentials():
    """Attempts to build Google OAuth2 user credentials from credentials.json and token.json."""
    if not os.path.exists(GOOGLE_CREDENTIALS_FILE) and not os.path.exists(GOOGLE_TOKEN_FILE):
        return None

    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request

        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets'
        ]
        
        creds = None
        if os.path.exists(GOOGLE_TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_FILE, SCOPES)
            
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif os.path.exists(GOOGLE_CREDENTIALS_FILE):
                flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
                with open(GOOGLE_TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
                    
        return creds
    except Exception as e:
        logger.warning(f"Could not load Google credentials: {e}")
        return None

def initialize_google_sheets():
    """Initializes Google Sheets API client if credentials exist."""
    global _sheets_service
    creds = get_google_credentials()
    if not creds:
        logger.info("Google API credentials not configured. Remote Sheets sync will be skipped.")
        return False
        
    try:
        from googleapiclient.discovery import build
        _sheets_service = build('sheets', 'v4', credentials=creds)
        return True
    except Exception as e:
        logger.warning(f"Failed to build Google Sheets service: {e}")
        return False

def ensure_sheets_service():
    global _sheets_service
    if not _sheets_service:
        initialize_google_sheets()
    return _sheets_service is not None

SHEET_HEADERS = [
    "Job ID", "Rank", "Company", "Position", "Location", "Employment Type",
    "Deterministic Score", "AI Score", "Final Score", "Matching Skills",
    "Missing Skills", "Why Match", "Job URL", "Resume URL", "Status",
    "Date Found", "Date Applied"
]

def _build_job_row(idx: int, job: Dict[str, Any], base_url: str) -> List[Any]:
    analysis = job.get("ai_analysis", {})
    matching = ", ".join(analysis.get("matching_requirements", [])) if isinstance(analysis, dict) else ""
    missing = ", ".join(analysis.get("missing_preferred_skills", [])) if isinstance(analysis, dict) else ""
    why_match = analysis.get("reason", "") if isinstance(analysis, dict) else ""
    job_db_id = job.get("id") or ""
    
    if job.get("resume_tex_path") or job.get("resume_json"):
        overleaf_url = f"{base_url}/jobs/{job_db_id}/overleaf" if job_db_id else ""
    else:
        overleaf_url = "Not generated"

    job_key = str(job.get("unique_id") or job.get("id") or "")

    return [
        job_key,
        idx,
        job.get("company", ""),
        job.get("title", ""),
        job.get("location", ""),
        job.get("employment_type", ""),
        job.get("deterministic_score", 0),
        job.get("ai_score", 0),
        job.get("final_score", 0),
        matching,
        missing,
        why_match,
        job.get("application_url", ""),
        overleaf_url,
        job.get("status", "selected"),
        str(job.get("first_seen", ""))[:10],
        str(job.get("applied_at", ""))[:10] if job.get("applied_at") else ""
    ]

def sync_jobs_to_sheet(selected_jobs: List[Dict[str, Any]]) -> bool:
    """
    Syncs selected jobs to Google Spreadsheet by appending new jobs and updating existing rows.
    Preserves historical rows across runs.
    """
    if not ensure_sheets_service() or not GOOGLE_SHEETS_SPREADSHEET_ID:
        logger.info("Google Sheets API service or SPREADSHEET_ID unconfigured. Skipping sheet sync.")
        return False

    try:
        base_url = os.getenv("LOCAL_BASE_URL", "http://localhost:5000")
        
        # Read existing rows from Sheet1!A:Q
        try:
            read_res = _sheets_service.spreadsheets().values().get(
                spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
                range='Sheet1!A:Q'
            ).execute()
            existing_values = read_res.get('values', [])
        except Exception:
            existing_values = []

        # If sheet is totally empty, insert header row
        if not existing_values:
            _sheets_service.spreadsheets().values().update(
                spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
                range='Sheet1!A1',
                valueInputOption='USER_ENTERED',
                body={'values': [SHEET_HEADERS]}
            ).execute()
            existing_values = [SHEET_HEADERS]

        # Map existing job keys (Job ID or Job URL) to 1-indexed row number
        job_row_map = {}
        for r_idx, row_data in enumerate(existing_values, 1):
            if r_idx == 1:
                continue
            if row_data:
                key = str(row_data[0]).strip() if len(row_data) > 0 else ""
                url_key = str(row_data[12]).strip() if len(row_data) > 12 else ""
                if key:
                    job_row_map[key] = r_idx
                if url_key:
                    job_row_map[url_key] = r_idx

        existing_rows_count = len(existing_values)
        for idx, job in enumerate(selected_jobs, 1):
            job_key = str(job.get("unique_id") or job.get("id") or "")
            app_url = str(job.get("application_url") or "")
            row_data = _build_job_row(idx, job, base_url)

            row_number = job_row_map.get(job_key) or job_row_map.get(app_url)
            if row_number:
                # Update existing row in-place
                _sheets_service.spreadsheets().values().update(
                    spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
                    range=f'Sheet1!A{row_number}:Q{row_number}',
                    valueInputOption='USER_ENTERED',
                    body={'values': [row_data]}
                ).execute()
            else:
                # Append new row
                _sheets_service.spreadsheets().values().append(
                    spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
                    range='Sheet1!A1',
                    valueInputOption='USER_ENTERED',
                    insertDataOption='INSERT_ROWS',
                    body={'values': [row_data]}
                ).execute()
                existing_rows_count += 1
                job_row_map[job_key] = existing_rows_count
                if app_url:
                    job_row_map[app_url] = existing_rows_count

        logger.info(f"Successfully synced {len(selected_jobs)} jobs to Google Sheet.")
        return True
    except Exception as e:
        logger.error(f"Error syncing jobs to Google Sheets: {e}")
        return False

def _find_job_row_number(job: Dict[str, Any]) -> Optional[int]:
    """Finds the 1-indexed row number of a job in Google Sheets."""
    if not ensure_sheets_service() or not GOOGLE_SHEETS_SPREADSHEET_ID:
        return None

    try:
        read_res = _sheets_service.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
            range='Sheet1!A:Q'
        ).execute()
        existing_values = read_res.get('values', [])
        job_key = str(job.get("unique_id") or job.get("id") or "")
        app_url = str(job.get("application_url") or "")

        for r_idx, row_data in enumerate(existing_values, 1):
            if r_idx == 1:
                continue
            if row_data:
                key = str(row_data[0]).strip() if len(row_data) > 0 else ""
                url_key = str(row_data[12]).strip() if len(row_data) > 12 else ""
                if (job_key and key == job_key) or (app_url and url_key == app_url):
                    return r_idx
        return None
    except Exception as e:
        logger.warning(f"Error finding job row number in Sheet: {e}")
        return None

def update_job_status_in_sheet(job: Dict[str, Any]) -> bool:
    """Updates application status column (Col O / Col 15) of a single job in Google Sheets without altering Resume URL."""
    row_num = _find_job_row_number(job)
    if not row_num or not ensure_sheets_service():
        return sync_jobs_to_sheet([job])

    try:
        status_val = job.get("status", "selected")
        applied_at_val = str(job.get("applied_at", ""))[:10] if job.get("applied_at") else ""
        
        # Col O is Status (15th col), Col Q is Date Applied (17th col)
        _sheets_service.spreadsheets().values().update(
            spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
            range=f'Sheet1!O{row_num}',
            valueInputOption='USER_ENTERED',
            body={'values': [[status_val]]}
        ).execute()

        if applied_at_val:
            _sheets_service.spreadsheets().values().update(
                spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
                range=f'Sheet1!Q{row_num}',
                valueInputOption='USER_ENTERED',
                body={'values': [[applied_at_val]]}
            ).execute()

        logger.info(f"Updated status for job #{job.get('id')} to '{status_val}' in Sheet row {row_num}.")
        return True
    except Exception as e:
        logger.error(f"Error updating job status in Sheet: {e}")
        return sync_jobs_to_sheet([job])

def update_job_resume_url_in_sheet(job: Dict[str, Any], overleaf_url: str) -> bool:
    """Updates Resume URL column (Col N / Col 14) of a single job in Google Sheets without altering application status."""
    row_num = _find_job_row_number(job)
    if not row_num or not ensure_sheets_service():
        return sync_jobs_to_sheet([job])

    try:
        # Col N is Resume URL (14th col)
        _sheets_service.spreadsheets().values().update(
            spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
            range=f'Sheet1!N{row_num}',
            valueInputOption='USER_ENTERED',
            body={'values': [[overleaf_url]]}
        ).execute()

        logger.info(f"Updated Resume URL for job #{job.get('id')} in Sheet row {row_num}.")
        return True
    except Exception as e:
        logger.error(f"Error updating Resume URL in Sheet: {e}")
        return sync_jobs_to_sheet([job])
