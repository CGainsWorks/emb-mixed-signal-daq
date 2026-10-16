"""House style and hygiene for every committed text file.

* No em or en dashes anywhere, code comments included.
* No comma before "and" or "but". Checked over whole file contents, not
  line by line, because in wrapped prose the comma often ends one line and
  the conjunction starts the next.
* British spelling in the prose.
* No carriage returns and no absolute Windows paths in generated files.
"""

import re
import subprocess

import pytest

from conftest import ROOT

TEXT_SUFFIXES = {".md", ".py", ".c", ".h", ".cir", ".csv", ".json", ".yml", ".txt",
                 ".sh", ".kicad_sch", ".toml", ""}


def tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout
    files = [ROOT / p for p in out.splitlines()]
    files += [ROOT / p for p in subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT,
        capture_output=True, text=True).stdout.splitlines()]
    return [f for f in files if f.is_file() and f.suffix in TEXT_SUFFIXES
            and f.name != "LICENSE"]


FILES = tracked()
AMERICAN = re.compile(r"\b(analyz\w*|behavior\w*|colo(?:r|rs)\b|center\w*|modeling|"
                      r"normaliz\w*|characteriz\w*|optimiz\w*|minimiz\w*|maximiz\w*|"
                      r"stabiliz\w*|digitiz\w*|initializ\w*|summariz\w*|organiz\w*|"
                      r"meters?\b|liters?\b|program\b)", re.I)


def ids(files):
    return [str(f.relative_to(ROOT)) for f in files]


@pytest.mark.parametrize("path", FILES, ids=ids(FILES))
def test_no_dashes_or_serial_commas(path):
    text = path.read_text(encoding="utf-8")
    assert chr(0x2014) not in text and chr(0x2013) not in text, "em or en dash"
    m = re.search(r",\s+(and|but)\b", text)
    assert m is None, f"comma before conjunction: {text[max(0, m.start() - 40):m.end() + 10]!r}"
    assert "\r" not in text, "carriage return"


MD = [f for f in FILES if f.suffix == ".md"]


@pytest.mark.parametrize("path", MD, ids=ids(MD))
def test_british_spelling_in_prose(path):
    text = path.read_text(encoding="utf-8")
    hits = sorted({m.group(0) for m in AMERICAN.finditer(text)})
    assert not hits, f"American spelling: {hits}"


def test_no_absolute_windows_paths():
    for f in FILES:
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"[A-Za-z]:\\\\?Users", text), f"absolute path in {f}"
