"""Fail-closed local readiness core with canonical plans and exact-input receipts."""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator

import yaml

ROOT = Path(__file__).resolve().parents[4]
CLI_ROOT = ROOT / "quwoquan_ops/cli"
for candidate in (CLI_ROOT, ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import evidence_runner  # noqa: E402
from lib.agent_governance_contract import (  # noqa: E402
    contract_schema_version,
    validate_declared_fields,
    validate_required_fields,
)
from lib.evidence_fingerprint import (  # noqa: E402
    EvidenceFingerprintError,
    build_evidence_fingerprint,
    canonical_digest,
    normalize_repo_relative_path,
    validate_evidence_fingerprint,
    workspace_digests,
)
from lib.feature_context_fingerprint import validate_current_feature_context_fingerprint  # noqa: E402
from lib.agent_governance_contract import validate_feature_context_manifest  # noqa: E402
from quwoquan_ops.ci.local_readiness_planner import (  # noqa: E402
    CHECK_FIELDS,
    PLAN_SCHEMA,
    build_impact_plan,
    classify_scopes,
)

CONTRACT_PATH = ROOT / "quwoquan_ops/policies/local_readiness_contract.yaml"
DEFAULT_STATE_ROOT = ROOT / ".qwq_output/env/repo/local/local-readiness"
RECEIPT_SCHEMA = "local-readiness-receipt-v1"
LEVEL_TO_STATE = {"fast": "fast_green", "scope": "scope_ready", "release": "release_ready"}
PLAN_FIELDS = ("schema", "impact_planner", "level", "paths", "scopes", "lockfiles", "checks", "deferred", "mode")
_ZERO_SHA = "0" * 40
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SOURCE_MODES = {"workspace", "staged", "commit", "push"}


class LocalReadinessError(RuntimeError):
    """Typed local readiness failure; callers must not project PASS."""


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _canonical_absolute(path: Path) -> Path:
    candidate = path.absolute()
    if sys.platform == "darwin" and candidate.parts[:2] == ("/", "var"):
        return Path("/private", *candidate.parts[1:])
    return candidate


def _reject_symlink_components(path: Path, *, label: str) -> None:
    candidate = _canonical_absolute(path)
    for component in (candidate, *candidate.parents):
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise LocalReadinessError(f"{label} 不接受 symlink component: {component}")


def _ensure_secure_directory(path: Path, *, label: str) -> Path:
    _reject_symlink_components(path, label=label)
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        _reject_symlink_components(path, label=label)
        metadata = path.lstat()
    except OSError as exc:
        raise LocalReadinessError(f"{label} 无法创建安全目录: {path}: {exc}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise LocalReadinessError(f"{label} 必须为 directory: {path}")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        try:
            path.chmod(stat.S_IMODE(metadata.st_mode) & ~0o077)
            metadata = path.lstat()
        except OSError as exc:
            raise LocalReadinessError(f"{label} 无法收紧目录权限: {path}: {exc}") from exc
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise LocalReadinessError(f"{label} directory 权限不安全: {path}")
    return path


def _state_root(state_root: Path | None = None) -> Path:
    override = os.environ.get("QWQ_LOCAL_READINESS_ROOT", "").strip()
    selected = Path(override) if override else (state_root or DEFAULT_STATE_ROOT)
    root = _canonical_absolute(selected)
    _reject_symlink_components(root, label="local readiness state root")
    return _ensure_secure_directory(root, label="local readiness state root")


def _read_regular_bytes(path: Path, *, label: str) -> bytes:
    _reject_symlink_components(path.parent, label=label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise LocalReadinessError(f"{label} 无法安全读取: {path}: {exc}") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise LocalReadinessError(f"{label} 必须为 regular file: {path}")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            return handle.read()
    finally:
        if fd >= 0:
            os.close(fd)


def _read_json_regular(path: Path, *, label: str) -> Any:
    try:
        return json.loads(_read_regular_bytes(path, label=label).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalReadinessError(f"{label} JSON 非法: {path}: {exc}") from exc


def _regular_file_exists(path: Path, *, label: str) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(metadata.st_mode):
        raise LocalReadinessError(f"{label} 必须为 regular file 且不得为 symlink: {path}")
    _reject_symlink_components(path.parent, label=label)
    return True


def _load_contract() -> dict[str, Any]:
    value = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise LocalReadinessError("local readiness contract schema_version 非法")
    if value.get("fingerprint", {}).get("canonical_implementation") != "quwoquan_ops/cli/lib/evidence_fingerprint.py":
        raise LocalReadinessError("local readiness 必须复用 canonical EvidenceFingerprint")
    return value


def _git_bytes(repo_root: Path, *args: str, stdin: bytes | None = None) -> bytes:
    proc = subprocess.run(["git", *args], cwd=repo_root, input=stdin, capture_output=True, check=False)
    if proc.returncode != 0:
        raise LocalReadinessError((proc.stderr or b"").decode("utf-8", errors="replace").strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def _git_text(repo_root: Path, *args: str) -> str:
    return _git_bytes(repo_root, *args).decode("utf-8")


def _head_sha(repo_root: Path) -> str:
    return _git_text(repo_root, "rev-parse", "HEAD").strip()


def _merge_base(repo_root: Path, head_sha: str | None = None) -> str:
    head = head_sha or _head_sha(repo_root)
    branch_proc = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=repo_root, capture_output=True, text=True, check=False,
    )
    branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""
    candidates = ("main",) if branch == "dev1.0" else ("dev1.0", "main")
    for base in candidates:
        exists = subprocess.run(["git", "rev-parse", "--verify", "--quiet", base], cwd=repo_root, capture_output=True, check=False)
        if exists.returncode != 0:
            continue
        proc = subprocess.run(["git", "merge-base", head, base], cwd=repo_root, capture_output=True, text=True, check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    return head


def _parse_name_status_z(output: bytes, repo_root: Path) -> list[dict[str, str | None]]:
    records = output.split(b"\0")
    entries: list[dict[str, str | None]] = []
    index = 0
    while index < len(records) and records[index]:
        status = records[index].decode("utf-8")
        index += 1
        if index >= len(records) or not records[index]:
            raise LocalReadinessError(f"git name-status 缺 path: {status}")
        source = normalize_repo_relative_path(records[index].decode("utf-8"), repo_root)
        index += 1
        destination: str | None = None
        if status[:1] in {"R", "C"}:
            if index >= len(records) or not records[index]:
                raise LocalReadinessError(f"git rename/copy 缺 destination: {source}")
            destination = normalize_repo_relative_path(records[index].decode("utf-8"), repo_root)
            index += 1
        entries.append({"status": status, "source": source, "destination": destination})
    return entries


def _staged_changes(repo_root: Path) -> list[dict[str, str | None]]:
    return _parse_name_status_z(
        _git_bytes(repo_root, "diff", "--cached", "--name-status", "-z", "--find-renames", "--diff-filter=ACDMRTUXB"),
        repo_root,
    )


def workspace_paths(repo_root: Path) -> list[str]:
    output = _git_bytes(repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    records = output.split(b"\0")
    paths: set[str] = set()
    index = 0
    while index < len(records) and records[index]:
        decoded = records[index].decode("utf-8")
        code = decoded[:2]
        current = normalize_repo_relative_path(decoded[3:], repo_root)
        paths.add(current)
        if "R" in code or "C" in code:
            index += 1
            if index >= len(records) or not records[index]:
                raise LocalReadinessError(f"git status rename 缺 source: {current}")
            paths.add(normalize_repo_relative_path(records[index].decode("utf-8"), repo_root))
        index += 1
    return sorted(paths)


def staged_paths(repo_root: Path) -> list[str]:
    paths: set[str] = set()
    for entry in _staged_changes(repo_root):
        paths.add(str(entry["source"]))
        if entry["destination"]:
            paths.add(str(entry["destination"]))
    return sorted(paths)


def _index_entries(repo_root: Path, paths: list[str]) -> dict[str, dict[str, str]]:
    if not paths:
        return {}
    output = _git_bytes(repo_root, "ls-files", "--stage", "-z", "--", *paths)
    entries: dict[str, dict[str, str]] = {}
    for raw in output.split(b"\0"):
        if not raw:
            continue
        metadata, separator, raw_path = raw.partition(b"\t")
        fields = metadata.decode("utf-8").split()
        if not separator or len(fields) != 3:
            raise LocalReadinessError("git index entry 格式非法")
        mode, blob, stage = fields
        if stage != "0":
            raise LocalReadinessError(f"unmerged index stage 禁止生成 readiness: {raw_path!r}")
        relative = normalize_repo_relative_path(raw_path.decode("utf-8"), repo_root)
        entries[relative] = {"mode": mode, "blob": blob}
    return entries


def _staged_identity(repo_root: Path, paths: list[str]) -> dict[str, str]:
    selected = set(paths)
    changes = _staged_changes(repo_root)
    index_entries = _index_entries(repo_root, paths)
    records: list[dict[str, Any]] = []
    for change in changes:
        source = str(change["source"])
        destination = str(change["destination"]) if change["destination"] else None
        if source not in selected and (destination is None or destination not in selected):
            continue
        index_path = destination or source
        index = index_entries.get(index_path)
        records.append({**change, "index_path": index_path, "index_mode": index.get("mode") if index else None, "index_blob": index.get("blob") if index else None})
    covered = {str(record["source"]) for record in records} | {str(record["destination"]) for record in records if record["destination"]}
    for relative in sorted(selected - covered):
        index = index_entries.get(relative)
        records.append({"status": "INDEX", "source": relative, "destination": None, "index_path": relative, "index_mode": index.get("mode") if index else None, "index_blob": index.get("blob") if index else None})
    deleted = [record for record in records if str(record["status"]).startswith("D")]
    renamed = [record for record in records if str(record["status"]).startswith(("R", "C"))]
    symlink = [record for record in records if record.get("index_mode") == "120000"]
    tracked = [record for record in records if record not in deleted and record not in renamed and record not in symlink]
    return {
        "tracked_digest": canonical_digest(tracked),
        "deleted_digest": canonical_digest(deleted),
        "renamed_digest": canonical_digest(renamed),
        "symlink_digest": canonical_digest(symlink),
    }


def _source_path(raw_path: str, repo_root: Path) -> str:
    if any(character in raw_path for character in ("\x00", "\n", "\r")):
        raise LocalReadinessError("source tree path 含控制字符")
    normalized = normalize_repo_relative_path(raw_path, repo_root)
    if normalized in {"", "."}:
        raise LocalReadinessError("source tree path 非法")
    return normalized


def _index_source_entries(repo_root: Path) -> list[dict[str, str]]:
    output = _git_bytes(repo_root, "ls-files", "--stage", "-z")
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in output.split(b"\0"):
        if not raw:
            continue
        metadata, separator, raw_path = raw.partition(b"\t")
        fields = metadata.decode("ascii").split()
        if not separator or len(fields) != 3:
            raise LocalReadinessError("git index source entry 格式非法")
        mode, blob, stage = fields
        if stage != "0":
            raise LocalReadinessError(f"unmerged index stage 禁止物化 readiness capsule: {raw_path!r}")
        relative = _source_path(raw_path.decode("utf-8"), repo_root)
        if relative in seen:
            raise LocalReadinessError(f"git index source path 重复: {relative}")
        if mode not in {"100644", "100755", "120000"} or not re.fullmatch(r"[0-9a-f]{40,64}", blob):
            raise LocalReadinessError(f"readiness capsule 不支持 index entry: mode={mode} path={relative}")
        seen.add(relative)
        entries.append({"path": relative, "mode": mode, "blob": blob})
    return sorted(entries, key=lambda item: item["path"].encode("utf-8"))


def _tree_source_entries(repo_root: Path, commit_sha: str) -> list[dict[str, str]]:
    output = _git_bytes(repo_root, "ls-tree", "-r", "-z", commit_sha)
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in output.split(b"\0"):
        if not raw:
            continue
        metadata, separator, raw_path = raw.partition(b"\t")
        fields = metadata.decode("ascii").split()
        if not separator or len(fields) != 3:
            raise LocalReadinessError("git commit tree entry 格式非法")
        mode, object_type, blob = fields
        relative = _source_path(raw_path.decode("utf-8"), repo_root)
        if relative in seen:
            raise LocalReadinessError(f"git commit tree path 重复: {relative}")
        if object_type != "blob" or mode not in {"100644", "100755", "120000"} or not re.fullmatch(r"[0-9a-f]{40,64}", blob):
            raise LocalReadinessError(f"readiness capsule 不支持 commit tree entry: mode={mode} type={object_type} path={relative}")
        seen.add(relative)
        entries.append({"path": relative, "mode": mode, "blob": blob})
    return sorted(entries, key=lambda item: item["path"].encode("utf-8"))


def _immutable_workspace(entries: list[dict[str, str]], changes: list[dict[str, str | None]]) -> dict[str, str]:
    regular = [entry for entry in entries if entry["mode"] != "120000"]
    symlinks = [entry for entry in entries if entry["mode"] == "120000"]
    deleted = [change for change in changes if str(change["status"]).startswith("D")]
    renamed = [change for change in changes if str(change["status"]).startswith(("R", "C"))]
    return {
        "tracked_digest": canonical_digest(regular),
        "untracked_digest": canonical_digest([]),
        "deleted_digest": canonical_digest(deleted),
        "renamed_digest": canonical_digest(renamed),
        "symlink_digest": canonical_digest(symlinks),
    }


def _worktree_workspace(repo_root: Path, *, state_root: Path | None = None) -> dict[str, str]:
    index_entries = _index_source_entries(repo_root)
    dirty_paths = workspace_paths(repo_root)
    excluded: list[str] = [".qwq_output"]
    if state_root is not None:
        canonical_state = _canonical_absolute(state_root)
        try:
            relative_state = canonical_state.relative_to(_canonical_absolute(repo_root))
        except ValueError:
            relative_state = None
        if relative_state is not None and relative_state.parts:
            excluded.append(relative_state.as_posix())

    def kept(relative: str) -> bool:
        return not any(relative == prefix or relative.startswith(prefix + "/") for prefix in excluded)

    source_paths = [entry["path"] for entry in index_entries]
    dirty = workspace_digests(
        sorted({path for path in source_paths + dirty_paths if kept(path)}),
        repo_root=repo_root,
    )
    return {
        "tracked_digest": canonical_digest({
            "complete_index": index_entries,
            "complete_tracked_worktree": dirty["tracked_digest"],
        }),
        "untracked_digest": dirty["untracked_digest"],
        "deleted_digest": dirty["deleted_digest"],
        "renamed_digest": dirty["renamed_digest"],
        "symlink_digest": dirty["symlink_digest"],
    }


def parse_push_updates(text: str) -> list[dict[str, str]]:
    updates: list[dict[str, str]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        fields = raw.split()
        if len(fields) != 4:
            raise LocalReadinessError("push update 必须包含 local_ref local_sha remote_ref remote_sha")
        local_ref, local_sha, remote_ref, remote_sha = fields
        if not (_SHA_RE.fullmatch(local_sha) and _SHA_RE.fullmatch(remote_sha)):
            raise LocalReadinessError("push update SHA 必须为 40 位小写十六进制")
        updates.append({"local_ref": local_ref, "local_sha": local_sha, "remote_ref": remote_ref, "remote_sha": remote_sha})
    return sorted(updates, key=lambda item: (item["remote_ref"], item["local_ref"]))


def _validated_push_identity(repo_root: Path, updates: list[dict[str, str]]) -> tuple[str, str]:
    active = [update for update in updates if update["local_sha"] != _ZERO_SHA]
    if not active:
        raise LocalReadinessError("push updates 不含可验证 local commit")
    heads: set[str] = set()
    bases: set[str] = set()
    for update in active:
        local_sha = update["local_sha"]
        proc = subprocess.run(["git", "cat-file", "-e", f"{local_sha}^{{commit}}"], cwd=repo_root, capture_output=True, check=False)
        if proc.returncode != 0:
            raise LocalReadinessError(f"push local sha 不存在或非 commit: {local_sha}")
        resolved = _git_text(repo_root, "rev-parse", update["local_ref"]).strip()
        if resolved != local_sha:
            raise LocalReadinessError(f"push local ref/sha mismatch: {update['local_ref']}")
        remote_sha = update["remote_sha"]
        if remote_sha == _ZERO_SHA:
            base = _merge_base(repo_root, local_sha)
        else:
            proc = subprocess.run(["git", "cat-file", "-e", f"{remote_sha}^{{commit}}"], cwd=repo_root, capture_output=True, check=False)
            if proc.returncode != 0:
                raise LocalReadinessError(f"push remote base 不存在或非 commit: {remote_sha}")
            base = _git_text(repo_root, "merge-base", remote_sha, local_sha).strip()
            if base != remote_sha:
                raise LocalReadinessError(f"push local sha 非 remote base 的 fast-forward 后继: {update['remote_ref']}")
        heads.add(local_sha)
        bases.add(base)
    if len(heads) != 1 or len(bases) != 1:
        raise LocalReadinessError("一次 readiness receipt 只接受同一 local sha/base 的 push updates")
    return next(iter(heads)), next(iter(bases))


def push_paths(repo_root: Path, updates: list[dict[str, str]]) -> list[str]:
    head, base = _validated_push_identity(repo_root, updates)
    output = _git_bytes(repo_root, "diff", "--name-status", "-z", "--find-renames", base, head)
    paths: set[str] = set()
    for entry in _parse_name_status_z(output, repo_root):
        paths.add(str(entry["source"]))
        if entry["destination"]:
            paths.add(str(entry["destination"]))
    return sorted(paths)


def _commit_workspace(repo_root: Path, *, head: str, base: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    changes = _parse_name_status_z(
        _git_bytes(repo_root, "diff", "--name-status", "-z", "--find-renames", base, head),
        repo_root,
    )
    entries = _tree_source_entries(repo_root, head)
    return _immutable_workspace(entries, changes), entries


def _push_workspace(repo_root: Path, paths: list[str], updates: list[dict[str, str]]) -> tuple[dict[str, str], str, str]:
    del paths  # The receipt owns the complete immutable commit tree, not selected path bytes only.
    head, base = _validated_push_identity(repo_root, updates)
    workspace, _entries = _commit_workspace(repo_root, head=head, base=base)
    return workspace, head, base


def _versions(commands: list[list[str]]) -> dict[str, str | None]:
    probes = {
        "python": [sys.executable, "--version"],
        "git": ["git", "--version"],
        "go": ["go", "version"],
        "dart": ["dart", "--version"],
        "flutter": ["flutter", "--version", "--machine"],
        "node": ["node", "--version"],
        "npm": ["npm", "--version"],
    }
    tokens = {Path(token).name for command in commands for token in command}
    needed = {"python", "git"} | {name for name in ("go", "dart", "flutter", "node", "npm") if name in tokens}
    result: dict[str, str | None] = {}
    for name in sorted(needed):
        try:
            proc = subprocess.run(probes[name], cwd=ROOT, capture_output=True, text=True, timeout=10, check=False)
            lines = (proc.stdout or proc.stderr).strip().splitlines()
            result[name] = lines[0] if proc.returncode == 0 and lines else None
        except (OSError, subprocess.TimeoutExpired):
            result[name] = None
    return result


def _owner_manifest_assets(owner_manifest: Path | None, *, repo_root: Path) -> tuple[list[str], dict[str, Any] | None]:
    assets = [] if repo_root.resolve() != ROOT.resolve() else [
        "quwoquan_ops/policies/local_readiness_contract.yaml",
        "quwoquan_ops/cli/lib/evidence_fingerprint.py",
        "quwoquan_ops/cli/lib/local_readiness/core.py",
        "quwoquan_ops/ci/local_readiness_planner.py",
        "quwoquan_ops/ci/detect_ci_impacted_scopes.py",
    ]
    manifest_value: dict[str, Any] | None = None
    if owner_manifest is not None:
        resolved = owner_manifest.resolve()
        try:
            relative = str(resolved.relative_to(repo_root.resolve()))
        except ValueError as exc:
            raise LocalReadinessError("owner manifest 必须位于仓库内") from exc
        try:
            value = json.loads(resolved.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise TypeError("manifest 必须为 object")
            validate_feature_context_manifest(value)
            validate_current_feature_context_fingerprint(value, repo_root=repo_root)
        except (OSError, TypeError, ValueError, EvidenceFingerprintError, json.JSONDecodeError) as exc:
            raise LocalReadinessError(f"owner manifest 非 current canonical manifest: {exc}") from exc
        manifest_value = value
        assets.append(relative)
    existing = [item for item in assets if (repo_root / item).exists()]
    return existing, manifest_value


def _load_review_inputs(
    review_consolidation: Path | None,
    required_evidence: list[Path] | None,
    *,
    repo_root: Path,
    required: bool,
    allow_missing: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    evidence_paths = list(required_evidence or [])
    if required and (review_consolidation is None or not evidence_paths):
        if allow_missing:
            return [], {"required": True, "consolidation": None, "evidence": []}
        raise LocalReadinessError("scope/release readiness 要求 Review consolidation PASS 与 required evidence receipts")
    if review_consolidation is None and not evidence_paths:
        return [], {"required": required, "consolidation": None, "evidence": []}
    if review_consolidation is None:
        raise LocalReadinessError("required evidence 缺 Review consolidation")
    paths = [review_consolidation, *evidence_paths]
    relatives: list[str] = []
    for item in paths:
        try:
            relatives.append(str(item.resolve().relative_to(repo_root.resolve())))
        except ValueError as exc:
            raise LocalReadinessError("Review/evidence receipt 必须位于仓库或 .qwq_output 内") from exc
    try:
        consolidation = json.loads(review_consolidation.read_text(encoding="utf-8"))
        validate_required_fields(consolidation, "review_consolidation")
        validate_declared_fields(consolidation, "review_consolidation", "required_fields")
        if consolidation.get("schema_version") != contract_schema_version("review_consolidation"):
            raise ValueError("Review consolidation schema_version 非法")
        if consolidation.get("terminal", {}).get("status") != "PASS":
            raise ValueError("Review consolidation terminal 非 PASS")
        if any(item.get("severity") == "GATE_BLOCK" for item in consolidation.get("findings", [])):
            raise ValueError("Review consolidation 含 GATE_BLOCK finding")
        receipts = [json.loads(item.read_text(encoding="utf-8")) for item in evidence_paths]
        for receipt in receipts:
            validate_declared_fields(receipt, "named_evidence_receipt", "required_fields")
            evidence_runner.validate_named_evidence_receipt(receipt)
            if receipt.get("schema_version") != contract_schema_version("named_evidence_receipt"):
                raise ValueError("required named evidence schema_version 非法")
            if receipt.get("terminal") != {"status": "PASS", "code": "EVIDENCE.PASSED", "failed_evidence": None}:
                raise ValueError("required named evidence 非 PASS")
            required_results = [item for item in receipt.get("evidence", []) if item.get("required")]
            if not required_results:
                raise ValueError("required named evidence receipt 未包含 required check")
            if any(item.get("exit_code") != 0 for item in required_results):
                raise ValueError("required named evidence check 非零退出")
        matched = [receipt for receipt in receipts if validate_evidence_fingerprint(receipt["result_fingerprint"])["digest"] == consolidation.get("evidence_receipt_digest")]
        if not matched:
            raise ValueError("Review consolidation 未绑定提供的 required evidence receipt")
        if not any(
            receipt.get("plan_fingerprint_ref") == consolidation.get("plan_fingerprint_ref")
            and receipt.get("plan_fingerprint_digest") == consolidation.get("plan_fingerprint_digest")
            for receipt in receipts
        ):
            raise ValueError("Review consolidation 与 evidence plan identity 不一致")
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise LocalReadinessError(f"Review admission receipt 非法: {exc}") from exc
    return relatives, {
        "required": required,
        "consolidation": canonical_digest(consolidation),
        "evidence": [canonical_digest(receipt) for receipt in receipts],
    }


def _execution_plan(plan: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in PLAN_FIELDS if field not in plan]
    extra = sorted(set(plan) - set(PLAN_FIELDS) - {"fingerprint"})
    if missing or extra:
        raise LocalReadinessError(f"local readiness plan 字段漂移: missing={missing}, extra={extra}")
    for check in plan["checks"]:
        if not isinstance(check, dict) or tuple(check) != CHECK_FIELDS:
            raise LocalReadinessError("local readiness check 字段漂移")
    return {field: plan[field] for field in PLAN_FIELDS}


def canonicalize_plan(plan: dict[str, Any], *, repo_root: Path = ROOT) -> dict[str, Any]:
    supplied = _execution_plan(plan)
    canonical = build_impact_plan(supplied["paths"], level=str(supplied["level"]), repo_root=repo_root)
    canonical = {**canonical, "mode": supplied["mode"]}
    if supplied != canonical:
        raise LocalReadinessError("local readiness plan 与 canonical planner exact plan 不一致")
    if not supplied["paths"] or not supplied["checks"]:
        raise LocalReadinessError("local readiness plan path/check 不能为空")
    if supplied["mode"] not in _SOURCE_MODES:
        raise LocalReadinessError("local readiness plan mode 非法")
    return canonical


def capture_fingerprint(
    plan: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    mode: str,
    owner_manifest: Path | None = None,
    push_updates: list[dict[str, str]] | None = None,
    review_consolidation: Path | None = None,
    required_evidence: list[Path] | None = None,
    allow_missing_admission: bool = False,
    state_root: Path | None = None,
) -> dict[str, Any]:
    execution = _execution_plan(plan)
    paths = list(execution["paths"])
    if not paths:
        raise LocalReadinessError("readiness fingerprint 不接受空输入范围")
    assets, manifest = _owner_manifest_assets(owner_manifest, repo_root=repo_root)
    if execution["level"] in {"scope", "release"} and manifest is None and not allow_missing_admission:
        raise LocalReadinessError("scope/release readiness 要求 current owner manifest")
    review_paths, review_identity = _load_review_inputs(
        review_consolidation,
        required_evidence,
        repo_root=repo_root,
        required=execution["level"] in {"scope", "release"},
        allow_missing=allow_missing_admission,
    )
    all_paths = sorted(set(paths + list(execution["lockfiles"]) + assets + review_paths))
    head_sha = _head_sha(repo_root)
    merge_base = _merge_base(repo_root, head_sha)
    if mode == "push":
        workspace, head_sha, merge_base = _push_workspace(repo_root, paths, push_updates or [])
    elif mode == "commit":
        head_sha = _head_sha(repo_root)
        merge_base = _merge_base(repo_root, head_sha)
        workspace, _entries = _commit_workspace(repo_root, head=head_sha, base=merge_base)
    elif mode == "staged":
        entries = _index_source_entries(repo_root)
        workspace = _immutable_workspace(entries, _staged_changes(repo_root))
    else:
        workspace = _worktree_workspace(repo_root, state_root=state_root)
    commands = [list(check["command"]) for check in execution["checks"]]
    return build_evidence_fingerprint(
        {
            "git": {"head_sha": head_sha, "merge_base_sha": merge_base},
            "workspace": workspace,
            "assets": {
                "canonical_assets_digest": canonical_digest({
                    "source_tree": workspace if mode != "workspace" else (workspace_digests(assets, repo_root=repo_root) if assets else {}),
                    "owner_manifest": manifest,
                }),
                "review_assets_digest": canonical_digest(review_identity),
            },
            "execution": {
                "commands_digest": canonical_digest(execution["checks"]),
                "toolchain_digest": canonical_digest(_versions(commands)),
                "provider_digest": canonical_digest({"mode": mode, "level": execution["level"], "push_updates": push_updates or []}),
                "generator_digest": canonical_digest({"planner": PLAN_SCHEMA, "schema": PLAN_SCHEMA}),
            },
        },
        captured_by="local-readiness",
        captured_metadata={"mode": mode, "path_count": len(paths)},
    )


def _atomic_json(path: Path, value: Any) -> None:
    parent = _ensure_secure_directory(path.parent, label="local readiness state directory")
    try:
        destination = path.lstat()
    except FileNotFoundError:
        destination = None
    if destination is not None and not stat.S_ISREG(destination.st_mode):
        raise LocalReadinessError(f"atomic JSON destination 必须为 regular file 且不得为 symlink: {path}")
    fd, raw = tempfile.mkstemp(prefix=path.name + ".", dir=parent)
    temporary = Path(raw)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            if path.exists() or path.is_symlink():
                destination = path.lstat()
                if not stat.S_ISREG(destination.st_mode):
                    raise LocalReadinessError(f"atomic JSON destination 在写入期间被替换: {path}")
            os.replace(temporary, path)
        except OSError as exc:
            raise LocalReadinessError(f"atomic JSON replace 失败: {path}: {exc}") from exc
        directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


@contextlib.contextmanager
def resource_lock(name: str, *, state_root: Path | None = None, wait: bool = True) -> Iterator[None]:
    if not name or "/" in name or name in {".", ".."}:
        raise LocalReadinessError("resource lock name 非法")
    root = _state_root(state_root)
    lock_path = root / "process/locks" / f"{name}.lock"
    _ensure_secure_directory(lock_path.parent, label="resource locks directory")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise LocalReadinessError(f"resource lock 非安全 regular file: {lock_path}: {exc}") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise LocalReadinessError(f"resource lock 必须为 regular file: {lock_path}")
        with os.fdopen(fd, "a+", encoding="utf-8") as handle:
            fd = -1
            lock_flags = fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB)
            try:
                fcntl.flock(handle.fileno(), lock_flags)
            except BlockingIOError as exc:
                raise LocalReadinessError(f"resource busy: {name}") from exc
            yield
    finally:
        if fd >= 0:
            os.close(fd)


def _path_queue_digest(path: str) -> str:
    from .queue import path_queue_digest
    return path_queue_digest(path)

def _validate_queue(value: Any) -> dict[str, Any]:
    from .queue import validate_queue
    return validate_queue(value)

def _read_queue(path: Path) -> dict[str, Any] | None:
    from .queue import read_queue
    return read_queue(path)

def enqueue_paths(paths: list[str], *, reason: str = "after_edit", state_root: Path | None = None) -> dict[str, Any]:
    from .queue import enqueue_paths as enqueue
    return enqueue(paths, reason=reason, state_root=state_root)

def _queue_items(*, state_root: Path | None = None) -> list[dict[str, Any]]:
    from .queue import queue_items
    return queue_items(state_root=state_root)

def _assert_scope_queue_closed(plan: dict[str, Any], *, state_root: Path | None = None) -> None:
    from .queue import assert_scope_queue_closed
    assert_scope_queue_closed(plan, state_root=state_root)

def _clear_queue_exact(paths: list[str], *, state_root: Path | None = None) -> None:
    from .queue import clear_queue_exact
    clear_queue_exact(paths, state_root=state_root)


def plan_readiness(
    *,
    level: str,
    paths: list[str],
    repo_root: Path = ROOT,
    mode: str = "workspace",
    owner_manifest: Path | None = None,
    push_updates: list[dict[str, str]] | None = None,
    review_consolidation: Path | None = None,
    required_evidence: list[Path] | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    _load_contract()
    plan = {**build_impact_plan(paths, level=level, repo_root=repo_root), "mode": mode}
    fingerprint = capture_fingerprint(
        plan,
        repo_root=repo_root,
        mode=mode,
        owner_manifest=owner_manifest,
        push_updates=push_updates,
        review_consolidation=review_consolidation,
        required_evidence=required_evidence,
        allow_missing_admission=True,
        state_root=state_root,
    )
    return {**plan, "fingerprint": fingerprint}


def _capsule_symlink_target(entry_path: str, target: str) -> str:
    if not target or "\x00" in target or "\n" in target or "\r" in target:
        raise LocalReadinessError(f"capsule symlink target 非法: {entry_path}")
    normalized_target = target.replace("\\", "/")
    if normalized_target.startswith("/") or re.match(r"^[A-Za-z]:/", normalized_target):
        raise LocalReadinessError(f"capsule symlink target 越出仓库: {entry_path} -> {target}")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(entry_path), normalized_target))
    if resolved in {"", ".", ".."} or resolved.startswith("../"):
        raise LocalReadinessError(f"capsule symlink target 越出仓库: {entry_path} -> {target}")
    return target


def _safe_capsule_destination(capsule_root: Path, relative: str) -> Path:
    normalized = _source_path(relative, capsule_root)
    current = capsule_root
    for part in Path(normalized).parts[:-1]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            current.mkdir(mode=0o700)
            metadata = current.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise LocalReadinessError(f"capsule parent 非安全 directory: {relative}")
    destination = capsule_root / normalized
    if destination.exists() or destination.is_symlink():
        raise LocalReadinessError(f"capsule destination 重复或已存在: {relative}")
    return destination


def _materialize_capsule_entry(repo_root: Path, capsule_root: Path, entry: dict[str, str]) -> None:
    relative, mode, blob = entry["path"], entry["mode"], entry["blob"]
    if relative == ".qwq_output" or relative.startswith(".qwq_output/"):
        raise LocalReadinessError("capsule source tree 不得占用受管 QWQ_OUTPUT_ROOT")
    destination = _safe_capsule_destination(capsule_root, relative)
    content = _git_bytes(repo_root, "cat-file", "blob", blob)
    if mode == "120000":
        try:
            target = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LocalReadinessError(f"capsule symlink target 非 UTF-8: {relative}") from exc
        os.symlink(_capsule_symlink_target(relative, target), destination)
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(destination, flags, 0o700 if mode == "100755" else 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if fd >= 0:
            os.close(fd)


def _capsule_entries(repo_root: Path, *, mode: str, push_updates: list[dict[str, str]] | None) -> tuple[list[dict[str, str]], str]:
    if mode == "staged":
        return _index_source_entries(repo_root), _head_sha(repo_root)
    if mode == "commit":
        head = _head_sha(repo_root)
        return _tree_source_entries(repo_root, head), head
    if mode == "push":
        head, _base = _validated_push_identity(repo_root, push_updates or [])
        return _tree_source_entries(repo_root, head), head
    raise LocalReadinessError(f"mode={mode} 不使用 immutable capsule")


@contextlib.contextmanager
def source_execution_root(
    *,
    repo_root: Path,
    mode: str,
    state_root: Path,
    fingerprint: dict[str, Any],
    push_updates: list[dict[str, str]] | None = None,
) -> Iterator[tuple[Path, dict[str, str], list[dict[str, str]]]]:
    if mode == "workspace":
        yield repo_root, {}, []
        return
    entries, source_sha = _capsule_entries(repo_root, mode=mode, push_updates=push_updates)
    process_root = _ensure_secure_directory(
        state_root / "process/materializations",
        label="local readiness materialization root",
    )
    container = Path(tempfile.mkdtemp(prefix=f"{fingerprint['digest'].removeprefix('sha256:')[:16]}-", dir=process_root))
    capsule = container / "worktree"
    git_dir = container / "git"
    try:
        os.chmod(container, 0o700)
        capsule.mkdir(mode=0o700)
        for entry in entries:
            _materialize_capsule_entry(repo_root, capsule, entry)

        initialized = subprocess.run(
            ["git", "init", "--bare", str(git_dir)],
            cwd=container,
            capture_output=True,
            check=False,
        )
        if initialized.returncode != 0:
            raise LocalReadinessError(initialized.stderr.decode("utf-8", errors="replace").strip() or "capsule isolated Git 初始化失败")
        os.chmod(git_dir, 0o700)
        raw_objects = _git_text(repo_root, "rev-parse", "--git-path", "objects").strip()
        source_objects = Path(raw_objects)
        if not source_objects.is_absolute():
            source_objects = repo_root / source_objects
        try:
            source_objects = source_objects.resolve(strict=True)
        except OSError as exc:
            raise LocalReadinessError(f"capsule source object database 不存在: {exc}") from exc
        if not source_objects.is_dir():
            raise LocalReadinessError("capsule source object database 必须为 directory")
        alternates = git_dir / "objects/info/alternates"
        alternates.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(alternates, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = -1
                handle.write(str(source_objects) + "\n")
        finally:
            if fd >= 0:
                os.close(fd)

        execution_env = {
            "GIT_DIR": str(git_dir),
            "GIT_WORK_TREE": str(capsule),
            "GIT_OPTIONAL_LOCKS": "0",
            "QWQ_OUTPUT_ROOT": str(capsule / ".qwq_output"),
            "QWQ_LOCAL_READINESS_SOURCE_MODE": mode,
            "QWQ_LOCAL_READINESS_SOURCE_SHA": source_sha,
        }
        for command in (
            ["git", "symbolic-ref", "HEAD", "refs/heads/dev1.0"],
            ["git", "update-ref", "refs/heads/dev1.0", source_sha],
            ["git", "read-tree", "--empty"],
        ):
            proc = subprocess.run(command, cwd=capsule, env={**os.environ, **execution_env}, capture_output=True, check=False)
            if proc.returncode != 0:
                raise LocalReadinessError(proc.stderr.decode("utf-8", errors="replace").strip() or f"capsule Git identity 初始化失败: {' '.join(command)}")
        index_info = b"".join(
            f"{entry['mode']} {entry['blob']}\t{entry['path']}".encode("utf-8") + b"\0"
            for entry in entries
        )
        indexed = subprocess.run(
            ["git", "update-index", "-z", "--index-info"],
            cwd=capsule,
            env={**os.environ, **execution_env},
            input=index_info,
            capture_output=True,
            check=False,
        )
        if indexed.returncode != 0:
            raise LocalReadinessError(indexed.stderr.decode("utf-8", errors="replace").strip() or "capsule isolated index 写入失败")
        yield capsule, execution_env, entries
    finally:
        _reject_symlink_components(container.parent, label="local readiness materialization cleanup")
        try:
            metadata = container.lstat()
        except FileNotFoundError:
            metadata = None
        if metadata is not None:
            if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise LocalReadinessError("local readiness materialization cleanup 拒绝非安全目录")
            shutil.rmtree(container)


def _safe_cwd(repo_root: Path, relative: str) -> Path:
    normalized = normalize_repo_relative_path(relative, repo_root)
    cwd = (repo_root / normalized).resolve()
    try:
        cwd.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise LocalReadinessError("check cwd 越出仓库") from exc
    if not cwd.is_dir():
        raise LocalReadinessError(f"check cwd 不存在: {relative}")
    return cwd


def _run_check(
    check: dict[str, Any],
    log_path: Path,
    *,
    repo_root: Path,
    execution_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    env = os.environ.copy()
    env.update(execution_env or {})
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = list(check["command"])
    proc = subprocess.run(command, cwd=_safe_cwd(repo_root, str(check["cwd"])), env=env, capture_output=True, text=True, check=False)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(proc.stdout + proc.stderr, encoding="utf-8")
    return {
        "id": check["id"],
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "exit_code": proc.returncode,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "log": str(log_path),
    }


def _scope_identity(plan: dict[str, Any], push_updates: list[dict[str, str]] | None = None) -> str:
    return canonical_digest({"level": plan["level"], "mode": plan["mode"], "paths": plan["paths"], "push_updates": push_updates or []}).removeprefix("sha256:")


def _receipt_locations(plan: dict[str, Any], fingerprint: dict[str, Any], *, state_root: Path | None = None, push_updates: list[dict[str, str]] | None = None) -> tuple[Path, Path]:
    root = _state_root(state_root) / "process/receipts"
    immutable = root / "by-fingerprint" / f"{fingerprint['digest'].removeprefix('sha256:')}.json"
    pointer = root / "current" / f"{_scope_identity(plan, push_updates)}.json"
    return immutable, pointer


def _write_pass_receipt(receipt: dict[str, Any], plan: dict[str, Any], *, state_root: Path | None, push_updates: list[dict[str, str]] | None) -> None:
    immutable, pointer = _receipt_locations(plan, receipt["fingerprint"], state_root=state_root, push_updates=push_updates)
    if _regular_file_exists(immutable, label="immutable readiness receipt"):
        existing = _read_json_regular(immutable, label="immutable readiness receipt")
        if not isinstance(existing, dict) or existing.get("fingerprint", {}).get("digest") != receipt["fingerprint"]["digest"] or existing.get("plan") != plan:
            raise LocalReadinessError("immutable readiness receipt identity collision")
    else:
        _atomic_json(immutable, receipt)
    _atomic_json(pointer, {"schema": "local-readiness-current-pointer-v1", "receipt": str(immutable), "fingerprint": receipt["fingerprint"]["ref"]})


def _canonical_receipt_from_pointer(path: Path, *, state_root: Path) -> Path:
    value = _read_json_regular(path, label="readiness current pointer")
    if (
        not isinstance(value, dict)
        or set(value) != {"fingerprint", "receipt", "schema"}
        or value.get("schema") != "local-readiness-current-pointer-v1"
        or not isinstance(value.get("receipt"), str)
        or not isinstance(value.get("fingerprint"), str)
    ):
        raise LocalReadinessError("readiness current pointer exact schema 非法")
    raw_receipt = Path(value["receipt"])
    if not raw_receipt.is_absolute():
        raw_receipt = path.parent / raw_receipt
    if not _regular_file_exists(raw_receipt, label="readiness receipt"):
        raise LocalReadinessError(f"readiness current pointer receipt 不存在: {raw_receipt}")
    try:
        receipt = raw_receipt.resolve(strict=True)
    except OSError as exc:
        raise LocalReadinessError(f"readiness current pointer receipt 不存在: {raw_receipt}: {exc}") from exc
    canonical_root = (state_root / "process/receipts/by-fingerprint").resolve(strict=True)
    try:
        relative = receipt.relative_to(canonical_root)
    except ValueError as exc:
        raise LocalReadinessError("readiness current pointer receipt 越出 canonical by-fingerprint root") from exc
    if len(relative.parts) != 1 or not re.fullmatch(r"[0-9a-f]{64}\.json", relative.name):
        raise LocalReadinessError("readiness current pointer receipt 非 canonical fingerprint path")
    _regular_file_exists(receipt, label="readiness receipt")
    return receipt


def run_readiness(
    plan: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    owner_manifest: Path | None = None,
    push_updates: list[dict[str, str]] | None = None,
    review_consolidation: Path | None = None,
    required_evidence: list[Path] | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    if plan.get("level") != "fast" and plan.get("deferred"):
        raise LocalReadinessError("scope/release readiness 要求 deferred=[]")
    canonical = canonicalize_plan(plan, repo_root=repo_root)
    level, mode = str(canonical["level"]), str(canonical["mode"])
    if level != "fast" and canonical["deferred"]:
        raise LocalReadinessError("scope/release readiness 要求 deferred=[]")
    _assert_scope_queue_closed(canonical, state_root=state_root)
    current = capture_fingerprint(
        canonical,
        repo_root=repo_root,
        mode=mode,
        owner_manifest=owner_manifest,
        push_updates=push_updates,
        review_consolidation=review_consolidation,
        required_evidence=required_evidence,
        state_root=state_root,
    )
    supplied = validate_evidence_fingerprint(plan.get("fingerprint"))
    if supplied["digest"] != current["digest"]:
        raise LocalReadinessError("local readiness plan fingerprint stale or tampered")
    root = _state_root(state_root)
    cache_path = root / "cache/exact-input" / f"{current['digest'].removeprefix('sha256:')}.json"
    resource_names = sorted({"runner", *[resource for check in canonical["checks"] for resource in check["resources"]]})
    with contextlib.ExitStack() as locks:
        for name in resource_names:
            locks.enter_context(resource_lock(name.replace("/", "_"), state_root=root))
        current = capture_fingerprint(
            canonical,
            repo_root=repo_root,
            mode=mode,
            owner_manifest=owner_manifest,
            push_updates=push_updates,
            review_consolidation=review_consolidation,
            required_evidence=required_evidence,
            state_root=state_root,
        )
        if current["digest"] != supplied["digest"]:
            raise LocalReadinessError("local readiness input changed before cache lookup")
        if _regular_file_exists(cache_path, label="readiness exact-input cache"):
            cached = _read_json_regular(cache_path, label="readiness exact-input cache")
            if not isinstance(cached, dict):
                raise LocalReadinessError("readiness exact-input cache 必须为 object")
            if (
                cached.get("status") == "PASS"
                and cached.get("fingerprint", {}).get("digest") == current["digest"]
                and cached.get("plan") == canonical
            ):
                receipt = {**cached, "cache_hit": True, "finished_at": _utc_now()}
                _write_pass_receipt(receipt, canonical, state_root=root, push_updates=push_updates)
                if not canonical["deferred"]:
                    _clear_queue_exact(canonical["paths"], state_root=root)
                    _assert_scope_queue_closed(canonical, state_root=root)
                return receipt
        results: list[dict[str, Any]] = []
        run_id = current["digest"].removeprefix("sha256:")[:16]
        with source_execution_root(
            repo_root=repo_root,
            mode=mode,
            state_root=root,
            fingerprint=current,
            push_updates=push_updates,
        ) as (execution_root, execution_env, _source_entries):
            for index, check in enumerate(canonical["checks"]):
                result = _run_check(
                    check,
                    root / "process/runs" / run_id / f"{index:03d}-{check['id'].replace(':', '-')}.log",
                    repo_root=execution_root,
                    execution_env=execution_env,
                )
                results.append(result)
                if result["status"] != "PASS":
                    break
        end = capture_fingerprint(
            canonical,
            repo_root=repo_root,
            mode=mode,
            owner_manifest=owner_manifest,
            push_updates=push_updates,
            review_consolidation=review_consolidation,
            required_evidence=required_evidence,
            state_root=state_root,
        )
        stable = end["digest"] == current["digest"]
        _assert_scope_queue_closed(canonical, state_root=root)
        status = "PASS" if len(results) == len(canonical["checks"]) and all(item["status"] == "PASS" for item in results) and stable and (level == "fast" or not canonical["deferred"]) else "FAIL"
        admission_paths, admission_identity = _load_review_inputs(review_consolidation, required_evidence, repo_root=repo_root, required=level in {"scope", "release"})
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "level": level,
            "readiness": LEVEL_TO_STATE[level] if status == "PASS" else "not_ready",
            "status": status,
            "mode": mode,
            "evidence_layer": "local_source_readiness_only",
            "source_execution": "worktree" if mode == "workspace" else "immutable_capsule",
            "fingerprint": current,
            "input_stable": stable,
            "paths": list(canonical["paths"]),
            "scopes": list(canonical["scopes"]),
            "deferred": list(canonical["deferred"]),
            "checks": results,
            "cache_hit": False,
            "plan": canonical,
            "owner_manifest": str(owner_manifest.resolve().relative_to(repo_root.resolve())) if owner_manifest else None,
            "review_admission": {"paths": admission_paths, "identity": admission_identity},
            "finished_at": _utc_now(),
        }
        if status == "PASS":
            _atomic_json(cache_path, receipt)
            _write_pass_receipt(receipt, canonical, state_root=root, push_updates=push_updates)
            if not canonical["deferred"]:
                _clear_queue_exact(canonical["paths"], state_root=root)
                _assert_scope_queue_closed(canonical, state_root=root)
        return receipt


def _receipt_admission_paths(receipt: dict[str, Any], repo_root: Path) -> tuple[Path | None, list[Path]]:
    raw_paths = receipt.get("review_admission", {}).get("paths", [])
    if not raw_paths:
        return None, []
    paths = [repo_root / normalize_repo_relative_path(path, repo_root) for path in raw_paths]
    return paths[0], paths[1:]


def verify_receipt(
    *,
    level: str,
    paths: list[str],
    repo_root: Path = ROOT,
    mode: str,
    owner_manifest: Path | None = None,
    push_updates: list[dict[str, str]] | None = None,
    receipt_path: Path | None = None,
    state_root: Path | None = None,
) -> dict[str, Any]:
    canonical = {**build_impact_plan(paths, level=level, repo_root=repo_root), "mode": mode}
    root = _state_root(state_root)
    if receipt_path is None:
        pointer = _receipt_locations(canonical, {"digest": "sha256:" + "0" * 64}, state_root=root, push_updates=push_updates)[1]
        if not _regular_file_exists(pointer, label="readiness current pointer"):
            raise LocalReadinessError(f"missing receipt pointer: {pointer}")
        receipt_path = _canonical_receipt_from_pointer(pointer, state_root=root)
    elif receipt_path.is_absolute():
        receipt_path = receipt_path.absolute()
    else:
        receipt_path = (repo_root / receipt_path).absolute()
    if not _regular_file_exists(receipt_path, label="readiness receipt"):
        raise LocalReadinessError(f"missing receipt: {receipt_path}")
    receipt = _read_json_regular(receipt_path, label="readiness receipt")
    if not isinstance(receipt, dict):
        raise LocalReadinessError("readiness receipt 必须为 object")
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("level") != level or receipt.get("status") != "PASS":
        raise LocalReadinessError("readiness receipt 不是所需等级的 PASS")
    if receipt.get("plan") != canonical:
        raise LocalReadinessError("readiness receipt exact canonical plan mismatch")
    if sorted(receipt.get("paths", [])) != canonical["paths"] or receipt.get("mode") != mode:
        raise LocalReadinessError("readiness receipt scope/mode mismatch")
    if level != "fast" and receipt.get("deferred") != []:
        raise LocalReadinessError("readiness receipt 仍含 deferred")
    _assert_scope_queue_closed(canonical, state_root=state_root)
    review_path, evidence_paths = _receipt_admission_paths(receipt, repo_root)
    if owner_manifest is None and receipt.get("owner_manifest"):
        owner_manifest = repo_root / normalize_repo_relative_path(receipt["owner_manifest"], repo_root)
    current = capture_fingerprint(
        canonical,
        repo_root=repo_root,
        mode=mode,
        owner_manifest=owner_manifest,
        push_updates=push_updates,
        review_consolidation=review_path,
        required_evidence=evidence_paths,
        state_root=state_root,
    )
    if receipt.get("fingerprint", {}).get("digest") != current["digest"]:
        raise LocalReadinessError("readiness receipt stale: exact input fingerprint changed")
    immutable, _pointer = _receipt_locations(canonical, current, state_root=state_root, push_updates=push_updates)
    if receipt_path != immutable.absolute():
        raise LocalReadinessError("readiness receipt path 未按 exact fingerprint 索引")
    return receipt


def worker_once(*, state_root: Path | None = None, debounce_seconds: float | None = None) -> dict[str, Any]:
    from .worker import worker_once as run_worker_once
    return run_worker_once(state_root=state_root, debounce_seconds=debounce_seconds)

def inspect_state(*, state_root: Path | None = None) -> dict[str, Any]:
    from .worker import inspect_state as inspect_worker_state
    return inspect_worker_state(state_root=state_root)
