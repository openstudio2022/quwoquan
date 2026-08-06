#!/usr/bin/env python3

import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

from pathlib import Path
import re, sys
ROOT = REPO_ROOT
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
