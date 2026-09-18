"""验收 bundle 的只读 exact-byte 边界与 create-once 传输。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.descriptor_safe_io import read_repo_relative_regular_single_link

ACCEPTANCE_BUNDLE_SCHEMA = "quwoquan_ops.acceptance_bundle.v1"
BUNDLE_MANIFEST = "bundle.json"
BUNDLE_STORE_DIR = "store"
_EAF_NAMED_FIELDS = (
    "runtimeIdentity", "dataLifecycle", "providerReadiness", "observabilityReadiness",
    "inspectEvidence", "doctorEvidence", "cleanupEvidence", "leaseClosureEvidence",
)


class IntegrationRunError(RuntimeError):
    """保留第一个 typed blocker，供 CLI summary 消费。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _bundle_path(root: Path, ref: str) -> Path:
    """exact ref 只允许物理根内 canonical POSIX 整文件，任何 symlink 分量拒绝。"""
    if not ref or ref == "." or any(char in ref for char in "\x00\n\r\\") or Path(ref).is_absolute() or Path(ref).as_posix() != ref or ".." in Path(ref).parts:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"unsafe bundle ref: {ref!r}")
    path = root / ref
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"linked bundle ref: {ref}")
    return path


def _bundle_bytes(root: Path, exact: Mapping[str, str]) -> bytes:
    if not isinstance(exact, Mapping) or set(exact) != {"ref", "digest"}:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", "bundle exact ref must contain ref and digest")
    if not isinstance(exact["ref"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(exact["digest"])):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", "bundle exact ref has invalid types or digest")
    path = _bundle_path(root, exact["ref"])
    if not path.is_file():
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INCOMPLETE", f"bundle file is absent: {exact['ref']}")
    raw = read_repo_relative_regular_single_link(root, exact["ref"], require_current_name=True)
    if _sha256_hex(raw) != exact["digest"]:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_DRIFT", f"bundle exact bytes drifted: {exact['ref']}")
    return raw


def _bundle_put(root: Path, ref: str, raw: bytes) -> bool:
    """先 fsync 私有临时文件，再 link 原子 create-once；竞争失败只接受 exact-byte replay。"""
    path = _bundle_path(root, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".bundle-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        _bundle_path(root, ref)
        try:
            os.link(temporary, path)
            return True
        except FileExistsError:
            _bundle_path(root, ref)
            if not path.is_file() or path.read_bytes() != raw:
                raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_DRIFT", f"create-once slot differs: {ref}")
            return False
    finally:
        temporary.unlink(missing_ok=True)


def _read_store_object(store: Path, exact: Mapping[str, str], label: str) -> dict[str, Any]:
    try:
        payload = json.loads(_bundle_bytes(store, exact))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"{label} is not JSON") from exc
    if not isinstance(payload, dict):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"{label} is not an object")
    return payload


def _source_receipt(source: Mapping[str, Any]) -> tuple[dict[str, str], str]:
    exact = source.get("receipt")
    if not isinstance(exact, Mapping) or not str(exact.get("ref", "")).startswith(".qwq_output/env/repo/"):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", "source receipt must be an exact repo output ref")
    return dict(exact), str(exact["ref"]).removeprefix(".qwq_output/")


def _fact_evidence_refs(fact: Mapping[str, Any]) -> list[dict[str, str]]:
    """EAF 的 store 引用；predecessor 由上层显式闭合。"""
    refs = [dict(item) for item in (fact.get("caseResultRefs") or [])]
    for field in _EAF_NAMED_FIELDS:
        value = fact.get(field)
        if not isinstance(value, Mapping):
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"acceptance fact lacks {field}")
        refs.append(dict(value))
    return refs


def _report_fact_refs(*, store: Path, fact: Mapping[str, Any]) -> list[dict[str, str]]:
    """只遍历签名 named evidence 的显式报告引用，不扫描宿主目录。"""
    refs = []
    for field in _EAF_NAMED_FIELDS:
        if field not in fact:
            continue
        source = _read_store_object(store, fact[field], field).get("source", {})
        if "reportRoot" not in source:
            continue
        if source["reportRoot"] != "store":
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", "unsupported report root")
        exact = {"ref": source["reportRef"], "digest": source["reportDigest"]}
        if not exact["ref"].startswith("runtime-reports/" + exact["digest"].removeprefix("sha256:") + "/"):
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", "report slot differs from exact digest")
        _bundle_bytes(store, exact)
        refs.append(exact)
    return refs


def _load_bundle_manifest(bundle_dir: Path) -> dict[str, Any]:
    manifest_path = _bundle_path(bundle_dir, BUNDLE_MANIFEST)
    if not bundle_dir.is_dir() or not manifest_path.is_file():
        raise IntegrationRunError("INTEGRATION_RUN.ACCEPTANCE_REQUIRED", f"lane acceptance bundle is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"bundle manifest is not JSON: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != ACCEPTANCE_BUNDLE_SCHEMA:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"bundle manifest schema must be {ACCEPTANCE_BUNDLE_SCHEMA}")
    material = {key: value for key, value in manifest.items() if key != "bundleId"}
    if manifest.get("bundleId") != _sha256_hex(_canonical_bytes(material)):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_DRIFT", "bundle manifest bytes do not match bundleId")
    required = ("candidateId", "commit", "tree", "expectedParent", "candidate", "claim", "sourceFact", "alphaFact", "betaFact", "storeFiles", "signerIdentity", "sourceReceipt", "impactPlan", "beta", "profile")
    for key in required:
        if key not in manifest:
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", f"bundle manifest lacks {key}")
    return manifest


def read_bundle_files(bundle_dir: Path, manifest: Mapping[str, Any]) -> dict[str, bytes]:
    """先读完整闭包，不允许目的 store 补齐 bundle 缺项。"""
    if not isinstance(manifest["storeFiles"], list) or not isinstance(manifest["impactPlan"], dict):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", "invalid storeFiles or impactPlan")
    files = {}
    for exact in manifest["storeFiles"]:
        raw = _bundle_bytes(bundle_dir / BUNDLE_STORE_DIR, exact)
        if exact["ref"] in files:
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_INVALID", "duplicate storeFiles ref")
        files[exact["ref"]] = raw
    _bundle_bytes(bundle_dir, {"ref": "impact-plan.json", "digest": manifest["impactPlan"].get("fileSha256")})
    return files


def validate_bundle_identity(manifest: Mapping[str, Any], *, commit: str, tree: str, parent: str) -> None:
    if manifest["commit"] != commit or manifest["tree"] != tree:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH", f"bundle candidate differs from {commit}")
    if manifest["expectedParent"] != parent:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_STALE", f"bundle parent differs from remote dev1.0 {parent}; re-run make accept")


def validate_manifest_candidate(manifest: Mapping[str, Any], candidate: Mapping[str, Any]) -> None:
    expected = {key: manifest[key] for key in ("candidateId", "commit", "tree", "expectedParent")}
    expected.update(claimRef=manifest["claim"].get("ref"), claimDigest=manifest["claim"].get("digest"))
    if any(candidate.get(key) != value for key, value in expected.items()):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH", "imported candidate does not bind the bundle identity")


def validate_manifest_source(manifest: Mapping[str, Any], source: Mapping[str, Any]) -> None:
    expected = {"status": "passed", "candidate": manifest["candidate"],
                **{key: manifest[key] for key in ("candidateId", "commit", "tree")}}
    if any(source.get(key) != value for key, value in expected.items()):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH", "imported source fact is not passed for this candidate")


def validate_manifest_fact(manifest: Mapping[str, Any], fact: Mapping[str, Any], environment: str) -> None:
    expected = {"profile": manifest["profile"], "nonPromotable": False, "environment": environment,
                "impactPlanDigest": manifest["impactPlan"].get("digest"),
                "candidate": {key: manifest[key] for key in ("candidateId", "commit", "tree")},
                "predecessor": None if environment == "alpha" else manifest["alphaFact"]}
    if any(fact.get(key) != value for key, value in expected.items()):
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH", f"{environment} signed fact differs from manifest")
    if environment == "alpha":
        from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import source_admitted_alpha

        if not source_admitted_alpha(fact):
            raise IntegrationRunError(
                "INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH",
                "Alpha must be passed or typed ACCEPTANCE.ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV",
            )
        declared = manifest.get("alpha")
        if declared is not None and declared != {
            "status": fact.get("status"), "executed": fact.get("status") == "passed", "reasonCode": fact.get("reasonCode")
        }:
            raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH", "Alpha policy differs from signed fact")
    if environment == "beta" and manifest["beta"] != {
        "status": fact.get("status"), "executed": fact.get("status") == "passed", "reasonCode": fact.get("reasonCode")
    }:
        raise IntegrationRunError("INTEGRATION_RUN.BUNDLE_CANDIDATE_MISMATCH", "Beta policy differs from signed fact")
