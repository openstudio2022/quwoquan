"""Strict append-only App launch, content, and release readiness facts.

The three facts are outputs, never caller-selected modes.  Every fact lives in
one fresh launch-attempt directory, binds exact predecessor bytes, and can only
advance ``LaunchReadyFact -> ContentReadyFact -> ReleaseReadyFact``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA = "quwoquan_ops.app_readiness_fact.v1"
LAUNCH = "LaunchReadyFact"
CONTENT = "ContentReadyFact"
RELEASE = "ReleaseReadyFact"
FACT_TYPES = (LAUNCH, CONTENT, RELEASE)
_FILENAMES = {
    LAUNCH: "launch-ready-fact.json",
    CONTENT: "content-ready-fact.json",
    RELEASE: "release-ready-fact.json",
}
_PREDECESSOR = {LAUNCH: None, CONTENT: LAUNCH, RELEASE: CONTENT}
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TREE_RE = re.compile(r"^(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_COMMON_FIELDS = frozenset(
    {"schema", "factType", "factDigest", "attemptId", "nonPromotable", "predecessor", "evidence"}
)
_FIELDS = {
    LAUNCH: _COMMON_FIELDS
    | {
        "sourceGitSha", "sourceTreeDigest", "artifactDigest", "runtimeConfigPackageDigest",
        "runtimeConfigTrustEnvelopeDigest", "effectiveLaunchManifestDigest", "platform", "deviceId",
        "consumerLeaseId", "transport", "launchAttempt", "launchReport", "installedConfigReadback",
    },
    CONTENT: _COMMON_FIELDS | {"journeys"},
    RELEASE: _COMMON_FIELDS | {"releaseCandidate", "qualification"},
}
_LAUNCH_ATTEMPT_FIELDS = frozenset({"ref", "digest", "attemptId", "status"})
_LAUNCH_REPORT_FIELDS = frozenset({"ref", "digest"})
_EXACT_REF_FIELDS = frozenset({"ref", "digest"})
_TRANSPORT_FIELDS = frozenset(
    {"required", "reverseExpectedPorts", "reverseActualPorts", "reverseReceiptDigest"}
)
_INSTALLED_CONFIG_FIELDS = frozenset(
    {"configurationState", "runtimeConfigPackageDigest", "runtimeConfigTrustEnvelopeDigest", "effectiveLaunchManifestDigest", "startupTerminalEvidenceRef", "startupTerminalEvidenceDigest"}
)
_JOURNEY_FIELDS = frozenset({"journeyId", "ref", "digest", "status", "producer", "layer"})
_REQUIRED_JOURNEYS = frozenset(
    {
        "login_otp", "anonymous_isolation", "feed_loaded", "content_image_decode",
        "author_avatar_decode", "video_terminal", "detail_terminal", "persona_isolation",
        "release_isolation", "cache_isolation", "grant_isolation",
    }
)
_RELEASE_CANDIDATE_FIELDS = frozenset(
    {"ref", "digest", "releaseCompositionId", "artifactDigest", "status", "sourceGitSha", "sourceTreeDigest"}
)
_QUALIFICATION_KEYS = frozenset(
    {"eaf", "androidPhysical", "iosPhysical", "provider", "migration", "rollback", "performance", "reliability", "cleanup"}
)


class AppReadinessFactError(ValueError):
    """Typed fail-closed readiness error."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def _block(code: str, detail: str) -> None:
    raise AppReadinessFactError(code, detail)


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AppReadinessFactError("APP.READINESS.invalid", "fact is not canonical JSON") from exc


def exact_byte_digest(value: bytes | Path) -> str:
    raw = value if isinstance(value, bytes) else Path(value).read_bytes()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _fact_digest(payload: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "factDigest"}
    return "sha256:" + hashlib.sha256(_canonical_json(unsigned)).hexdigest()


def _require_digest(value: object, *, field: str) -> str:
    text = str(value or "")
    if _DIGEST_RE.fullmatch(text) is None:
        _block("APP.READINESS.invalid", f"{field} must be sha256:<64 lowercase hex>")
    return text


def _require_id(value: object, *, field: str) -> str:
    text = str(value or "")
    if _ID_RE.fullmatch(text) is None:
        _block("APP.READINESS.invalid", f"{field} is not a canonical identity")
    return text


def _require_attempt_dir(attempt_dir: Path, *, create: bool) -> Path:
    raw = Path(attempt_dir).expanduser()
    if not raw.is_absolute():
        _block("APP.READINESS.path_blocked", "attempt directory must be absolute")
    absolute = Path(os.path.abspath(raw))
    if create:
        if absolute.exists() or absolute.is_symlink():
            _block("APP.READINESS.stale_attempt", "attempt directory must be fresh")
        parent = absolute.parent
        if parent.is_symlink() or not parent.is_dir() or parent.resolve() != parent:
            _block("APP.READINESS.path_blocked", "attempt parent must be a real directory")
        absolute.mkdir(mode=0o700)
    try:
        metadata = absolute.lstat()
    except OSError as exc:
        raise AppReadinessFactError("APP.READINESS.path_blocked", "attempt directory is unavailable") from exc
    if absolute.is_symlink() or absolute.resolve() != absolute or not stat.S_ISDIR(metadata.st_mode):
        _block("APP.READINESS.path_blocked", "attempt directory must be real and non-symlink")
    return absolute


def _secure_read_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        _block("APP.READINESS.path_blocked", f"evidence is missing or linked: {path}")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        _block("APP.READINESS.path_blocked", "platform lacks O_NOFOLLOW")
    descriptor = os.open(path, os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0))
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            _block("APP.READINESS.path_blocked", "evidence must be a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            _block("APP.READINESS.path_blocked", "evidence changed while read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _contained_ref(attempt_dir: Path, value: object, *, field: str) -> tuple[str, Path]:
    text = str(value or "")
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = attempt_dir / path
    path = Path(os.path.abspath(path))
    try:
        relative = path.relative_to(attempt_dir)
    except ValueError as exc:
        raise AppReadinessFactError("APP.READINESS.path_blocked", f"{field} escapes attempt directory") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        _block("APP.READINESS.path_blocked", f"{field} is invalid")
    return relative.as_posix(), path


def _verify_exact_ref(attempt_dir: Path, value: object, *, field: str) -> tuple[dict[str, str], bytes]:
    if not isinstance(value, Mapping) or set(value) != _EXACT_REF_FIELDS:
        _block("APP.READINESS.invalid", f"{field} fields are invalid")
    ref, path = _contained_ref(attempt_dir, value.get("ref"), field=f"{field}.ref")
    digest = _require_digest(value.get("digest"), field=f"{field}.digest")
    raw = _secure_read_file(path)
    if exact_byte_digest(raw) != digest:
        _block("APP.READINESS.evidence_blocked", f"{field} exact-byte digest drifted")
    return {"ref": ref, "digest": digest}, raw


def _decode_json(raw: bytes, *, field: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppReadinessFactError("APP.READINESS.evidence_blocked", f"{field} is not JSON") from exc
    if not isinstance(value, dict):
        _block("APP.READINESS.evidence_blocked", f"{field} must be an object")
    return value


def validate_app_readiness_fact(payload: Mapping[str, Any], *, attempt_dir: Path) -> dict[str, Any]:
    root = _require_attempt_dir(attempt_dir, create=False)
    if not isinstance(payload, Mapping):
        _block("APP.READINESS.invalid", "fact must be an object")
    fact = dict(payload)
    fact_type = str(fact.get("factType") or "")
    if fact.get("schema") != SCHEMA or fact_type not in FACT_TYPES:
        _block("APP.READINESS.invalid", "fact schema/type is invalid")
    if set(fact) != _FIELDS[fact_type]:
        _block("APP.READINESS.invalid", f"{fact_type} fields are not closed")
    attempt_id = _require_id(fact.get("attemptId"), field="attemptId")
    if not isinstance(fact.get("nonPromotable"), bool):
        _block("APP.READINESS.invalid", "nonPromotable must be boolean")
    if not isinstance(fact.get("evidence"), list):
        _block("APP.READINESS.invalid", "evidence must be an array")
    _require_digest(fact.get("factDigest"), field="factDigest")
    if fact["factDigest"] != _fact_digest(fact):
        _block("APP.READINESS.digest_drift", "factDigest drifted")

    expected_predecessor = _PREDECESSOR[fact_type]
    predecessor = fact.get("predecessor")
    if expected_predecessor is None:
        if predecessor is not None:
            _block("APP.READINESS.predecessor_blocked", "LaunchReadyFact cannot have a predecessor")
    else:
        exact, raw = _verify_exact_ref(root, predecessor, field="predecessor")
        expected_name = _FILENAMES[expected_predecessor]
        if exact["ref"] != expected_name:
            _block("APP.READINESS.predecessor_blocked", f"{fact_type} requires {expected_predecessor}")
        previous = validate_app_readiness_fact(_decode_json(raw, field="predecessor"), attempt_dir=root)
        if previous["factType"] != expected_predecessor or previous["attemptId"] != attempt_id:
            _block("APP.READINESS.predecessor_blocked", "predecessor identity drifted")
        if fact_type == CONTENT and fact["nonPromotable"] != previous["nonPromotable"]:
            _block("APP.READINESS.predecessor_blocked", "ContentReadyFact cannot change promotability")
        if fact_type == RELEASE and (previous["nonPromotable"] or fact["nonPromotable"]):
            _block("APP.READINESS.non_promotable", "ReleaseReadyFact rejects non-promotable predecessors")

    if fact_type == LAUNCH:
        _validate_launch(fact, root)
    elif fact_type == CONTENT:
        _validate_content(fact, root)
    else:
        _validate_release(fact, root)
    return fact


def _validate_launch(fact: dict[str, Any], root: Path) -> None:
    if _GIT_SHA_RE.fullmatch(str(fact.get("sourceGitSha") or "")) is None:
        _block("APP.READINESS.invalid", "sourceGitSha must be exact")
    for field in (
        "artifactDigest", "runtimeConfigPackageDigest",
        "runtimeConfigTrustEnvelopeDigest", "effectiveLaunchManifestDigest", "consumerLeaseId",
    ):
        _require_digest(fact.get(field), field=field)
    if _TREE_RE.fullmatch(str(fact.get("sourceTreeDigest") or "")) is None:
        _block("APP.READINESS.invalid", "sourceTreeDigest must be an exact Git tree identity")
    if fact.get("platform") not in {"android", "ios"}:
        _block("APP.READINESS.invalid", "platform is unknown")
    _require_id(fact.get("deviceId"), field="deviceId")
    transport = fact.get("transport")
    if not isinstance(transport, Mapping) or set(transport) != _TRANSPORT_FIELDS or not isinstance(transport.get("required"), bool):
        _block("APP.READINESS.invalid", "transport fields are invalid")
    transport_values = [str(transport.get(field) or "") for field in _TRANSPORT_FIELDS if field != "required"]
    if transport["required"]:
        if fact["platform"] != "android" or not all(transport_values):
            _block("APP.READINESS.evidence_blocked", "required Android reverse transport is incomplete")
        _require_digest(transport.get("reverseReceiptDigest"), field="transport.reverseReceiptDigest")
        if transport["reverseExpectedPorts"] != transport["reverseActualPorts"]:
            _block("APP.READINESS.evidence_blocked", "Android reverse readback drifted")
    elif any(transport_values):
        _block("APP.READINESS.invalid", "non-required transport must be empty")
    attempt = fact.get("launchAttempt")
    if not isinstance(attempt, Mapping) or set(attempt) != _LAUNCH_ATTEMPT_FIELDS:
        _block("APP.READINESS.invalid", "launchAttempt fields are invalid")
    exact, raw = _verify_exact_ref(root, {"ref": attempt.get("ref"), "digest": attempt.get("digest")}, field="launchAttempt")
    launch = _decode_json(raw, field="launchAttempt")
    if attempt.get("status") != "launched" or launch.get("status") != "launched":
        _block("APP.READINESS.evidence_blocked", "launch attempt did not reach launched")
    if launch.get("attemptId") != attempt.get("attemptId") or launch.get("attemptId") != fact["attemptId"]:
        _block("APP.READINESS.evidence_blocked", "launch attempt identity drifted")
    expected = {
        "artifactDigest": fact["artifactDigest"], "runtimeConfigPackageDigest": fact["runtimeConfigPackageDigest"],
        "runtimeConfigTrustEnvelopeDigest": fact["runtimeConfigTrustEnvelopeDigest"], "launchDigest": fact["effectiveLaunchManifestDigest"],
        "platform": fact["platform"], "deviceId": fact["deviceId"], "nonPromotable": fact["nonPromotable"],
    }
    if any(launch.get(field) != value for field, value in expected.items()):
        _block("APP.READINESS.evidence_blocked", "launch attempt exact identity drifted")
    installed = fact.get("installedConfigReadback")
    if not isinstance(installed, Mapping) or set(installed) != _INSTALLED_CONFIG_FIELDS:
        _block("APP.READINESS.invalid", "installedConfigReadback fields are invalid")
    installed_expected = {
        "configurationState": "complete", "runtimeConfigPackageDigest": fact["runtimeConfigPackageDigest"],
        "runtimeConfigTrustEnvelopeDigest": fact["runtimeConfigTrustEnvelopeDigest"],
        "effectiveLaunchManifestDigest": fact["effectiveLaunchManifestDigest"],
    }
    if any(installed.get(field) != value for field, value in installed_expected.items()):
        _block("APP.READINESS.evidence_blocked", "installed config readback drifted")
    terminal_exact, terminal_raw = _verify_exact_ref(
        root,
        {"ref": installed.get("startupTerminalEvidenceRef"), "digest": installed.get("startupTerminalEvidenceDigest")},
        field="installedConfigReadback.startupTerminal",
    )
    terminal = _decode_json(terminal_raw, field="installedConfigReadback.startupTerminal")
    terminal_expected = {
        "launchAttemptId": fact["attemptId"], "platform": fact["platform"], "deviceId": fact["deviceId"],
        "artifactDigest": fact["artifactDigest"], "configurationState": "complete",
        "effectiveLaunchManifestDigest": fact["effectiveLaunchManifestDigest"], "canonicalTerminal": "routerShell",
    }
    if any(terminal.get(field) != value for field, value in terminal_expected.items()):
        _block("APP.READINESS.evidence_blocked", "startup terminal config readback drifted")
    if exact["ref"] == terminal_exact["ref"]:
        _block("APP.READINESS.invalid", "launch and terminal evidence must be distinct")
    report_value = fact.get("launchReport")
    if not isinstance(report_value, Mapping) or set(report_value) != _LAUNCH_REPORT_FIELDS:
        _block("APP.READINESS.invalid", "launchReport fields are invalid")
    report_exact, report_raw = _verify_exact_ref(root, report_value, field="launchReport")
    report = _decode_json(report_raw, field="launchReport")
    report_expected = {
        "schema": "quwoquan_app.test_live_launch", "launchAttemptId": fact["attemptId"],
        "artifactDigest": fact["artifactDigest"],
        "sourceGitSha": fact["sourceGitSha"], "sourceTreeDigest": fact["sourceTreeDigest"],
        "runtimeConfigPackageDigest": fact["runtimeConfigPackageDigest"],
        "runtimeConfigTrustEnvelopeDigest": fact["runtimeConfigTrustEnvelopeDigest"],
        "effectiveLaunchManifestDigest": fact["effectiveLaunchManifestDigest"],
        "deviceId": fact["deviceId"], "platform": fact["platform"], "nonPromotable": fact["nonPromotable"],
        "compileStatus": "compiled", "installStatus": "installed", "launchStatus": "launched",
        "runtimeStatus": "healthy",
    }
    if any(report.get(field) != value for field, value in report_expected.items()):
        _block("APP.READINESS.evidence_blocked", "canonical launch report identity/readiness drifted")
    canonical_launch_digest = "sha256:" + hashlib.sha256(_canonical_json(launch)).hexdigest()
    if report.get("launchAttemptDigest") != canonical_launch_digest:
        _block("APP.READINESS.evidence_blocked", "canonical launch report attempt digest drifted")
    if len({exact["ref"], terminal_exact["ref"], report_exact["ref"]}) != 3:
        _block("APP.READINESS.invalid", "launch evidence references must be distinct")


def _validate_content(fact: dict[str, Any], root: Path) -> None:
    journeys = fact.get("journeys")
    if not isinstance(journeys, list) or not journeys:
        _block("APP.READINESS.content_blocked", "raw UAT journeys are required")
    observed: set[str] = set()
    for index, item in enumerate(journeys):
        label = f"journeys[{index}]"
        if not isinstance(item, Mapping) or set(item) != _JOURNEY_FIELDS:
            _block("APP.READINESS.invalid", f"{label} fields are invalid")
        journey_id = str(item.get("journeyId") or "")
        if journey_id not in _REQUIRED_JOURNEYS or journey_id in observed:
            _block("APP.READINESS.content_blocked", f"{label}.journeyId is unknown or duplicated")
        observed.add(journey_id)
        if item.get("status") != "passed" or item.get("producer") != "app" or item.get("layer") != "user_acceptance":
            _block("APP.READINESS.content_blocked", f"{label} is not passed raw App UAT")
        _exact, raw = _verify_exact_ref(root, {"ref": item.get("ref"), "digest": item.get("digest")}, field=label)
        evidence = _decode_json(raw, field=label)
        if (
            evidence.get("status") != "passed" or evidence.get("producer") != "app"
            or evidence.get("layer") != "user_acceptance" or evidence.get("journeyId") != journey_id
            or evidence.get("attemptId") != fact["attemptId"]
        ):
            _block("APP.READINESS.content_blocked", f"{label} exact raw authority drifted")
    if observed != _REQUIRED_JOURNEYS:
        _block("APP.READINESS.content_blocked", f"required journeys missing: {sorted(_REQUIRED_JOURNEYS - observed)}")


def _validate_release(fact: dict[str, Any], root: Path) -> None:
    candidate = fact.get("releaseCandidate")
    if not isinstance(candidate, Mapping) or set(candidate) != _RELEASE_CANDIDATE_FIELDS:
        _block("APP.READINESS.invalid", "releaseCandidate fields are invalid")
    for field in ("digest", "releaseCompositionId", "artifactDigest"):
        _require_digest(candidate.get(field), field=f"releaseCandidate.{field}")
    if _TREE_RE.fullmatch(str(candidate.get("sourceTreeDigest") or "")) is None:
        _block("APP.READINESS.invalid", "releaseCandidate.sourceTreeDigest must be exact")
    if _GIT_SHA_RE.fullmatch(str(candidate.get("sourceGitSha") or "")) is None:
        _block("APP.READINESS.invalid", "releaseCandidate.sourceGitSha must be exact")
    if candidate.get("status") not in {"artifact-complete", "qualified", "main-admitted"}:
        _block("APP.READINESS.release_blocked", "candidate is not immutable and qualification-eligible")
    exact, raw = _verify_exact_ref(root, {"ref": candidate.get("ref"), "digest": candidate.get("digest")}, field="releaseCandidate")
    manifest = _decode_json(raw, field="releaseCandidate")
    expected = {
        "releaseCompositionId": candidate["releaseCompositionId"], "artifactDigest": candidate["artifactDigest"],
        "sourceGitSha": candidate["sourceGitSha"], "sourceTreeDigest": candidate["sourceTreeDigest"], "status": candidate["status"],
    }
    if any(manifest.get(field) != value for field, value in expected.items()):
        _block("APP.READINESS.release_blocked", "candidate manifest identity drifted")
    qualification = fact.get("qualification")
    if not isinstance(qualification, Mapping) or set(qualification) != _QUALIFICATION_KEYS:
        _block("APP.READINESS.invalid", "qualification closure is invalid")
    for name, value in qualification.items():
        _exact, raw = _verify_exact_ref(root, value, field=f"qualification.{name}")
        evidence = _decode_json(raw, field=f"qualification.{name}")
        if evidence.get("status") not in {"passed", "ready"}:
            _block("APP.READINESS.release_blocked", f"qualification.{name} is not passed")
        if evidence.get("releaseCompositionId") != candidate["releaseCompositionId"]:
            _block("APP.READINESS.release_blocked", f"qualification.{name} candidate drifted")
        if name in {"androidPhysical", "iosPhysical"}:
            if evidence.get("platform") != name.removesuffix("Physical").lower() or evidence.get("deviceClass") != "physical" or evidence.get("registered") is not True:
                _block("APP.READINESS.release_blocked", f"qualification.{name} is not a registered physical device")
        if name == "provider" and evidence.get("providerClass") != "real":
            _block("APP.READINESS.release_blocked", "qualification.provider is not real Provider evidence")
    if exact["ref"] in {str(value.get("ref")) for value in qualification.values() if isinstance(value, Mapping)}:
        _block("APP.READINESS.invalid", "candidate and qualification evidence must be distinct")


def _write_create_once(path: Path, payload: Mapping[str, Any]) -> Path:
    encoded = _canonical_json(payload)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("readiness fact write made no progress")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.link(temporary, path, follow_symlinks=False)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except FileExistsError as exc:
        raise AppReadinessFactError("APP.READINESS.create_once_conflict", f"fact path already exists: {path.name}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
    return path


def write_app_readiness_fact(payload: Mapping[str, Any], *, attempt_dir: Path, create_attempt: bool = False) -> Path:
    root = _require_attempt_dir(attempt_dir, create=create_attempt)
    fact = dict(payload)
    fact["factDigest"] = _fact_digest(fact)
    validated = validate_app_readiness_fact(fact, attempt_dir=root)
    return _write_create_once(root / _FILENAMES[validated["factType"]], validated)


def load_app_readiness_fact(path: Path, *, attempt_dir: Path | None = None) -> dict[str, Any]:
    raw_path = Path(path).expanduser()
    root = _require_attempt_dir(attempt_dir or raw_path.parent, create=False)
    try:
        raw_path = root / raw_path.resolve().relative_to(root)
    except (OSError, ValueError) as exc:
        raise AppReadinessFactError("APP.READINESS.path_blocked", "fact path escapes attempt directory") from exc
    return validate_app_readiness_fact(_decode_json(_secure_read_file(raw_path), field="fact"), attempt_dir=root)


def exact_ref(path: Path, *, attempt_dir: Path) -> dict[str, str]:
    root = _require_attempt_dir(attempt_dir, create=False)
    ref, contained = _contained_ref(root, path, field="ref")
    return {"ref": ref, "digest": exact_byte_digest(_secure_read_file(contained))}


def launch_ready_report_fields(*, handoff: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Project the canonical report fields consumed by ``LaunchReadyFact``."""

    transport = handoff.get("transport") or {}
    return {
        "launchAttemptDigest": exact_byte_digest(_canonical_json(receipt)),
        "consumerLeaseId": str(transport.get("consumerLeaseId") or ""),
        "transport": {
            "required": bool(transport.get("required")),
            "reverseExpectedPorts": str(transport.get("reverseExpectedPorts") or ""),
            "reverseActualPorts": str(transport.get("reverseActualPorts") or ""),
            "reverseReceiptDigest": str(transport.get("reverseReceiptDigest") or ""),
        },
        "installedConfigReadback": {
            "configurationState": str(receipt.get("configurationState") or ""),
            "runtimeConfigPackageDigest": str(receipt.get("runtimeConfigPackageDigest") or ""),
            "runtimeConfigTrustEnvelopeDigest": str(receipt.get("runtimeConfigTrustEnvelopeDigest") or ""),
            "effectiveLaunchManifestDigest": str(receipt.get("launchDigest") or ""),
        },
    }


def build_launch_ready_fact(*, attempt_id: str, source_git_sha: str, source_tree_digest: str, artifact_digest: str,
                            runtime_config_package_digest: str, runtime_config_trust_envelope_digest: str,
                            effective_launch_manifest_digest: str, platform: str, device_id: str,
                            consumer_lease_id: str, transport: Mapping[str, Any], launch_attempt: Mapping[str, Any],
                            launch_report: Mapping[str, str], installed_config_readback: Mapping[str, Any],
                            evidence: Sequence[Mapping[str, str]] = (),
                            non_promotable: bool = True) -> dict[str, Any]:
    return {"schema": SCHEMA, "factType": LAUNCH, "factDigest": "", "attemptId": attempt_id,
            "nonPromotable": non_promotable, "predecessor": None, "evidence": [dict(item) for item in evidence],
            "sourceGitSha": source_git_sha, "sourceTreeDigest": source_tree_digest, "artifactDigest": artifact_digest,
            "runtimeConfigPackageDigest": runtime_config_package_digest,
            "runtimeConfigTrustEnvelopeDigest": runtime_config_trust_envelope_digest,
            "effectiveLaunchManifestDigest": effective_launch_manifest_digest, "platform": platform, "deviceId": device_id,
            "consumerLeaseId": consumer_lease_id, "transport": dict(transport), "launchAttempt": dict(launch_attempt),
            "launchReport": dict(launch_report), "installedConfigReadback": dict(installed_config_readback)}


def build_content_ready_fact(*, attempt_id: str, predecessor: Mapping[str, str], journeys: Sequence[Mapping[str, Any]],
                             evidence: Sequence[Mapping[str, str]] = (), non_promotable: bool) -> dict[str, Any]:
    return {"schema": SCHEMA, "factType": CONTENT, "factDigest": "", "attemptId": attempt_id,
            "nonPromotable": non_promotable, "predecessor": dict(predecessor),
            "evidence": [dict(item) for item in evidence], "journeys": [dict(item) for item in journeys]}


def build_release_ready_fact(*, attempt_id: str, predecessor: Mapping[str, str], release_candidate: Mapping[str, Any],
                             qualification: Mapping[str, Mapping[str, str]], evidence: Sequence[Mapping[str, str]] = ()) -> dict[str, Any]:
    return {"schema": SCHEMA, "factType": RELEASE, "factDigest": "", "attemptId": attempt_id,
            "nonPromotable": False, "predecessor": dict(predecessor), "evidence": [dict(item) for item in evidence],
            "releaseCandidate": dict(release_candidate),
            "qualification": {key: dict(value) for key, value in qualification.items()}}


def create_launch_ready_fact_from_report(*, report_path: Path) -> Path:
    """Derive one LaunchReadyFact from the completed canonical report bytes."""

    report_file = Path(report_path).expanduser()
    attempt_dir = _require_attempt_dir(report_file.parent, create=False)
    report_ref, report_file = _contained_ref(attempt_dir, report_file, field="launchReport.ref")
    report_raw = _secure_read_file(report_file)
    report = _decode_json(report_raw, field="launchReport")
    if report.get("schema") != "quwoquan_app.test_live_launch":
        _block("APP.READINESS.evidence_blocked", "canonical launch report schema drifted")
    attempt_ref, attempt_path = _contained_ref(
        attempt_dir, report.get("launchAttemptRef"), field="launchAttempt.ref"
    )
    attempt_raw = _secure_read_file(attempt_path)
    attempt = _decode_json(attempt_raw, field="launchAttempt")
    terminal_ref, terminal_path = _contained_ref(
        attempt_dir, report.get("startupTerminalEvidenceRef"), field="startupTerminal.ref"
    )
    terminal_raw = _secure_read_file(terminal_path)
    transport = report.get("transport")
    if not isinstance(transport, Mapping):
        _block("APP.READINESS.evidence_blocked", "canonical launch report lacks transport readback")
    installed = report.get("installedConfigReadback")
    if not isinstance(installed, Mapping):
        _block("APP.READINESS.evidence_blocked", "canonical launch report lacks installed config readback")
    payload = build_launch_ready_fact(
        attempt_id=str(report.get("launchAttemptId") or ""),
        source_git_sha=str(report.get("sourceGitSha") or ""),
        source_tree_digest=str(report.get("sourceTreeDigest") or ""),
        artifact_digest=str(report.get("artifactDigest") or ""),
        runtime_config_package_digest=str(report.get("runtimeConfigPackageDigest") or ""),
        runtime_config_trust_envelope_digest=str(report.get("runtimeConfigTrustEnvelopeDigest") or ""),
        effective_launch_manifest_digest=str(report.get("effectiveLaunchManifestDigest") or ""),
        platform=str(report.get("platform") or ""),
        device_id=str(report.get("deviceId") or ""),
        consumer_lease_id=str(report.get("consumerLeaseId") or ""),
        transport=dict(transport),
        launch_attempt={
            "ref": attempt_ref, "digest": exact_byte_digest(attempt_raw),
            "attemptId": str(attempt.get("attemptId") or ""), "status": str(attempt.get("status") or ""),
        },
        launch_report={"ref": report_ref, "digest": exact_byte_digest(report_raw)},
        installed_config_readback={
            **dict(installed),
            "startupTerminalEvidenceRef": terminal_ref,
            "startupTerminalEvidenceDigest": exact_byte_digest(terminal_raw),
        },
        non_promotable=bool(report.get("nonPromotable")),
    )
    return write_app_readiness_fact(payload, attempt_dir=attempt_dir)


__all__ = [
    "AppReadinessFactError", "CONTENT", "FACT_TYPES", "LAUNCH", "RELEASE", "SCHEMA",
    "build_content_ready_fact", "build_launch_ready_fact", "build_release_ready_fact",
    "create_launch_ready_fact_from_report", "exact_byte_digest", "launch_ready_report_fields",
    "exact_ref", "load_app_readiness_fact", "validate_app_readiness_fact", "write_app_readiness_fact",
]
