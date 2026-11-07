"""The coverage script, run as a command on the frozen snapshot.

AGENTS.md makes it the source of strike-coverage facts, so its blank-cell
counts are pinned to the log-moneyness-surface spec table.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "snapshot_coverage.py"


def _run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=120,
    )


@pytest.mark.parametrize(
    "range_args, source, bounds, blank, total",
    [
        (["Core"], "Exchange mark", "0.80–1.20", 6, 504),
        (["Wide"], "Exchange mark", "0.50–2.00", 155, 936),
        (["All listed"], "Exchange mark", "0.24–3.04", 263, 1092),
        (["Core"], "Quote midpoint", "0.80–1.20", 67, 504),
        (["Wide"], "Quote midpoint", "0.50–2.00", 257, 936),
        (["All listed"], "Quote midpoint", "0.24–3.04", 369, 1092),
        (["0.5", "2.0"], "Exchange mark", "0.50–2.00", 155, 936),
    ],
)
def test_surface_blank_counts_match_the_dashboard(range_args, source, bounds, blank, total):
    result = _run("--range", *range_args, "--source", source)

    assert result.returncode == 0, result.stderr
    header = re.search(r"Surface cells by expiry, (.+), K / S (\S+) · (\d+) of (\d+)", result.stdout)
    assert header.groups() == (source, bounds, str(blank), str(total))


@pytest.mark.parametrize("range_args", [["1.2", "0.8"], ["Extended"], ["0", "1"]])
def test_invalid_range_exits_with_a_usage_message(range_args):
    result = _run("--range", *range_args)

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "--range takes one of Core, Wide, All listed or LOW HIGH" in result.stderr
