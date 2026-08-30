#!/usr/bin/env python3
"""Hosted adapter for the canonical CI impact planner."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
CLI_ROOT = ROOT / "quwoquan_ops/cli"
for entry in (str(ROOT), str(CLI_ROOT)):
    if entry in sys.path:
        sys.path.remove(entry)
    sys.path.insert(0, entry)

from quwoquan_ops.cli.lib.evidence_fingerprint import (  # noqa: E402
    build_evidence_fingerprint,
    canonical_digest,
    validate_evidence_fingerprint,
)
from quwoquan_ops.ci.impact_planner_core import (  # noqa: E402
    SCOPE_NAMES,
    classify_impacts,
    planner_identity,
    validate_exact_sha,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--head-sha", default="HEAD")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--github-output", default="")
    parser.add_argument("--scope-receipt", default="")
    parser.add_argument(
        "--required-scope",
        action="append",
        choices=SCOPE_NAMES,
        default=[],
    )
    return parser.parse_args()


def git_changed_files(base_sha: str, head_sha: str) -> list[str]:
    if not base_sha:
        if head_sha != "HEAD":
            validate_exact_sha(head_sha, label="head_sha")
        return []
    validate_exact_sha(base_sha, label="base_sha")
    validate_exact_sha(head_sha, label="head_sha")
    proc = subprocess.run(
        ["git", "diff", "--name-only", base_sha, head_sha],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git diff failed")
    return proc.stdout.splitlines()


def classify(paths: list[str]) -> dict[str, bool]:
    """Compatibility projection over the canonical planner core."""

    return dict(classify_impacts(paths)["scopes"])


def write_github_outputs(path: str, impacted: dict[str, bool]) -> None:
    lines = [f"{key}={'true' if value else 'false'}" for key, value in impacted.items()]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _scope_fingerprint(
    *,
    base_sha: str,
    head_sha: str,
    changed_files: list[str],
    impacted: dict[str, bool],
    required_scopes: list[str],
) -> dict[str, object]:
    base = validate_exact_sha(base_sha, label="base_sha")
    head = validate_exact_sha(head_sha, label="head_sha")
    classified = classify_impacts(changed_files)
    identity = planner_identity()
    planner_source_digest = "sha256:" + hashlib.sha256(
        (ROOT / "quwoquan_ops/ci/impact_planner_core.py").read_bytes()
    ).hexdigest()
    scope_state = {
        scope: "required" if impacted[scope] else "not_required"
        for scope in SCOPE_NAMES
    }
    receipt = build_evidence_fingerprint(
        {
            "git": {"head_sha": head, "merge_base_sha": base},
            "workspace": {
                "tracked_digest": classified["path_digest"],
                "untracked_digest": canonical_digest([]),
                "deleted_digest": canonical_digest([]),
                "renamed_digest": canonical_digest([]),
                "symlink_digest": canonical_digest([]),
            },
            "assets": {
                "canonical_assets_digest": identity["digest"],
                "review_assets_digest": canonical_digest(scope_state),
            },
            "execution": {
                "commands_digest": canonical_digest(classified["paths"]),
                "toolchain_digest": canonical_digest(
                    {"adapter": "detect_ci_impacted_scopes.py", "version": 1}
                ),
                "provider_digest": canonical_digest(
                    {"required_scopes": sorted(set(required_scopes))}
                ),
                "generator_digest": planner_source_digest,
            },
        },
        captured_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        captured_by="hosted-impact-planner",
        captured_metadata={
            "changed_paths": classified["paths"],
            "scope_states": scope_state,
            "changed_paths_digest": classified["path_digest"],
            "planner_digest": planner_source_digest,
            "planner_identity_digest": identity["digest"],
            "planner_source": identity["source"],
            "planner_version": identity["version"],
        },
    )
    return validate_evidence_fingerprint(receipt)


def write_scope_receipt(
    path: str,
    *,
    base_sha: str,
    head_sha: str,
    changed_files: list[str],
    impacted: dict[str, bool],
    required_scopes: list[str] | None = None,
) -> None:
    payload = _scope_fingerprint(
        base_sha=base_sha,
        head_sha=head_sha,
        changed_files=changed_files,
        impacted=impacted,
        required_scopes=required_scopes or [],
    )
    receipt_path = Path(path)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    try:
        explicit_paths = bool(args.changed_file)
        if explicit_paths:
            changed_files = args.changed_file
            if args.scope_receipt or args.base_sha or args.head_sha != "HEAD":
                validate_exact_sha(args.base_sha, label="base_sha")
                validate_exact_sha(args.head_sha, label="head_sha")
        else:
            changed_files = git_changed_files(args.base_sha, args.head_sha)
        classified = classify_impacts(changed_files, fail_closed_empty=True)
        impacted = dict(classified["scopes"])
        if not classified["paths"]:
            print(
                "No diff range available; defaulting all scopes to impacted for safety.",
                file=sys.stderr,
            )
        for required_scope in args.required_scope:
            impacted[required_scope] = True
    except Exception as exc:  # noqa: BLE001
        print(f"detect_ci_impacted_scopes: FAIL: {exc}", file=sys.stderr)
        return 1

    if args.github_output:
        write_github_outputs(args.github_output, impacted)
    if args.scope_receipt:
        try:
            write_scope_receipt(
                args.scope_receipt,
                base_sha=args.base_sha,
                head_sha=args.head_sha,
                changed_files=list(classified["paths"]),
                impacted=impacted,
                required_scopes=args.required_scope,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"detect_ci_impacted_scopes: FAIL: {exc}", file=sys.stderr)
            return 1

    for key, value in impacted.items():
        print(f"{key}={'true' if value else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
