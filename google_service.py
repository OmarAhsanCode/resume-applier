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

def initialize_google_drive():
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

def upload_pdf_to_drive(pdf_path: str, company_name: str) -> Optional[str]:
    """Stub upload_pdf_to_drive function - Google Drive is disabled in favor of Overleaf."""
    return None

def sync_jobs_to_sheet(selected_jobs: List[Dict[str, Any]]) -> bool:
    """
    Syncs selected jobs dashboard to Google Spreadsheet according to PROJECT_SPEC.md column specification.
    """
    global _sheets_service
    if not _sheets_service or not GOOGLE_SHEETS_SPREADSHEET_ID:
        logger.info("Google Sheets API service or SPREADSHEET_ID unconfigured. Skipping sheet sync.")
        return False

    try:
        headers = [
            "Rank", "Company", "Position", "Location", "Employment Type",
            "Deterministic Score", "AI Score", "Final Score", "Matching Skills",
            "Missing Skills", "Why Match", "Job URL", "Resume URL", "Status",
            "Date Found", "Date Applied"
        ]

        rows = [headers]
        for idx, job in enumerate(selected_jobs, 1):
            analysis = job.get("ai_analysis", {})
            matching = ", ".join(analysis.get("matching_requirements", [])) if isinstance(analysis, dict) else ""
            missing = ", ".join(analysis.get("missing_preferred_skills", [])) if isinstance(analysis, dict) else ""
            why_match = analysis.get("reason", "") if isinstance(analysis, dict) else ""

            row = [
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
                job.get("drive_url") or job.get("resume_pdf_path") or "",
                job.get("status", "selected"),
                job.get("first_seen", "")[:10],
                job.get("applied_at", "")[:10] if job.get("applied_at") else ""
            ]
            rows.append(row)

        body = {'values': rows}
        range_name = 'Sheet1!A1'
        
        _sheets_service.spreadsheets().values().update(
            spreadsheetId=GOOGLE_SHEETS_SPREADSHEET_ID,
            range=range_name,
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
        logger.info(f"Successfully synced {len(selected_jobs)} jobs to Google Sheet.")
        return True
    except Exception as e:
        logger.error(f"Error syncing jobs to Google Sheets: {e}")
        return False
