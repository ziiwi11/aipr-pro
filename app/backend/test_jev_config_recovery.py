import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import jev_local_client as client
class JevConfigRecoveryTests(unittest.TestCase):
    def test_wrong_json_shapes_do_not_crash_admission(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(client, 'ROOT', Path(directory)):
            for raw in ('[]', 'null', '"text"', '42', '{broken'):
                (Path(directory) / 'aipr-pro.json').write_text(raw)
                self.assertEqual(client.settings('aipr-pro'), {})
    def test_unreadable_enable_file_is_disabled(self):
        with patch.dict('os.environ', {'JEV_INTEGRATION': '1'}), patch.object(Path, 'exists', return_value=True), patch.object(Path, 'read_text', side_effect=PermissionError('denied')):
            self.assertFalse(client.enabled('aipr-pro'))
