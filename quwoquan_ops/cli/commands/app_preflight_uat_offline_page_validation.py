"""离线页面计划与原生 terminal 的纯校验。"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any

from quwoquan_ops.cli.commands.app_preflight_uat_offline import (
    OFFLINE_REQUIRED_CASES, offline_case_blocker, offline_case_spec_ref,
)

OPERATIONS = frozenset({
    "visible", "tap", "scroll", "seek", "playback", "back", "reveal",
    "tab-roundtrip", "input-otp", "wait", "restart", "observe",
})


def require_executable_page_plan(plan: Mapping[str, Any], *, blocker: Any = offline_case_blocker) -> None:
    validate_page_plan(plan, blocker=blocker)
    if plan["executionBlocker"]:
        raise ValueError(plan["executionBlocker"])



def document_digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                                separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_page_plan(plan: Mapping[str, Any], *, blocker: Any = offline_case_blocker) -> None:
    _validate_plan_identity(plan, blocker=blocker)
    _validate_page_steps(plan.get("steps"))
    if plan["executionBlocker"]:
        return
    _validate_native_contract(plan)
    _validate_required_operations(plan)
    _validate_identity_journey(plan)


def _validate_plan_identity(plan: Mapping[str, Any], *, blocker: Any = offline_case_blocker) -> None:
    if (plan.get("schema") != "quwoquan_ops.offline_page_case.v1"
            or plan.get("caseId") not in OFFLINE_REQUIRED_CASES
            or plan.get("planDigest") != document_digest({k: v for k, v in plan.items() if k != "planDigest"})):
        raise ValueError("APP.UAT.page_plan_invalid: offline page plan identity drifted")
    if (plan.get("specRef") != offline_case_spec_ref(plan["caseId"])
            or plan.get("executionBlocker") != blocker(plan["caseId"])):
        raise ValueError("APP.UAT.page_plan_invalid: case acceptance or required blocker drifted")


def _validate_native_contract(plan: Mapping[str, Any]) -> None:
    native_contract = plan.get("nativeContract")
    native_cases = {
        "login-success", "login-error", "private-continuation", "local-write",
        "otp-expiry", "identity-restart", "network-refusal", "otp-refusal",
        "push-refusal", "remote-refusal", "outbox-refusal",
    }
    if plan["caseId"] in native_cases:
        from quwoquan_ops.cli.commands.app_preflight_uat_offline_native_contract import validate_native_case_contract
        if not isinstance(native_contract, Mapping):
            raise ValueError("APP.UAT.page_plan_invalid: GWT-008 native contract is missing")
        validate_native_case_contract(native_contract, launch=plan)
    elif native_contract is not None:
        raise ValueError("APP.UAT.page_plan_invalid: unexpected GWT-008 native contract")


def _validate_required_operations(plan: Mapping[str, Any]) -> None:
    operations = [step["operation"] for step in plan["steps"]]
    case_id = plan["caseId"]
    required = set() if case_id.endswith("-refusal") else {"visible"}
    restore_only = case_id == "identity-restart" and int(plan.get("generation") or 1) >= 2
    if case_id != "default-entry" and not case_id.endswith("-refusal") and not restore_only:
        required.add("tap")
    if case_id.endswith("-refusal"):
        required.add("observe")
    if case_id in {"article-detail", "image-detail", "creator-avatar", "pagination-end"}:
        required.add("reveal")
    if case_id in {"video-complete", "video-seek", "homepage-video-playback"}:
        required.add("seek" if case_id == "video-seek" else "playback")
    if case_id == "homepage-video-playback":
        required.add("reveal")
    if case_id == "homepage-tab-roundtrip":
        required.add("tab-roundtrip")
    terminals = {"visible", "playback", "seek", "tab-roundtrip", "observe"}
    if not required.issubset(operations) or operations[-1] not in terminals:
        raise ValueError("APP.UAT.page_plan_invalid: required page journey cannot be replaced by first frame")


def _validate_identity_journey(plan: Mapping[str, Any]) -> None:
    validators = {
        "homepage-video-playback": _validate_home_video_journey,
        "homepage-tab-roundtrip": _validate_tab_roundtrip_journey,
        "login-cancel": _validate_login_cancel_journey,
        "creator-avatar": _validate_creator_avatar_journey,
    }
    validator = validators.get(plan["caseId"])
    if validator is not None:
        validator(plan)


def _validate_home_video_journey(plan: Mapping[str, Any]) -> None:
    steps = plan["steps"]
    valid = (len(steps) >= 6 and steps[-4]["operation"] == "reveal"
             and steps[-3] == {"operation": "tap", "selector": steps[-4]["selector"]}
             and steps[-2]["operation"] == "visible" and steps[-1]["operation"] == "playback"
             and plan.get("route") not in {"/", "/video-book"})
    if not valid:
        raise ValueError("APP.UAT.page_plan_invalid: home video requires feed reveal/tap and playback")


def _validate_tab_roundtrip_journey(plan: Mapping[str, Any]) -> None:
    steps = plan["steps"]
    labels = steps[-1]["selector"].split("|")
    if (steps[-1]["operation"] != "tab-roundtrip" or len(labels) != 2 or not all(labels)
            or steps[-2] != {"operation": "visible", "selector": labels[1]} or plan.get("route") != "/"):
        raise ValueError("APP.UAT.page_plan_invalid: tab roundtrip requires original following and geometry")


def _validate_login_cancel_journey(plan: Mapping[str, Any]) -> None:
    steps = plan["steps"]
    if (plan.get("route") != "/" or len(steps) < 5
            or [step["operation"] for step in steps[-5:]] != ["tap", "visible", "tap", "visible", "visible"]
            or steps[-5]["selector"] != steps[-1]["selector"]):
        raise ValueError("APP.UAT.page_plan_invalid: cancellation requires login entry and guest return observation")


def _validate_creator_avatar_journey(plan: Mapping[str, Any]) -> None:
    steps = plan["steps"]
    selector = steps[-1]["selector"]
    persona = selector.removeprefix("creator-profile-avatar:")
    if (not selector.startswith("creator-profile-avatar:") or not persona
            or plan.get("route") != "/user/" + persona):
        raise ValueError("APP.UAT.page_plan_invalid: decoded creator identity is required")
    reveal = {"operation": "reveal", "selector": "creator-avatar:" + persona}
    tap = {"operation": "tap", "selector": "creator-avatar:" + persona}
    if reveal not in steps or tap not in steps or not steps.index(reveal) < steps.index(tap) < len(steps) - 1:
        raise ValueError("APP.UAT.page_plan_invalid: identity-bound reveal and tap journey is required")


def _validate_page_steps(steps: object) -> None:
    if not isinstance(steps, list) or not steps or len(steps) > 40:
        raise ValueError("APP.UAT.page_plan_invalid: actual page steps are required")
    if not any(step.get("operation") in {"visible", "playback", "seek", "observe"} for step in steps if isinstance(step, Mapping)):
        raise ValueError("APP.UAT.page_plan_invalid: page observation is required")
    for step in steps:
        _validate_page_step(step)


def _validate_page_step(step: object) -> None:
    if not isinstance(step, Mapping) or step.get("operation") not in OPERATIONS:
        raise ValueError("APP.UAT.page_plan_invalid: unknown or unsafe operation")
    operation = step["operation"]
    if operation == "input-otp":
        _validate_otp_step(step)
    elif operation == "wait":
        if step != {"operation": "wait", "seconds": 300, "clock": "monotonic-real-time-no-adjustment"}:
            raise ValueError("APP.UAT.page_plan_invalid: wait must preserve the real 300-second boundary")
    elif operation == "restart":
        if step != {"operation": "restart", "mode": "cold-new-attempt"}:
            raise ValueError("APP.UAT.page_plan_invalid: restart must create a new attempt")
    elif operation == "observe":
        _validate_observe_step(step)
    else:
        _validate_selector_step(step)


def _validate_otp_step(step: Mapping[str, Any]) -> None:
    invalid_text = any(not isinstance(step.get(key), str) or not step[key].strip()
                       or step[key].startswith("text-prefix:") for key in ("selector", "sourceSelector"))
    if (set(step) != {"operation", "selector", "sourceSelector", "mode"}
            or step.get("mode") not in {"correct", "incorrect"} or invalid_text):
        raise ValueError("APP.UAT.page_plan_invalid: OTP input requires exact UI source and closed mode, never literal values")


def _validate_observe_step(step: Mapping[str, Any]) -> None:
    selectors = {
        "native-network-attempt", "native-otp-delivery-attempt", "native-push-registration-attempt",
        "native-remote-transport-attempt", "native-connected-outbox-attempt",
    }
    if set(step) != {"operation", "selector"} or step.get("selector") not in selectors:
        raise ValueError("APP.UAT.page_plan_invalid: refusal observer source drifted")


def _validate_selector_step(step: Mapping[str, Any]) -> None:
    if set(step) != {"operation", "selector"} or not isinstance(step["selector"], str) or not step["selector"].strip():
        raise ValueError("APP.UAT.page_plan_invalid: an exact observation selector is required")
    if step["selector"].startswith("text-prefix:") and (
            step["operation"] not in {"visible", "playback", "seek"}
            or not step["selector"].removeprefix("text-prefix:").strip()):
        raise ValueError("APP.UAT.page_plan_invalid: prefix is only allowed for body/playback observations")


def _read_native_terminal(output: str) -> object:
    markers = ("QWQ_EXTERNAL_UAT_TERMINAL ", "QWQ_OFFLINE_PAGE ")
    lines = [line.split(marker, 1)[1] for line in output.splitlines() for marker in markers if marker in line]
    if len(lines) != 1:
        raise ValueError("offline page must have exactly one current native terminal result")
    return json.loads(lines[0])


def _validate_native_result_identity(result: object, *, plan: Mapping[str, Any],
                                     launch: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("APP.UAT.relay_terminal_invalid: runner terminal identity drifted")
    if "nativeContract" in plan:
        _validate_relay_terminal_identity(result, plan=plan, launch=launch)
    else:
        _validate_page_terminal_identity(result, plan=plan, launch=launch)
    screenshot_digest = result.get("screenshotDigest")
    if not isinstance(screenshot_digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", screenshot_digest) is None:
        raise ValueError("offline native screenshot identity is missing")
    length = result.get("screenshotByteLength")
    if "screenshotByteLength" in result and (type(length) is not int or not 32 <= length <= 8 * 1024 * 1024):
        raise ValueError("offline native screenshot identity is missing")
    return result


def _validate_relay_terminal_identity(result: dict[str, Any], *, plan: Mapping[str, Any],
                                      launch: Mapping[str, Any]) -> None:
    expected = {"schema": "external-uat-terminal-result", "planDigest": plan["planDigest"],
                "caseId": plan["caseId"], "launchAttemptId": launch["launchAttemptId"],
                "processId": launch["canonicalProcessId"], "deviceId": launch["deviceId"],
                "status": "passed", "generation": plan["nativeContract"]["generation"],
                "sessionId": plan["nativeContract"]["sessionId"]}
    required = {"screenshotDigest", "terminalDigest", "terminalRef"}
    if set(result) != set(expected) | required or any(result.get(key) != value for key, value in expected.items()):
        raise ValueError("APP.UAT.relay_terminal_invalid: runner terminal identity drifted")
    body = {key: value for key, value in result.items() if key not in {"terminalDigest", "terminalRef"}}
    if result.get("terminalDigest") != document_digest(body):
        raise ValueError("APP.UAT.relay_terminal_invalid: runner terminal digest drifted")


def _validate_page_terminal_identity(result: dict[str, Any], *, plan: Mapping[str, Any],
                                       launch: Mapping[str, Any]) -> None:
    expected = {
        **{key: launch[key] for key in ("candidateDigest", "artifactDigest", "deviceId", "launchAttemptId")},
        "caseId": plan["caseId"], "planDigest": plan["planDigest"], "applicationId": launch["applicationId"],
        "status": "passed", "schema": "quwoquan_ops.offline_native_page_result.v1",
        "platform": launch["platform"], "processIdBefore": launch["canonicalProcessId"],
    }
    required = {"observations", "screenshotDigest", "screenshotByteLength", "processIdAfter"}
    if (set(result) != set(expected) | required or any(result.get(key) != value for key, value in expected.items())
            or type(result.get("processIdAfter")) is not int
            or result.get("processIdAfter") != launch["canonicalProcessId"]):
        raise ValueError("offline native page candidate/artifact/process identity drifted")


def native_page_screenshot(output: str, result: Mapping[str, Any]) -> bytes:
    """截图在原生观察终态且 canonical PID 仍在前台时产生，不截宿主返回后的屏幕。"""
    marker = "QWQ_OFFLINE_SCREENSHOT "
    chunks = [line.split(marker, 1)[1].split(" ", 2) for line in output.splitlines() if marker in line]
    if not chunks:
        if result.get("schema") == "external-uat-terminal-result":
            return b""
        raise ValueError("APP.UAT.page_artifact_binding_missing: native screenshot chunks are missing or drifted")
    if any(len(chunk) != 3 or chunk[:2] != [result["planDigest"], str(index)]
           for index, chunk in enumerate(chunks)):
        raise ValueError("APP.UAT.page_artifact_binding_missing: native screenshot chunks are missing or drifted")
    encoded = "".join(chunk[2] for chunk in chunks)
    if len(encoded) > 12 * 1024 * 1024:
        raise ValueError("APP.UAT.page_artifact_binding_missing: native screenshot exceeds bound")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("APP.UAT.page_artifact_binding_missing: native screenshot encoding is invalid") from error
    expected_length = result.get("screenshotByteLength")
    if (not raw.startswith(b"\x89PNG\r\n\x1a\n")
            or (expected_length is not None and len(raw) != expected_length)
            or "sha256:" + hashlib.sha256(raw).hexdigest() != result["screenshotDigest"]):
        raise ValueError("APP.UAT.page_artifact_binding_missing: native screenshot bytes drifted")
    return raw


def _validate_playback_observation(operation: str, observed: str) -> None:
    match = re.search(r"(\d+):(\d{2})\s*/\s*(\d+):(\d{2})", observed)
    if match is None:
        raise ValueError("offline native playback has no observed position")
    current, seconds, duration, duration_seconds = map(int, match.groups())
    position, total = current * 60 + seconds, duration * 60 + duration_seconds
    if total <= 0 or (operation == "playback" and position < total - 1):
        raise ValueError("offline native playback did not complete")


def _validate_step_observation(step: Mapping[str, Any], observation: object) -> None:
    if not isinstance(observation, dict) or observation.get("operation") != step.get("operation"):
        raise ValueError("offline native page step order drifted")
    operation = step["operation"]
    exact = {
        "wait": {"operation": "wait", "observed": "elapsed-300s-challenge-expired"},
        "restart": {"operation": "restart", "observed": "cold-new-attempt-identity-restored"},
        "input-otp": {"operation": "input-otp", "selector": step.get("selector"), "observed": "input-redacted"},
        "observe": {"operation": "observe", "selector": step.get("selector"), "observed": "refusal-redacted"},
    }
    if operation in exact:
        if observation != exact[operation]:
            messages = {
                "wait": "offline native expiry observation is missing",
                "restart": "offline native restart observation is missing",
                "input-otp": "offline native input observation must be redacted",
                "observe": "offline native refusal observation must stay redacted",
            }
            raise ValueError(messages[operation])
        return
    _validate_selector_observation(step, observation)
    if operation in {"seek", "playback"}:
        _validate_playback_observation(operation, observation["observed"])
    if operation == "tab-roundtrip":
        _validate_tab_geometry(observation["observed"])


def _validate_selector_observation(step: Mapping[str, Any], observation: dict[str, Any]) -> None:
    observed = observation.get("observed")
    if (set(observation) != {"operation", "selector", "observed"}
            or observation.get("selector") != step.get("selector")
            or not isinstance(observed, str) or not observed.strip()
            or step["selector"].removeprefix("text-prefix:") not in observed):
        raise ValueError("offline native page observation is missing or drifted")


def _validate_tab_geometry(observed: str) -> None:
    try:
        geometry = json.loads(observed.split(" geometry=", 1)[1])
        initial, middle, further, restored = [geometry[key] for key in ("initial", "middle", "further", "restored")]
        for coordinates, count in ((initial, 2), (middle, 1), (further, 1), (restored, 2)):
            _validate_coordinates(coordinates, count)
        if not (middle[0] < initial[0] - 5 and abs(middle[0] - further[0]) <= 5
                and abs(restored[0] - initial[0]) <= 5 and abs(restored[1] - initial[1]) <= 5
                and initial[1] < initial[0] and restored[1] < restored[0]):
            raise ValueError("tab geometry did not pin and restore")
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("offline native tab geometry is incomplete") from error


def _validate_coordinates(coordinates: object, count: int) -> None:
    if not isinstance(coordinates, list) or len(coordinates) != count:
        raise ValueError("offline native tab geometry is invalid")
    if any(type(value) not in {int, float} or not math.isfinite(value) or value < 0 for value in coordinates):
        raise ValueError("offline native tab geometry is invalid")


def validate_native_page_result(output: str, *, plan: Mapping[str, Any], launch: Mapping[str, Any],
                                blocker: Any = offline_case_blocker) -> dict[str, Any]:
    """只接受runner terminal；GWT-008 actual必须由launcher relay后续附加。"""
    require_executable_page_plan(plan, blocker=blocker)
    if any(plan.get(key) != launch.get(key) for key in (
        "candidateDigest", "artifactDigest", "deviceId", "applicationId", "canonicalProcessId", "platform", "launchAttemptId",
    )):
        raise ValueError("APP.UAT.page_artifact_binding_missing: page plan launch binding drifted")
    result = _validate_native_result_identity(_read_native_terminal(output), plan=plan, launch=launch)
    if "nativeContract" not in plan:
        observations = result["observations"]
        if not isinstance(observations, list) or len(observations) != len(plan["steps"]):
            raise ValueError("offline native page coverage is incomplete")
        for step, observation in zip(plan["steps"], observations, strict=True):
            _validate_step_observation(step, observation)
    return result
