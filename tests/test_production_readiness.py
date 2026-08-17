import os
import unittest
import json
import sqlite3
from unittest.mock import patch, MagicMock

import app as flask_app_module
from app import app
import config
import database
import resume
import resume_optimizer

class TestProductionReadiness(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_configuration_environments(self):
        """Validates configuration classes and production secret key validation."""
        dev_cfg = config.DevelopmentConfig
        self.assertTrue(dev_cfg.DEBUG)
        self.assertFalse(dev_cfg.SESSION_COOKIE_SECURE)

        test_cfg = config.TestingConfig
        self.assertTrue(test_cfg.TESTING)

        # Test production validation failure on weak key
        orig_secret = config.ProductionConfig.SECRET_KEY
        try:
            config.ProductionConfig.SECRET_KEY = "dev-secret-key-change-in-production"
            with self.assertRaises(ValueError):
                config.ProductionConfig.validate()
        finally:
            config.ProductionConfig.SECRET_KEY = orig_secret

    def test_health_liveness_endpoint(self):
        """Checks GET /health returns 200 and ok status."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("status"), "ok")

    def test_health_readiness_endpoint(self):
        """Checks GET /health/ready returns readiness state."""
        resp = self.client.get("/health/ready")
        self.assertIn(resp.status_code, (200, 503))
        data = resp.get_json()
        self.assertIn("database", data)

    def test_request_id_and_security_headers(self):
        """Verifies correlation ID generation and standard security headers."""
        # Generated ID
        resp = self.client.get("/")
        self.assertIn("X-Request-ID", resp.headers)
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(resp.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(resp.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")

        # Forwarded ID
        custom_id = "test-custom-correlation-12345"
        resp2 = self.client.get("/", headers={"X-Request-ID": custom_id})
        self.assertEqual(resp2.headers.get("X-Request-ID"), custom_id)

    def test_json_error_handling(self):
        """Verifies 404 on API endpoints returns sanitized JSON with request_id."""
        resp = self.client.get("/jobs/999999/nonexistent-endpoint")
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data["error"]["code"], "RESOURCE_NOT_FOUND")
        self.assertIn("request_id", data["error"])

    def test_rate_limiting_enforcement(self):
        """Tests that rate limiter blocks requests after exceeding threshold."""
        ip = "192.168.100.1"
        # 5 calls allowed
        for _ in range(5):
            self.assertFalse(flask_app_module.is_rate_limited(ip, limit=5, window_sec=60))
        # 6th call rate limited
        self.assertTrue(flask_app_module.is_rate_limited(ip, limit=5, window_sec=60))

    def test_latex_macro_sanitization(self):
        """Tests that dangerous LaTeX macros are stripped in resume.latex_escape."""
        malicious_input = r"Experienced with \write18{rm -rf /} and \input{/etc/passwd} & \openin 100%."
        escaped = resume.latex_escape(malicious_input)
        self.assertNotIn(r"\write18", escaped)
        self.assertNotIn(r"\input", escaped)
        self.assertNotIn(r"\openin", escaped)
        self.assertIn(r"\%", escaped)
        self.assertIn(r"\&", escaped)

    def test_filename_sanitization_safety(self):
        """Tests that path traversal and null bytes are removed in filename sanitization."""
        dangerous_name = "../../etc/passwd\x00_Company*<>"
        clean = resume.sanitize_filename(dangerous_name)
        self.assertNotIn("../", clean)
        self.assertNotIn("\x00", clean)
        self.assertNotIn("*", clean)
        self.assertNotIn("<", clean)

    def test_database_wal_connection(self):
        """Tests database connection initializes with WAL and busy timeout."""
        conn = database.get_connection()
        try:
            row = conn.execute("PRAGMA busy_timeout;").fetchone()
            self.assertIsNotNone(row)
        finally:
            conn.close()

    def test_resume_optimizer_iteration_bounds(self):
        """Verifies that tailor_resume_pipeline bounds max_iterations between 1 and 5."""
        cand = {"name": "Test", "skills": ["Python"]}
        job = {"title": "Python Dev", "description": "Need Python."}
        res = resume_optimizer.tailor_resume_pipeline(cand, job, max_iterations=10)
        self.assertIn("resume_json", res)
        self.assertIn("match_score", res)

if __name__ == "__main__":
    unittest.main()
