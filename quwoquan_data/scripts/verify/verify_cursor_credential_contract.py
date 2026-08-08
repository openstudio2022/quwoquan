"""Credential contract: external 0600 key file, no repo secret or old alias."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.cursor_credentials import cursor_key_file_issues
from core.paths import REPO_ROOT

RETIRED_ALIAS = "QWQ_CURSOR_API_KEY" + "FILE"
_PROHIBITED_SOURCE_FRAGMENTS = (
    ("allow_api_key_env_fallback" + "=True", "credential environment fallback"),
    ("os.environ[CURSOR_API_KEY_ENV]" + " =", "credential environment export"),
    ("sys.stdin." + "readline().strip()", "credential stdin transport"),
    ('input=f"{' + 'key}\\n"', "credential stdin transport"),
    ("Client.launch_" + "bridge(", "SDK callback-token argv transport"),
    ("child_env = os.environ." + "copy()", "runtime child environment passthrough"),
)

_RUNTIME_CHILD_HANDLER = Path(
    "quwoquan_data/scripts/content/execution/preflight/handler.py"
)
_RUNTIME_CHILD_SANITIZER = "child_env = cursor_safe_subprocess_env(os.environ)"


def cursor_credential_contract_issues(
    *,
    require_configured_file: bool = False,
    repo_root: Path = REPO_ROOT,
) -> list[str]:
    issues: list[str] = []
    if require_configured_file:
        issues.extend(cursor_key_file_issues())
    tracked = subprocess.run(
        ["git", "grep", "-n", "-I", "-e", RETIRED_ALIAS, "--", "."],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if tracked.stdout.strip():
        issues.extend(
            f"retired credential alias: {line}"
            for line in tracked.stdout.splitlines()[:20]
        )
    runtime_child = repo_root / _RUNTIME_CHILD_HANDLER
    if runtime_child.is_file():
        source = runtime_child.read_text(encoding="utf-8")
        if (
            "def _preflight_in_python" in source
            and _RUNTIME_CHILD_SANITIZER not in source
        ):
            issues.append(
                "forbidden Cursor runtime child sanitizer missing: "
                f"{_RUNTIME_CHILD_HANDLER.as_posix()}"
            )
    for fragment, reason in _PROHIBITED_SOURCE_FRAGMENTS:
        matches = subprocess.run(
            [
                "git",
                "grep",
                "-n",
                "-I",
                "-F",
                "-e",
                fragment,
                "--",
                "quwoquan_data/scripts",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if matches.stdout.strip():
            issues.extend(
                f"forbidden Cursor {reason}: {line}"
                for line in matches.stdout.splitlines()[:20]
            )
    return issues


def main() -> int:
    issues = cursor_credential_contract_issues(require_configured_file=False)
    if issues:
        print("[verify_cursor_credential_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_cursor_credential_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
