#!/usr/bin/env python3
"""Normalize feature-tree acceptance files to the three-layer test evidence schema."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[3]
FEATURE_TREE = ROOT / "specs" / "feature-tree"

RETIRED_NUMERIC_LAYER_MAP = {
    1: "local_contract",
    2: "local_contract",
    3: "api_integration",
    4: "user_acceptance",
}

ENVS_BY_LAYER = {
    "local_contract": ["local", "alpha"],
    "api_integration": ["beta", "gamma"],
    "user_acceptance": ["gamma_local", "prod_gray_initial"],
}

ACCEPTANCE_GROUPS = {
    "uat_acceptance",
    "domain_acceptance",
    "sit_acceptance",
    "gwt_acceptance",
    "contract_acceptance",
}

STATUS_MAP = {
    "passing": "completed",
    "passed": "completed",
    "done": "completed",
    "已完成": "completed",
    "已解决": "completed",
    "planned": "pending",
    "specified": "pending",
    "partially_implemented_p0": "partial",
}

DONE_STATUSES = {"implemented", "completed"}
COMMAND_PREFIXES = (
    "make ",
    "bash ",
    "python ",
    "python3 ",
    "go test ",
    "go vet ",
    "go build ",
    "go run ",
    "flutter test ",
    "flutter analyze ",
    "dart ",
    "cd ",
    "curl ",
)
GENERIC_SUITES = {
    "static_contract",
    "module_interaction",
    "service_contract",
    "app_api_integration",
    "story_local_contract",
    "story_api_integration",
    "metadata_contract",
    "domain_static_contract",
    "domain_service_contract",
    "capability_api_integration",
    "capability_local_contract",
    "affected_user_journey",
    "app_root_journey",
    "app_root_api_integration",
    "suite_id",
}
GENERIC_CASES = {
    "local_contract.static_contract",
    "local_contract.module_interaction",
    "local_contract.contract",
    "local_contract.domain.metadata.contract",
    "api_integration.service_contract",
    "api_integration.app_api_integration",
    "api_integration.domain.service.contract",
    "api_integration.domain.capability.primary_flow",
    "api_integration.domain.operation.primary",
    "api_integration.domain.operation.story_case",
    "user_acceptance.journey-id.scenario-id.primary",
    "user_acceptance.journey-id.scenario-id.domain_effect",
}


def slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"^[tT][1-4][_-]?", "", value)
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "contract"


def layer_for_entry(entry: Any) -> str:
    text = str(entry)
    match = re.match(r"^[Tt]([1-4])(?:_|$)", text)
    if match:
        return RETIRED_NUMERIC_LAYER_MAP[int(match.group(1))]
    if text.startswith(("local_contract.", "api_integration.", "user_acceptance.")):
        return text.split(".", 1)[0]
    return "local_contract"


def _node_parts(node_path: str) -> list[str]:
    normalized = str(node_path).strip().replace("\\", "/")
    prefix = "specs/feature-tree/"
    if normalized.startswith(prefix):
        normalized = normalized[len(prefix):]
    return [slug(part) for part in normalized.split("/") if part]


def canonical_case_id(
    *,
    layer: str,
    node_path: str,
    item_id: str,
    suite: str,
) -> str:
    parts = _node_parts(node_path)
    if not parts:
        domain, capability, story = "app_root", "root", slug(item_id)
    elif len(parts) == 1:
        domain, capability, story = parts[0], "domain_service", slug(item_id)
    elif len(parts) == 2:
        domain, capability, story = parts[0], parts[1], slug(item_id)
    else:
        domain, capability, story = parts[0], parts[1], parts[2]
    case = slug(suite or item_id)
    return f"{layer}.{domain}.{capability}.{story}.{case}"


def evidence_entry(raw: Any, *, node_path: str, item_id: str) -> dict[str, Any]:
    layer = layer_for_entry(raw)
    raw_text = str(raw)
    case_tail = slug(raw_text)
    return {
        "layer": layer,
        "suite": case_tail,
        "cases": [canonical_case_id(layer=layer, node_path=node_path, item_id=item_id, suite=case_tail)],
        "envs": ENVS_BY_LAYER[layer],
    }


def path_exists(path_text: str) -> bool:
    normalized = path_text.split("::", 1)[0].strip()
    if not normalized:
        return False
    if any(ch.isspace() for ch in normalized):
        return False
    if len(normalized) > 512:
        return False
    candidates = [ROOT / normalized]
    if not normalized.startswith(("quwoquan_app/", "quwoquan_service/", "quwoquan_data/", "quwoquan_ops/")):
        candidates.extend(
            [
                ROOT / "quwoquan_service" / normalized,
                ROOT / "quwoquan_data" / normalized,
                ROOT / "quwoquan_ops" / normalized,
            ]
        )
    return any(candidate.exists() for candidate in candidates)


def normalize_test_ref(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    if isinstance(raw, dict):
        if raw.get("file"):
            return {"file": str(raw["file"]).strip()}, None
        if raw.get("command"):
            return {"command": str(raw["command"]).strip()}, None
        if raw.get("artifact"):
            return {"artifact": str(raw["artifact"]).strip()}, None
        return None, str(raw)

    text = str(raw).strip()
    if not text:
        return None, None
    if text.startswith("file:"):
        return {"file": text.split(":", 1)[1].strip()}, None
    if text.startswith("command:"):
        return {"command": text.split(":", 1)[1].strip()}, None
    if text.startswith("artifact:"):
        return {"artifact": text.split(":", 1)[1].strip()}, None
    if any(text.startswith(prefix) for prefix in COMMAND_PREFIXES):
        return {"command": text}, None
    if text.startswith(".qwq_output/env/repo/runs/"):
        return {"artifact": text}, None
    if path_exists(text):
        return {"file": text}, None

    path_match = re.match(r"^([A-Za-z0-9_./-]+\.(?:dart|go|py|sh|yaml|yml|json|md))(?:\s|$|（|\()", text)
    if path_match and path_exists(path_match.group(1)):
        return {"file": path_match.group(1)}, text
    return None, text


def normalize_tests_bucket(item: dict[str, Any], bucket_name: str) -> bool:
    tests = item.setdefault("tests", {})
    bucket = tests.get(bucket_name, [])
    if not isinstance(bucket, list):
        bucket = [bucket] if bucket else []
        tests[bucket_name] = bucket

    notes = item.setdefault("notes", [])
    if not isinstance(notes, list):
        notes = [str(notes)]
        item["notes"] = notes

    normalized: list[dict[str, Any]] = []
    changed = False
    for entry in bucket:
        structured, note = normalize_test_ref(entry)
        if structured is not None:
            normalized.append(structured)
            if structured != entry:
                changed = True
        else:
            changed = True
        if note:
            message = f"[migrated_from_{bucket_name}] {note}"
            if message not in notes:
                notes.append(message)
                changed = True
    if normalized != bucket:
        tests[bucket_name] = normalized
        changed = True
    return changed


def normalize_test_evidence(item: dict[str, Any], *, node_path: str, item_id: str) -> bool:
    changed = False
    old_evidence = item.pop("evidence", None)
    if old_evidence is not None:
        item["test_evidence"] = {
            "primary": [evidence_entry(entry, node_path=node_path, item_id=item_id) for entry in old_evidence.get("primary", [])],
            "supporting": [evidence_entry(entry, node_path=node_path, item_id=item_id) for entry in old_evidence.get("supporting", [])],
        }
        changed = True
    elif "test_evidence" not in item:
        item["test_evidence"] = {
            "primary": [evidence_entry("local_contract_contract", node_path=node_path, item_id=item_id)],
            "supporting": [],
        }
        changed = True

    test_evidence = item.get("test_evidence") or {}
    for bucket_name in ("primary", "supporting"):
        bucket = test_evidence.get(bucket_name, [])
        if not isinstance(bucket, list):
            continue
        for index, entry in enumerate(bucket):
            if not isinstance(entry, dict):
                continue
            layer = str(entry.get("layer") or "").strip() or "local_contract"
            suite = str(entry.get("suite") or "").strip()
            if not suite or suite in GENERIC_SUITES:
                suite = slug(f"{item_id}_{layer}")
                entry["suite"] = suite
                changed = True
            cases = entry.get("cases")
            if not isinstance(cases, list) or not cases:
                entry["cases"] = [canonical_case_id(layer=layer, node_path=node_path, item_id=item_id, suite=suite)]
                changed = True
                continue
            normalized_cases: list[str] = []
            for case in cases:
                case_text = str(case).strip()
                if case_text in GENERIC_CASES or len(case_text.split(".")) < 5:
                    normalized_cases.append(
                        canonical_case_id(layer=layer, node_path=node_path, item_id=item_id, suite=suite)
                    )
                    changed = True
                else:
                    normalized_cases.append(case_text)
            if normalized_cases != cases:
                entry["cases"] = normalized_cases
                changed = True
            envs = entry.get("envs")
            if not isinstance(envs, list) or not envs:
                entry["envs"] = ENVS_BY_LAYER.get(layer, ["local"])
                changed = True
    return changed


def normalize_status(item: dict[str, Any]) -> bool:
    changed = False
    status = str(item.get("status", "")).strip()
    normalized = STATUS_MAP.get(status, status or "pending")
    tests = item.setdefault("tests", {})
    recorded = tests.get("recorded") or []
    if normalized in DONE_STATUSES and not recorded:
        normalized = "pending_evidence"
    if normalized != status:
        item["status"] = normalized
        changed = True
    return changed


def migrate_item(item: dict[str, Any], *, node_path: str, item_id: str) -> bool:
    changed = False
    changed = normalize_test_evidence(item, node_path=node_path, item_id=item_id) or changed
    tests = item.setdefault("tests", {})
    tests.setdefault("planned", [])
    tests.setdefault("recorded", [])
    changed = normalize_tests_bucket(item, "planned") or changed
    changed = normalize_tests_bucket(item, "recorded") or changed
    for bucket_name in ("planned", "recorded"):
        bucket = tests.get(bucket_name)
        if not isinstance(bucket, list):
            tests[bucket_name] = []
            changed = True
        for record in tests[bucket_name]:
            if isinstance(record, dict) and "evidence" in record:
                record["layer"] = layer_for_entry(record.pop("evidence"))
                changed = True
    changed = normalize_status(item) or changed
    return changed


def migrate_file(path: Path) -> bool:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    node = data.get("node") if isinstance(data.get("node"), dict) else {}
    node_path = str(node.get("path") or path.parent.as_posix())

    changed = False
    for group_name in ACCEPTANCE_GROUPS:
        group = data.get(group_name)
        if not isinstance(group, dict):
            continue
        for item_id, item in group.items():
            if isinstance(item, dict):
                changed = migrate_item(item, node_path=node_path, item_id=str(item_id)) or changed

    if changed:
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(
                data,
                handle,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
    return changed


def main() -> int:
    changed_files = []
    for path in sorted(FEATURE_TREE.rglob("acceptance.yaml")):
        if migrate_file(path):
            changed_files.append(path.relative_to(ROOT).as_posix())

    print(f"[migrate] acceptance test spec files changed: {len(changed_files)}")
    for path in changed_files:
        print(f"[migrate] {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
