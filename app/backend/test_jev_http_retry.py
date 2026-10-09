import io
import json
import unittest
import urllib.error
from unittest.mock import patch, MagicMock
import jev_local_client as client


class JevHttpRetryTests(unittest.TestCase):
    def test_server_error_retries_then_succeeds_and_honors_retry_after(self):
        response = MagicMock()
        response.__enter__.return_value = io.StringIO(json.dumps({'answers': {}}))
        opener = MagicMock()
        opener.open.side_effect = [urllib.error.HTTPError('https://api.typesafe.ai', 503,
            'unavailable', {'Retry-After': '7'}, None), response]
        with patch.object(client, 'enabled', return_value=True), patch.object(client, 'settings',
                return_value={'backend': 'cloud', 'api_key': 'test-only'}), \
                patch.object(client.urllib.request, 'build_opener', return_value=opener), \
                patch.object(client.time, 'sleep') as sleep, patch.object(client, 'record_usage'):
            result = client.decide({'state': {}, 'questions': {}}, 'test')
        self.assertEqual(result['answers'], {})
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_called_once_with(7)

    def test_payment_error_is_not_blindly_retried(self):
        opener = MagicMock()
        opener.open.side_effect = urllib.error.HTTPError('https://api.typesafe.ai', 402, 'payment', {}, None)
        with patch.object(client, 'enabled', return_value=True), patch.object(client, 'settings',
                return_value={'backend': 'cloud', 'api_key': 'test-only'}), \
                patch.object(client.urllib.request, 'build_opener', return_value=opener), \
                patch.object(client.time, 'sleep') as sleep, patch.object(client, 'record_usage'):
            with self.assertRaises(urllib.error.HTTPError):
                client.decide({'state': {}, 'questions': {}}, 'test')
        self.assertEqual(opener.open.call_count, 1)
        sleep.assert_not_called()
