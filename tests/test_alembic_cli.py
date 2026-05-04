"""Migration sanity: single Alembic head (no branching drift in repo)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_single_head() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    lines = [ln.strip() for ln in r.stdout.strip().splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected exactly one head, got: {lines!r}"
