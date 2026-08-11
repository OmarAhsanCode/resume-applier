import unittest
from unittest.mock import MagicMock, patch
import google_service

class TestSheetsHistory(unittest.TestCase):
    def setUp(self):
        self.mock_sheet_storage = []
        google_service.GOOGLE_SHEETS_SPREADSHEET_ID = "mock_sheet_id"

    def _mock_get(self, spreadsheetId=None, range=None):
        mock_exec = MagicMock()
        mock_exec.execute.return_value = {'values': [list(r) for r in self.mock_sheet_storage]}
        return mock_exec

    def _mock_update(self, spreadsheetId=None, range=None, valueInputOption=None, body=None):
        values = (body or {}).get('values', [])
        if range == 'Sheet1!A1' and len(values) == 1 and values[0] == google_service.SHEET_HEADERS:
            self.mock_sheet_storage = [list(google_service.SHEET_HEADERS)]
        elif range and '!A' in range:
            try:
                row_idx = int(range.split('!A')[1].split(':')[0]) - 1
                if row_idx < len(self.mock_sheet_storage):
                    self.mock_sheet_storage[row_idx] = list(values[0])
                else:
                    self.mock_sheet_storage.append(list(values[0]))
            except Exception:
                pass
        elif range and '!O' in range:
            try:
                row_idx = int(range.split('!O')[1]) - 1
                if row_idx < len(self.mock_sheet_storage):
                    self.mock_sheet_storage[row_idx][14] = values[0][0]
            except Exception:
                pass
        elif range and '!N' in range:
            try:
                row_idx = int(range.split('!N')[1]) - 1
                if row_idx < len(self.mock_sheet_storage):
                    self.mock_sheet_storage[row_idx][13] = values[0][0]
            except Exception:
                pass
        mock_exec = MagicMock()
        mock_exec.execute.return_value = {}
        return mock_exec

    def _mock_append(self, spreadsheetId=None, range=None, valueInputOption=None, insertDataOption=None, body=None):
        values = (body or {}).get('values', [])
        for v in values:
            self.mock_sheet_storage.append(list(v))
        mock_exec = MagicMock()
        mock_exec.execute.return_value = {}
        return mock_exec

    def _setup_mock_service(self, mock_service):
        google_service._sheets_service = mock_service
        mock_values = MagicMock()
        mock_values.get.side_effect = self._mock_get
        mock_values.update.side_effect = self._mock_update
        mock_values.append.side_effect = self._mock_append
        mock_service.spreadsheets.return_value.values.return_value = mock_values

    @patch('google_service._sheets_service')
    def test_1_first_run_appends_header_and_jobs(self, mock_service):
        self._setup_mock_service(mock_service)

        jobs = [
            {"id": 1, "unique_id": "gh:101", "company": "Acme 1", "title": "Dev 1", "application_url": "https://example.com/1"},
            {"id": 2, "unique_id": "gh:102", "company": "Acme 2", "title": "Dev 2", "application_url": "https://example.com/2"}
        ]
        
        res = google_service.sync_jobs_to_sheet(jobs)
        self.assertTrue(res)
        # Should have header + 2 jobs = 3 rows
        self.assertEqual(len(self.mock_sheet_storage), 3)
        self.assertEqual(self.mock_sheet_storage[0][0], "Job ID")
        self.assertEqual(self.mock_sheet_storage[1][0], "gh:101")
        self.assertEqual(self.mock_sheet_storage[2][0], "gh:102")

    @patch('google_service._sheets_service')
    def test_2_second_run_appends_new_jobs_preserving_history(self, mock_service):
        self.mock_sheet_storage = [
            list(google_service.SHEET_HEADERS),
            ["gh:101", 1, "Acme 1", "Dev 1", "Remote", "Full-time", 80, 80, 80, "", "", "", "https://example.com/1", "", "selected", "2026-08-11", ""],
            ["gh:102", 2, "Acme 2", "Dev 2", "Remote", "Full-time", 85, 85, 85, "", "", "", "https://example.com/2", "", "selected", "2026-08-11", ""]
        ]
        self._setup_mock_service(mock_service)

        new_jobs = [
            {"id": 3, "unique_id": "gh:103", "company": "Acme 3", "title": "Dev 3", "application_url": "https://example.com/3"}
        ]
        
        res = google_service.sync_jobs_to_sheet(new_jobs)
        self.assertTrue(res)
        # Total rows should now be 1 header + 2 old + 1 new = 4 rows
        self.assertEqual(len(self.mock_sheet_storage), 4)
        self.assertEqual(self.mock_sheet_storage[1][0], "gh:101")
        self.assertEqual(self.mock_sheet_storage[3][0], "gh:103")

    @patch('google_service._sheets_service')
    def test_3_duplicate_run_does_not_append(self, mock_service):
        self.mock_sheet_storage = [
            list(google_service.SHEET_HEADERS),
            ["gh:101", 1, "Acme 1", "Dev 1", "Remote", "Full-time", 80, 80, 80, "", "", "", "https://example.com/1", "", "selected", "2026-08-11", ""]
        ]
        self._setup_mock_service(mock_service)

        duplicate_jobs = [
            {"id": 1, "unique_id": "gh:101", "company": "Acme 1", "title": "Dev 1", "application_url": "https://example.com/1", "status": "selected"}
        ]
        
        res = google_service.sync_jobs_to_sheet(duplicate_jobs)
        self.assertTrue(res)
        # Rows should remain 2 (no duplicate row added)
        self.assertEqual(len(self.mock_sheet_storage), 2)

    @patch('google_service._sheets_service')
    def test_4_status_update_modifies_existing_row(self, mock_service):
        self.mock_sheet_storage = [
            list(google_service.SHEET_HEADERS),
            ["gh:101", 1, "Acme 1", "Dev 1", "Remote", "Full-time", 80, 80, 80, "", "", "", "https://example.com/1", "", "selected", "2026-08-11", ""]
        ]
        self._setup_mock_service(mock_service)

        updated_job = {
            "id": 1,
            "unique_id": "gh:101",
            "company": "Acme 1",
            "title": "Dev 1",
            "application_url": "https://example.com/1",
            "status": "applied",
            "applied_at": "2026-08-11T12:00:00"
        }
        
        res = google_service.update_job_status_in_sheet(updated_job)
        self.assertTrue(res)
        self.assertEqual(len(self.mock_sheet_storage), 2)
        # Status column index is 14
        self.assertEqual(self.mock_sheet_storage[1][14], "applied")

if __name__ == "__main__":
    unittest.main()
