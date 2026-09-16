"""受治理地把明示支持的 legacy sealed release 重物化为 current-schema terminal facts。"""
from __future__ import annotations

import json
import errno
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from content.release.canonical.aggregate_release import build_pool_release
from content.release.canonical.object_transaction_contract import ObjectTransactionError, _tree_digest
from content.release.canonical.producer_release_handoff import (
    _canonical_bytes, _digest, read_producer_release_handoff, write_producer_release_handoff,
)
from core.publish_repository import require_publish_repository
from core.schema import assert_valid

LEGACY_V1_LITERAL = "quwoquan_data.producer_release_handoff"
_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

class LegacyReleaseRepackageError(ObjectTransactionError):
    pass

def _error(code: str, detail: str) -> LegacyReleaseRepackageError:
    return LegacyReleaseRepackageError(f"{code}: {detail}")

def safe_release_id(value: object, *, label: str) -> str:
    text = str(value or "")
    if not _RELEASE_ID.fullmatch(text) or text in {".", ".."}:
        raise _error("DATA.RELEASE.REPACKAGE.RELEASE_ID_INVALID", f"{label}={text!r}")
    return text

def _trusted_root(path: Path, *, label: str) -> Path:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    try:
        for part in absolute.parts[1:]:
            current = current / part
            mode = os.lstat(current).st_mode
            if stat.S_ISLNK(mode):
                raise _error("DATA.RELEASE.REPACKAGE.ROOT_SYMLINK", f"{label}={current}")
    except FileNotFoundError as exc:
        raise _error("DATA.RELEASE.REPACKAGE.ROOT_MISSING", f"{label}={absolute}") from exc
    if not absolute.is_dir():
        raise _error("DATA.RELEASE.REPACKAGE.ROOT_INVALID", f"{label}={absolute}")
    return absolute

def _child(root: Path, release_id: str, *, label: str, must_exist: bool) -> Path:
    trusted = _trusted_root(root, label=f"{label} root")
    name = safe_release_id(release_id, label=label)
    target = trusted / name
    if target.parent != trusted:
        raise _error("DATA.RELEASE.REPACKAGE.PATH_ESCAPE", label)
    if target.exists() or target.is_symlink():
        if target.is_symlink():
            raise _error("DATA.RELEASE.REPACKAGE.RELEASE_SYMLINK", f"{label}={target}")
        if not target.is_dir():
            raise _error("DATA.RELEASE.REPACKAGE.RELEASE_INVALID", f"{label}={target}")
    elif must_exist:
        raise _error("DATA.RELEASE.REPACKAGE.RELEASE_MISSING", f"{label}={target}")
    return target

def _read(path: Path, *, code: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise _error(code, str(path))
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _error(code, str(path)) from exc
    if not isinstance(value, dict):
        raise _error(code, str(path))
    return value, raw

@dataclass(frozen=True, slots=True)
class FrozenLegacySource:
    root: Path
    release_dir: Path
    release_id: str
    handoff: dict[str, Any]
    cohort: dict[str, Any]
    refs: tuple[str, ...]
    handoff_digest: str
    cohort_digest: str
    tree_digest: str
    schema_name: str

def freeze_legacy_source(*, source_root: Path, release_id: str,
                         handoff_digest: str, cohort_digest: str) -> FrozenLegacySource:
    """只读一次 exact source handoff/cohort；返回供 fence 与 writer 共用的冻结事实。"""
    source_id = safe_release_id(release_id, label="sourceReleaseId")
    trusted_root = _trusted_root(source_root, label="source")
    release = _child(trusted_root, source_id, label="sourceReleaseId", must_exist=True)
    tree_digest = _tree_digest(release)
    handoff, handoff_raw = _read(release / "producer_release_handoff.json", code="DATA.RELEASE.REPACKAGE.SOURCE_HANDOFF_MISSING")
    cohort, cohort_raw = _read(release / "cohort.json", code="DATA.RELEASE.REPACKAGE.SOURCE_COHORT_MISSING")
    if not (handoff.get("schema") == LEGACY_V1_LITERAL and "repositoryId" not in handoff
            and "artifact" not in handoff and "releaseClass" in cohort):
        raise _error("DATA.RELEASE.REPACKAGE.LEGACY_SCHEMA_UNSUPPORTED", str(handoff.get("schema")))
    try:
        assert_valid(handoff, "release", "legacy_producer_release_handoff_v1", label="legacy producer handoff")
        assert_valid(cohort, "release", "legacy_release_cohort_v1", label="legacy cohort")
    except ValueError as exc:
        raise _error("DATA.RELEASE.REPACKAGE.LEGACY_SCHEMA_INVALID", str(exc)) from exc
    if _digest(handoff_raw) != handoff_digest:
        raise _error("DATA.RELEASE.REPACKAGE.SOURCE_HANDOFF_DIGEST_DRIFT", source_id)
    if (_digest(cohort_raw) != cohort_digest or handoff["explicitCohort"]["digest"] != cohort_digest
            or handoff["explicitCohort"]["document"] != cohort):
        raise _error("DATA.RELEASE.REPACKAGE.SOURCE_COHORT_DIGEST_DRIFT", source_id)
    if handoff["releaseId"] != source_id or handoff["handoffId"] != source_id:
        raise _error("DATA.RELEASE.REPACKAGE.SOURCE_IDENTITY_DRIFT", source_id)
    refs = tuple(sorted(str(ref) for ref in cohort["objectRefs"]))
    if tuple(sorted(row["objectRef"] for row in handoff["contentPoolObjects"])) != refs:
        raise _error("DATA.RELEASE.REPACKAGE.SOURCE_MEMBERSHIP_DRIFT", source_id)
    header = release / "payload/release.json"
    if not header.is_file() or handoff["release"]["headerDigest"] != _digest(header.read_bytes()):
        raise _error("DATA.RELEASE.REPACKAGE.SOURCE_RELEASE_DIGEST_DRIFT", source_id)
    from core.release_layout import payload_digest
    if handoff["release"]["payloadDigest"] != payload_digest(release):
        raise _error("DATA.RELEASE.REPACKAGE.SOURCE_RELEASE_DIGEST_DRIFT", source_id)
    try:
        from content.release.canonical.producer_release_handoff import _validate_embedded_pool_rows
        _validate_embedded_pool_rows(rows=handoff["contentPoolObjects"],
            sealed_root=release / "payload/objects", object_refs=list(refs), header=json.loads(header.read_bytes()))
    except (OSError, TypeError, ValueError, ObjectTransactionError) as exc:
        raise _error("DATA.RELEASE.REPACKAGE.SOURCE_PUBLISH_PROOF_DRIFT", str(exc)) from exc
    return FrozenLegacySource(trusted_root, release, source_id, handoff, cohort, refs,
        handoff_digest, cohort_digest, tree_digest, "legacy_producer_release_handoff_v1")

def _publish_staging(staging: Path, target: Path) -> bool:
    if target.exists():
        if _tree_digest(target) != _tree_digest(staging):
            raise _error("DATA.RELEASE.REPACKAGE.TARGET_CONFLICT", target.name)
        return True
    # durability preparation precedes the atomic visibility boundary; after rename no fallible check may turn success into failure.
    directory = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    try:
        staging.replace(target)
    except OSError as exc:
        if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY} or not target.exists() or target.is_symlink() or not target.is_dir():
            raise
        if target.is_symlink() or _tree_digest(target) != _tree_digest(staging):
            raise _error("DATA.RELEASE.REPACKAGE.TARGET_CONFLICT", target.name) from None
        return True
    return False

def _terminal_copy(*, output: Path, publish_root: Path, release_id: str) -> Path:
    target = publish_root / "releases" / release_id
    target.parent.mkdir(exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{release_id}.", dir=target.parent))
    try:
        for name in ("cohort.json", "producer_release_handoff.json"):
            shutil.copy2(output / name, staging / name)
        if target.exists():
            expected = {name:(output/name).read_bytes() for name in ("cohort.json","producer_release_handoff.json")}
            actual = {name:(target/name).read_bytes() for name in expected if (target/name).is_file()}
            if actual != expected or len(actual) != 2:
                raise _error("DATA.RELEASE.REPACKAGE.PUBLISH_TERMINAL_CONFLICT", release_id)
            return target
        try:
            staging.replace(target)
        except OSError as exc:
            if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY} or not target.exists() or target.is_symlink() or not target.is_dir():
                raise
            expected={name:(output/name).read_bytes() for name in ("cohort.json","producer_release_handoff.json")}
            actual={name:(target/name).read_bytes() for name in expected if (target/name).is_file()}
            if actual!=expected or len(actual)!=2:
                raise _error("DATA.RELEASE.REPACKAGE.PUBLISH_TERMINAL_CONFLICT",release_id) from None
        return target
    finally:
        shutil.rmtree(staging, ignore_errors=True)

def _dual_readback(*, output: Path, terminal: Path, release_root: Path, repo_root: Path, repository_id: str, lineage: dict[str, Any]) -> dict[str, Any]:
    document = read_producer_release_handoff(output/"producer_release_handoff.json", repo_root=repo_root,
        output_root=release_root.parent.parent, release_root=release_root, expected_repository_id=repository_id)
    cohort_bytes=(output/"cohort.json").read_bytes(); handoff_bytes=(output/"producer_release_handoff.json").read_bytes()
    if document.get("repackageLineage") != lineage:
        raise _error("DATA.RELEASE.REPACKAGE.OUTPUT_READBACK_DRIFT", output.name)
    if (terminal/"cohort.json").read_bytes()!=cohort_bytes or (terminal/"producer_release_handoff.json").read_bytes()!=handoff_bytes:
        raise _error("DATA.RELEASE.REPACKAGE.PUBLISH_READBACK_DRIFT", output.name)
    # publish terminal reader validates exact current document against output release payload, then byte equality proves terminal copy.
    terminal_document=read_producer_release_handoff(terminal/"producer_release_handoff.json", repo_root=repo_root,
        output_root=release_root.parent.parent, release_root=release_root, expected_repository_id=repository_id)
    if terminal_document != document:
        raise _error("DATA.RELEASE.REPACKAGE.PUBLISH_READBACK_DRIFT", output.name)
    return {"outputHandoffDigest":_digest(handoff_bytes),"publishHandoffDigest":_digest((terminal/"producer_release_handoff.json").read_bytes()),
        "outputCohortDigest":_digest(cohort_bytes),"publishCohortDigest":_digest((terminal/"cohort.json").read_bytes())}

def repackage_legacy_release(*, frozen_source: FrozenLegacySource, publish_root: Path,
        target_release_root: Path, repository_id: str, source_repository_evidence: dict[str, Any],
        source_repository_evidence_ref: str,
        source_repository_evidence_digest: str, target_release_id: str, milestone: str,
        producer_baseline_revision: str, repo_root: Path, fault: str | None = None,
        before_source_cas: Callable[[], None] | None = None) -> dict[str, Any]:
    source = frozen_source
    target_id = safe_release_id(target_release_id, label="targetReleaseId")
    if source.release_id == target_id:
        raise _error("DATA.RELEASE.REPACKAGE.TARGET_ID_NOT_FRESH", target_id)
    target_root = _trusted_root(target_release_root, label="target")
    if target_root != source.root:
        raise _error("DATA.RELEASE.REPACKAGE.ROOT_BINDING_MISMATCH", "source/target release roots differ")
    require_publish_repository(publish_root, expected_repository_id=repository_id)
    try:
        assert_valid(source_repository_evidence, "release", "legacy_source_repository_evidence", label="source repository evidence")
    except ValueError as exc:
        raise _error("DATA.RELEASE.REPACKAGE.SOURCE_REPOSITORY_EVIDENCE_INVALID", str(exc)) from exc
    evidence_ref = str(source_repository_evidence_ref or "")
    expected_evidence_ref = f".repository-authorities/{source.release_id}.json"
    if evidence_ref != expected_evidence_ref:
        raise _error("DATA.RELEASE.REPACKAGE.SOURCE_REPOSITORY_EVIDENCE_REF_INVALID", evidence_ref)
    evidence_path = source.root / evidence_ref
    if evidence_path.is_symlink() or not evidence_path.is_file() or json.loads(evidence_path.read_bytes()) != source_repository_evidence:
        raise _error("DATA.RELEASE.REPACKAGE.SOURCE_REPOSITORY_EVIDENCE_INVALID", evidence_ref)
    if _digest(evidence_path.read_bytes()) != source_repository_evidence_digest:
        raise _error("DATA.RELEASE.REPACKAGE.SOURCE_REPOSITORY_EVIDENCE_DIGEST_DRIFT", source.release_id)
    from content.coordination.authority import verify_authority_artifact
    authority=verify_authority_artifact(source_repository_evidence["authorityRef"],source_repository_evidence["authorityDigest"],purpose="legacy-source-repository-seal")
    if (authority.get("repositoryId")!=source_repository_evidence["sourceRepositoryId"]
            or authority.get("sourceTerminalDigest")!=source_repository_evidence["sourceTerminalDigest"]):
        raise _error("DATA.RELEASE.REPACKAGE.SOURCE_REPOSITORY_AUTHORITY_INVALID",source.release_id)
    source_terminal_digest=_digest(_canonical_bytes({"releaseId":source.release_id,"handoffDigest":source.handoff_digest,"cohortDigest":source.cohort_digest}))
    if source_repository_evidence["sourceTerminalDigest"] != source_terminal_digest:
        raise _error("DATA.RELEASE.REPACKAGE.SOURCE_REPOSITORY_ROOT_DRIFT", source.release_id)
    target = _child(target_root, target_id, label="targetReleaseId", must_exist=False)
    lineage = {"schema":"quwoquan_data.legacy_release_repackage_lineage",
        "sourceRepositoryId":source_repository_evidence["sourceRepositoryId"],
        "sourceRepositoryEvidenceRef":evidence_ref,"sourceRepositoryEvidenceDigest":source_repository_evidence_digest,
        "sourceReleaseId":source.release_id,"sourceHandoffId":str(source.handoff["handoffId"]),
        "sourceHandoffDigest":source.handoff_digest,"sourceCohortDigest":source.cohort_digest}
    if target.exists():
        if _tree_digest(source.release_dir) != source.tree_digest:
            raise _error("DATA.RELEASE.REPACKAGE.SOURCE_TREE_MUTATED", source.release_id)
        document = read_producer_release_handoff(target / "producer_release_handoff.json", repo_root=repo_root,
            output_root=target_root.parent.parent, release_root=target_root, expected_repository_id=repository_id)
        if (document.get("repackageLineage") != lineage or document.get("producerBaselineRevision") != producer_baseline_revision
                or document.get("milestone") != milestone):
            raise _error("DATA.RELEASE.REPACKAGE.TARGET_CONFLICT", target_id)
        terminal=_terminal_copy(output=target,publish_root=publish_root,release_id=target_id)
        readback=_dual_readback(output=target,terminal=terminal,release_root=target_root,repo_root=repo_root,repository_id=repository_id,lineage=lineage)
        return {"status":"replayed","sourceReleaseId":source.release_id,"targetReleaseId":target_id,
            "sourceTreeDigest":source.tree_digest,"outputReadback":{"passed":True},"publishReadback":{"passed":True},**readback}
    staging_parent = target_root / ".repackage-staging"
    if staging_parent.exists() and staging_parent.is_symlink():
        raise _error("DATA.RELEASE.REPACKAGE.ROOT_SYMLINK", str(staging_parent))
    staging_parent.mkdir(exist_ok=True)
    staging_parent = _trusted_root(staging_parent, label="staging")
    staging_root = Path(tempfile.mkdtemp(prefix=f".{target_id}.", dir=staging_parent))
    work_release_root = staging_root / "releases"
    try:
        cohort = {"schema":"quwoquan_data.release_cohort","producerBaselineRevision":producer_baseline_revision,
            "objectRefs":list(source.refs),"milestone":milestone,
            "expectedCarrierCounts":{k:sum(ref.startswith(p) for ref in source.refs) for k,p in (("homepage","entities/"),("article","posts/article/"),("image","posts/image/"),("video","posts/video/"))},
            "repackageLineage":lineage}
        cohort_path = work_release_root / target_id / "cohort.json"
        cohort_path.parent.mkdir(parents=True); cohort_path.write_bytes(_canonical_bytes(cohort))
        if fault == "staging_write": raise OSError("injected staging write")
        build_pool_release(publish_root=publish_root, release_root=work_release_root, release_id=target_id, cohort_file=cohort_path)
        # repackage 不签发新 attestation；builder 复用只负责 current payload canonicalization。
        attestation = work_release_root / target_id / "attestations/release.json"
        if attestation.is_file():
            attestation.unlink()
            try:
                attestation.parent.rmdir()
            except OSError:
                pass
        if fault == "canonicalization": raise _error("DATA.RELEASE.REPACKAGE.CANONICALIZATION_FAILED", "injected")
        document, handoff_path, _ = write_producer_release_handoff(release_id=target_id, cohort_file=cohort_path,
            milestone=milestone, producer_baseline_revision=producer_baseline_revision, repo_root=repo_root,
            output_root=target_root.parent.parent, publish_root=publish_root, release_root=work_release_root)
        document["repackageLineage"] = lineage
        assert_valid(document, "release", "producer_release_handoff", label="repackaged handoff")
        handoff_path.write_bytes(_canonical_bytes(document))
        read_producer_release_handoff(handoff_path, repo_root=repo_root, output_root=target_root.parent.parent,
                                      release_root=work_release_root, expected_repository_id=repository_id)
        if fault == "integrity": raise _error("DATA.RELEASE.REPACKAGE.INTEGRITY_FAILED", "injected")
        if before_source_cas is not None: before_source_cas()
        # 最后一项可能失败的 source 判定必须位于原子 publish 之前；rename 后只返回已成功事实。
        if _tree_digest(source.release_dir) != source.tree_digest:
            raise _error("DATA.RELEASE.REPACKAGE.SOURCE_TREE_MUTATED", source.release_id)
        if fault in {"rename", "terminal"}: raise OSError(f"injected {fault}")
        replayed = _publish_staging(work_release_root / target_id, target)
        if fault == "publish_terminal": raise OSError("injected publish terminal")
        terminal=_terminal_copy(output=target,publish_root=publish_root,release_id=target_id)
        if fault == "readback": raise OSError("injected readback")
        readback=_dual_readback(output=target,terminal=terminal,release_root=target_root,repo_root=repo_root,repository_id=repository_id,lineage=lineage)
        return {"status":"replayed" if replayed else "created","sourceReleaseId":source.release_id,
            "targetReleaseId":target_id,"sourceTreeDigest":source.tree_digest,"sourceSchema":source.schema_name,
            "outputReadback":{"passed":True},"publishReadback":{"passed":True},**readback}
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)
