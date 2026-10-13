# -*- coding: utf-8 -*-
"""Kept so ``启动编辑器.bat`` and muscle memory keep working.

The real entry point is ``main.py`` — that is what the frozen EXE runs, and it
is where the logging and the crash handler live.  Duplicating any of that here
would be a second place to keep in step, so this file defers instead.

Unlike the packaged build this prints to the console, because a console is
right there when you launch it from a terminal.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import main       # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
