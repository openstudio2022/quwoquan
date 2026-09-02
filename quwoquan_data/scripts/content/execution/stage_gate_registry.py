"""Stage registry：由 authority gate 调用的 canonical argv 单点。"""
from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core import paths

def _cli(*parts: str) -> tuple[str, ...]:
    return (sys.executable, "-B", str(paths.REPO_ROOT / "quwoquan_data/scripts/cli.py"), *parts)



def _semantic_result_bindings(
    execution_id: str, stage: str, context: Mapping[str, Any]
) -> list[dict[str, str]]:
    result_ref = str(context.get("semanticResultRef") or "")
    result_path = paths.DATA_EXECUTIONS_ROOT / execution_id / result_ref
    try:
        wrapper = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{stage} semantic result wrapper is unreadable") from exc
    if (
        not isinstance(wrapper, dict)
        or wrapper.get("executionId") != execution_id
        or wrapper.get("stage") != stage
        or not isinstance(wrapper.get("resultBindings"), list)
    ):
        raise ValueError(f"{stage} semantic result wrapper identity/bindings are invalid")
    bindings = wrapper["resultBindings"]
    if not all(isinstance(item, Mapping) for item in bindings):
        raise ValueError(f"{stage} semantic resultBindings are invalid")
    return [dict(item) for item in bindings]


def _review_rubric_commands(
    execution_id: str, context: Mapping[str, Any]
) -> list[tuple[str, tuple[str, ...]]]:
    bindings = _semantic_result_bindings(execution_id, "5.review", context)
    rubric_refs = [str(item.get("ref") or "") for item in bindings if Path(str(item.get("ref") or "")).name == "rubric_review.json"]
    if not rubric_refs:
        raise ValueError("5.review semantic result requires rubric_review.json")
    draft_receipts = sorted(
        (paths.DATA_EXECUTIONS_ROOT / execution_id / "_shared/receipts").glob("*-4.draft.json")
    )
    if len(draft_receipts) != 1:
        raise ValueError("5.review requires exactly one canonical 4.draft receipt")
    try:
        draft_receipt = json.loads(draft_receipts[0].read_text(encoding="utf-8"))
        semantic = (draft_receipt.get("authority") or {}).get("semanticResult")
        draft_wrapper = json.loads(
            (paths.DATA_EXECUTIONS_ROOT / execution_id / str(semantic["ref"])).read_text(encoding="utf-8")
        )
        generation_family = str((draft_wrapper.get("actor") or {})["modelFamily"])
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("5.review cannot derive generation family from 4.draft authority") from exc
    return [
        (
            f"rubric-independence-{index}",
            _cli("verify", "rubric", "--file", str(paths.DATA_EXECUTIONS_ROOT / execution_id / ref), "--generation-family", generation_family),
        )
        for index, ref in enumerate(sorted(rubric_refs))
    ]


def _homepage_entities(execution_id: str) -> list[str]:
    target_set = paths.DATA_EXECUTIONS_ROOT / execution_id / "0.plan/target_set.json"
    try:
        value = json.loads(target_set.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("homepage registry cannot read frozen target_set.json") from exc
    targets = value.get("targets") if isinstance(value, dict) else None
    names = sorted({str(item.get("name") or "").strip() for item in targets if isinstance(item, Mapping)}) if isinstance(targets, list) else []
    if not names or any(not name for name in names):
        raise ValueError("homepage registry requires non-empty frozen target names")
    return names


def registry_argv(execution_id: str, stage: str, context: Mapping[str, Any]) -> list[tuple[str, tuple[str, ...]]]:
    common: dict[str, list[tuple[str, tuple[str, ...]]]] = {
        "0.plan": [
            ("runtime-input-ownership", _cli("verify", "runtime-input-ownership")),
            ("task-init-contract", _cli("verify", "task-init-contract", "--execution-id", execution_id)),
        ],
        "sources": [("source-digest", _cli("verify", "source-digest", "--execution-id", execution_id))],
        "1.download": [("stage-artifacts", _cli("verify", "stage-artifacts", "--execution-id", execution_id, "--through", "1.download"))],
        "2.quality": [("stage-artifacts", _cli("verify", "stage-artifacts", "--execution-id", execution_id, "--through", "2.quality"))],
        "3.compose": [("stage-artifacts", _cli("verify", "stage-artifacts", "--execution-id", execution_id, "--through", "3.compose"))],
        "4.draft": [("stage-artifacts", _cli("verify", "stage-artifacts", "--execution-id", execution_id, "--through", "4.draft"))],
        "5.review": [("stage-artifacts", _cli("verify", "stage-artifacts", "--execution-id", execution_id, "--through", "5.review"))],
        "publish": [
            ("publish-execution", _cli("release", "publish-execution", "--execution-id", execution_id, "--apply")),
            ("publish-purity", _cli("verify", "publish-purity")),
            ("publish-closure", _cli("verify", "publish-closure")),
        ],
    }
    if stage in common:
        commands = list(common[stage])
        if stage == "1.download":
            request = json.loads((paths.DATA_EXECUTIONS_ROOT / execution_id / "0.plan/request.json").read_text(encoding="utf-8"))
            carrier = str(request.get("carrier") or "")
            if carrier in {"homepage", "image"}:
                commands.append(("homepage-media-decision", _cli("verify", "homepage-media-decision", "--execution", execution_id)))
        if stage == "4.draft":
            request = json.loads((paths.DATA_EXECUTIONS_ROOT / execution_id / "0.plan/request.json").read_text(encoding="utf-8"))
            if request.get("carrier") == "homepage":
                commands.extend((f"homepage-draft-{index}", _cli("verify", "homepage-draft", "--execution", execution_id, "--entity", entity)) for index, entity in enumerate(_homepage_entities(execution_id)))
        if stage == "5.review":
            commands.extend(_review_rubric_commands(execution_id, context))
        return commands
    release_id = str(context["releaseId"])
    if stage == "release":
        return [
            ("pool-build", _cli("release", "pool-build", "--release-id", release_id, "--release-class", str(context["releaseClass"]), "--all-publishable")),
            ("release-integrity", _cli("verify", "release-integrity", "--release", release_id)),
            ("media-release-contract", _cli("verify", "media-release-contract")),
        ]
    if stage == "ship":
        environment = str(context["environment"])
        import_run = str(context["importRunId"])
        verify_run = str(context["verifyRunId"])
        stackctl = (sys.executable, "-B", str(paths.REPO_ROOT / "quwoquan_ops/cli/stackctl.py"))
        commands = [
            ("ship-apply", _cli("ship", "apply", "--release-id", release_id, "--env", environment, "--run-id", import_run, "--import", "--full-sync")),
            ("ship-verify", _cli("ship", "verify", "--release-id", release_id, "--env", environment, "--import-run-id", import_run, "--run-id", verify_run, "--readiness-phase", str(context["readinessPhase"]))),
            ("release-lifecycle", _cli("verify", "release-lifecycle", "--release", release_id, "--environment", environment, "--import-run", import_run, "--verify-run", verify_run, "--prod-mode", "activated")),
        ]
        if context["acceptanceProfile"] == "environment_promotion":
            commands.append(("stackctl-verify", (*stackctl, "verify", "--env", environment, "--kind", "all", "--profile", "release", "--data-release-id", release_id, "--data-import-run-id", import_run, "--data-verify-run-id", verify_run)))
        else:
            commands.append(("stackctl-health-content-consumer", (*stackctl, "health", "--target", str(context["target"]), "--scope", "content-consumer")))
        return commands
    raise ValueError(f"stage registry lacks canonical argv: {stage}")



def normalize_context(stage: str, raw: Mapping[str, Any] | None) -> dict[str, Any]:
    context = dict(raw or {})
    allowed = {"artifactRefs"}
    if stage in {"sources", "2.quality", "3.compose", "4.draft", "5.review"}:
        allowed |= {"semanticResultRef", "semanticResultDigest"}
    if stage == "release":
        allowed |= {"releaseId", "releaseDigest", "releaseClass"}
    if stage == "ship":
        allowed |= {
            "releaseId", "releaseDigest", "environment", "importRunId", "verifyRunId",
            "readinessPhase", "target", "acceptanceProfile", "requiredTargetProfiles",
            "environmentAcceptanceFactRef", "environmentAcceptanceFactDigest",
        }
    unknown = sorted(set(context) - allowed)
    if unknown:
        raise ValueError(f"stage gate context has unknown fields: {unknown}")
    refs = context.get("artifactRefs", [])
    if isinstance(refs, (str, bytes)) or not isinstance(refs, Sequence):
        raise ValueError("artifactRefs must be an array of scope/ref objects")
    normalized_refs: list[dict[str, str]] = []
    for index, item in enumerate(refs):
        if not isinstance(item, Mapping) or set(item) != {"scope", "ref"}:
            raise ValueError(f"artifactRefs[{index}] must contain scope/ref")
        normalized_refs.append({"scope": str(item["scope"]), "ref": str(item["ref"])})
    context["artifactRefs"] = normalized_refs
    if stage in {"sources", "2.quality", "3.compose", "4.draft", "5.review"}:
        semantic_ref = str(context.get("semanticResultRef") or "")
        semantic_digest = str(context.get("semanticResultDigest") or "")
        relative = Path(semantic_ref)
        if not semantic_ref or relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"{stage} gate requires safe semanticResultRef")
        if (len(semantic_digest) != 71 or not semantic_digest.startswith("sha256:")
                or any(char not in "0123456789abcdef" for char in semantic_digest[7:])):
            raise ValueError(f"{stage} gate requires semanticResultDigest=sha256:<64 lowercase hex>")
        context["semanticResultRef"] = semantic_ref
        context["semanticResultDigest"] = semantic_digest
    if stage in {"release", "ship"}:
        for field in ("releaseId", "releaseDigest"):
            value = str(context.get(field) or "")
            if not value:
                raise ValueError(f"{stage} gate requires {field}")
            context[field] = value
        digest = str(context["releaseDigest"])
        if (len(digest) != 71 or not digest.startswith("sha256:")
                or any(char not in "0123456789abcdef" for char in digest[7:])):
            raise ValueError("releaseDigest must be sha256:<64 lowercase hex>")
    if stage == "release":
        if context.get("releaseClass") not in {"research", "commercial"}:
            raise ValueError("release gate requires releaseClass=research|commercial")
    if stage == "ship":
        required = (
            "environmentAcceptanceFactRef", "environmentAcceptanceFactDigest",
            "environment", "importRunId", "verifyRunId", "readinessPhase", "target",
            "acceptanceProfile",
        )
        for field in required:
            if not str(context.get(field) or ""):
                raise ValueError(f"ship gate requires {field}")
        acceptance_digest = str(context["environmentAcceptanceFactDigest"])
        if (len(acceptance_digest) != 71 or not acceptance_digest.startswith("sha256:")
                or any(char not in "0123456789abcdef" for char in acceptance_digest[7:])):
            raise ValueError("environmentAcceptanceFactDigest must be sha256:<64 lowercase hex>")
        acceptance_profile = str(context["acceptanceProfile"])
        if acceptance_profile not in {"environment_promotion", "m1_api_consumer"}:
            raise ValueError("ship acceptanceProfile is invalid")
        context["acceptanceProfile"] = acceptance_profile
        profiles = context.get("requiredTargetProfiles")
        if isinstance(profiles, (str, bytes)) or not isinstance(profiles, Sequence):
            raise ValueError("ship gate requires requiredTargetProfiles array")
        normalized_profiles: list[dict[str, str]] = []
        for index, profile in enumerate(profiles):
            if not isinstance(profile, Mapping) or set(profile) != {"platform", "deviceProfile"}:
                raise ValueError(f"requiredTargetProfiles[{index}] must contain platform/deviceProfile")
            row = {"platform": str(profile["platform"]), "deviceProfile": str(profile["deviceProfile"])}
            if row["platform"] not in {"android", "ios"} or row["deviceProfile"] not in {"rehearsal", "promotable", "production"}:
                raise ValueError(f"requiredTargetProfiles[{index}] uses unknown values")
            normalized_profiles.append(row)
        if len({(row["platform"], row["deviceProfile"]) for row in normalized_profiles}) != len(normalized_profiles):
            raise ValueError("requiredTargetProfiles must be unique")
        context["requiredTargetProfiles"] = sorted(normalized_profiles, key=lambda row: (row["platform"], row["deviceProfile"]))
        if context["environment"] not in {"alpha", "beta", "gamma", "prod"}:
            raise ValueError("ship environment is invalid")
        if context["readinessPhase"] not in {"research", "consumer", "commercial"}:
            raise ValueError("ship readinessPhase is invalid")
        if acceptance_profile == "environment_promotion" and not normalized_profiles:
            raise ValueError("environment_promotion requires non-empty requiredTargetProfiles")
        if acceptance_profile == "m1_api_consumer":
            if normalized_profiles:
                raise ValueError("m1_api_consumer requires requiredTargetProfiles=[]")
            if context["environment"] != "alpha" or context["target"] not in {"alpha", "alpha-local"}:
                raise ValueError("m1_api_consumer requires environment=alpha,target=alpha|alpha-local")
            if context["readinessPhase"] not in {"research", "consumer"}:
                raise ValueError("m1_api_consumer readinessPhase must be research|consumer")
    return context



__all__ = ["normalize_context", "registry_argv"]
