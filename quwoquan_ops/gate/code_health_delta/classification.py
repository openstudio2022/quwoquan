"""Mutually-exclusive source-path classification."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Callable
from typing import Any


def _matches_marker(path: str, marker: str) -> bool:
    lowered = path.lower()
    token = str(marker).lower()
    if token.startswith("/") or token.endswith("/"):
        return token.strip("/") in lowered.split("/")
    return lowered.endswith(token) or token in lowered


def _manifest_outputs(source: dict[str, str], read: Callable[[str], bytes | None]) -> list[dict[str, Any]]:
    body = read(source["path"])
    if body is None:
        return []
    try:
        manifest = json.loads(body)
    except (ValueError, UnicodeError):
        return []
    if not isinstance(manifest, dict) or manifest.get("generator") != source["generator"]:
        return []
    outputs = manifest.get("outputs")
    return outputs if isinstance(outputs, list) else []


def generated_output_declarations(policy: dict[str, Any], read: Callable[[str], bytes | None]) -> dict[str, list[dict[str, Any]]]:
    """只读 manifest 得到待校验声明表；调用方可据 keys 批量读取同一 snapshot outputs。"""
    declarations: dict[str, list[dict[str, Any]]] = {}
    for source in policy["classification"]["generated_manifests"]:
        for output in _manifest_outputs(source, read):
            if not isinstance(output, dict) or not isinstance(output.get("path"), str):
                continue
            path = PurePosixPath(source["root"], output["path"])
            if path.is_absolute() or ".." in path.parts:
                continue
            declarations.setdefault(path.as_posix(), []).append({"source": source["path"], "sha256": output.get("sha256")})
    return declarations


def _output_status(declarations: list[dict[str, Any]], body: bytes | None) -> dict[str, Any]:
    expected = [item["sha256"] for item in declarations]
    actual = None if body is None else hashlib.sha256(body).hexdigest()
    if any(not isinstance(value, str) or re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", value) is None for value in expected):
        state = "invalid-output-digest"
    elif actual is None:
        state = "output-unavailable"
    elif any(value.removeprefix("sha256:") != actual for value in expected):
        state = "output-digest-mismatch"
    else:
        state = "manifest-output-verified"
    return {"status": state, "sources": [item["source"] for item in declarations],
            "expectedDigests": expected, "actualDigest": None if actual is None else "sha256:" + actual}


def generated_provenance(policy: dict[str, Any], read: Callable[[str], bytes | None], *, statuses: dict[str, Any] | None = None) -> dict[str, str]:
    """read 必须按需提供同一 snapshot 的来源和输出；匹配只证明 manifest bytes，不证明重生成。"""
    states = {} if statuses is None else statuses
    result = {}
    for path, source in policy["classification"]["generated_exact_sources"].items():
        if read(source) is not None:
            result[path] = source
            states[path] = {"status": "registered-source-only-not-output-verified", "sources": [source]}
    for path, declarations in generated_output_declarations(policy, read).items():
        state = _output_status(declarations, read(path))
        states[path] = state
        result.pop(path, None)
        if state["status"] == "manifest-output-verified":
            result[path] = declarations[0]["source"]
    return result


def generated_classification_report(policy: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    """把未覆盖生成命名单列为不确定，不伪装为已确认手写/误判率为零。"""
    statuses = policy.get("_generated_statuses", {})
    selected = {path: statuses[path] for path in paths if path in statuses}
    uncovered = [path for path in paths if path not in statuses and re.search(r"(?:^|/)(?:generated|gen)/|(?:_generated|\.generated|\.g)\.", path)]
    return {"statuses": selected, "statusCounts": {state: sum(item["status"] == state for item in selected.values()) for state in sorted({item["status"] for item in selected.values()})},
            "uncoveredGeneratedCandidates": uncovered,
            "verification": "manifest-output-byte-match-not-regeneration",
            "classificationVersion": "generated-manifest-output-sha256-v2",
            "limitations": ["unregistered-generators-conservatively-handwritten", "registered-exact-source-does-not-verify-output", "matching-manifest-is-not-authenticated-generator-execution"],
            "falseClassificationRate": None, "falseClassificationRateStatus": "unmeasured-no-reviewed-sample"}


def classify_path(path: str, policy: dict[str, Any]) -> str:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    lowered = normalized.lower()
    rules = policy["classification"]
    if any(_matches_marker(lowered, marker) for marker in rules["vendor_markers"]):
        return "vendor"
    if normalized in policy.get("_generated_provenance", {}):
        return "generated"
    if any(_matches_marker(lowered, marker) for marker in rules["test_markers"]):
        return "test"
    suffix = PurePosixPath(lowered).suffix
    # Skill 和 contracts 都可能携带实现；目录名不能掩盖手写代码。
    if suffix == ".md":
        return "docs"
    if suffix in set(rules["source_extensions"]):
        return "handwritten-production"
    if any(_matches_marker(lowered, marker) for marker in rules["contract_markers"]):
        return "contract-metadata"
    if any(lowered.startswith(str(prefix).lower()) for prefix in rules["docs_prefixes"]):
        return "docs"
    if suffix in set(rules["config_extensions"]):
        return "config-data"
    return "config-data"
