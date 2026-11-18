"""The FastAPI app starts the way uvicorn starts it.

main.py populates its own short list of Django apps rather than INSTALLED_APPS,
so a router importing a model from an app missing there crashes the server at
import. pytest-django loads every installed app before main is ever imported,
which hides it: the opengraph router passed all its tests while the dev server
it reloaded into served nothing on /api/v2. Hence a fresh interpreter.
"""
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]


def test_main_imports_in_a_fresh_interpreter():
    result = subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=SRC,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "backend.settings"},
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr[-3000:]
