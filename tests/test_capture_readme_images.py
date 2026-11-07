"""The capture script keeps docs/images/ for the dark README images.

Arguments are checked before any browser starts, so these runs need none.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "capture_readme_images.py"
IMAGES = ROOT / "docs" / "images"


@pytest.mark.parametrize(
    "args",
    [
        ["--scheme", "light"],
        ["--scheme", "light", "--out", str(IMAGES)],
        ["--scheme", "light", "--out", str(IMAGES / "light")],
        ["--states"],
        ["--states", "--out", str(IMAGES / "states")],
    ],
)
def test_light_and_state_captures_refuse_the_readme_images(args):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--browser", "unused", *args],
        capture_output=True, text=True, timeout=60,
    )

    assert result.returncode == 2
    assert "need --out with a directory outside docs/images/" in result.stderr
