#!/usr/bin/env python3
"""Pure admission for create-only annotated RC and stable release tags."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

RC_SCHEMA = "quwoquan_ops.release_candidate_tag_admission_fact.v1"
STABLE_SCHEMA = "quwoquan_ops.release_tag_admission_fact.v1"
INTENT_SCHEMA = "quwoquan_ops.release_tag_admission_intent.v1"
MUTATION_SCHEMA = "quwoquan_ops.release_tag_mutation_outcome_fact.v1"
MANIFEST_SCHEMA = "quwoquan_ops.product_version_manifest.v1"
POLICY_SCHEMA = "quwoquan_ops.release_selection_policy.v1"
QUALIFICATION_SCHEMA = "quwoquan_ops.qualification_fact.v1"
MATERIAL_SCHEMA = "quwoquan_ops.candidate_material_manifest.v1"
ALLOCATION_SCHEMA = "quwoquan_ops.artifact_build_number_allocation.v1"
REQUEST_SCHEMA = "quwoquan_ops.release_qualification_request.v1"
HOSTED_ALLOCATION_PROVIDER = "github_actions_workflow_run_number"
_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_RC_PATTERN = r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-rc\.([1-9][0-9]*)$"
_STABLE_PATTERN = r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
_TEMP_PATTERN = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-dev\.([0-9]{14})\.([1-9][0-9]*)\+sha\.([0-9a-f]{12})$"


class ReleaseTagAdmissionError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def digest(value: Mapping[str, Any] | bytes | Path) -> str:
    raw = value.read_bytes() if isinstance(value, Path) else (
        value if isinstance(value, bytes) else canonical_bytes(value)
    )
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _fail(code: str, detail: str) -> None:
    raise ReleaseTagAdmissionError(code, detail)


def _text(value: object, field: str) -> str:
    if (
        not isinstance(value, str) or not value or value != value.strip()
        or any(char in value for char in "\x00\r\n")
    ):
        _fail("RELEASE_TAG.INVALID", f"{field} is invalid")
    return value


def _sha(value: object, field: str) -> str:
    result = _text(value, field)
    if _SHA.fullmatch(result) is None:
        _fail("RELEASE_TAG.INVALID", f"{field} is not an exact Git object id")
    return result


def _digest(value: object, field: str) -> str:
    result = _text(value, field)
    if _DIGEST.fullmatch(result) is None:
        _fail("RELEASE_TAG.INVALID", f"{field} is not an exact digest")
    return result


def _repository(value: object, field: str) -> str:
    result = _text(value, field)
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", result) is None:
        _fail("RELEASE_TAG.INVALID", f"{field} is not owner/repository")
    return result


def _timestamp(value: object, field: str) -> str:
    result = _text(value, field)
    try:
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReleaseTagAdmissionError(
            "RELEASE_TAG.INVALID", f"{field} is not RFC3339"
        ) from exc
    if parsed.tzinfo is None:
        _fail("RELEASE_TAG.INVALID", f"{field} lacks timezone")
    return result


def _time(value: object, field: str) -> datetime:
    return datetime.fromisoformat(_timestamp(value, field).replace("Z", "+00:00"))


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        _fail("RELEASE_TAG.READBACK_INVALID", f"{field} must be a positive integer")
    return value


def _identity(payload: Mapping[str, Any], field: str) -> None:
    claimed = _digest(payload.get(field), field)
    body = {key: value for key, value in payload.items() if key != field}
    if digest(body) != claimed:
        _fail("RELEASE_TAG.IDENTITY_INVALID", f"{field} does not match canonical bytes")


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    if set(value) != expected:
        _fail("RELEASE_TAG.VERSION_MANIFEST_INVALID", f"{field} shape drifted")


def _git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repository, text=True,
        capture_output=True, check=False,
    )
    if completed.returncode:
        _fail(
            "RELEASE_TAG.GIT_UNAVAILABLE",
            " ".join(completed.stderr.split()) or "Git query failed",
        )
    return completed.stdout.strip()


def _load_yaml(path: Path, field: str) -> tuple[dict[str, Any], str]:
    if not path.is_file() or path.is_symlink():
        _fail("RELEASE_TAG.POLICY_INVALID", f"{field} is missing or unsafe")
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ReleaseTagAdmissionError(
            "RELEASE_TAG.POLICY_INVALID", f"{field} is not strict YAML"
        ) from exc
    if not isinstance(value, dict):
        _fail("RELEASE_TAG.POLICY_INVALID", f"{field} must be an object")
    return value, digest(path)


def _exact(
    root: Path, value: object, field: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(value, Mapping) or set(value) != {"ref", "digest"}:
        _fail("RELEASE_TAG.INVALID", f"{field} must contain ref and digest")
    ref = _text(value.get("ref"), f"{field}.ref")
    relative = PurePosixPath(ref)
    if (
        relative.is_absolute() or relative.as_posix() != ref or "\\" in ref
        or any(part in {"", ".", "..", "latest"} for part in relative.parts)
    ):
        _fail("RELEASE_TAG.INVALID", f"{field}.ref is mutable or unsafe")
    expected = _digest(value.get("digest"), f"{field}.digest")
    path = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            _fail("RELEASE_TAG.INVALID", f"{field}.ref traverses symlink")
    if not path.is_file() or digest(path) != expected:
        _fail("RELEASE_TAG.STALE", f"{field} exact bytes drifted")
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseTagAdmissionError(
            "RELEASE_TAG.INVALID", f"{field} is invalid JSON"
        ) from exc
    if not isinstance(payload, dict):
        _fail("RELEASE_TAG.INVALID", f"{field} must be an object")
    return payload, {"ref": ref, "digest": expected}


def _write_once(path: Path, payload: Mapping[str, Any]) -> Path:
    encoded = canonical_bytes(payload) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0), 0o600,
        )
    except FileExistsError as exc:
        if path.is_symlink() or path.read_bytes() != encoded:
            raise ReleaseTagAdmissionError(
                "RELEASE_TAG.CREATE_CONFLICT", path.name
            ) from exc
        return path
    with os.fdopen(fd, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _policy(path: Path) -> tuple[dict[str, Any], str, re.Pattern[str], re.Pattern[str]]:
    policy, policy_digest = _load_yaml(path.resolve(), "releaseSelectionPolicy")
    if policy.get("schema") != POLICY_SCHEMA:
        _fail("RELEASE_TAG.POLICY_INVALID", "release selection schema drifted")
    try:
        semver = policy["semver"]
        rc_regex = re.compile(semver["rcTagRegex"])
        stable_regex = re.compile(semver["stableTagRegex"])
    except (KeyError, TypeError, re.error) as exc:
        raise ReleaseTagAdmissionError(
            "RELEASE_TAG.POLICY_INVALID", "tag regex is invalid"
        ) from exc
    expected_controls = (
        semver.get("version") == "2.0.0"
        and semver.get("rcTagRegex") == _RC_PATTERN
        and semver.get("stableTagRegex") == _STABLE_PATTERN
        and semver.get("temporaryArtifactRegex") == _TEMP_PATTERN
        and semver.get("temporaryArtifactCreatesGitRef") is False
        and policy.get("releaseTrain", {}).get("maximumActive") == 1
        and policy.get("releaseTrain", {}).get("activationRequiresAny")
        == ["previous_stable_imported", "initial_release_authority_approved"]
        and policy.get("tagObject", {}).get("representation") == "annotated"
        and policy.get("tagObject", {}).get("target") == "direct_commit"
        and policy.get("tagObject", {}).get("rejectLightweight") is True
        and policy.get("tagObject", {}).get("rejectTagOfTag") is True
        and policy.get("tagObject", {}).get("requiredReachabilityRef")
        == "refs/heads/main"
        and policy.get("controller", {}).get("count") == 1
        and policy.get("references", {}).get("create", {}).get("mode")
        == "create_only"
        and policy.get("references", {}).get("create", {}).get("allowedControllers")
        == [policy.get("controller", {}).get("identity")]
        and policy.get("references", {}).get("update")
        == {"decision": "denied", "bypassActors": []}
        and policy.get("references", {}).get("delete")
        == {"decision": "denied", "bypassActors": []}
        and policy.get("releaseCandidate", {}).get("sequence")
        == "monotonically_increasing_positive_integer"
        and policy.get("releaseCandidate", {}).get("reuse") == "denied"
        and policy.get("releaseCandidate", {}).get("productionEligible") is False
        and policy.get("stableSelection", {}).get("source")
        == "one_exact_qualified_rc"
        and policy.get("stableSelection", {}).get("rebuild") == "denied"
        and policy.get("stableSelection", {}).get("maximumStableTagsPerMaterial") == 1
        and policy.get("production", {}).get("selector")
        == "ReleaseTagAdmissionFact"
        and policy.get("production", {}).get("acceptedTagKind") == "stable"
        and policy.get("production", {}).get("rcDenied") is True
        and policy.get("production", {}).get("mainHeadDenied") is True
        and policy.get("production", {}).get("mutablePointerDenied") is True
    )
    if not expected_controls:
        _fail("RELEASE_TAG.POLICY_INVALID", "immutable tag controls drifted")
    return policy, policy_digest, rc_regex, stable_regex


def validate_product_version_manifest(
    *, manifest_path: Path, initial_release_authority: Mapping[str, str] | None = None,
    evidence_root: Path | None = None,
) -> tuple[dict[str, Any], str, str]:
    """Validate one active train and exact previous/initial activation authority."""
    manifest, manifest_digest = _load_yaml(
        manifest_path.resolve(), "productVersionManifest"
    )
    _exact_keys(manifest, {
        "schema", "kind", "authoringSource", "semverVersion", "activeTrainLimit",
        "releaseTrain", "previousStable", "initialReleaseAuthority", "activation",
    }, "ProductVersionManifest")
    if (
        manifest.get("schema") != MANIFEST_SCHEMA
        or manifest.get("kind") != "ProductVersionManifest"
        or manifest.get("authoringSource")
        != "quwoquan_ops/policies/product_version.yaml"
        or manifest.get("semverVersion") != "2.0.0"
        or manifest.get("activeTrainLimit") != 1
    ):
        _fail("RELEASE_TAG.VERSION_MANIFEST_INVALID", "manifest identity drifted")
    train = manifest.get("releaseTrain")
    previous = manifest.get("previousStable")
    initial = manifest.get("initialReleaseAuthority")
    activation = manifest.get("activation")
    if not all(isinstance(item, Mapping) for item in (train, previous, initial, activation)):
        _fail("RELEASE_TAG.VERSION_MANIFEST_INVALID", "manifest sections are incomplete")
    _exact_keys(train, {
        "state", "targetVersion", "bump", "bumpReason", "compatibilityBoundary",
    }, "releaseTrain")
    _exact_keys(previous, {
        "status", "tagName", "tagObjectOid", "peeledCommit", "admissionFact",
        "reasonCode",
    }, "previousStable")
    _exact_keys(initial, {"status", "authorityFact"}, "initialReleaseAuthority")
    _exact_keys(activation, {"decision", "basis", "reasonCode"}, "activation")
    state = train.get("state")
    if state not in {"inactive", "active", "released", "abandoned"}:
        _fail("RELEASE_TAG.VERSION_MANIFEST_INVALID", "release train state is invalid")

    root = evidence_root.resolve() if evidence_root is not None else None
    previous_imported = previous.get("status") == "imported"
    if previous_imported:
        if root is None:
            _fail("RELEASE_TAG.PREVIOUS_STABLE_NOT_IMPORTED", "previous stable readback is unavailable")
        previous_tag = _text(previous.get("tagName"), "previousStable.tagName")
        previous_oid = _sha(previous.get("tagObjectOid"), "previousStable.tagObjectOid")
        previous_commit = _sha(previous.get("peeledCommit"), "previousStable.peeledCommit")
        previous_fact, _ = _exact(root, previous.get("admissionFact"), "previousStable.admissionFact")
        if (
            previous_fact.get("schema") != STABLE_SCHEMA
            or previous_fact.get("decision") != "admitted"
            or previous_fact.get("tagName") != previous_tag
            or previous_fact.get("tagObjectOid") != previous_oid
            or previous_fact.get("peeledCommit") != previous_commit
        ):
            _fail("RELEASE_TAG.PREVIOUS_STABLE_NOT_IMPORTED", "previous stable exact admission drifted")
    elif previous.get("status") == "not_imported":
        if any(previous.get(name) is not None for name in (
            "tagName", "tagObjectOid", "peeledCommit", "admissionFact"
        )):
            _fail("RELEASE_TAG.VERSION_MANIFEST_INVALID", "unimported previous stable contains identity")
    else:
        _fail("RELEASE_TAG.VERSION_MANIFEST_INVALID", "previous stable status is invalid")

    authority_approved = False
    authority_exact: dict[str, str] | None = None
    if initial_release_authority is not None:
        if root is None:
            _fail("RELEASE_TAG.INVALID", "evidenceRoot is required for initial authority")
        authority, authority_exact = _exact(
            root, initial_release_authority, "initialReleaseAuthority"
        )
        authority_approved = (
            authority.get("schema") == "quwoquan_ops.initial_release_authority_fact.v1"
            and authority.get("status") == "approved"
            and authority.get("purpose") == "activate_initial_product_release_train"
        )
        if not authority_approved or initial.get("status") != "approved" or initial.get("authorityFact") != authority_exact:
            _fail("RELEASE_TAG.VERSION_AUTHORITY_INVALID", "initial release authority is invalid")
    elif initial.get("status") == "approved":
        _fail("RELEASE_TAG.VERSION_AUTHORITY_INVALID", "initial release authority readback is missing")
    elif initial != {"status": "absent", "authorityFact": None}:
        _fail("RELEASE_TAG.VERSION_MANIFEST_INVALID", "initial release authority state drifted")

    active = state == "active"
    if active:
        target = _text(train.get("targetVersion"), "releaseTrain.targetVersion")
        if re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", target) is None:
            _fail("RELEASE_TAG.VERSION_MANIFEST_INVALID", "targetVersion is not strict SemVer core")
        if train.get("bump") not in {"major", "minor", "patch", "initial"}:
            _fail("RELEASE_TAG.VERSION_MANIFEST_INVALID", "releaseTrain.bump is invalid")
        _text(train.get("bumpReason"), "releaseTrain.bumpReason")
        _text(train.get("compatibilityBoundary"), "releaseTrain.compatibilityBoundary")
        if not (previous_imported or authority_approved):
            _fail(
                "RELEASE_TAG.PREVIOUS_STABLE_NOT_IMPORTED",
                "active train requires imported previous stable or initial-release authority",
            )
        expected_basis = (
            "previous_stable_imported" if previous_imported
            else "initial_release_authority_approved"
        )
        if activation != {"decision": "active", "basis": expected_basis, "reasonCode": None}:
            _fail("RELEASE_TAG.VERSION_MANIFEST_INVALID", "activation decision drifted")
    elif state == "inactive":
        if any(train.get(name) is not None for name in (
            "targetVersion", "bump", "bumpReason", "compatibilityBoundary"
        )):
            _fail("RELEASE_TAG.VERSION_MANIFEST_INVALID", "inactive train contains a target")
        if (
            activation.get("decision") != "blocked"
            or activation.get("basis") != "none"
            or not isinstance(activation.get("reasonCode"), str)
        ):
            _fail("RELEASE_TAG.VERSION_MANIFEST_INVALID", "inactive train must be blocked")
        if not previous_imported and not authority_approved:
            return manifest, manifest_digest, "blocked"
    return manifest, manifest_digest, "active" if active else str(state)


def inspect_tag(repository: Path, tag_name: str) -> dict[str, str]:
    """Read an existing Git tag object without mutating refs."""
    tag = _text(tag_name, "tagName")
    ref = f"refs/tags/{tag}"
    try:
        object_oid = _sha(_git(repository, "rev-parse", "--verify", ref), "tagObjectOid")
    except ReleaseTagAdmissionError as exc:
        if exc.code == "RELEASE_TAG.GIT_UNAVAILABLE":
            _fail("RELEASE_TAG.MISSING", f"{tag} does not exist")
        raise
    if _git(repository, "cat-file", "-t", object_oid) != "tag":
        _fail("RELEASE_TAG.LIGHTWEIGHT", f"{tag} must be annotated")
    target_oid = _sha(_git(repository, "rev-parse", f"{ref}^{{}}"), "peeledCommit")
    if _git(repository, "cat-file", "-t", target_oid) != "commit":
        _fail("RELEASE_TAG.TAG_OF_TAG", f"{tag} must directly target a commit")
    raw = _git(repository, "cat-file", "-p", object_oid)
    target_line = next((line for line in raw.splitlines() if line.startswith("object ")), "")
    direct_oid = _sha(target_line.removeprefix("object "), "directTarget")
    if direct_oid != target_oid or _git(repository, "cat-file", "-t", direct_oid) != "commit":
        _fail("RELEASE_TAG.TAG_OF_TAG", f"{tag} must not point to another tag")
    return {
        "tagName": tag, "tagObjectOid": object_oid,
        "peeledCommit": target_oid,
        "sourceTree": _sha(
            _git(repository, "show", "-s", "--format=%T", target_oid),
            "sourceTree",
        ),
    }


def _require_main_reachable(repository: Path, commit: str) -> None:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "refs/heads/main"],
        cwd=repository, text=True, capture_output=True, check=False,
    )
    if completed.returncode == 1:
        _fail("RELEASE_TAG.NOT_MAIN_REACHABLE", "tag commit is not reachable from main")
    if completed.returncode != 0:
        _fail("RELEASE_TAG.GIT_UNAVAILABLE", "main reachability is unavailable")


def _controller_producer(
    *, app_id: int, installation_id: int, app_slug: str,
) -> dict[str, Any]:
    return {
        "kind": "github_app_installation",
        "appId": _positive_int(app_id, "controllerAppId"),
        "installationId": _positive_int(
            installation_id, "controllerInstallationId"
        ),
        "slug": _text(app_slug, "controllerAppSlug"),
    }


def _readback_common(
    root: Path, exact: Mapping[str, str], *, name: str, phase: str,
    tag_name: str, tag: Mapping[str, str] | None,
    producer: Mapping[str, Any], repository: str,
) -> tuple[dict[str, Any], dict[str, str], datetime]:
    fact, normalized = _exact(root, exact, name)
    if fact.get("schema") == f"quwoquan_ops.{name}_fact.v1":
        _identity(fact, "readbackId")
    expected_object = None if tag is None else tag["tagObjectOid"]
    expected_commit = None if tag is None else tag["peeledCommit"]
    if (
        fact.get("schema") != f"quwoquan_ops.{name}_fact.v1"
        or fact.get("status") != "verified"
        or fact.get("phase") != phase
        or fact.get("producer") != dict(producer)
        or fact.get("repository") != repository
        or fact.get("tagRef") != f"refs/tags/{tag_name}"
        or fact.get("tagName") != tag_name
        or fact.get("tagObjectOid") != expected_object
        or fact.get("peeledCommit") != expected_commit
    ):
        _fail(
            "RELEASE_TAG.READBACK_INVALID",
            f"{name} authority or tag identity drifted",
        )
    return fact, normalized, _time(
        fact.get("observedAt"), f"{name}.observedAt"
    )


def _creator_readback(
    root: Path, exact: Mapping[str, str], *, phase: str, tag_name: str,
    tag: Mapping[str, str] | None, producer: Mapping[str, Any],
    repository: str, outcome_id: str | None = None,
) -> tuple[dict[str, str], datetime]:
    fact, normalized, observed = _readback_common(
        root, exact, name="creator_readback", phase=phase,
        tag_name=tag_name, tag=tag, producer=producer,
        repository=repository,
    )
    if set(fact) != {
        "schema", "readbackId", "status", "phase", "producer",
        "repository", "tagRef", "tagName", "tagObjectOid",
        "peeledCommit", "creator", "creationRecord", "observedAt",
    }:
        _fail("RELEASE_TAG.READBACK_INVALID", "creator readback shape drifted")
    if phase == "pre_mutation":
        if fact.get("creator") is not None or fact.get("creationRecord") is not None:
            _fail(
                "RELEASE_TAG.READBACK_INVALID",
                "pre-mutation creator readback must prove absence",
            )
        return normalized, observed
    if tag is None or outcome_id is None:
        _fail("RELEASE_TAG.READBACK_INVALID", "post-mutation binding is incomplete")
    record = fact.get("creationRecord")
    expected_actor = f"{producer['slug']}[bot]"
    expected_external_id = (
        f"release-tag:{repository}:{tag_name}:"
        f"{tag['tagObjectOid']}:{outcome_id}"
    )
    if (
        fact.get("creator") != expected_actor
        or not isinstance(record, Mapping)
        or set(record) != {
            "kind", "recordId", "nodeId", "name", "externalId",
            "status", "conclusion", "headSha", "appId", "appSlug",
            "repository", "completedAt",
        }
        or record.get("kind") != "github_check_run"
        or _positive_int(record.get("recordId"), "creationRecord.recordId") <= 0
        or record.get("name") != "release-tag-creation"
        or record.get("externalId") != expected_external_id
        or record.get("status") != "completed"
        or record.get("conclusion") != "success"
        or record.get("headSha") != tag["peeledCommit"]
        or record.get("appId") != producer["appId"]
        or record.get("appSlug") != producer["slug"]
        or record.get("repository") != repository
        or _time(record.get("completedAt"), "creationRecord.completedAt")
        > observed
    ):
        _fail(
            "RELEASE_TAG.CONTROLLER_DENIED",
            "creator is not the authenticated controller App",
        )
    _text(record.get("nodeId"), "creationRecord.nodeId")
    return normalized, observed


def _ruleset_readback(
    root: Path, exact: Mapping[str, str], *, phase: str, tag_name: str,
    tag: Mapping[str, str] | None, producer: Mapping[str, Any],
    repository: str,
) -> tuple[dict[str, str], datetime, tuple[int, str, str]]:
    fact, normalized, observed = _readback_common(
        root, exact, name="ruleset_readback", phase=phase,
        tag_name=tag_name, tag=tag, producer=producer,
        repository=repository,
    )
    version, pattern = fact.get("rulesetVersion"), fact.get("refNamePattern")
    if (
        set(fact) != {
            "schema", "readbackId", "status", "phase", "producer",
            "repository", "tagRef", "tagName", "tagObjectOid",
            "peeledCommit", "rulesetId", "rulesetVersion", "target",
            "enforcement", "refNamePattern", "create", "update",
            "delete", "bypass", "observedAt",
        }
        or not isinstance(version, Mapping)
        or set(version) != {"etag", "apiPayloadDigest"}
        or pattern != {"include": ["refs/tags/v*"], "exclude": []}
        or fact.get("target") != "tag"
        or fact.get("enforcement") != "active"
        or fact.get("create") != {
            "decision": "allowed", "mode": "create_only", "bypassActors": [],
        }
        or fact.get("update") != {"decision": "denied", "bypassActors": []}
        or fact.get("delete") != {"decision": "denied", "bypassActors": []}
        or fact.get("bypass") != {"mode": "closed", "actors": []}
    ):
        _fail(
            "RELEASE_TAG.READBACK_INVALID",
            "tag ruleset closed controls drifted",
        )
    ruleset_id = _positive_int(fact.get("rulesetId"), "rulesetId")
    etag = _text(version.get("etag"), "rulesetVersion.etag")
    payload_digest = _digest(
        version.get("apiPayloadDigest"), "rulesetVersion.apiPayloadDigest"
    )
    return normalized, observed, (ruleset_id, etag, payload_digest)

def _existing_facts(root: Path, schema: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not root.exists():
        return result
    for path in sorted(root.rglob("*.json")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            value = json.loads(path.read_bytes())
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("schema") == schema:
            result.append(value)
    return result


def _source_identity(repository: Path, commit: str) -> dict[str, str]:
    source = _sha(commit, "sourceGitSha")
    if _git(repository, "cat-file", "-t", source) != "commit":
        _fail("RELEASE_TAG.INVALID", "sourceGitSha is not a commit")
    _require_main_reachable(repository, source)
    return {
        "peeledCommit": source,
        "sourceTree": _sha(
            _git(repository, "show", "-s", "--format=%T", source),
            "sourceTree",
        ),
    }


def _reservation(root: Path, exact: Mapping[str, str], *, tag: Mapping[str, str]) -> dict[str, str]:
    fact, normalized = _exact(root, exact, "reservation")
    if (
        fact.get("schema") != "quwoquan_ops.release_tag_reservation_fact.v1"
        or fact.get("status") != "reserved"
        or fact.get("tagName") != tag["tagName"]
        or fact.get("tagKind") != tag["tagKind"]
        or fact.get("sourceGitSha") != tag["peeledCommit"]
        or fact.get("sourceTree") != tag["sourceTree"]
    ):
        _fail("RELEASE_TAG.RESERVATION_INVALID", "reservation does not bind exact tag input")
    return normalized


def _intent_path(root: Path, tag_kind: str, tag_name: str) -> Path:
    return root / "release-tags" / "intents" / tag_kind / tag_name / "intent.json"


def _outcome_path(root: Path, intent_id: str) -> Path:
    return root / "release-tags" / "mutation-outcomes" / intent_id / "outcome.json"


def _intent(
    root: Path, exact: Mapping[str, str], *, tag_kind: str, tag_name: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    value, normalized = _exact(root, exact, "admissionIntent")
    if value.get("schema") == INTENT_SCHEMA:
        _identity(value, "intentId")
    common = {
        "schema", "intentId", "decision", "tagKind", "tagName",
        "peeledCommit", "sourceTree", "productVersion", "reservation",
        "productVersionManifestDigest", "releaseSelectionPolicyDigest",
        "repository", "controllerProducer", "preCreatorReadback",
        "preRulesetReadback", "admittedAt",
    }
    kind_specific = (
        {"rcSequence", "selectionFact"}
        if tag_kind == "rc"
        else {
            "selectedRcAdmission", "selectedRcTagName",
            "selectedRcTagObjectOid", "qualificationFact",
            "qualificationId", "candidateMaterialManifest",
            "candidateMaterialId", "candidateIdentity",
            "artifactBuildNumber", "artifacts", "productAuthorityFact",
            "releaseAuthorityFact",
        }
    )
    if (
        set(value) != common | kind_specific
        or value.get("schema") != INTENT_SCHEMA
        or value.get("decision") != "mutation_admitted"
        or value.get("tagKind") != tag_kind
        or value.get("tagName") != tag_name
    ):
        _fail("RELEASE_TAG.INTENT_INVALID", "admission intent shape or authority drifted")
    return value, normalized


def record_tag_mutation_outcome(
    *, evidence_root: Path, admission_intent_ref: Mapping[str, str],
    tag_kind: str, tag_name: str, status: str, recorded_at: str,
    tag_object_oid: str | None = None, peeled_commit: str | None = None,
) -> Path:
    """Seal one terminal mutation outcome; failed intents can never be reused."""
    root = evidence_root.resolve()
    intent, intent_exact = _intent(
        root, admission_intent_ref, tag_kind=tag_kind, tag_name=tag_name,
    )
    _assert_intent_unused(root, intent)
    if status not in {"created", "failed"}:
        _fail("RELEASE_TAG.INVALID", "mutation status must be created or failed")
    object_oid = _sha(tag_object_oid, "tagObjectOid") if status == "created" else None
    commit = _sha(peeled_commit, "peeledCommit") if status == "created" else None
    if status == "created" and commit != intent.get("peeledCommit"):
        _fail("RELEASE_TAG.MUTATION_MISMATCH", "created tag target drifted from intent")
    if status == "failed" and (tag_object_oid is not None or peeled_commit is not None):
        _fail("RELEASE_TAG.INVALID", "failed mutation must not claim a Git object")
    recorded = _time(recorded_at, "recordedAt")
    if recorded < _time(intent.get("admittedAt"), "intent.admittedAt"):
        _fail("RELEASE_TAG.TIME_ORDER_INVALID", "mutation outcome predates admission intent")
    body: dict[str, Any] = {
        "schema": MUTATION_SCHEMA, "intent": intent_exact,
        "intentId": intent["intentId"], "tagKind": tag_kind,
        "tagName": tag_name, "status": status,
        "tagObjectOid": object_oid, "peeledCommit": commit,
        "recordedAt": _timestamp(recorded_at, "recordedAt"),
    }
    body["outcomeId"] = digest(body)
    return _write_once(_outcome_path(root, intent["intentId"]), body)


def _created_outcome(
    root: Path, intent: Mapping[str, Any], intent_exact: Mapping[str, str],
    outcome_ref: Mapping[str, str], *, tag: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, str]]:
    outcome, normalized = _exact(root, outcome_ref, "mutationOutcome")
    if outcome.get("schema") == MUTATION_SCHEMA:
        _identity(outcome, "outcomeId")
    if (
        set(outcome) != {
            "schema", "outcomeId", "intent", "intentId", "tagKind",
            "tagName", "status", "tagObjectOid", "peeledCommit", "recordedAt",
        }
        or outcome.get("schema") != MUTATION_SCHEMA
        or outcome.get("intent") != dict(intent_exact)
        or outcome.get("intentId") != intent.get("intentId")
        or outcome.get("tagKind") != intent.get("tagKind")
        or outcome.get("tagName") != tag["tagName"]
        or outcome.get("status") != "created"
        or outcome.get("tagObjectOid") != tag["tagObjectOid"]
        or outcome.get("peeledCommit") != tag["peeledCommit"]
    ):
        _fail("RELEASE_TAG.MUTATION_MISMATCH", "mutation outcome does not bind hosted tag")
    return outcome, normalized


def _assert_intent_unused(root: Path, intent: Mapping[str, Any]) -> None:
    outcome = _outcome_path(root, str(intent["intentId"]))
    if not outcome.exists():
        return
    try:
        value = json.loads(outcome.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseTagAdmissionError(
            "RELEASE_TAG.MUTATION_OUTCOME_INVALID", "mutation outcome is unreadable"
        ) from exc
    status = value.get("status") if isinstance(value, Mapping) else None
    if status == "failed":
        _fail("RELEASE_TAG.MUTATION_FAILED", "admission intent is terminally failed")
    _fail("RELEASE_TAG.INTENT_REPLAY", "admission intent was already consumed")


def _artifact_map(value: object, field: str) -> list[dict[str, str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        _fail("RELEASE_TAG.QUALIFICATION_INVALID", f"{field} is empty")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, artifact in enumerate(value):
        if not isinstance(artifact, Mapping) or set(artifact) != {"platform", "ociRef", "digest"}:
            _fail("RELEASE_TAG.QUALIFICATION_INVALID", f"{field}[{index}] shape drifted")
        platform = _text(artifact.get("platform"), f"{field}[{index}].platform")
        exact_digest = _digest(artifact.get("digest"), f"{field}[{index}].digest")
        oci = _text(artifact.get("ociRef"), f"{field}[{index}].ociRef")
        if platform in seen or not oci.endswith("@" + exact_digest):
            _fail("RELEASE_TAG.QUALIFICATION_INVALID", f"{field} is not exact OCI material")
        seen.add(platform)
        result.append({"platform": platform, "ociRef": oci, "digest": exact_digest})
    return sorted(result, key=lambda item: item["platform"])


def _base_and_rc(tag_name: str, rc_regex: re.Pattern[str]) -> tuple[str, int]:
    match = rc_regex.fullmatch(tag_name)
    if match is None:
        _fail("RELEASE_TAG.MALFORMED", "tag is not a strict RC")
    return ".".join(match.groups()[:3]), int(match.group(4))


def create_release_candidate_tag_intent(
    *, repository: Path, evidence_root: Path, tag_name: str, source_git_sha: str,
    product_version_manifest_path: Path, release_selection_policy_path: Path,
    reservation_ref: Mapping[str, str], selection_fact_ref: Mapping[str, str],
    creator_readback_ref: Mapping[str, str], ruleset_readback_ref: Mapping[str, str],
    repository_identity: str, controller_app_id: int,
    controller_installation_id: int, controller_app_slug: str,
    admitted_at: str,
    initial_release_authority_ref: Mapping[str, str] | None = None,
) -> Path:
    """Validate RC authorities and seal create-once intent before Git mutation."""
    repository, root = repository.resolve(), evidence_root.resolve()
    policy, policy_digest, rc_regex, _ = _policy(release_selection_policy_path)
    manifest, manifest_digest, state = validate_product_version_manifest(
        manifest_path=product_version_manifest_path,
        initial_release_authority=initial_release_authority_ref, evidence_root=root,
    )
    if state != "active":
        _fail("RELEASE_TAG.VERSION_TRAIN_INACTIVE", "product release train is not active")
    base, sequence = _base_and_rc(tag_name, rc_regex)
    if manifest["releaseTrain"]["targetVersion"] != base:
        _fail("RELEASE_TAG.VERSION_MISMATCH", "RC does not match the active target version")
    source = _source_identity(repository, source_git_sha)
    tag = {"tagKind": "rc", "tagName": tag_name, **source}
    reservation = _reservation(root, reservation_ref, tag=tag)
    selection, selection_exact = _exact(root, selection_fact_ref, "selectionFact")
    if (
        selection.get("schema") != "quwoquan_ops.release_candidate_selection_fact.v1"
        or selection.get("status") != "approved"
        or selection.get("tagName") != tag_name
        or selection.get("sourceGitSha") != source["peeledCommit"]
        or selection.get("sourceTree") != source["sourceTree"]
        or selection.get("productVersionManifestDigest") != manifest_digest
    ):
        _fail("RELEASE_TAG.SELECTION_INVALID", "RC selection does not bind exact source and manifest")
    controller = _text(policy["controller"]["identity"], "controller.identity")
    repository_identity = _repository(repository_identity, "repositoryIdentity")
    producer = _controller_producer(
        app_id=controller_app_id,
        installation_id=controller_installation_id,
        app_slug=controller_app_slug,
    )
    if producer["slug"] != controller:
        _fail("RELEASE_TAG.CONTROLLER_DENIED", "controller App slug drifted from policy")
    admitted = _time(admitted_at, "admittedAt")
    creator, creator_at = _creator_readback(
        root, creator_readback_ref, phase="pre_mutation",
        tag_name=tag_name, tag=None, producer=producer,
        repository=repository_identity,
    )
    ruleset, ruleset_at, _ = _ruleset_readback(
        root, ruleset_readback_ref, phase="pre_mutation",
        tag_name=tag_name, tag=None, producer=producer,
        repository=repository_identity,
    )
    if max(creator_at, ruleset_at) > admitted:
        _fail(
            "RELEASE_TAG.TIME_ORDER_INVALID",
            "hosted pre-readback occurred after intent admission",
        )
    for intent in _existing_facts(root / "release-tags" / "intents" / "rc", INTENT_SCHEMA):
        if intent.get("tagName") == tag_name:
            _fail("RELEASE_TAG.INTENT_REPLAY", "RC tag name already has an admission intent")
        if intent.get("productVersion") == base and intent.get("rcSequence") == sequence:
            _fail("RELEASE_TAG.RC_REUSED", "RC sequence is already reserved")
        if intent.get("productVersion") == base and int(intent.get("rcSequence", 0)) >= sequence:
            _fail("RELEASE_TAG.RC_NOT_MONOTONIC", "RC sequence must increase")
    body: dict[str, Any] = {
        "schema": INTENT_SCHEMA, "decision": "mutation_admitted",
        **tag, "productVersion": base, "rcSequence": sequence,
        "reservation": reservation, "selectionFact": selection_exact,
        "productVersionManifestDigest": manifest_digest,
        "releaseSelectionPolicyDigest": policy_digest,
        "repository": repository_identity, "controllerProducer": producer,
        "preCreatorReadback": creator, "preRulesetReadback": ruleset,
        "admittedAt": _timestamp(admitted_at, "admittedAt"),
    }
    body["intentId"] = digest(body)
    return _write_once(_intent_path(root, "rc", tag_name), body)


def _validate_stable_authorities(
    *, root: Path, tag_name: str, source: Mapping[str, str], version: str,
    manifest_digest: str, selected_rc_admission_ref: Mapping[str, str],
    qualification_fact_ref: Mapping[str, str],
    product_authority_fact_ref: Mapping[str, str],
    release_authority_fact_ref: Mapping[str, str],
) -> dict[str, Any]:
    rc, rc_exact = _exact(root, selected_rc_admission_ref, "selectedRcAdmission")
    qualification, qualification_exact = _exact(root, qualification_fact_ref, "qualificationFact")
    material, material_exact = _exact(root, qualification.get("candidateMaterialManifest"), "candidateMaterialManifest")
    request, request_exact = _exact(root, material.get("qualificationRequest"), "qualificationRequest")
    allocation_ref = material.get("artifactBuildNumberAllocation")
    if not isinstance(allocation_ref, Mapping):
        _fail("RELEASE_TAG.QUALIFICATION_INVALID", "hosted build-number allocation is required")
    allocation, _ = _exact(root, allocation_ref, "artifactBuildNumberAllocation")
    for value, schema, identity, code in (
        (rc, RC_SCHEMA, "admissionId", "RELEASE_TAG.RC_INVALID"),
        (qualification, QUALIFICATION_SCHEMA, "qualificationId", "RELEASE_TAG.QUALIFICATION_INVALID"),
        (material, MATERIAL_SCHEMA, "materialId", "RELEASE_TAG.QUALIFICATION_INVALID"),
        (request, REQUEST_SCHEMA, "requestId", "RELEASE_TAG.QUALIFICATION_INVALID"),
        (allocation, ALLOCATION_SCHEMA, "allocationId", "RELEASE_TAG.QUALIFICATION_INVALID"),
    ):
        if value.get("schema") == schema:
            try:
                _identity(value, identity)
            except ReleaseTagAdmissionError as exc:
                raise ReleaseTagAdmissionError(code, exc.detail) from exc
    if (
        rc.get("schema") != RC_SCHEMA or rc.get("decision") != "admitted"
        or rc.get("productVersion") != version
        or rc.get("peeledCommit") != source["peeledCommit"]
        or rc.get("sourceTree") != source["sourceTree"]
        or rc.get("productVersionManifestDigest") != manifest_digest
    ):
        _fail("RELEASE_TAG.RC_INVALID", "selected RC does not bind stable tag")
    qualified_artifacts = _artifact_map(qualification.get("artifacts"), "qualification.artifacts")
    material_artifacts = _artifact_map(material.get("artifacts"), "material.artifacts")
    hosted = allocation.get("hostedAuthority")
    if (
        request.get("schema") != REQUEST_SCHEMA or request.get("rcTagAdmission") != rc_exact
        or request.get("sourceGitSha") != source["peeledCommit"]
        or request.get("sourceTree") != source["sourceTree"]
        or request.get("tagName") != rc.get("tagName")
        or material.get("qualificationRequest") != request_exact
        or qualification.get("qualificationRequest") != request_exact
        or allocation.get("schema") != ALLOCATION_SCHEMA
        or allocation.get("requestId") != request.get("requestId")
        or allocation.get("qualificationRequest") != request_exact
        or allocation.get("artifactBuildNumber") != material.get("artifactBuildNumber")
        or allocation.get("predecessor") is not None
        or not isinstance(hosted, Mapping)
        or set(hosted) != {"provider", "runId", "runNumber"}
        or hosted.get("provider") != HOSTED_ALLOCATION_PROVIDER
        or hosted.get("runNumber") != material.get("artifactBuildNumber")
    ):
        _fail("RELEASE_TAG.QUALIFICATION_INVALID", "hosted build-number allocation drifted")
    _text(hosted.get("runId"), "hostedAuthority.runId")
    if (
        qualification.get("schema") != QUALIFICATION_SCHEMA
        or qualification.get("decision") != "qualified"
        or material.get("schema") != MATERIAL_SCHEMA
        or qualification.get("tagName") != rc.get("tagName")
        or qualification.get("sourceGitSha") != source["peeledCommit"]
        or qualification.get("sourceTree") != source["sourceTree"]
        or qualification.get("artifactBuildNumber") != material.get("artifactBuildNumber")
        or qualified_artifacts != material_artifacts
        or qualification.get("candidateMaterialManifest") != material_exact
        or material.get("sourceGitSha") != source["peeledCommit"]
        or material.get("sourceTree") != source["sourceTree"]
        or material.get("tagName") != rc.get("tagName")
        or material.get("productVersionManifest", {}).get("digest") != manifest_digest
    ):
        _fail("RELEASE_TAG.QUALIFICATION_INVALID", "QualificationFact/material exact binding drifted")
    product, product_exact = _exact(root, product_authority_fact_ref, "productAuthority")
    release, release_exact = _exact(root, release_authority_fact_ref, "releaseAuthority")
    qualification_id = _digest(qualification.get("qualificationId"), "qualificationId")
    material_id = _digest(material.get("materialId"), "materialId")
    if (
        product.get("schema") != "quwoquan_ops.product_release_authority_fact.v1"
        or product.get("status") != "approved"
        or product.get("selectedRcTagObjectOid") != rc.get("tagObjectOid")
        or product.get("qualificationId") != qualification_id
        or product.get("productVersionManifestDigest") != manifest_digest
        or product.get("sourceGitSha") != source["peeledCommit"]
        or product.get("candidateMaterialId") != material_id
    ):
        _fail("RELEASE_TAG.PRODUCT_AUTHORITY_INVALID", "product authority did not select exact RC")
    if (
        release.get("schema") != "quwoquan_ops.release_authority_fact.v1"
        or release.get("status") != "approved" or release.get("stableTagName") != tag_name
        or release.get("selectedRcTagObjectOid") != rc.get("tagObjectOid")
        or release.get("qualificationId") != qualification_id
        or release.get("sourceGitSha") != source["peeledCommit"]
        or release.get("candidateMaterialId") != material_id
    ):
        _fail("RELEASE_TAG.RELEASE_AUTHORITY_INVALID", "release authority did not approve exact stable")
    candidate_identity = digest({
        "peeledCommit": source["peeledCommit"], "sourceTree": source["sourceTree"],
        "artifactBuildNumber": material["artifactBuildNumber"], "artifacts": material_artifacts,
    })
    return {
        "selectedRcAdmission": rc_exact, "selectedRcTagName": rc["tagName"],
        "selectedRcTagObjectOid": rc["tagObjectOid"],
        "qualificationFact": qualification_exact, "qualificationId": qualification_id,
        "candidateMaterialManifest": material_exact, "candidateMaterialId": material_id,
        "candidateIdentity": candidate_identity,
        "artifactBuildNumber": material["artifactBuildNumber"], "artifacts": material_artifacts,
        "productAuthorityFact": product_exact, "releaseAuthorityFact": release_exact,
    }

def create_release_tag_intent(
    *, repository: Path, evidence_root: Path, tag_name: str, source_git_sha: str,
    product_version_manifest_path: Path, release_selection_policy_path: Path,
    reservation_ref: Mapping[str, str], selected_rc_admission_ref: Mapping[str, str],
    qualification_fact_ref: Mapping[str, str],
    product_authority_fact_ref: Mapping[str, str], release_authority_fact_ref: Mapping[str, str],
    creator_readback_ref: Mapping[str, str], ruleset_readback_ref: Mapping[str, str],
    repository_identity: str, controller_app_id: int,
    controller_installation_id: int, controller_app_slug: str,
    admitted_at: str,
    initial_release_authority_ref: Mapping[str, str] | None = None,
) -> Path:
    """Validate stable authorities and seal create-once intent before mutation."""
    repository, root = repository.resolve(), evidence_root.resolve()
    policy, policy_digest, _, stable_regex = _policy(release_selection_policy_path)
    manifest, manifest_digest, state = validate_product_version_manifest(
        manifest_path=product_version_manifest_path,
        initial_release_authority=initial_release_authority_ref, evidence_root=root,
    )
    if state != "active":
        _fail("RELEASE_TAG.VERSION_TRAIN_INACTIVE", "product release train is not active")
    match = stable_regex.fullmatch(tag_name)
    if match is None:
        _fail("RELEASE_TAG.MALFORMED", "tag is not a strict stable version")
    version = ".".join(match.groups())
    if manifest["releaseTrain"]["targetVersion"] != version:
        _fail("RELEASE_TAG.VERSION_MISMATCH", "stable tag does not match active target")
    source = _source_identity(repository, source_git_sha)
    tag = {"tagKind": "stable", "tagName": tag_name, **source}
    reservation = _reservation(root, reservation_ref, tag=tag)
    authorities = _validate_stable_authorities(
        root=root, tag_name=tag_name, source=source, version=version,
        manifest_digest=manifest_digest, selected_rc_admission_ref=selected_rc_admission_ref,
        qualification_fact_ref=qualification_fact_ref,
        product_authority_fact_ref=product_authority_fact_ref,
        release_authority_fact_ref=release_authority_fact_ref,
    )
    controller = _text(policy["controller"]["identity"], "controller.identity")
    repository_identity = _repository(repository_identity, "repositoryIdentity")
    producer = _controller_producer(
        app_id=controller_app_id,
        installation_id=controller_installation_id,
        app_slug=controller_app_slug,
    )
    if producer["slug"] != controller:
        _fail("RELEASE_TAG.CONTROLLER_DENIED", "controller App slug drifted from policy")
    admitted = _time(admitted_at, "admittedAt")
    creator, creator_at = _creator_readback(
        root, creator_readback_ref, phase="pre_mutation",
        tag_name=tag_name, tag=None, producer=producer,
        repository=repository_identity,
    )
    ruleset, ruleset_at, _ = _ruleset_readback(
        root, ruleset_readback_ref, phase="pre_mutation",
        tag_name=tag_name, tag=None, producer=producer,
        repository=repository_identity,
    )
    if max(creator_at, ruleset_at) > admitted:
        _fail(
            "RELEASE_TAG.TIME_ORDER_INVALID",
            "hosted pre-readback occurred after intent admission",
        )
    for intent in _existing_facts(root / "release-tags" / "intents" / "stable", INTENT_SCHEMA):
        if intent.get("tagName") == tag_name:
            _fail("RELEASE_TAG.INTENT_REPLAY", "stable tag already has an admission intent")
        if intent.get("productVersion") == version:
            _fail("RELEASE_TAG.STABLE_ALREADY_EXISTS", "stable version already has an intent")
        if intent.get("candidateIdentity") == authorities["candidateIdentity"]:
            _fail("RELEASE_TAG.MULTIPLE_STABLES", "candidate already has a stable intent")
    body: dict[str, Any] = {
        "schema": INTENT_SCHEMA, "decision": "mutation_admitted",
        **tag, "productVersion": version, "reservation": reservation,
        **authorities, "productVersionManifestDigest": manifest_digest,
        "releaseSelectionPolicyDigest": policy_digest,
        "repository": repository_identity, "controllerProducer": producer,
        "preCreatorReadback": creator, "preRulesetReadback": ruleset,
        "admittedAt": _timestamp(admitted_at, "admittedAt"),
    }
    body["intentId"] = digest(body)
    return _write_once(_intent_path(root, "stable", tag_name), body)


def _final_readbacks(
    root: Path, *, intent: Mapping[str, Any], tag: Mapping[str, str],
    outcome: Mapping[str, Any], creator_ref: Mapping[str, str],
    ruleset_ref: Mapping[str, str], admitted_at: str,
) -> tuple[dict[str, str], dict[str, str]]:
    producer = intent.get("controllerProducer")
    repository = intent.get("repository")
    if not isinstance(producer, Mapping):
        _fail("RELEASE_TAG.INTENT_INVALID", "controller producer is missing")
    repository = _repository(repository, "intent.repository")
    pre_creator, pre_creator_at = _creator_readback(
        root, intent.get("preCreatorReadback"), phase="pre_mutation",
        tag_name=tag["tagName"], tag=None, producer=producer,
        repository=repository,
    )
    pre_ruleset, pre_ruleset_at, pre_ruleset_identity = _ruleset_readback(
        root, intent.get("preRulesetReadback"), phase="pre_mutation",
        tag_name=tag["tagName"], tag=None, producer=producer,
        repository=repository,
    )
    if pre_creator != intent.get("preCreatorReadback") or pre_ruleset != intent.get("preRulesetReadback"):
        _fail("RELEASE_TAG.INTENT_INVALID", "pre-mutation readback predecessor drifted")
    outcome_id = _digest(outcome.get("outcomeId"), "mutationOutcome.outcomeId")
    creator, creator_at = _creator_readback(
        root, creator_ref, phase="post_mutation", tag_name=tag["tagName"],
        tag=tag, producer=producer, repository=repository,
        outcome_id=outcome_id,
    )
    ruleset, ruleset_at, post_ruleset_identity = _ruleset_readback(
        root, ruleset_ref, phase="post_mutation", tag_name=tag["tagName"],
        tag=tag, producer=producer, repository=repository,
    )
    if pre_ruleset_identity != post_ruleset_identity:
        _fail(
            "RELEASE_TAG.READBACK_INVALID",
            "ruleset id or version drifted during mutation",
        )
    intent_at = _time(intent.get("admittedAt"), "intent.admittedAt")
    outcome_at = _time(outcome.get("recordedAt"), "mutationOutcome.recordedAt")
    final_at = _time(admitted_at, "admittedAt")
    if (
        max(pre_creator_at, pre_ruleset_at) > intent_at
        or not (intent_at <= outcome_at <= min(creator_at, ruleset_at))
        or max(creator_at, ruleset_at) > final_at
    ):
        _fail(
            "RELEASE_TAG.TIME_ORDER_INVALID",
            "intent, outcome, hosted readback, and final admission are out of order",
        )
    return creator, ruleset


def finalize_release_candidate_tag_admission(
    *, repository: Path, evidence_root: Path, tag_name: str,
    admission_intent_ref: Mapping[str, str], mutation_outcome_ref: Mapping[str, str],
    creator_readback_ref: Mapping[str, str], ruleset_readback_ref: Mapping[str, str],
    admitted_at: str, release_selection_policy_path: Path,
) -> Path:
    """Finalize immutable RC admission from actual Hosted tag readbacks."""
    repository, root = repository.resolve(), evidence_root.resolve()
    policy, _, _, _ = _policy(release_selection_policy_path)
    intent, intent_exact = _intent(
        root, admission_intent_ref, tag_kind="rc", tag_name=tag_name,
    )
    tag = inspect_tag(repository, tag_name)
    if (
        tag["peeledCommit"] != intent.get("peeledCommit")
        or tag["sourceTree"] != intent.get("sourceTree")
    ):
        _fail("RELEASE_TAG.MUTATION_MISMATCH", "hosted RC drifted from admission intent")
    _require_main_reachable(repository, tag["peeledCommit"] )
    outcome_fact, outcome = _created_outcome(
        root, intent, intent_exact, mutation_outcome_ref, tag=tag,
    )
    _text(policy["controller"]["identity"], "controller.identity")
    creator, ruleset = _final_readbacks(
        root, intent=intent, tag=tag, outcome=outcome_fact,
        creator_ref=creator_readback_ref, ruleset_ref=ruleset_readback_ref,
        admitted_at=admitted_at,
    )
    body = {
        "schema": RC_SCHEMA, "decision": "admitted", "tagKind": "rc",
        **tag, "productVersion": intent["productVersion"],
        "rcSequence": intent["rcSequence"], "selectionFact": intent["selectionFact"],
        "productVersionManifestDigest": intent["productVersionManifestDigest"],
        "releaseSelectionPolicyDigest": intent["releaseSelectionPolicyDigest"],
        "admissionIntent": intent_exact, "mutationOutcome": outcome,
        "creatorReadback": creator, "rulesetReadback": ruleset,
        "admittedAt": _timestamp(admitted_at, "admittedAt"),
    }
    body["admissionId"] = digest(body)
    return _write_once(root / "release-tags" / "rc" / tag_name / "admission.json", body)


def finalize_release_tag_admission(
    *, repository: Path, evidence_root: Path, tag_name: str,
    admission_intent_ref: Mapping[str, str], mutation_outcome_ref: Mapping[str, str],
    creator_readback_ref: Mapping[str, str], ruleset_readback_ref: Mapping[str, str],
    admitted_at: str, release_selection_policy_path: Path,
) -> Path:
    """Finalize immutable stable admission from actual Hosted tag readbacks."""
    repository, root = repository.resolve(), evidence_root.resolve()
    policy, _, _, _ = _policy(release_selection_policy_path)
    intent, intent_exact = _intent(
        root, admission_intent_ref, tag_kind="stable", tag_name=tag_name,
    )
    tag = inspect_tag(repository, tag_name)
    if (
        tag["peeledCommit"] != intent.get("peeledCommit")
        or tag["sourceTree"] != intent.get("sourceTree")
    ):
        _fail("RELEASE_TAG.MUTATION_MISMATCH", "hosted stable drifted from admission intent")
    _require_main_reachable(repository, tag["peeledCommit"] )
    outcome_fact, outcome = _created_outcome(
        root, intent, intent_exact, mutation_outcome_ref, tag=tag,
    )
    _text(policy["controller"]["identity"], "controller.identity")
    creator, ruleset = _final_readbacks(
        root, intent=intent, tag=tag, outcome=outcome_fact,
        creator_ref=creator_readback_ref, ruleset_ref=ruleset_readback_ref,
        admitted_at=admitted_at,
    )
    carried = {key: intent[key] for key in (
        "selectedRcAdmission", "selectedRcTagName", "selectedRcTagObjectOid",
        "qualificationFact", "qualificationId", "candidateMaterialManifest",
        "candidateMaterialId", "candidateIdentity", "artifactBuildNumber", "artifacts",
        "productAuthorityFact", "releaseAuthorityFact",
    )}
    body = {
        "schema": STABLE_SCHEMA, "decision": "admitted", "tagKind": "stable",
        **tag, "productVersion": intent["productVersion"], **carried,
        "productVersionManifestDigest": intent["productVersionManifestDigest"],
        "releaseSelectionPolicyDigest": intent["releaseSelectionPolicyDigest"],
        "admissionIntent": intent_exact, "mutationOutcome": outcome,
        "creatorReadback": creator, "rulesetReadback": ruleset,
        "admittedAt": _timestamp(admitted_at, "admittedAt"),
    }
    body["admissionId"] = digest(body)
    return _write_once(root / "release-tags" / "stable" / tag_name / "admission.json", body)


def assert_release_tag_intent_unused(
    *, evidence_root: Path, admission_intent_ref: Mapping[str, str],
    tag_kind: str, tag_name: str,
) -> None:
    """Reject replay before a controller performs any Git mutation."""
    root = evidence_root.resolve()
    intent, _ = _intent(root, admission_intent_ref, tag_kind=tag_kind, tag_name=tag_name)
    _assert_intent_unused(root, intent)
    for fact in _existing_facts(root / "release-tags", RC_SCHEMA if tag_kind == "rc" else STABLE_SCHEMA):
        if fact.get("tagName") == tag_name:
            _fail("RELEASE_TAG.INTENT_REPLAY", "tag already has an immutable admission")
