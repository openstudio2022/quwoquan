"""离线页面的实际制品、原生步骤与 canonical raw case 证据。"""

from __future__ import annotations

import argparse
import binascii
import base64
import hashlib
import json
import os
import plistlib
import re
import zipfile
from datetime import datetime, timezone
from contextlib import ExitStack
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.commands.app_preflight_uat_offline import OFFLINE_REQUIRED_CASES, OFFLINE_SPEC_REF
from quwoquan_ops.cli.lib.readiness_case_result import (
    validate_readiness_case_result, write_create_once_json, write_readiness_case_result,
)
from quwoquan_ops.cli.lib.target_uat_binding import (
    build_offline_target_uat_binding, target_uat_binding_digest, validate_target_uat_binding,
    write_create_once_target_uat_binding,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke import external_aut_driver as driver
from quwoquan_ops.cli.smoke.environment_patrol_smoke import artifact_binding as artifacts
from quwoquan_ops.cli.smoke.environment_patrol_smoke.execution import run_command
RUNNER_SOURCE = "quwoquan_ops/cli/commands/app_preflight_uat_offline_pages.py"
RUNNER_IDENTITY = "stackctl.offline-native-pages.v1"
ANDROID_PAGE_METHOD = "executesOfflinePageCaseInCanonicalProductionProcess"
IOS_PAGE_METHOD = "testExecutesOfflinePageCaseInCanonicalProductionProcess"
OPERATIONS = frozenset({"visible", "tap", "scroll", "seek", "playback", "back", "reveal"})


def document_digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                                separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_page_plan(plan: Mapping[str, Any]) -> None:
    if (plan.get("schema") != "quwoquan_ops.offline_page_case.v1"
            or plan.get("caseId") not in OFFLINE_REQUIRED_CASES
            or plan.get("planDigest") != document_digest({k: v for k, v in plan.items() if k != "planDigest"})):
        raise ValueError("APP.UAT.page_plan_invalid: offline page plan identity drifted")
    _validate_page_steps(plan.get("steps"))
    operations = [step["operation"] for step in plan["steps"]]
    case_id = plan["caseId"]
    required = {"visible"}
    if case_id != "default-entry":
        required.add("tap")
    if case_id in {"article-detail", "image-detail", "creator-avatar", "pagination-end"}:
        required.add("reveal")
    if case_id in {"video-complete", "video-seek"}:
        required.add("playback" if case_id == "video-complete" else "seek")
    if not required.issubset(operations) or operations[-1] not in {"visible", "playback", "seek"}:
        raise ValueError("APP.UAT.page_plan_invalid: required page journey cannot be replaced by first frame")
    _validate_identity_journey(plan)


def _validate_identity_journey(plan: Mapping[str, Any]) -> None:
    steps, case_id = plan["steps"], plan["caseId"]
    terminal = {
        "login-unavailable": "capability-unavailable:account_authentication:profileTab",
        "write-unavailable": "capability-unavailable:like",
        "private-unavailable": "capability-unavailable:account_authentication:openChat",
    }.get(case_id)
    if terminal is not None and steps[-1] != {"operation": "visible", "selector": terminal}:
        raise ValueError("APP.UAT.page_plan_invalid: typed capability terminal is required")
    if case_id in {"login-unavailable", "private-unavailable"} and plan.get("route") != "/login":
        raise ValueError("APP.UAT.page_plan_invalid: refused entry must record the login terminal route")
    if case_id == "creator-avatar":
        selector = steps[-1]["selector"]
        persona = selector.removeprefix("creator-profile-avatar:")
        if (not selector.startswith("creator-profile-avatar:") or not persona
                or plan.get("route") != "/user/" + persona):
            raise ValueError("APP.UAT.page_plan_invalid: decoded creator identity is required")
        action = "creator-avatar:" + persona
    elif case_id == "write-unavailable":
        actions = [step["selector"] for step in steps if step["operation"] == "tap"
                   and step["selector"].startswith("post-like:") and step["selector"] != "post-like:"]
        if len(actions) != 1 or plan.get("route") != "/":
            raise ValueError("APP.UAT.page_plan_invalid: write refusal requires a real feed like action")
        action = actions[0]
    else:
        return
    reveal = {"operation": "reveal", "selector": action}
    tap = {"operation": "tap", "selector": action}
    if reveal not in steps or tap not in steps or not steps.index(reveal) < steps.index(tap) < len(steps) - 1:
        raise ValueError("APP.UAT.page_plan_invalid: identity-bound reveal and tap journey is required")


def _validate_page_steps(steps: object) -> None:
    if not isinstance(steps, list) or not steps or len(steps) > 40:
        raise ValueError("APP.UAT.page_plan_invalid: actual page steps are required")
    if not any(step.get("operation") in {"visible", "playback", "seek"} for step in steps if isinstance(step, Mapping)):
        raise ValueError("APP.UAT.page_plan_invalid: page observation is required")
    for step in steps:
        _validate_page_step(step)


def _validate_page_step(step: object) -> None:
    if not isinstance(step, Mapping) or step.get("operation") not in OPERATIONS:
        raise ValueError("APP.UAT.page_plan_invalid: unknown or unsafe operation")
    if set(step) != {"operation", "selector"} or not isinstance(step["selector"], str) or not step["selector"].strip():
        raise ValueError("APP.UAT.page_plan_invalid: an exact observation selector is required")
    if step["selector"].startswith("text-prefix:") and (
            step["operation"] not in {"visible", "playback", "seek"}
            or not step["selector"].removeprefix("text-prefix:").strip()):
        raise ValueError("APP.UAT.page_plan_invalid: prefix is only allowed for body/playback observations")


def _read_native_terminal(output: str) -> object:
    marker = "QWQ_OFFLINE_PAGE "
    lines = [line.split(marker, 1)[1] for line in output.splitlines() if marker in line]
    if len(lines) != 1:
        raise ValueError("offline page must have exactly one current native terminal result")
    return json.loads(lines[0])


def _validate_native_result_identity(result: object, *, plan: Mapping[str, Any],
                                     launch: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        **{key: launch[key] for key in ("candidateDigest", "artifactDigest", "deviceId", "launchAttemptId")},
        "schema": "quwoquan_ops.offline_native_page_result.v1", "caseId": plan["caseId"],
        "planDigest": plan["planDigest"], "platform": launch["platform"],
        "applicationId": launch["applicationId"], "status": "passed",
        "processIdBefore": launch["canonicalProcessId"], "processIdAfter": launch["canonicalProcessId"],
    }
    if (not isinstance(result, dict) or set(result) != set(expected) | {"observations", "screenshotDigest", "screenshotByteLength"}
            or any(result.get(key) != value for key, value in expected.items())
            or any(type(result.get(key)) is not int for key in ("processIdBefore", "processIdAfter"))):
        raise ValueError("offline native page candidate/artifact/process identity drifted")
    if (not isinstance(result["screenshotDigest"], str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", result["screenshotDigest"]) is None
            or type(result["screenshotByteLength"]) is not int
            or not 32 <= result["screenshotByteLength"] <= 8 * 1024 * 1024):
        raise ValueError("offline native screenshot identity is missing")
    return result


def native_page_screenshot(output: str, result: Mapping[str, Any]) -> bytes:
    """截图在原生观察终态且 canonical PID 仍在前台时产生，不截宿主返回后的屏幕。"""
    marker = "QWQ_OFFLINE_SCREENSHOT "
    chunks = [line.split(marker, 1)[1].split(" ", 2) for line in output.splitlines() if marker in line]
    if not chunks or any(len(chunk) != 3 or chunk[:2] != [result["planDigest"], str(index)]
                         for index, chunk in enumerate(chunks)):
        raise ValueError("APP.UAT.page_artifact_binding_missing: native screenshot chunks are missing or drifted")
    encoded = "".join(chunk[2] for chunk in chunks)
    if len(encoded) > 12 * 1024 * 1024:
        raise ValueError("APP.UAT.page_artifact_binding_missing: native screenshot exceeds bound")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("APP.UAT.page_artifact_binding_missing: native screenshot encoding is invalid") from error
    if (not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) != result["screenshotByteLength"]
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
    if (set(observation) != {"operation", "selector", "observed"}
            or observation.get("selector") != step.get("selector")
            or not isinstance(observation.get("observed"), str)
            or not observation["observed"].strip()
            or step["selector"].removeprefix("text-prefix:") not in observation["observed"]):
        raise ValueError("offline native page observation is missing or drifted")
    if step["operation"] in {"seek", "playback"}:
        _validate_playback_observation(step["operation"], observation["observed"])


def validate_native_page_result(output: str, *, plan: Mapping[str, Any], launch: Mapping[str, Any]) -> dict[str, Any]:
    """只接受本次原生命令的一条终态，拒绝旧日志、代理进程或不完整步骤。"""
    validate_page_plan(plan)
    if any(plan.get(key) != launch.get(key) for key in (
        "candidateDigest", "artifactDigest", "deviceId", "applicationId", "canonicalProcessId", "platform", "launchAttemptId",
    )):
        raise ValueError("APP.UAT.page_artifact_binding_missing: page plan launch binding drifted")
    result = _validate_native_result_identity(_read_native_terminal(output), plan=plan, launch=launch)
    observations = result["observations"]
    steps = plan["steps"]
    if not steps or not isinstance(observations, list) or len(observations) != len(steps):
        raise ValueError("offline native page coverage is incomplete")
    for step, observation in zip(steps, observations, strict=True):
        _validate_step_observation(step, observation)
    return result


def _verify_snapshot_assets(read_asset: Any, *, source: Path, raw: bytes, manifest: Mapping[str, Any]) -> None:
    if (read_asset("assets/content/alpha/manifest.json") != raw
            or read_asset("assets/content/alpha/bundle_identity.json") != (source.parent / "bundle_identity.json").read_bytes()):
        raise ValueError("offline AUT contains a different snapshot")
    for row in manifest["media"]:
        relative = str(row["assetPath"])
        if not re.fullmatch(r"assets/content/alpha/media/[a-zA-Z0-9._-]+", relative):
            raise ValueError("offline snapshot media path escapes artifact assets")
        body = read_asset(relative)
        if len(body) != row["byteLength"] or "sha256:" + hashlib.sha256(body).hexdigest() != row["sha256"]:
            raise ValueError("offline AUT media is missing or corrupted: " + row["assetId"])


def read_artifact_snapshot(*, artifact: Path, platform: str, expected_artifact_digest: str,
                           app_root: Path) -> dict[str, Any]:
    """逐字核对真实 AUT 内的 manifest 与全部媒体，不以源码目录代替安装制品。"""
    from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import artifact_payload_digest

    if artifact_payload_digest(artifact, platform) != expected_artifact_digest:
        raise ValueError("offline AUT artifact digest drifted")
    source = app_root / "assets/content/alpha/manifest.json"
    raw = source.read_bytes()
    manifest = json.loads(raw)
    identity = json.loads((source.parent / "bundle_identity.json").read_bytes())
    if identity["manifestDigest"] != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise ValueError("offline snapshot manifest digest drifted")
    manifest_body = {key: value for key, value in manifest.items() if key != "bundleId"}
    if manifest["bundleId"] != "alpha-" + document_digest(manifest_body).removeprefix("sha256:"):
        raise ValueError("offline snapshot bundle identity drifted")
    if identity["bundleId"] != manifest["bundleId"]:
        raise ValueError("offline snapshot artifact identity disagrees with manifest")

    if platform == "android":
        with zipfile.ZipFile(artifact) as package:
            if len(package.namelist()) != len(set(package.namelist())):
                raise ValueError("offline AUT APK contains duplicate entries")
            _verify_snapshot_assets(lambda ref: package.read("assets/flutter_assets/" + ref),
                source=source, raw=raw, manifest=manifest)
    else:
        assets = artifact / "Frameworks/App.framework/flutter_assets"
        def read_asset(ref: str) -> bytes:
            path = assets / ref
            if path.is_symlink() or not path.resolve().is_relative_to(artifact.resolve()):
                raise ValueError("offline AUT assets contain unsafe links")
            return path.read_bytes()
        _verify_snapshot_assets(read_asset, source=source, raw=raw, manifest=manifest)
    if artifact_payload_digest(artifact, platform) != expected_artifact_digest:
        raise ValueError("offline AUT changed while verifying snapshot")
    return manifest


def _offline_binding_index(bindings: Sequence[Mapping[str, Any]],
                           candidate: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    by_id = {}
    for raw in bindings:
        binding = validate_target_uat_binding(raw)
        if (binding.get("contentSource") != "bundled_snapshot" or binding["candidateDigest"] != candidate["candidateId"]
                or binding["commitSha"] != candidate["commit"] or binding["treeSha"] != candidate["tree"]):
            raise ValueError("offline page TargetUatBinding candidate identity drifted")
        digest = target_uat_binding_digest(binding)
        if digest in by_id:
            raise ValueError("duplicate offline TargetUatBinding")
        by_id[digest] = binding
    return by_id


def _validate_offline_result_binding(result: Mapping[str, Any], *, binding: Mapping[str, Any],
                                     candidate: Mapping[str, Any]) -> None:
    expected = {
        "contentSource": "bundled_snapshot", "status": "passed", "specRef": OFFLINE_SPEC_REF,
        "commitSha": candidate["commit"], "candidateDigest": candidate["candidateId"],
        "platform": binding["platform"], "deviceIdentity": binding["device"]["identity"],
        "deviceRegistered": binding["device"]["registered"], "runnerIdentity": binding["runner"]["identity"],
        "artifactClass": binding["artifact"]["class"], "uatProfile": binding["profile"],
        "artifactSha256": binding["artifact"]["digest"].removeprefix("sha256:"),
    }
    if (any(result.get(key) != value for key, value in expected.items())
            or result["nonPromotable"] is not True or result["physicalDevice"] is not False):
        raise ValueError("offline page result candidate/artifact/device identity drifted")
    if result.get("observedOutcome") != offline_case_outcome(str(result["caseId"])):
        raise ValueError("offline page required outcome was not observed")


def validate_offline_page_coverage(*, results: Sequence[Mapping[str, Any]],
                                   bindings: Sequence[Mapping[str, Any]], candidate: Mapping[str, Any],
                                   platforms: Sequence[str] = ("android", "ios")) -> None:
    """同一 exact candidate 的 required 平台 × 页面矩阵；日志与服务 readback 不占位。"""
    by_id = _offline_binding_index(bindings, candidate)
    seen = set()
    for raw in results:
        result = validate_readiness_case_result(raw, generated_at=str(raw.get("completedAt") or ""))
        binding = by_id.get(result.get("targetUatBindingDigest"))
        slot = (result.get("platform"), result.get("caseId"))
        if binding is None or slot in seen:
            raise ValueError("offline page binding is absent or case is duplicated")
        _validate_offline_result_binding(result, binding=binding, candidate=candidate)
        seen.add(slot)
    expected = {(platform, case) for platform in platforms for case in OFFLINE_REQUIRED_CASES}
    if seen != expected:
        raise ValueError("offline page required matrix is incomplete: " + repr(sorted(expected - seen)))


def offline_case_outcome(case_id: str) -> str:
    if case_id.endswith("-unavailable"):
        return "capability_unavailable"
    return "empty" if case_id in {"empty-state", "pagination-end"} else "content"


def _file_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("APP.UAT.page_artifact_binding_missing: evidence file is missing or unsafe")
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _reference(path: Path, root: Path) -> dict[str, str]:
    resolved = path.resolve(strict=True)
    if path.absolute() != resolved or not resolved.is_relative_to(root.resolve(strict=True)):
        raise ValueError("APP.UAT.page_artifact_binding_missing: evidence escaped output root")
    return {"ref": resolved.relative_to(root.resolve()).as_posix(), "digest": _file_digest(resolved)}


def _copy_evidence(source: Path, destination: Path, root: Path) -> dict[str, str]:
    # JSON 事实引用绑定实际字节，不把 digest 字符串当作已核验材料。
    raw = source.read_bytes()
    write_create_once_json(destination, json.loads(raw))
    return _reference(destination, root)


def _dart_text(app_root: Path, relative: str, symbol: str) -> str:
    source = (app_root / relative).read_text(encoding="utf-8")
    matches = re.findall(r"\b" + re.escape(symbol) + r"\s*=\s*'([^'\n]+)'", source)
    if len(matches) != 1:
        raise ValueError("APP.UAT.page_plan_invalid: canonical selector is absent or ambiguous: " + symbol)
    return matches[0]


def _snapshot_article_excerpt(article: Mapping[str, Any]) -> str:
    body = str(article.get("articleMarkdown") or article.get("body") or "")
    paragraphs = [line.strip() for line in body.splitlines() if len(line.strip()) > 25 and not line.startswith(("#", "---", "title:", "tagRefs:", "creatorProfileId:"))]
    if not paragraphs:
        raise ValueError("APP.UAT.page_plan_invalid: article has no readable body")
    return paragraphs[0][:28]


def build_offline_page_plans(*, snapshot: Mapping[str, Any], app_root: Path,
                             launch: Mapping[str, Any]) -> list[dict[str, Any]]:
    """用制品快照对象与已有页面文案/typed route 构造黑盒旅程，不创建用户。"""
    copies = "lib/l10n/copy/"
    def text(file: str, symbol: str) -> str:
        return _dart_text(app_root, copies + file + ".dart", symbol)
    def step(operation: str, selector: str) -> dict[str, str]:
        return {"operation": operation, "selector": selector}
    def visible(selector: str) -> dict[str, str]:
        return step("visible", selector)
    def tap(selector: str) -> dict[str, str]:
        return step("tap", selector)
    def reveal(selector: str) -> dict[str, str]:
        return step("reveal", selector)
    home = _dart_text(app_root, "lib/design_system/semantics/navigation_semantic_constants.dart", "homeSurfaceIdentifier")
    home_tab = text("app_concept_constants", "discovery")
    recommend = text("ui_text_constants_discovery", "homeTabRecommended")
    premium = text("app_concept_constants", "premium")
    empty_channel = text("ui_text_constants_discovery", "circleScenarioCampus")
    completed = text("discovery_feed_text_constants", "contentLoadingCompleted")
    progress = "text-prefix:" + text("ui_text_constants_media", "videoPlaybackProgressLabel")
    success_source = (app_root / "lib/design_system/media/app_cached_network_image.dart").read_text()
    success = re.search(r"appImageLoadSuccessKey\s*=\s*ValueKey<String>\(\s*'([^']+)'", success_source)
    if success is None:
        raise ValueError("APP.UAT.page_plan_invalid: decoded image selector is missing")
    posts = {row["projection"]["postId"]: row["detail"] for row in snapshot["posts"]}
    channels = {row["channelId"]: row["orderedPostIds"] for row in snapshot["channels"]}
    def post(kind: str, channel: str = "recommend") -> Mapping[str, Any]:
        selected = [posts[identity] for identity in channels[channel] if posts[identity]["contentType"] == kind]
        if not selected:
            raise ValueError("APP.UAT.page_plan_invalid: snapshot lacks required " + channel + "/" + kind)
        return selected[0]
    article, image, video = post("article"), post("image"), post("video", "premium")
    if channels.get("campus"):
        raise ValueError("APP.UAT.page_plan_invalid: canonical empty channel is no longer empty")
    route_file = app_root / "lib/runtime/shell/navigation/generated/app_route_paths.g.dart"
    route_source = route_file.read_text()
    def route(symbol: str, **parameters: str) -> str:
        value = _dart_text(app_root, str(route_file.relative_to(app_root)), symbol)
        for key, item in parameters.items():
            value = value.replace("{" + key + "}", item)
        if "{" in value or not value.startswith("/"):
            raise ValueError("APP.UAT.page_plan_invalid: unresolved typed route")
        return value
    if "workBrowser" not in route_source:
        raise ValueError("APP.UAT.page_plan_invalid: canonical work browser route absent")
    base = [tap(home_tab), tap(recommend)]
    open_image = [*base, reveal(image["title"]), tap(image["title"])]
    open_video = [tap(premium), visible(video["title"])]
    # 视频书主动隐藏底栏；只点击 canonical 顶栏返回，再观察首页已恢复。
    exit_video = [tap("works-top-back"), visible(home)]
    article_excerpt = _snapshot_article_excerpt(article)
    # 每例停留在观察终态供截图；下一例才恢复同一进程的导航状态。
    cases = [
        ("default-entry", "homepage", route("home"), [visible(home)], []),
        ("homepage-recommendation", "homepage", route("home"), [*base, visible(article["title"])], []),
        ("premium-video-book", "video", route("videoBook"), open_video, exit_video),
        ("article-detail", "article", route("workBrowserPathTemplate", workId=article["postId"]),
         [*base, reveal(article["title"]), tap(article["title"]), visible("text-prefix:" + article_excerpt)], [step("back", home)]),
        ("image-detail", "image", route("workBrowserPathTemplate", workId=image["postId"]),
         [*open_image, visible(success[1])], [step("back", home)]),
        ("creator-avatar", "image", route("userProfilePathTemplate", userHandle=image["authorId"]),
         [*base, reveal("creator-avatar:" + image["authorId"]), tap("creator-avatar:" + image["authorId"]),
          visible("creator-profile-avatar:" + image["authorId"])], [step("back", home)]),
        ("video-complete", "video", route("videoBook"), [*open_video, step("playback", progress)], exit_video),
        ("video-seek", "video", route("videoBook"), [*open_video, step("seek", progress)], exit_video),
        ("empty-state", "homepage", route("home"), [*base, tap(empty_channel), visible(completed)], []),
        ("pagination-end", "homepage", route("home"), [*base, reveal(completed), visible(completed)], []),
        ("login-unavailable", "homepage", route("loginPathTemplate"),
         [tap(text("ui_text_constants_foundation", "bottomNavGuestProfile")),
          visible("capability-unavailable:account_authentication:profileTab")], [step("back", home)]),
        # 离线禁止远端写入，不禁止本地创作；点赞从推荐流触发真实 typed 拒绝。
        ("write-unavailable", "homepage", route("home"),
         [*base, reveal("post-like:" + article["postId"]), tap("post-like:" + article["postId"]),
          visible("capability-unavailable:like")], [step("back", home)]),
        # 联系人入口停在登录拒绝页，不能把未进入的 chat 路由记录为已观察。
        ("private-unavailable", "homepage", route("loginPathTemplate"),
         [tap(text("chat_text_constants", "chatPrimaryContacts")),
          visible("capability-unavailable:account_authentication:openChat")], []),
    ]
    plans: list[dict[str, Any]] = []
    restore: list[dict[str, str]] = []
    for case_id, carrier, route_path, steps, next_restore in cases:
        plan = {
            "schema": "quwoquan_ops.offline_page_case.v1", "caseId": case_id,
            "candidateDigest": launch["candidateDigest"], "artifactDigest": launch["artifactDigest"],
            "deviceId": launch["deviceId"], "applicationId": launch["applicationId"],
            "canonicalProcessId": launch["canonicalProcessId"], "platform": launch["platform"],
            "launchAttemptId": launch["launchAttemptId"], "snapshotDigest": document_digest(snapshot),
            "route": route_path, "carrier": carrier, "steps": [*restore, *steps],
        }
        plan["planDigest"] = document_digest(plan)
        validate_page_plan(plan)
        plans.append(plan)
        restore = next_restore
    return plans


def _run_native_command(command: list[str], *, cwd: Path, environment: dict[str, str],
                        log_path: Path, timeout: float = 300) -> dict[str, Any]:
    from quwoquan_ops.cli.commands.app_preflight_uat_offline import first_typed_blocker
    if log_path.exists() or log_path.is_symlink():
        raise ValueError("APP.UAT.page_artifact_binding_missing: native command log must be fresh")
    result = run_command(command, cwd=cwd, env=environment, timeout_seconds=timeout, log_path=log_path)
    if result.get("exitCode") != 0:
        detail = str(result.get("outputSummary") or "native command failed")
        raise ValueError(first_typed_blocker(detail) + ": " + detail)
    return result


def _acquire_page_device_lock(device_id: str, application_id: str) -> Any:
    from quwoquan_ops.cli.lib.host_locks import acquire_device_lock
    return acquire_device_lock(device=device_id, app=application_id)


def _verify_page_projection(projection: Mapping[str, Any]) -> None:
    from quwoquan_ops.cli.commands.app_preflight_uat_launch import verify_app_content_launch_projection
    verified = verify_app_content_launch_projection(projection_root=Path(projection["sourceProjectionRoot"]),
        evidence_path=Path(projection["sourceProjectionEvidenceRef"]), reject_unmanifested=False)
    if any(verified.get(key) != value for key, value in projection.items()
           if key not in {"sourceProjectionEvidenceDigest", "sourceProjectionEvidenceRef"}):
        raise ValueError("APP.LAUNCH.receipt_invalid: source projection identity drifted")


def _device(args: argparse.Namespace) -> dict[str, Any]:
    from quwoquan_ops.cli.lib.local_device_trust.device_commands import resolve_managed_device
    platform = "android-emulator" if args.platform == "android" else "ios-simulator"
    identity = str(args.device_id or "")
    if not identity or resolve_managed_device(platform, identity) != identity:
        raise ValueError("APP.LAUNCH.device_unavailable: exact managed device required")
    return {"id": identity, "targetPlatform": "android" if args.platform == "android" else "ios", "emulator": True}


def _prepare_native_driver(*, args: argparse.Namespace, projection: Mapping[str, Any], launch: Mapping[str, Any],
                           artifact: Path, report_dir: Path, output_root: Path, device: dict[str, Any]) -> dict[str, Any]:
    """仅 stackctl 编排调用；私有投影编译独立宿主，不运行宿主 Dart 旅程或注入账号。"""
    from quwoquan_ops.cli.commands.app_preflight_uat_launch import materialize_app_content_launch_projection
    from quwoquan_ops.cli.lib.app_dependency_toolchain import resolve_cocoapods_executable
    from quwoquan_ops.cli.lib.package_reuse.dependency_bundle_projection import (
        materialize_dependency_bundle_projection, replay_ios_dependency_projections,
    )
    from quwoquan_ops.cli.lib.package_reuse.dependency_projection_prepare import prepare_dependency_projection_cas_evidence
    from quwoquan_ops.cli.lib.package_reuse.patrol_command_envelope import build_patrol_command_envelope, rebuild_patrol_command_environment
    from quwoquan_ops.cli.lib.patrol_execution_lock import acquire_patrol_execution_lock
    from quwoquan_ops.ci.device_matrix.android import resolve_android_debug_bridge
    manifest_path = Path(projection["sourceCapsuleManifestRef"])
    manifest = json.loads(manifest_path.read_bytes())
    runtime = {
        "contentSource": "bundled_snapshot", "environment": "alpha", "target": "alpha-local",
        "candidateDigest": projection["candidateDigest"], "sourceRevision": projection["sourceRevision"],
        "sourceCapsuleBaselineId": manifest["baselineId"], "sourceCapsuleManifestRef": str(manifest_path),
        "sourceCapsuleDigest": projection["sourceCapsuleDigest"],
        "sourceCapsuleWorkspaceStatusDigest": projection["sourceCapsuleWorkspaceStatusDigest"],
    }
    with acquire_patrol_execution_lock(env_name="alpha", target="offline-native-pages"):
        native_projection = materialize_app_content_launch_projection(
            runtime_binding=runtime, output_root=output_root, projection_root=report_dir / "native-source",
            evidence_path=report_dir / "native-source.json",
        )
        root = Path(native_projection["sourceProjectionRoot"])
        host = root / "quwoquan_app/test_host/patrol"
        platform = device["targetPlatform"]
        pod = resolve_cocoapods_executable() if platform == "ios" else None
        dependencies = materialize_dependency_bundle_projection(
            manifest_path=manifest_path, projection_root=root, private_state_root=report_dir / "native-state",
            platform=platform, base_environment=dict(os.environ), include_patrol=True, replay_ios=False,
            pod_executable=pod,
        )
        environment = dict(dependencies.patrol_environment or {})
        envelope = build_patrol_command_envelope(environment)
        environment = rebuild_patrol_command_environment(
            envelope=envelope, ambient_environment={}, dependency_environment=envelope["dependencyEnvironment"], command_environment={},
        )
        flutter = envelope["flutterExecutable"]
        # 宿主只嵌入已验真 AUT 的公开信任封套；不请求在线包或伪造登录材料。
        trust_root = report_dir / "native-material"
        trust_path = trust_root / "qwq_runtime/runtime-config-trust.json"
        if platform == "android":
            with zipfile.ZipFile(artifact) as package:
                trust = json.loads(package.read("assets/qwq_runtime/runtime-config-trust.json"))
        else:
            trust = json.loads((artifact / "qwq_runtime/runtime-config-trust.json").read_bytes())
        if document_digest(trust) != launch["runtimeConfigTrustEnvelopeDigest"]:
            raise ValueError("APP.LAUNCH.runtime_config_trust_invalid: native host trust differs from AUT")
        write_create_once_json(trust_path, trust)
        environment["QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT"] = str(trust_root)
        environment["QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH"] = str(trust_path)
        environment["QWQ_APP_BUILD_PROFILE"] = "nonprod"
        commands = []
        commands.append(_run_native_command([flutter, "pub", "get", "--offline", "--enforce-lockfile"],
            cwd=host, environment=environment, log_path=report_dir / "native-pub.log", timeout=120))
        ios_results = None
        if platform == "ios":
            commands.append(_run_native_command([flutter, "pub", "get", "--offline", "--enforce-lockfile"],
                cwd=root / "quwoquan_app", environment=dependencies.production_environment,
                log_path=report_dir / "native-production-pub.log", timeout=120))
            ios_results = replay_ios_dependency_projections(dependency_projection=dependencies, pod_executable=pod)
        expectation = prepare_dependency_projection_cas_evidence(
            projection_root=root, source_manifest_path=manifest_path, dependency_projection=dependencies,
            evidence_path=root / "native-dependencies.json", ios_install_results=ios_results,
        )
        adb = resolve_android_debug_bridge() if platform == "android" else ""
        if platform == "android":
            if not adb:
                raise ValueError("APP.LAUNCH.device_unavailable: adb unavailable")
            commands.append(_run_native_command([flutter, "build", "apk", "--debug", "--no-pub"],
                cwd=host, environment=environment, log_path=report_dir / "native-host-build.log", timeout=900))
            commands.append(_run_native_command(
                [str(host / "android/gradlew"), "--offline", "--no-daemon", ":app:assembleDebugAndroidTest"],
                cwd=host / "android", environment=environment, log_path=report_dir / "native-build.log", timeout=900))
            for index, artifact in enumerate(("build/app/outputs/apk/debug/app-debug.apk", "build/app/outputs/apk/androidTest/debug/app-debug-androidTest.apk")):
                commands.append(_run_native_command([adb, "-s", device["id"], "install", "-r", str(host / artifact)],
                    cwd=host, environment=environment, log_path=report_dir / f"native-install-{index}.log", timeout=120))
        else:
            commands.append(_run_native_command([flutter, "build", "ios", "--debug", "--simulator", "--no-codesign", "--no-pub", "--config-only"],
                cwd=host, environment=environment, log_path=report_dir / "native-config.log", timeout=120))
            commands.append(_run_native_command(["xcodebuild", "build-for-testing", "-workspace", "ios/Runner.xcworkspace", "-scheme", "Runner",
                "-configuration", "Debug", "-sdk", "iphonesimulator", "-destination", "platform=iOS Simulator,id=" + device["id"],
                "-derivedDataPath", str(host / "build/ios_integ"), "CODE_SIGNING_ALLOWED=NO"],
                cwd=host, environment=environment, log_path=report_dir / "native-build.log", timeout=900))
        source = {"root": "quwoquan_app/test_host/patrol", "rootIdentityDigest": document_digest({"root": str(host)}),
                  "sourceDigest": native_projection["sourceProjectionDigest"], "sourceFileCount": native_projection["sourceProjectionFileCount"]}
        context = {"host": host, "environment": environment, "adb": adb, "source": source, "device": device,
                   "commands": commands, "expectation": expectation, "projection": native_projection}
        context["binding"] = _read_driver_binding(context)
        _verify_driver_dependencies(context)
        return context


def _verify_driver_dependencies(context: Mapping[str, Any]) -> None:
    from quwoquan_ops.cli.lib.package_reuse.dependency_projection_readback import revalidate_dependency_projection_cas
    _verify_page_projection(context["projection"])
    expectation = context["expectation"]
    revalidate_dependency_projection_cas(projection_root=expectation.projection_root,
        evidence_path=expectation.evidence_path, expected_digest=expectation.evidence_digest,
        command_environment_owner="patrol", command_environment=context["environment"])


def _read_driver_binding(context: Mapping[str, Any]) -> dict[str, Any]:
    from quwoquan_ops.cli.smoke.environment_patrol_smoke.external_aut_driver_artifact import _driver_artifact_envelope
    device, host = context["device"], context["host"]
    if device["targetPlatform"] == "ios":
        source = driver.resolve_ios_external_aut_xctestrun(patrol_host_dir=host, patrol_output="")
        return driver.build_ios_external_aut_driver_artifact_binding(source=source, patrol_host_dir=host, device_id=device["id"])
    raw = artifacts.collect_tested_app_artifact_binding(device=device,
        patrol_command=["external-aut-native-driver", "--package-name", driver.PATROL_ANDROID_DRIVER_APPLICATION_ID],
        command_env=context["environment"], artifact_path=host / "build/app/outputs/apk/androidTest/debug/app-debug-androidTest.apk",
        host_source=context["source"], android_adb=context["adb"])
    comparison = artifacts.validate_tested_app_artifact_binding(raw)
    return _driver_artifact_envelope(platform="android", device_id=device["id"],
        driver_application_id=driver.PATROL_ANDROID_DRIVER_APPLICATION_ID,
        test_host_application_id=driver.PATROL_ANDROID_HOST_APPLICATION_ID,
        artifact_kind="android_test_apk_installed_readback", artifact_digest=comparison["artifactDigest"],
        evidence={"testedDriverArtifactBinding": raw})


def _execute_native_page(*, plan: Mapping[str, Any], launch: Mapping[str, Any],
                         context: Mapping[str, Any], case_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    from quwoquan_ops.cli.smoke.environment_patrol_smoke.external_aut_driver_artifact import _ios_runner_configuration
    validate_page_plan(plan)
    screenshot_path = case_dir / "screenshot.png"
    if screenshot_path.exists() or screenshot_path.is_symlink():
        raise ValueError("APP.UAT.page_artifact_binding_missing: native screenshot path must be fresh")
    encoded = base64.b64encode(json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).decode()
    temporary: Path | None = None
    environment = dict(context["environment"])
    try:
        if launch["platform"] == "android":
            command = driver.android_external_aut_instrumentation_command(adb=context["adb"], device_id=launch["deviceId"],
                production_application_id=launch["applicationId"])
            command[command.index(driver.ANDROID_EXTERNAL_AUT_TEST_CLASS)] += "#" + ANDROID_PAGE_METHOD
            command[-1:-1] = ["-e", "qwqOfflinePagePlan", encoded]
        else:
            binding = context["binding"]
            temporary, _ = driver.materialize_ios_external_aut_xctestrun(source=Path(binding["evidence"]["xctestrunPath"]),
                production_application_id=launch["applicationId"], expected_source_digest=binding["evidence"]["xctestrunDigest"])
            payload = plistlib.loads(temporary.read_bytes())
            runner = _ios_runner_configuration(payload)
            runner["EnvironmentVariables"]["QWQ_OFFLINE_PAGE_PLAN"] = encoded
            temporary.write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_BINARY, sort_keys=True))
            command = driver.ios_external_aut_xcodebuild_command(xctestrun=temporary, device_id=launch["deviceId"])
            command[command.index(driver.IOS_EXTERNAL_AUT_ONLY_TESTING)] = "RunnerUITests/QWQProductionHomepageExternalAUTTests/" + IOS_PAGE_METHOD
            command.extend(["-parallel-testing-enabled", "NO", "-maximum-concurrent-test-simulator-destinations", "1"])
        log_path = case_dir / "native.log"
        result = _run_native_command(command, cwd=context["host"], environment=environment, log_path=log_path)
        output = log_path.read_text(encoding="utf-8")
        # am instrument 的 shell exit=0 不代表 JUnit 通过；必须观察本次单方法终态。
        if launch["platform"] == "android" and (
                re.search(r"\bOK \(1 test\)", output) is None
                or "INSTRUMENTATION_CODE: -1" not in output
                or re.search(r"FAILURES!!!|INSTRUMENTATION_FAILED|Process crashed", output)):
            raise ValueError("APP.UAT.page_artifact_binding_missing: Instrumentation did not finish one successful test")
        evidence = validate_native_page_result(output, plan=plan, launch=launch)
        screenshot = native_page_screenshot(output, evidence)
        with screenshot_path.open("xb") as destination:
            destination.write(screenshot)
        return evidence, result
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read_aut_binding(*, artifact: Path, launch: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    flag = "--package-name" if launch["platform"] == "android" else "--bundle-id"
    raw = artifacts.collect_tested_app_artifact_binding(device=context["device"],
        patrol_command=["external-aut", flag, launch["applicationId"]], command_env=context["environment"],
        artifact_path=artifact, host_source=context["source"], android_adb=context["adb"])
    comparison = artifacts.validate_tested_app_artifact_binding(raw)
    if any(comparison.get(key) != launch[key] for key in ("applicationId", "artifactDigest")):
        raise ValueError("APP.UAT.page_artifact_binding_missing: installed AUT identity drifted")
    return raw


def _validate_offline_launch_identity(*, args: argparse.Namespace, candidate: Mapping[str, Any],
                                      launch: Mapping[str, Any], projection: Mapping[str, Any]) -> str:
    if args.platform not in {"android", "ios-simulator"}:
        raise ValueError("APP.LAUNCH.receipt_invalid: unsupported rehearsal platform")
    platform = "android" if args.platform == "android" else "ios"
    driver.external_aut_canonical_binding_projection(launch, platform=platform, device_id=args.device_id,
        environment="alpha", target="alpha-local")
    if (launch.get("contentSource") != "bundled_snapshot" or launch["candidateDigest"] != candidate["candidateId"]
            or launch["sourceGitSha"] != candidate["commit"] or projection["candidateDigest"] != candidate["candidateId"]
            or projection["sourceRevision"] != candidate["commit"]):
        raise ValueError("APP.LAUNCH.receipt_invalid: offline candidate/source identity drifted")
    return platform


def _write_offline_run_bindings(*, candidate: Mapping[str, Any], launch: Mapping[str, Any],
                                root: Path, context: Mapping[str, Any], report_dir: Path,
                                output_root: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    """启动与 driver 的事实只封存一次；后续页面仍逐次回读实际制品。"""
    native_binding_ref = _reference(write_create_once_json(report_dir / "native-driver-binding.json", context["binding"]), output_root)
    receipt["nativeDriverBindingRef"] = native_binding_ref
    snapshot_ref = _copy_evidence(root / "quwoquan_app/assets/content/alpha/manifest.json", report_dir / "snapshot.json", output_root)
    attempt_path = Path(launch["launchAttemptRef"])
    if document_digest(json.loads(attempt_path.read_bytes())) != launch["launchAttemptDigest"]:
        raise ValueError("APP.LAUNCH.receipt_invalid: exact launch attempt drifted")
    attempt_ref = _copy_evidence(attempt_path, report_dir / "launch-attempt.json", output_root)
    launch_ref = _reference(write_create_once_json(report_dir / "launch-binding.json", launch), output_root)
    binding = build_offline_target_uat_binding(candidate_digest=candidate["candidateId"], commit_sha=candidate["commit"],
        tree_sha=candidate["tree"], runtime_config_digest=launch["runtimeConfigPackageDigest"], snapshot=snapshot_ref,
        launch_attempt=attempt_ref, artifact={"class": "production_behavior", "digest": launch["artifactDigest"],
        "applicationId": launch["applicationId"], "buildMode": "debug", "buildProfile": "nonprod"},
        platform=launch["platform"], device={"identity": launch["deviceId"], "class": "emulator" if launch["platform"] == "android" else "simulator", "registered": False},
        runner={"identity": RUNNER_IDENTITY, "sourcePath": RUNNER_SOURCE, "digest": _file_digest(root / RUNNER_SOURCE), "registered": False},
        created_at=datetime.now(timezone.utc).isoformat())
    stored = write_create_once_target_uat_binding(output_root=output_root, binding=binding)
    receipt["targetUatBindingRefs"] = {"alpha-local": {"ref": stored.ref, "digest": stored.digest}}
    receipt["launchBindingRef"] = launch_ref
    return binding


def _collect_offline_page_evidence(*, plan: Mapping[str, Any], launch: Mapping[str, Any],
                                   projection: Mapping[str, Any], artifact: Path, context: Mapping[str, Any],
                                   device: dict[str, Any], case_dir: Path, output_root: Path,
                                   receipt: Mapping[str, Any]) -> tuple[dict[str, str], str]:
    plan_ref = _reference(write_create_once_json(case_dir / "plan.json", plan), output_root)
    started = datetime.now(timezone.utc).isoformat()
    before = _read_aut_binding(artifact=artifact, launch=launch, context=context)
    native, command = _execute_native_page(plan=plan, launch=launch, context=context, case_dir=case_dir)
    screenshot_path = case_dir / "screenshot.png"
    if _file_digest(screenshot_path) != native["screenshotDigest"]:
        raise ValueError("APP.UAT.page_artifact_binding_missing: native screenshot artifact drifted")
    after = _read_aut_binding(artifact=artifact, launch=launch, context=context)
    if _read_driver_binding(context) != context["binding"]:
        raise ValueError("APP.UAT.page_artifact_binding_missing: native driver artifact drifted")
    _verify_driver_dependencies(context)
    _verify_page_projection(projection)
    native_ref = _reference(write_create_once_json(case_dir / "native-result.json", native), output_root)
    evidence_ref = _reference(write_create_once_json(case_dir / "evidence.json", {
        "plan": plan_ref, "nativeResult": native_ref, "nativeDriverBinding": receipt["nativeDriverBindingRef"],
        "launchBinding": receipt["launchBindingRef"], "targetUatBinding": receipt["targetUatBindingRefs"]["alpha-local"],
        "screenshot": _reference(screenshot_path, output_root), "log": _reference(case_dir / "native.log", output_root),
        "command": command, "autBefore": before, "autAfter": after,
    }), output_root)
    # raw schema 的 receiptRef 有 128 字符上界，长 run 路径不截断身份。
    evidence_ref = _copy_evidence(output_root / evidence_ref["ref"],
        output_root / "offline-pages" / (evidence_ref["digest"].removeprefix("sha256:") + ".json"), output_root)
    return evidence_ref, started


def _write_offline_case_result(*, plan: Mapping[str, Any], candidate: Mapping[str, Any], launch: Mapping[str, Any],
                               binding: Mapping[str, Any], evidence_ref: Mapping[str, str], started: str,
                               case_dir: Path, output_root: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    completed = datetime.now(timezone.utc).isoformat()
    raw = {"objectId": "app_runtime", "specRef": OFFLINE_SPEC_REF, "caseId": plan["caseId"],
        "producer": "app", "layer": "user_acceptance", "status": "passed", "contentSource": "bundled_snapshot",
        "target": {"kind": "page", "id": plan["route"]}, "commitSha": candidate["commit"],
        "contractGraphSourceHash": launch["contractGraphDigest"].removeprefix("sha256:"),
        "deploymentTarget": "alpha-local", "environment": "alpha", "startedAt": started, "completedAt": completed,
        "runnerIdentity": RUNNER_IDENTITY, "artifactSha256": launch["artifactDigest"].removeprefix("sha256:"),
        "receiptRef": evidence_ref["ref"],
        "candidateDigest": candidate["candidateId"], "targetUatBindingDigest": receipt["targetUatBindingRefs"]["alpha-local"]["digest"],
        "platform": launch["platform"], "deviceIdentity": launch["deviceId"], "deviceRegistered": False,
        "deviceClass": binding["device"]["class"], "uatProfile": "rehearsal", "nonPromotable": True,
        "physicalDevice": False, "artifactClass": "production_behavior", "carrier": plan["carrier"],
        "entrySurface": "feed" if plan["caseId"] in {"default-entry", "homepage-recommendation", "empty-state", "pagination-end"} else "direct_or_object_route",
        "observedOutcome": offline_case_outcome(plan["caseId"])}
    raw_ref = _reference(write_readiness_case_result(case_dir / "result.json", raw, generated_at=completed), output_root)
    slot = launch["platform"] + ":" + plan["caseId"]
    receipt["rawResultRefs"]["alpha-local"].append({"slotId": slot, "ref": raw_ref["ref"]})
    receipt["rawResultDigests"]["alpha-local"].append({"slotId": slot, "digest": raw_ref["digest"]})
    receipt["pageResultRefs"].append({"slotId": slot, "result": raw_ref, "evidence": evidence_ref})
    receipt["runs"].append({"caseId": plan["caseId"], "platform": launch["platform"], "exitCode": 0, "evidence": evidence_ref})
    return raw


def _close_offline_page_resources(owned: ExitStack, receipt: dict[str, Any]) -> None:
    from quwoquan_ops.cli.commands.app_preflight_uat_offline import first_typed_blocker
    try:
        owned.close()
    except (OSError, RuntimeError, ValueError) as error:
        # 释放自己的锁失败不能覆盖本次页面执行的首个 typed blocker。
        receipt.update(status="gate_block", exitCode=2,
            firstBlocker=receipt["firstBlocker"] or first_typed_blocker(error),
            details=[*receipt["details"], str(error)], summary="Offline page resource cleanup is GATE_BLOCK")


def execute_offline_page_cases(*, args: argparse.Namespace, candidate: Mapping[str, Any], launch: Mapping[str, Any],
                               projection: Mapping[str, Any], report_dir: Path, output_root: Path) -> dict[str, Any]:
    """单平台 13 格；所有 ref 均 output_root 相对，rawResultRefs 可直接交 acceptance。

    对象边界是设备解析、制品 readback 与原生命令；无 test-only execution 分支。
    失败保留已产出的 raw refs 与第一个 typed blocker，不制造剩余用例的 PASS。
    """
    from quwoquan_ops.cli.commands.app_preflight_uat_offline import first_typed_blocker
    receipt: dict[str, Any] = {"status": "gate_block", "exitCode": 2, "firstBlocker": "", "details": [],
        "rawResultRefs": {"alpha-local": []}, "rawResultDigests": {"alpha-local": []},
        "targetUatBindingRefs": {}, "pageResultRefs": [], "runs": [],
        "rawCoverage": {"alpha-local": {"expected": len(OFFLINE_REQUIRED_CASES), "present": 0, "missing": len(OFFLINE_REQUIRED_CASES)}}}
    results: list[dict[str, Any]] = []
    owned = ExitStack()
    try:
        platform = _validate_offline_launch_identity(args=args, candidate=candidate, launch=launch, projection=projection)
        _verify_page_projection(projection)
        owned.enter_context(_acquire_page_device_lock(args.device_id, launch["applicationId"]))
        root = Path(projection["sourceProjectionRoot"])
        app_root = root / "quwoquan_app"
        artifact = app_root / ("build/app/outputs/flutter-apk/app-nonprod-debug.apk" if platform == "android" else "build/ios/iphonesimulator/Runner.app")
        snapshot = read_artifact_snapshot(artifact=artifact, platform=platform, expected_artifact_digest=launch["artifactDigest"], app_root=app_root)
        plans = build_offline_page_plans(snapshot=snapshot, app_root=app_root, launch=launch)
        if tuple(plan["caseId"] for plan in plans) != OFFLINE_REQUIRED_CASES:
            raise ValueError("APP.UAT.page_plan_invalid: required cases drifted")
        device = _device(args)
        report_dir.mkdir(parents=True, exist_ok=True)
        context = _prepare_native_driver(args=args, projection=projection, launch=launch, artifact=artifact,
                                         report_dir=report_dir, output_root=output_root, device=device)
        binding = _write_offline_run_bindings(candidate=candidate, launch=launch, root=root, context=context,
            report_dir=report_dir, output_root=output_root, receipt=receipt)
        for plan in plans:
            case_dir = report_dir / "pages" / plan["caseId"]
            evidence_ref, started = _collect_offline_page_evidence(plan=plan, launch=launch, projection=projection,
                artifact=artifact, context=context, device=device, case_dir=case_dir, output_root=output_root, receipt=receipt)
            raw = _write_offline_case_result(plan=plan, candidate=candidate, launch=launch, binding=binding,
                evidence_ref=evidence_ref, started=started, case_dir=case_dir, output_root=output_root, receipt=receipt)
            results.append(raw)
        validate_offline_page_coverage(results=results, bindings=[binding], candidate=candidate, platforms=[platform])
        receipt.update(status="passed", exitCode=0, summary="Offline native page cases passed for " + platform)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as error:
        receipt.update(firstBlocker=first_typed_blocker(error), details=[str(error)], summary="Offline native page cases are GATE_BLOCK")
    finally:
        _close_offline_page_resources(owned, receipt)
    present = len(results)
    receipt["rawCoverage"]["alpha-local"].update(present=present, missing=len(OFFLINE_REQUIRED_CASES) - present)
    return receipt
