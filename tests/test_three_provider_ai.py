import time
import unittest
from unittest.mock import patch, MagicMock

import ai
from ai import AIProvider, AIRouter

class TestThreeProviderAIFailover(unittest.TestCase):

    def setUp(self):
        self.router = AIRouter()
        self.router.primary = AIProvider("ProviderA", "key_a", "https://api.a.com/v1", "model_a")
        self.router.secondary = AIProvider("ProviderB", "key_b", "https://api.b.com/v1", "model_b")
        self.router.third = AIProvider("ProviderC", "key_c", "https://api.c.com/v1", "model_c")

        self.cand_profile = {
            "name": "Alex Smith",
            "email": "alex@example.com",
            "phone": "555-0100",
            "skills": ["Python", "SQL", "Flask"],
            "education": [{"degree": "BS CS", "institution": "Tech Uni", "graduation_year": 2026}],
            "experience": [{"company": "Acme Inc", "role": "Software Developer", "start_date": "2025-01", "end_date": "2025-06", "bullets": ["Developed APIs"]}]
        }

    def test_1_provider_a_succeeds(self):
        """1. Provider A succeeds -> A called, B not called, C not called."""
        with patch.object(self.router.primary, 'call_chat_completion', return_value='{"res": "ok_a"}') as mock_a, \
             patch.object(self.router.secondary, 'call_chat_completion') as mock_b, \
             patch.object(self.router.third, 'call_chat_completion') as mock_c:

            res = self.router.call_ai("Test Prompt")
            self.assertEqual(res, '{"res": "ok_a"}')
            mock_a.assert_called_once()
            mock_b.assert_not_called()
            mock_c.assert_not_called()

    def test_2_provider_a_429_fails_over_to_b(self):
        """2. Provider A returns 429 -> A enters cooldown -> B called & succeeds, C not called."""
        with patch.object(self.router.primary, 'call_chat_completion', return_value=None), \
             patch.object(self.router.secondary, 'call_chat_completion', return_value='{"res": "ok_b"}') as mock_b, \
             patch.object(self.router.third, 'call_chat_completion') as mock_c:

            self.router.primary.mark_rate_limited(60.0)
            res = self.router.call_ai("Test Prompt")
            self.assertEqual(res, '{"res": "ok_b"}')
            mock_b.assert_called_once()
            mock_c.assert_not_called()

    def test_3_provider_a_and_b_fail_fails_over_to_c(self):
        """3. Provider A + B fail -> A called, B called, C called & succeeds."""
        with patch.object(self.router.primary, 'call_chat_completion', return_value=None) as mock_a, \
             patch.object(self.router.secondary, 'call_chat_completion', return_value=None) as mock_b, \
             patch.object(self.router.third, 'call_chat_completion', return_value='{"res": "ok_c"}') as mock_c:

            res = self.router.call_ai("Test Prompt")
            self.assertEqual(res, '{"res": "ok_c"}')
            mock_a.assert_called_once()
            mock_b.assert_called_once()
            mock_c.assert_called_once()

    def test_4_all_providers_fail_controlled_failure(self):
        """4. Provider A + B + C all fail -> Controlled AI failure, returns None."""
        with patch.object(self.router.primary, 'call_chat_completion', return_value=None), \
             patch.object(self.router.secondary, 'call_chat_completion', return_value=None), \
             patch.object(self.router.third, 'call_chat_completion', return_value=None):

            res = self.router.call_ai("Test Prompt")
            self.assertIsNone(res)

    def test_5_provider_a_cooldown_active_skipped(self):
        """5. Provider A active cooldown -> A skipped, B attempted."""
        self.router.primary.mark_rate_limited(120.0)

        with patch.object(self.router.primary, 'call_chat_completion') as mock_a, \
             patch.object(self.router.secondary, 'call_chat_completion', return_value='{"res": "ok_b"}') as mock_b:

            res = self.router.call_ai("Test Prompt")
            self.assertEqual(res, '{"res": "ok_b"}')
            mock_a.assert_not_called()
            mock_b.assert_called_once()

    def test_6_a_and_b_cooldown_active_calls_c(self):
        """6. A and B cooldown active -> A skipped, B skipped, C attempted."""
        self.router.primary.mark_rate_limited(120.0)
        self.router.secondary.mark_rate_limited(120.0)

        with patch.object(self.router.primary, 'call_chat_completion') as mock_a, \
             patch.object(self.router.secondary, 'call_chat_completion') as mock_b, \
             patch.object(self.router.third, 'call_chat_completion', return_value='{"res": "ok_c"}') as mock_c:

            res = self.router.call_ai("Test Prompt")
            self.assertEqual(res, '{"res": "ok_c"}')
            mock_a.assert_not_called()
            mock_b.assert_not_called()
            mock_c.assert_called_once()

    def test_7_cooldown_expiration_restores_eligibility(self):
        """7. A cooldown expires -> A becomes eligible again and is preferred over B/C."""
        self.router.primary.rate_limit_reset_time = time.time() - 1.0  # Expired

        with patch.object(self.router.primary, 'call_chat_completion', return_value='{"res": "ok_a"}') as mock_a, \
             patch.object(self.router.secondary, 'call_chat_completion') as mock_b:

            res = self.router.call_ai("Test Prompt")
            self.assertEqual(res, '{"res": "ok_a"}')
            mock_a.assert_called_once()
            mock_b.assert_not_called()

    @patch("requests.post")
    def test_8_retry_after_header_respected(self, mock_post):
        """8. Verify HTTP 429 Retry-After header is parsed and applied to cooldown."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "45.0"}
        mock_post.return_value = mock_resp

        prov = AIProvider("TestProv", "valid_key", "https://api.test.com/v1", "model_test")
        res = prov.call_chat_completion("Prompt")
        self.assertIsNone(res)
        self.assertFalse(prov.is_available())
        self.assertGreaterEqual(prov.rate_limit_reset_time, time.time() + 40.0)

    @patch("requests.post")
    def test_9_missing_retry_after_uses_default_cooldown(self, mock_post):
        """9. Missing Retry-After header defaults to 60.0s cooldown."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        prov = AIProvider("TestProv", "valid_key", "https://api.test.com/v1", "model_test")
        res = prov.call_chat_completion("Prompt")
        self.assertIsNone(res)
        self.assertFalse(prov.is_available())

    @patch("requests.post")
    def test_10_auth_errors_prevent_endless_retries(self, mock_post):
        """10. 401/403 auth errors mark provider disabled so it is not endlessly retried."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp

        prov = AIProvider("TestProv", "invalid_key", "https://api.test.com/v1", "model_test")
        res = prov.call_chat_completion("Prompt")
        self.assertIsNone(res)
        self.assertFalse(prov.is_available())

    def test_11_response_normalization_identical(self):
        """11. Provider response normalization works identically regardless of provider."""
        raw_json_a = '{"recommendation": "strong_match", "score": 90, "eligibility": true, "matching_requirements": ["Python"]}'
        raw_json_c = '{"recommendation": "strong_match", "score": 90, "eligibility": true, "matching_requirements": ["Python"]}'

        parsed_a = ai.robust_json_loads(raw_json_a)
        parsed_c = ai.robust_json_loads(raw_json_c)
        self.assertEqual(parsed_a, parsed_c)

    def test_12_resume_tailoring_passes_factuality_validation(self):
        """12. Resume tailoring passes validate_tailored_resume() regardless of provider."""
        raw_tailored = {
            "header": {"name": "Alex Smith", "email": "alex@example.com", "phone": "555-0100"},
            "summary": "Experienced engineer with hands-on technical skills.",
            "skills": {"languages": ["Python", "SQL"]},
            "experience": [
                {
                    "company": "Acme Inc",
                    "role": "Software Developer",
                    "bullets": ["Developed REST APIs using Python and Flask."]
                }
            ],
            "projects": []
        }

        validated = ai.validate_tailored_resume(raw_tailored, self.cand_profile)
        self.assertEqual(validated["header"]["name"], "Alex Smith")
        self.assertIn("Python", validated["skills"]["languages"])

    def test_14_nemotron_openrouter_markdown_and_thinking_tags_extracted(self):
        """14. Nemotron/OpenRouter responses with reasoning tags or markdown blocks are normalized to clean JSON."""
        response_with_think = """
        <think>
        Analyzing candidate fit...
        Core skills match Python and SQL.
        </think>
        Here is the JSON evaluation:
        ```json
        {
          "recommendation": "good_match",
          "score": 88,
          "eligibility": true,
          "matching_requirements": ["Python", "SQL"]
        }
        ```
        Hope this helps!
        """
        parsed = ai.robust_json_loads(response_with_think)
        self.assertEqual(parsed["score"], 88)
        self.assertEqual(parsed["recommendation"], "good_match")
        self.assertIn("Python", parsed["matching_requirements"])

    def test_15_trailing_commas_and_unescaped_newlines_handled(self):
        """15. Robust JSON loader cleans trailing commas and unescaped line breaks."""
        raw_bad_json = """
        {
          "recommendation": "strong_match",
          "score": 92,
          "matching_requirements": ["Python", "SQL",],
          "reason": "Great candidate
with strong Python experience.",
        }
        """
        parsed = ai.robust_json_loads(raw_bad_json)
        self.assertEqual(parsed["score"], 92)
        self.assertEqual(parsed["recommendation"], "strong_match")

    def test_16_openrouter_400_retry_without_response_format(self):
        """16. OpenRouter returning 400 Bad Request for response_format triggers a successful retry without response_format."""
        prov = AIProvider("OpenRouterNemotron", "or_key", "https://openrouter.ai/api/v1", "nvidia/nemotron-3.5-lightning:free")
        
        mock_400 = MagicMock()
        mock_400.status_code = 400

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {
            "choices": [
                {"message": {"content": '{"recommendation": "good_match", "score": 85}'}}
            ]
        }

        with patch("requests.post", side_effect=[mock_400, mock_200]) as mock_post:
            res = prov.call_chat_completion("Evaluate job")
            self.assertEqual(res, '{"recommendation": "good_match", "score": 85}')
            self.assertEqual(mock_post.call_count, 2)
            # Second call should not have response_format
            second_call_json = mock_post.call_args_list[1][1]["json"]
            self.assertNotIn("response_format", second_call_json)

if __name__ == "__main__":
    unittest.main()
