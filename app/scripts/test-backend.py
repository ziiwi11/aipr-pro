"""Run deterministic regression tests without reading a customer's Jev settings."""
import os
import pathlib
import subprocess
import sys
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='aipr-test-jev-') as isolated:
    env = {**os.environ, 'JEV_INTEGRATION': '0', 'JEV_CONFIG_DIR': isolated}
    raise SystemExit(subprocess.call([sys.executable, '-m', 'unittest', 'discover',
        '-s', str(root / 'backend'), '-p', 'test_*.py'], cwd=root, env=env))
