"""Writing generated files: always LF, always UTF-8.

Every generated text file is committed and compared against a fresh run in
CI, on Linux. Writing through the platform default would give CRLF on
Windows and a diff on every line.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def write_text(rel: str | Path, text: str) -> Path:
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="\n", encoding="utf-8") as h:
        h.write(text if text.endswith("\n") else text + "\n")
    return p


def write_csv(rel: str | Path, header: list, rows: list) -> Path:
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as h:
        w = csv.writer(h, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    return p


def write_json(rel: str | Path, data) -> Path:
    return write_text(rel, json.dumps(data, indent=2, sort_keys=True))
