"""Pure release loading, media sync, and environment action policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from types import MappingProxyType
from typing import Any

_OPS_CLI_ROOT = Path(__file__).resolve().parents[5] / "quwoquan_ops" / "cli"
if str(_OPS_CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(_OPS_CLI_ROOT))

import handoff_consumer
from lib import handoff_store

from content.release.canonical.producer_release_handoff import (
    read_producer_release_handoff,
)
from content.release.canonical.release_header import validate_release_header
from content.release.canonical.environment_release_selection import DATA_POST_CAPS
from content.release.environment.topology import (
    EnvironmentReleaseMode,
    EnvironmentReleaseTarget,
)
from content.release.model import FULL_SYNC_RELEASE_KINDS, ReleaseKind
from core.io import read_json, write_json
from core.media_asset_url import (
    is_public_media_slice_key,
    release_media_delivery_key,
)
from core.media_library_sync import sync_media_library
from core.release_layout import payload_digest, payload_file, payload_root
from core.schema import assert_valid


_HANDOFF_FILENAME = "producer_release_handoff.json"
_SYSTEM_ATTESTATION_SUFFIX = ("attestations", "release.json")
_ADMISSION_KINDS = frozenset(
    {"producer_handoff", "empty_baseline_attestation"}
)
_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ReleaseAdmission:
    """One sealed release admission accepted before environment-side effects."""

    release: Path
    contract: Mapping[str, Any]
    release_id: str
    manifest_digest: str
    admission_kind: str
    handoff_ref: str = ""
    handoff_artifact_ref: str = ""
    handoff_artifact_digest: str = ""
    system_attestation_ref: str = ""
    system_attestation_digest: str = ""

    def __post_init__(self) -> None:
        if self.admission_kind not in _ADMISSION_KINDS:
            raise ValueError(
                "DATA.RELEASE.ADMISSION_KIND_INVALID: unsupported admission kind"
            )
        if self.admission_kind == "producer_handoff":
            if not (
                self.handoff_ref
                and self.handoff_artifact_ref
                and _SHA256_DIGEST.fullmatch(self.handoff_artifact_digest)
                and not self.system_attestation_ref
                and not self.system_attestation_digest
            ):
                raise ValueError(
                    "DATA.RELEASE.HANDOFF_ENVELOPE_INVALID: producer admission identity is incomplete"
                )
        elif not (
            self.system_attestation_ref
            and _SHA256_DIGEST.fullmatch(self.system_attestation_digest)
            and not self.handoff_ref
            and not self.handoff_artifact_ref
            and not self.handoff_artifact_digest
        ):
            raise ValueError(
                "DATA.RELEASE.SYSTEM_ATTESTATION_ENVELOPE_INVALID: baseline admission identity is incomplete"
            )

    def result_envelope(self) -> dict[str, str]:
        if self.admission_kind == "producer_handoff":
            return {
                "admissionKind": self.admission_kind,
                "handoffRef": self.handoff_ref,
                "handoffArtifactRef": self.handoff_artifact_ref,
                "handoffArtifactDigest": self.handoff_artifact_digest,
            }
        return {
            "admissionKind": self.admission_kind,
            "systemAttestationRef": self.system_attestation_ref,
            "systemAttestationDigest": self.system_attestation_digest,
        }


def _canonical_system_attestation_ref(value: object) -> tuple[str, str]:
    ref = str(value or "")
    relative = PurePosixPath(ref)
    if (
        not ref
        or relative.is_absolute()
        or ref != relative.as_posix()
        or "\\" in ref
        or any(part in {"", ".", ".."} for part in relative.parts)
        or any(ord(character) < 32 or ord(character) == 127 for character in ref)
    ):
        raise ValueError(
            "DATA.RELEASE.SYSTEM_ATTESTATION_REF_INVALID: ref must be an exact canonical QWQ_OUTPUT_ROOT-relative path"
        )
    parts = relative.parts
    if not (
        len(parts) == 5
        and parts[:2] == ("data", "releases")
        and parts[3:] == _SYSTEM_ATTESTATION_SUFFIX
    ):
        raise ValueError(
            "DATA.RELEASE.SYSTEM_ATTESTATION_REF_INVALID: expected data/releases/<releaseId>/attestations/release.json"
        )
    release_id = parts[2]
    if len(release_id.encode("utf-8")) > 255:
        raise ValueError(
            "DATA.RELEASE.ADMISSION_RELEASE_ID_DRIFT: releaseId invalid"
        )
    return ref, release_id


def _canonical_expected_digest(value: object, *, admission_kind: str) -> str:
    digest = str(value or "")
    if _SHA256_DIGEST.fullmatch(digest) is None:
        prefix = (
            "DATA.RELEASE.HANDOFF"
            if admission_kind == "producer_handoff"
            else "DATA.RELEASE.SYSTEM_ATTESTATION"
        )
        raise ValueError(f"{prefix}_DIGEST_INVALID: expected canonical sha256 digest")
    return digest


def _selected_admission(args: Any) -> tuple[str, str, str]:
    handoff_ref = getattr(args, "handoff_ref", None)
    attestation_ref = getattr(args, "system_attestation_ref", None)
    attestation_digest = getattr(args, "system_attestation_digest", None)
    if handoff_ref is not None:
        if attestation_ref is not None or attestation_digest is not None:
            raise ValueError(
                "DATA.RELEASE.ADMISSION_PAIR_INVALID: handoff and system attestation are mutually exclusive"
            )
        if not isinstance(handoff_ref, str) or not handoff_ref:
            raise ValueError("DATA.RELEASE.HANDOFF_REF_INVALID: authoritative ref is empty")
        return "producer_handoff", handoff_ref, ""
    if attestation_ref is None or attestation_digest is None:
        raise ValueError(
            "DATA.RELEASE.ADMISSION_PAIR_INVALID: choose --handoff-ref or a complete --system-attestation-ref/--system-attestation-digest pair"
        )
    return "empty_baseline_attestation", str(attestation_ref), str(attestation_digest)


def _assert_regular_file_without_symlinks(
    path: Path,
    *,
    root: Path,
    admission_kind: str,
) -> None:
    absolute_root = root.expanduser().absolute()
    absolute_path = path.expanduser().absolute()
    prefix = (
        "DATA.RELEASE.HANDOFF"
        if admission_kind == "producer_handoff"
        else "DATA.RELEASE.SYSTEM_ATTESTATION"
    )
    try:
        relative = absolute_path.relative_to(absolute_root)
    except ValueError as exc:
        raise ValueError(
            f"{prefix}_REF_INVALID: admission artifact escapes its canonical root"
        ) from exc
    candidates = list(reversed((absolute_root, *absolute_root.parents)))
    current = absolute_root
    for part in relative.parts:
        current = current / part
        candidates.append(current)
    try:
        for candidate in candidates:
            mode = os.lstat(candidate).st_mode
            if stat.S_ISLNK(mode):
                raise ValueError(f"{prefix}_SYMLINK_REJECTED: {candidate}")
    except FileNotFoundError as exc:
        raise ValueError(f"{prefix}_MISSING: {absolute_path}") from exc
    if not stat.S_ISREG(os.lstat(absolute_path).st_mode):
        raise ValueError(
            f"{prefix}_REF_INVALID: admission target must be a regular file"
        )


def _read_exact_json_object(
    path: Path,
    *,
    label: str,
    code: str,
) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"{code}: {label} is not valid JSON") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{code}: {label} must be an object")
    return document, raw


def _release_inputs(
    release: Path,
    *,
    release_id: str,
    failure_prefix: str,
) -> tuple[Mapping[str, Any], dict[str, Any], str]:
    desired_path = payload_file(release, "desired_state.json")
    header_path = payload_file(release, "release.json")
    try:
        admission_kind = (
            "producer_handoff"
            if failure_prefix == "DATA.RELEASE.HANDOFF"
            else "empty_baseline_attestation"
        )
        release_root = release.parent
        _assert_regular_file_without_symlinks(
            desired_path, root=release_root, admission_kind=admission_kind
        )
        _assert_regular_file_without_symlinks(
            header_path, root=release_root, admission_kind=admission_kind
        )
        contract, desired_raw = _read_exact_json_object(
            desired_path, label="desired_state",
            code=f"{failure_prefix}_RELEASE_INTEGRITY_FAILED",
        )
        header, header_raw = _read_exact_json_object(
            header_path, label="release header",
            code=f"{failure_prefix}_RELEASE_INTEGRITY_FAILED",
        )
        assert_valid(contract, "release", "release_desired_state", label=f"desired_state:{release_id}")
        validate_release_header(header, label=f"release_header:{release_id}")
        manifest_digest = payload_digest(release)
        if desired_path.read_bytes() != desired_raw or header_path.read_bytes() != header_raw:
            raise ValueError("release identity bytes changed during admission")
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise ValueError(f"{failure_prefix}_RELEASE_INTEGRITY_FAILED: {exc}") from exc
    if contract.get("releaseId") != release_id or header.get("releaseId") != release_id:
        raise ValueError(
            f"{failure_prefix}_RELEASE_ID_DRIFT: desired/header/release directory identities differ"
        )
    return MappingProxyType(dict(contract)), header, manifest_digest


def _admit_producer_handoff(
    *,
    handoff_ref: str,
    repo_root: Path,
    output_root: Path,
    release_root: Path,
) -> ReleaseAdmission:
    try:
        authority_bytes = handoff_store.read(handoff_ref, repo_root=repo_root)
        authority = handoff_consumer.validate_published_bytes(
            handoff_ref, authority_bytes, validate_current=True
        )
        artifact_ref, artifact_path, artifact_bytes, artifact_digest = (
            handoff_store.resolve_unique_artifact(
                authority, repo_root=repo_root,
                filename=_HANDOFF_FILENAME,
                schema="quwoquan_data.producer_release_handoff",
            )
        )
    except (OSError, TypeError, ValueError, handoff_store.HandoffStoreError) as exc:
        raise ValueError(f"DATA.RELEASE.HANDOFF_AUTHORITY_INVALID: {exc}") from exc
    try:
        document = read_producer_release_handoff(
            artifact_path, repo_root=repo_root, output_root=output_root,
            release_root=release_root,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError(f"DATA.RELEASE.HANDOFF_ARTIFACT_INVALID: {exc}") from exc
    if artifact_path.read_bytes() != artifact_bytes:
        raise ValueError(
            "DATA.RELEASE.HANDOFF_ARTIFACT_DIGEST_DRIFT: artifact changed during admission"
        )
    release_id = str(document.get("releaseId") or "")
    release = release_root.expanduser().absolute() / release_id
    binding = document.get("release")
    if not release_id or not isinstance(binding, Mapping):
        raise ValueError("DATA.RELEASE.HANDOFF_RELEASE_ID_DRIFT: release binding missing")
    contract, header, manifest_digest = _release_inputs(
        release, release_id=release_id, failure_prefix="DATA.RELEASE.HANDOFF"
    )
    if header.get("releaseKind") != "content":
        raise ValueError(
            "DATA.RELEASE.HANDOFF_RELEASE_KIND_INVALID: producer handoff admits only content releases"
        )
    if (
        document.get("handoffId") != release_id
        or binding.get("ref") != f"data/releases/{release_id}"
        or binding.get("headerRef") != f"data/releases/{release_id}/payload/release.json"
    ):
        raise ValueError(
            "DATA.RELEASE.HANDOFF_RELEASE_ID_DRIFT: artifact and release identities differ"
        )
    if binding.get("payloadDigest") != manifest_digest:
        raise ValueError(
            "DATA.RELEASE.HANDOFF_RELEASE_DIGEST_DRIFT: payload identity differs from artifact"
        )
    if (
        handoff_store.read(handoff_ref, repo_root=repo_root) != authority_bytes
        or artifact_path.read_bytes() != artifact_bytes
        or payload_digest(release) != manifest_digest
    ):
        raise ValueError(
            "DATA.RELEASE.HANDOFF_AUTHORITY_DRIFT: authority, artifact, or payload changed during admission"
        )
    return ReleaseAdmission(
        release=release, contract=contract, release_id=release_id,
        manifest_digest=manifest_digest, admission_kind="producer_handoff",
        handoff_ref=handoff_ref, handoff_artifact_ref=artifact_ref,
        handoff_artifact_digest=artifact_digest,
    )


def _admit_empty_baseline_attestation(
    *,
    admission_ref: str,
    release_id: str,
    expected_digest: str,
    output_root: Path,
    release_root: Path,
) -> ReleaseAdmission:
    output = output_root.expanduser().absolute()
    release_base = release_root.expanduser().absolute()
    artifact_path = output / PurePosixPath(admission_ref)
    release = release_base / release_id
    if artifact_path != release / "attestations" / "release.json":
        raise ValueError(
            "DATA.RELEASE.SYSTEM_ATTESTATION_REF_INVALID: attestation ref is outside the canonical release root"
        )
    _assert_regular_file_without_symlinks(
        artifact_path, root=output, admission_kind="empty_baseline_attestation"
    )
    attestation, raw = _read_exact_json_object(
        artifact_path, label="system attestation",
        code="DATA.RELEASE.SYSTEM_ATTESTATION_JSON_INVALID",
    )
    actual_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if actual_digest != expected_digest:
        raise ValueError(
            "DATA.RELEASE.SYSTEM_ATTESTATION_DIGEST_DRIFT: supplied digest does not bind the exact attestation bytes"
        )
    try:
        assert_valid(attestation, "release", "release_attestation", label=f"release_attestation:{release_id}")
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ValueError(f"DATA.RELEASE.SYSTEM_ATTESTATION_SCHEMA_INVALID: {exc}") from exc
    contract, header, manifest_digest = _release_inputs(
        release, release_id=release_id, failure_prefix="DATA.RELEASE.SYSTEM_ATTESTATION"
    )
    if (
        attestation.get("sourceOwner") != "qwq_data"
        or attestation.get("releaseKind") != "empty_baseline"
        or attestation.get("releaseId") != release_id
    ):
        raise ValueError(
            "DATA.RELEASE.SYSTEM_ATTESTATION_IDENTITY_DRIFT: attestation identity is invalid"
        )
    identity_fields = (
        "releaseId", "sourceOwner", "releaseKind", "releaseClass",
        "productLifecycleState", "containsUnverifiedAssets", "rightsStatusCounts",
        "authorizationRequiredAssetIds", "researchAcceptedCount",
        "commercialAcceptedCount", "canonicalMerkle", "executionIds", "sourceDigests",
    )
    if any(header.get(field) != attestation.get(field) for field in identity_fields):
        raise ValueError(
            "DATA.RELEASE.SYSTEM_ATTESTATION_RELEASE_ID_DRIFT: release header identity differs from attestation"
        )
    if attestation.get("payloadSha256") != manifest_digest:
        raise ValueError(
            "DATA.RELEASE.SYSTEM_ATTESTATION_PAYLOAD_DIGEST_DRIFT: payload differs from attestation"
        )
    if artifact_path.read_bytes() != raw or payload_digest(release) != manifest_digest:
        raise ValueError(
            "DATA.RELEASE.SYSTEM_ATTESTATION_DIGEST_DRIFT: attestation or payload changed during admission"
        )
    return ReleaseAdmission(
        release=release, contract=contract, release_id=release_id,
        manifest_digest=manifest_digest, admission_kind="empty_baseline_attestation",
        system_attestation_ref=admission_ref,
        system_attestation_digest=actual_digest,
    )


def admit_environment_release(
    args: Any,
    *,
    repo_root: Path,
    output_root: Path,
    release_root: Path,
) -> ReleaseAdmission:
    """Admit one authoritative producer handoff or empty baseline attestation."""

    admission_kind, raw_ref, raw_digest = _selected_admission(args)
    if admission_kind == "producer_handoff":
        return _admit_producer_handoff(
            handoff_ref=raw_ref, repo_root=repo_root, output_root=output_root,
            release_root=release_root,
        )
    admission_ref, release_id = _canonical_system_attestation_ref(raw_ref)
    expected_digest = _canonical_expected_digest(
        raw_digest, admission_kind=admission_kind
    )
    return _admit_empty_baseline_attestation(
        admission_ref=admission_ref, release_id=release_id,
        expected_digest=expected_digest, output_root=output_root,
        release_root=release_root,
    )


def load_release(release_root: Path, release_id: str) -> tuple[Path, dict[str, Any]]:
    release = release_root / release_id
    desired = payload_file(release, "desired_state.json")
    if not desired.is_file():
        raise SystemExit(f"[ship] immutable release desired_state 不存在：{desired}")
    contract = read_json(desired)
    header = read_json(payload_file(release, "release.json"))
    try:
        assert_valid(
            contract,
            "release",
            "release_desired_state",
            label=f"desired_state:{release_id}",
        )
        validate_release_header(header, label=f"release_header:{release_id}")
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"[ship] immutable release contract invalid: {exc}") from exc
    if contract.get("releaseId") != release_id or header.get("releaseId") != release_id:
        raise SystemExit("[ship] immutable release identity differs from requested release")
    return release, contract


def release_requires_full_sync(release: Path) -> bool:
    header = read_json(payload_file(release, "release.json"))
    try:
        return ReleaseKind(str(header.get("releaseKind") or "")) in FULL_SYNC_RELEASE_KINDS
    except ValueError as exc:
        raise SystemExit("[ship] releaseKind is invalid") from exc


def release_has_posts(contract: Mapping[str, Any]) -> bool:
    desired_refs = contract.get("desiredRefs")
    if not isinstance(desired_refs, Mapping):
        raise SystemExit("[ship] release desiredRefs is invalid")
    posts = desired_refs.get("posts")
    if not isinstance(posts, list):
        raise SystemExit("[ship] release desiredRefs.posts is invalid")
    return bool(posts)


def assert_environment_release_policy(
    *,
    release: Path,
    contract: Mapping[str, Any],
    environment: str,
) -> None:
    """Fail closed on environment mode and Data Post capacity drift."""

    env = str(environment).strip()
    if env not in DATA_POST_CAPS:
        raise SystemExit(
            f"[ship] DATA.RELEASE.ENVIRONMENT_POLICY_INVALID: unsupported environment {env!r}"
        )
    desired_refs = contract.get("desiredRefs")
    posts = desired_refs.get("posts") if isinstance(desired_refs, Mapping) else None
    if not isinstance(posts, list):
        raise SystemExit(
            "[ship] DATA.RELEASE.ENVIRONMENT_POLICY_INVALID: desiredRefs.posts must be an array"
        )
    post_refs = [str(item).strip() for item in posts]
    if any(not item for item in post_refs) or len(post_refs) != len(set(post_refs)):
        raise SystemExit(
            "[ship] DATA.RELEASE.ENVIRONMENT_POLICY_INVALID: Data Post refs must be unique and non-empty"
        )
    cap = DATA_POST_CAPS[env]
    if cap is not None and len(post_refs) > cap:
        raise SystemExit(
            "[ship] DATA.RELEASE.POST_CAP_EXCEEDED: "
            f"environment={env} count={len(post_refs)} cap={cap}"
        )
    header = read_json(payload_file(release, "release.json"))
    target_environment = str(header.get("targetEnvironment") or "").strip()
    if target_environment and target_environment != env:
        raise SystemExit(
            "[ship] DATA.RELEASE.TARGET_ENVIRONMENT_MISMATCH: "
            f"manifest={target_environment} requested={env}"
        )
    release_class = str(header.get("releaseClass") or "").strip()
    lifecycle = str(header.get("productLifecycleState") or "").strip()
    if release_class not in {"research", "commercial"} or lifecycle != release_class:
        raise SystemExit(
            "[ship] DATA.RELEASE.USAGE_SCOPE_MISMATCH: "
            "environment names cannot derive authorization; immutable "
            f"releaseClass/lifecycle={release_class or '<missing>'}/"
            f"{lifecycle or '<missing>'}"
        )


def release_media_public_slices(release: Path) -> dict[str, str]:
    """Map每个交付 key 到其摘要，形态必须与 header releaseClass 一致（DEC-031）。"""
    header_path = payload_file(release, "release.json")
    if not header_path.is_file():
        raise SystemExit(f"[ship] immutable release header 不存在：{header_path}")
    release_class = str(read_json(header_path).get("releaseClass") or "").strip()
    if release_class not in {"research", "commercial"}:
        raise SystemExit(
            "[ship] release header 必须声明 research/commercial releaseClass"
        )
    manifest = read_json(payload_file(release, "media_manifest.json"))
    if manifest.get("schema") != "quwoquan_data.release_media_manifest":
        raise SystemExit("[ship] release media manifest schema 无效")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise SystemExit("[ship] release media manifest assets 必须为数组")
    slices: dict[str, str] = {}
    for index, row in enumerate(assets):
        if not isinstance(row, Mapping):
            raise SystemExit(f"[ship] release media manifest assets[{index}] 必须为对象")
        try:
            key = release_media_delivery_key(row)
        except ValueError as exc:
            raise SystemExit(f"[ship] release media manifest 交付 key 非法: {exc}") from exc
        is_public = is_public_media_slice_key(key)
        if release_class == "research" and is_public:
            raise SystemExit(
                f"[ship] research release 不得携带公开交付 slice: {key}"
            )
        if release_class == "commercial" and not is_public:
            raise SystemExit(
                f"[ship] commercial release 不得携带私有交付 key: {key}"
            )
        sha256 = str(row.get("sha256") or "")
        prior = slices.get(key)
        if prior is not None and prior != sha256:
            raise SystemExit(f"[ship] release media manifest 交付 key 摘要冲突: {key}")
        slices[key] = sha256
    return dict(sorted(slices.items()))


def sync_media(*, release: Path, destination: str, run: Path) -> None:
    report = sync_media_library(
        payload_root(release),
        Path(destination),
        object_digests=release_media_public_slices(release),
        prune_unselected=False,
    )
    write_json(run / "media-sync.json", report)
    if report["failed"] or report["issues"]:
        raise SystemExit(f"[ship] media sync failed: {report['issues'][:5]}")


def assert_target_action_allowed(
    *,
    target: EnvironmentReleaseTarget,
    import_to_db: bool,
    dry_run: bool,
    action: str,
) -> None:
    if not import_to_db:
        return
    if target.mode is EnvironmentReleaseMode.PROJECTION_ONLY:
        raise SystemExit(
            f"[ship] {target.environment.value} is projection-only; database {action} is not a valid environment action"
        )
    if target.missing_requirements and not dry_run:
        raise SystemExit(
            f"[ship] environment release target is not ready for {action}; "
            "missing secret inputs: " + ", ".join(target.missing_requirements)
        )
