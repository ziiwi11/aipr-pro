from __future__ import annotations

import sys


def configure_utf8_stdout() -> None:
    """Keep worker JSON logs valid on Chinese Windows consoles."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
