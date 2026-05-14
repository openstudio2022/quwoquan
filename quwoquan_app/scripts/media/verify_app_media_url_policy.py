#!/usr/bin/env python3
from pathlib import Path
import re, sys
ROOT = Path(__file__).resolve().parents[3]
forbidden = re.compile(r"cdn\.example/.+\+|origin\.example/.+\+|/i/\$\{")
violations = []
for path in (ROOT / "quwoquan_app/lib").rglob("*.dart"):
    text = path.read_text(errors="ignore")
    if forbidden.search(text):
        violations.append(path.relative_to(ROOT).as_posix())
if violations:
    print("[app-media-url-policy] FAIL")
    print("\n".join(violations))
    sys.exit(2)
print("[app-media-url-policy] OK")
