#!/usr/bin/env python3
"""验证 S0 知识资产迁移夹具可从冻结 Git 对象确定性重算。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = ROOT / "quwoquan_ops/policies/migrations/knowledge_assets_s0_v1.json"
SCHEMA_VERSION = "knowledge-assets-s0-migration/v1"
FIXTURE_VERSION = "1.0.0"
PARSER_VERSION = "ledger-to-fixture/1.0.0"
EXPECTED_HEAD = "e6af548e4a55748574a1ca6c021103e75f39fffc"
EXPECTED_SOURCE_FILES = 53
EXPECTED_ROWS = 333
DIGEST_FORMULA = (
    "source_path + NUL + source_anchor + NUL + fact_type + NUL + "
    "normalized_clause_identity"
)
ACTIONS = {"migrate_to_canonical", "retain_existing_coverage", "discard"}
DISPOSITIONS = {"canonical", "existing_coverage", "discard"}
STATUSES = {"resolved"}
BINDING_TYPES = {
    "markdown-anchor",
    "agents-heading",
    "contract-yaml-key",
    "make-target",
    "non-anchor-owner",
    "none",
}
ROW_FIELDS = {
    "source_path",
    "source_anchor",
    "source_blob_sha256",
    "normalized_clause_identity",
    "clause_digest",
    "fact_type",
    "action",
    "disposition",
    "target_path",
    "target_anchor",
    "binding_type",
    "evidence",
    "dangling_refs",
    "terminal_status",
    "discard_reason",
    "historical_ledger",
    "historical_digest_12",
    "parser_version",
    "historical_parser_version",
    "historical_input_head",
    "fixture_version",
    "historical_action",
    "historical_terminal_status",
    "final_adjudication_id",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_bytes(root: Path, head: str, source_path: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{head}:{source_path}"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"冻结 source 不可读: {source_path}: {detail}")
    return completed.stdout


def _digest(row: dict[str, Any]) -> str:
    identity = "\0".join(
        str(row[key])
        for key in (
            "source_path",
            "source_anchor",
            "fact_type",
            "normalized_clause_identity",
        )
    )
    return _sha256(identity.encode("utf-8"))


def _anchor_exists(path: Path, anchor: str, binding_type: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if binding_type == "markdown-anchor":
        escaped = re.escape(anchor)
        return bool(
            re.search(rf'<a\s+id=["\']{escaped}["\']\s*>', text, re.IGNORECASE)
            or re.search(rf"^#+\s+.*\b{escaped}\b", text, re.IGNORECASE | re.MULTILINE)
        )
    if binding_type == "agents-heading":
        return bool(re.search(rf"^#+\s+{re.escape(anchor)}\s*$", text, re.MULTILINE))
    if binding_type == "contract-yaml-key":
        return bool(re.search(rf"^\s*{re.escape(anchor)}\s*:", text, re.MULTILINE))
    if binding_type == "make-target":
        return bool(re.search(rf"^{re.escape(anchor)}\s*:", text, re.MULTILINE))
    return True


def verify_fixture(fixture_path: Path, *, root: Path = ROOT) -> list[str]:
    issues: list[str] = []
    try:
        document = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"fixture 不可读取: {exc}"]
    if not isinstance(document, dict):
        return ["fixture 顶层必须是 object"]

    exact_top = {
        "schema_version",
        "fixture_version",
        "parser_version",
        "historical_input_head",
        "canonical_digest",
        "expected_source_file_count",
        "expected_row_count",
        "source_files",
        "rows",
        "final_adjudications",
    }
    if set(document) != exact_top:
        issues.append(
            "fixture 顶层字段漂移: "
            f"missing={sorted(exact_top - set(document))}, "
            f"extra={sorted(set(document) - exact_top)}"
        )
    for field, expected in (
        ("schema_version", SCHEMA_VERSION),
        ("fixture_version", FIXTURE_VERSION),
        ("parser_version", PARSER_VERSION),
        ("historical_input_head", EXPECTED_HEAD),
        ("expected_source_file_count", EXPECTED_SOURCE_FILES),
        ("expected_row_count", EXPECTED_ROWS),
    ):
        if document.get(field) != expected:
            issues.append(f"{field} 必须精确为 {expected!r}")
    digest_contract = document.get("canonical_digest")
    expected_digest_contract = {
        "algorithm": "sha256",
        "formula": DIGEST_FORMULA,
        "encoding": "UTF-8",
        "hex_length": 64,
        "identity_requirement": (
            "normalized_clause_identity binds frozen source_blob_sha256, "
            "source_anchor, and historical ledger summary"
        ),
    }
    if digest_contract != expected_digest_contract:
        issues.append("canonical_digest 契约漂移")

    source_files = document.get("source_files")
    rows = document.get("rows")
    if not isinstance(source_files, list):
        issues.append("source_files 必须是 list")
        source_files = []
    if not isinstance(rows, list):
        issues.append("rows 必须是 list")
        rows = []
    if len(source_files) != EXPECTED_SOURCE_FILES:
        issues.append(f"source file count drift: expected=53 actual={len(source_files)}")
    if len(rows) != EXPECTED_ROWS:
        issues.append(f"row count drift: expected=333 actual={len(rows)}")

    source_entries: dict[str, str] = {}
    for index, entry in enumerate(source_files):
        if not isinstance(entry, dict) or set(entry) != {
            "source_path",
            "source_blob_sha256",
        }:
            issues.append(f"source_files[{index}] schema 非法")
            continue
        source_path = entry.get("source_path")
        source_digest = entry.get("source_blob_sha256")
        if not isinstance(source_path, str) or not source_path:
            issues.append(f"source_files[{index}] source_path 非法")
            continue
        if source_path in source_entries:
            issues.append(f"source set 重复: {source_path}")
        source_entries[source_path] = str(source_digest)

    head = str(document.get("historical_input_head", ""))
    source_bytes: dict[str, bytes] = {}
    for source_path, expected_digest in source_entries.items():
        try:
            blob = _git_bytes(root, head, source_path)
        except ValueError as exc:
            issues.append(str(exc))
            continue
        source_bytes[source_path] = blob
        actual = _sha256(blob)
        if actual != expected_digest:
            issues.append(
                f"source bytes drift: {source_path} expected={expected_digest} actual={actual}"
            )

    row_source_set: set[str] = set()
    digest_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    final_counts: Counter[str] = Counter()
    for index, row in enumerate(rows):
        label = f"rows[{index}]"
        if not isinstance(row, dict):
            issues.append(f"{label} 必须是 object")
            continue
        missing = ROW_FIELDS - set(row)
        extra = set(row) - ROW_FIELDS
        if missing or extra:
            issues.append(f"{label} schema drift: missing={sorted(missing)} extra={sorted(extra)}")
        for field in (
            "source_path",
            "source_anchor",
            "source_blob_sha256",
            "normalized_clause_identity",
            "clause_digest",
            "fact_type",
            "action",
            "disposition",
            "binding_type",
            "evidence",
            "terminal_status",
            "historical_ledger",
            "historical_digest_12",
            "parser_version",
            "historical_parser_version",
            "historical_input_head",
            "fixture_version",
            "historical_action",
        ):
            if not isinstance(row.get(field), str) or not row.get(field):
                issues.append(f"{label}.{field} 必须是非空字符串")
        source_path = str(row.get("source_path", ""))
        row_source_set.add(source_path)
        if source_path not in source_entries:
            issues.append(f"{label} source 不在 53-file source set: {source_path}")
        elif row.get("source_blob_sha256") != source_entries[source_path]:
            issues.append(f"{label} source bytes drift: row/source_files digest 不一致")
        expected_identity = (
            f"source-blob-sha256:{row.get('source_blob_sha256')}\n"
            f"source-anchor:{row.get('source_anchor')}\n"
            f"historical-summary:{str(row.get('evidence', '')).strip()}"
        )
        if row.get("normalized_clause_identity") != expected_identity:
            issues.append(f"{label} normalized clause identity drift")
        digest = str(row.get("clause_digest", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            issues.append(f"{label} clause_digest 必须是 64 位小写 sha256")
        elif digest != _digest(row):
            issues.append(f"{label} digest drift: expected={_digest(row)} actual={digest}")
        digest_rows[digest].append(row)
        if row.get("parser_version") != PARSER_VERSION:
            issues.append(f"{label} parser_version 非法")
        if row.get("historical_parser_version") not in {
            "cursor-rules-v0",
            "review-assets-1-v0",
            "review-assets-2-v0",
        }:
            issues.append(f"{label} historical_parser_version 非法")
        if row.get("historical_input_head") != EXPECTED_HEAD:
            issues.append(f"{label} historical_input_head 漂移")
        if row.get("fixture_version") != FIXTURE_VERSION:
            issues.append(f"{label} fixture_version 漂移")
        action = row.get("action")
        disposition = row.get("disposition")
        status = row.get("terminal_status")
        binding_type = row.get("binding_type")
        if action not in ACTIONS:
            issues.append(f"{label} action 非闭集值: {action}")
        if disposition not in DISPOSITIONS:
            issues.append(f"{label} disposition 非闭集值: {disposition}")
        if status not in STATUSES:
            issues.append(f"{label} unresolved blocker: terminal_status={status}")
        if binding_type not in BINDING_TYPES:
            issues.append(f"{label} binding_type 非闭集值: {binding_type}")
        if not isinstance(row.get("dangling_refs"), list):
            issues.append(f"{label} dangling_refs 必须是 list")
        elif row["dangling_refs"]:
            issues.append(f"{label} dangling refs 未清零: {row['dangling_refs']}")
        if disposition == "discard":
            if not isinstance(row.get("discard_reason"), str) or not row["discard_reason"].strip():
                issues.append(f"{label} discard 必须有 reason")
            if row.get("target_path") is not None or row.get("target_anchor") is not None:
                issues.append(f"{label} discard 不得声明 target")
        else:
            if row.get("discard_reason") is not None:
                issues.append(f"{label} 非 discard 不得有 discard_reason")
            target_path = row.get("target_path")
            if not isinstance(target_path, str) or not target_path:
                issues.append(f"{label} resolved disposition 缺 target_path")
            else:
                target = root / target_path
                if not target.is_file():
                    issues.append(f"{label} target missing: {target_path}")
                else:
                    target_anchor = row.get("target_anchor")
                    if binding_type in {
                        "markdown-anchor",
                        "agents-heading",
                        "contract-yaml-key",
                        "make-target",
                    }:
                        if not isinstance(target_anchor, str) or not target_anchor:
                            issues.append(f"{label} anchor missing: {target_path}")
                        elif not _anchor_exists(target, target_anchor, str(binding_type)):
                            issues.append(
                                f"{label} anchor missing: {target_path}#{target_anchor}"
                            )
                    elif binding_type == "non-anchor-owner" and target_anchor is not None:
                        issues.append(f"{label} non-anchor owner 不得伪造 anchor")
        if isinstance(disposition, str):
            final_counts[disposition] += 1

    adjudications = document.get("final_adjudications")
    if not isinstance(adjudications, list):
        issues.append("final_adjudications 必须是 list")
        adjudications = []
    if len(adjudications) != 17:
        issues.append(f"17 blocker adjudication count drift: actual={len(adjudications)}")
    adjudication_ids: set[str] = set()
    adjudication_counts: Counter[str] = Counter()
    adjudication_by_id: dict[str, dict[str, Any]] = {}
    row_keys = {(row.get("source_path"), row.get("source_anchor")) for row in rows}
    covered_keys: set[tuple[Any, Any]] = set()
    for index, adjudication in enumerate(adjudications):
        label = f"final_adjudications[{index}]"
        expected_fields = {
            "id", "disposition", "summary", "covered_rows", "terminal_status"
        }
        if not isinstance(adjudication, dict) or set(adjudication) != expected_fields:
            issues.append(f"{label} schema 非法")
            continue
        adjudication_id = adjudication.get("id")
        if not isinstance(adjudication_id, str) or not re.fullmatch(r"ADJ-\d{3}", adjudication_id):
            issues.append(f"{label}.id 非法")
        elif adjudication_id in adjudication_ids:
            issues.append(f"{label}.id 重复: {adjudication_id}")
        else:
            adjudication_ids.add(adjudication_id)
            adjudication_by_id[adjudication_id] = adjudication
        disposition = adjudication.get("disposition")
        if disposition not in DISPOSITIONS:
            issues.append(f"{label}.disposition 非闭集值")
        else:
            adjudication_counts[str(disposition)] += 1
        if adjudication.get("terminal_status") != "resolved":
            issues.append(f"{label} unresolved blocker")
        if not isinstance(adjudication.get("summary"), str) or not adjudication["summary"].strip():
            issues.append(f"{label}.summary 缺失")
        covered_rows = adjudication.get("covered_rows")
        if not isinstance(covered_rows, list) or not covered_rows:
            issues.append(f"{label}.covered_rows 缺失")
        else:
            for covered_index, covered in enumerate(covered_rows):
                if not isinstance(covered, dict) or set(covered) != {
                    "source_path", "source_anchor"
                }:
                    issues.append(f"{label}.covered_rows[{covered_index}] schema 非法")
                    continue
                key = (covered.get("source_path"), covered.get("source_anchor"))
                if key not in row_keys:
                    issues.append(f"{label}.covered_rows[{covered_index}] 不存在于 fixture rows")
                if key in covered_keys:
                    issues.append(f"{label}.covered_rows[{covered_index}] 被多个裁决覆盖")
                covered_keys.add(key)
    if adjudication_ids != {f"ADJ-{number:03d}" for number in range(1, 18)}:
        issues.append(f"17 blocker adjudication id set drift: {sorted(adjudication_ids)}")
    if adjudication_counts != Counter(
        {"canonical": 8, "existing_coverage": 4, "discard": 5}
    ):
        issues.append(f"17 blocker disposition drift: {dict(adjudication_counts)}")
    historical_blockers = [
        row for row in rows if row.get("historical_terminal_status") is not None
    ]
    if len(historical_blockers) != 17:
        issues.append(f"historical blocker row count drift: actual={len(historical_blockers)}")
    for index, row in enumerate(rows):
        adjudication_id = row.get("final_adjudication_id")
        if row.get("historical_terminal_status") is not None:
            if row.get("historical_terminal_status") != "GATE_BLOCK(owner_or_anchor_missing)":
                issues.append(f"rows[{index}] historical blocker code 漂移")
            if adjudication_id not in adjudication_ids:
                issues.append(f"rows[{index}] historical blocker 缺最终裁决")
            elif adjudication_by_id[adjudication_id].get("disposition") != row.get("disposition"):
                issues.append(f"rows[{index}] blocker disposition 与最终裁决不一致")
        elif adjudication_id is not None and adjudication_id not in adjudication_ids:
            issues.append(f"rows[{index}] final_adjudication_id 悬空")
        if adjudication_id is not None:
            key = (row.get("source_path"), row.get("source_anchor"))
            adjudication = adjudication_by_id.get(adjudication_id)
            expected_keys = {
                (item.get("source_path"), item.get("source_anchor"))
                for item in (adjudication or {}).get("covered_rows", [])
                if isinstance(item, dict)
            }
            if key not in expected_keys:
                issues.append(f"rows[{index}] final_adjudication_id 未覆盖本行")
            elif adjudication.get("disposition") != row.get("disposition"):
                issues.append(f"rows[{index}] disposition 与 final_adjudication_id 不一致")

    if row_source_set != set(source_entries):
        issues.append(
            "source set drift: "
            f"rows_only={sorted(row_source_set - set(source_entries))}, "
            f"files_only={sorted(set(source_entries) - row_source_set)}"
        )
    for digest, grouped in digest_rows.items():
        if len(grouped) == 1:
            continue
        # 唯一例外：同一 source requirement/acceptance 分行共享 clause identity；
        # v1 digest 含 fact_type，所以正常 fixture 实际仍是全局唯一。保留该检查用于
        # 明确拒绝任何其他 digest collision。
        keys = {(r.get("source_path"), r.get("source_anchor")) for r in grouped}
        fact_types = {r.get("fact_type") for r in grouped}
        if len(keys) != 1 or fact_types != {"behavior", "acceptance"}:
            issues.append(f"digest collision 非法: {digest} rows={len(grouped)}")

    if not issues:
        print(
            "[knowledge-asset-s0] OK: "
            f"source_files={len(source_entries)} rows={len(rows)} "
            f"canonical={final_counts['canonical']} "
            f"existing_coverage={final_counts['existing_coverage']} "
            f"discard={final_counts['discard']} unresolved=0 dangling=0"
        )
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    issues = verify_fixture(args.fixture.resolve(), root=args.repo_root.resolve())
    if issues:
        for issue in issues:
            print(f"[knowledge-asset-s0] FAIL: {issue}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
