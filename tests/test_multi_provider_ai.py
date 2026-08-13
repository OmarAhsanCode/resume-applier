import unittest
from unittest.mock import patch, MagicMock
from ai import AIProvider, AIRouter

class TestMultiProviderAI(unittest.TestCase):

    def test_primary_provider_success(self):
        router = AIRouter()
        router.primary = AIProvider("PrimaryMock", "key_1", "https://api.groq.com/openai/v1", "model_1")
        router.secondary = AIProvider("SecondaryMock", "key_2", "https://api.secondary.com/v1", "model_2")

        with patch.object(router.primary, 'call_chat_completion', return_value='{"status": "primary_ok"}') as mock_p:
            with patch.object(router.secondary, 'call_chat_completion') as mock_s:
                res = router.call_ai("Test prompt")
                self.assertEqual(res, '{"status": "primary_ok"}')
                mock_p.assert_called_once()
                mock_s.assert_not_called()

    def test_primary_429_failover_to_secondary(self):
        router = AIRouter()
        router.primary = AIProvider("PrimaryMock", "key_1", "https://api.groq.com/openai/v1", "model_1")
        router.secondary = AIProvider("SecondaryMock", "key_2", "https://api.secondary.com/v1", "model_2")

        # Simulate Primary returning 429 and marking itself rate-limited
        with patch.object(router.primary, 'call_chat_completion', return_value=None) as mock_p:
            router.primary.mark_rate_limited(60.0)
            with patch.object(router.secondary, 'call_chat_completion', return_value='{"status": "secondary_ok"}') as mock_s:
                res = router.call_ai("Test prompt")
                self.assertEqual(res, '{"status": "secondary_ok"}')
                # Primary is marked unavailable so not called; Secondary called and succeeds
                mock_s.assert_called_once()

    def test_all_providers_fail(self):
        router = AIRouter()
        router.primary = AIProvider("PrimaryMock", "key_1", "https://api.groq.com/openai/v1", "model_1")
        router.secondary = AIProvider("SecondaryMock", "key_2", "https://api.secondary.com/v1", "model_2")
        router.third = AIProvider("ThirdMock", "key_3", "https://api.third.com/v1", "model_3")

        with patch.object(router.primary, 'call_chat_completion', return_value=None):
            with patch.object(router.secondary, 'call_chat_completion', return_value=None):
                with patch.object(router.third, 'call_chat_completion', return_value=None):
                    res = router.call_ai("Test prompt")
                    self.assertIsNone(res)

if __name__ == '__main__':
    unittest.main()
