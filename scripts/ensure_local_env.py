#!/usr/bin/env python3
"""Создаёт src/backend/.env из .env.example, если файла ещё нет."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "src/backend/.env.example"
TARGET = ROOT / "src/backend/.env"


def main() -> int:
    if TARGET.exists():
        print(f"Already exists: {TARGET}")
        return 0
    if not EXAMPLE.is_file():
        print(f"Missing template: {EXAMPLE}", file=sys.stderr)
        return 1
    shutil.copy(EXAMPLE, TARGET)
    print(f"Created {TARGET} from .env.example — добавьте учётные данные Saby.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
