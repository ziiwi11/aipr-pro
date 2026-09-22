import json
import tempfile
import unittest
from pathlib import Path

from atomic_json_io import atomic_write_json


class AtomicJsonIoTest(unittest.TestCase):
    def test_replaces_json_without_leaving_partial_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "highwater.json"
            atomic_write_json(path, {"status": "ready", "name": "中文达人"})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["name"], "中文达人")
            self.assertEqual(list(path.parent.glob(".highwater.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
