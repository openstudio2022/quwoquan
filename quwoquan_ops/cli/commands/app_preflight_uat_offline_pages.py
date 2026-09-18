"""离线页面的实际制品、原生步骤与 canonical raw case 证据。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import plistlib
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from contextlib import ExitStack
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

from quwoquan_ops.cli.commands.app_preflight_uat_offline import (
    OFFLINE_REQUIRED_CASES, OFFLINE_SPEC_REF, offline_case_spec_ref, offline_case_blocker,
)
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
from quwoquan_ops.cli.lib.package_reuse.pub_cache_capsule import seal_lock_hosted_url
RUNNER_SOURCE = "quwoquan_ops/cli/commands/app_preflight_uat_offline_pages.py"
RUNNER_IDENTITY = "stackctl.offline-native-pages.v1"
ANDROID_PAGE_METHOD = "executesOfflinePageCaseInCanonicalProductionProcess"
IOS_PAGE_METHOD = "testExecutesOfflinePageCaseInCanonicalProductionProcess"


def ios_native_driver_xcodebuild_command(*, host: Path, device_id: str) -> list[str]:
    """把 products 钉在私有 derivedData，避免 Xcode 写到共享 DerivedData。"""
    derived = (Path(host) / "build/ios_integ").resolve()
    return [
        "xcodebuild", "build-for-testing",
        "-workspace", "ios/Runner.xcworkspace",
        "-scheme", "Runner",
        "-configuration", "Debug",
        "-sdk", "iphonesimulator",
        "-destination", "platform=iOS Simulator,id=" + device_id,
        "-derivedDataPath", str(derived),
        "SYMROOT=" + str(derived / "Build/Products"),
        "OBJROOT=" + str(derived / "Build/Intermediates.noindex"),
        "CODE_SIGNING_ALLOWED=NO",
    ]


from quwoquan_ops.cli.commands.app_preflight_uat_offline_page_validation import (
    _validate_identity_journey, _validate_native_result_identity, _validate_page_step,
    _validate_page_steps, _validate_playback_observation, _validate_step_observation,
    document_digest, native_page_screenshot,
    validate_native_page_result as _validate_native_page_result,
    validate_page_plan as _validate_page_plan,
)


def validate_page_plan(plan: Mapping[str, Any]) -> None:
    _validate_page_plan(plan, blocker=offline_case_blocker)


def require_executable_page_plan(plan: Mapping[str, Any]) -> None:
    validate_page_plan(plan)
    if plan["executionBlocker"]:
        raise ValueError(plan["executionBlocker"])


def validate_native_page_result(output: str, *, plan: Mapping[str, Any],
                                launch: Mapping[str, Any]) -> dict[str, Any]:
    return _validate_native_page_result(output, plan=plan, launch=launch, blocker=offline_case_blocker)


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
    if offline_case_blocker(str(result["caseId"])):
        raise ValueError("APP.UAT.page_artifact_binding_missing: unsupported required case cannot carry a passed result")
    expected = {
        "contentSource": "bundled_snapshot", "status": "passed", "specRef": offline_case_spec_ref(str(result["caseId"])),
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


def build_offline_page_plans(*, snapshot: Mapping[str, Any], app_root: Path,
                             launch: Mapping[str, Any], fresh_launch: bool = False) -> list[dict[str, Any]]:
    """用制品快照对象与已有页面文案/typed route 构造黑盒旅程，不创建用户。"""
    copies = "lib/l10n/copy/"
    def text(file: str, symbol: str) -> str:
        return _dart_text(app_root, copies + file + ".dart", symbol)
    def step(operation: str, selector: str) -> dict[str, str]:
        if operation == "input-otp":
            return {"operation": operation, "selector": selector, "sourceSelector": "alpha-rehearsal-confirm", "mode": "correct"}
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
    def post_after(kind: str, predecessor: Mapping[str, Any], channel: str = "recommend") -> Mapping[str, Any]:
        order = channels[channel]
        start = order.index(predecessor["postId"]) + 1
        selected = [posts[identity] for identity in order[start:] if posts[identity]["contentType"] == kind]
        if not selected:
            raise ValueError("APP.UAT.page_plan_invalid: snapshot lacks " + channel + "/" + kind + " after predecessor")
        return selected[0]
    article = post("article")
    # iOS reveal 只向下滑；generation-1 复用 AUT 时上一格停在文章卡。
    # 图/首页视频取文章之后的对象，避免再切「关注」（关注面没有「推荐」）。
    image, video = post_after("image", article), post("video", "premium")
    home_video = post_after("video", article)
    following = text("ui_text_constants_discovery", "homeTabFollowing")
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
    # 每例停留在观察终态供截图；下一例才恢复同一进程的导航状态。
    # 文章详情走 Work Browser 沉浸顶栏；正文在 pageflip 纹理上 ExcludeSemantics，
    # 不能再用 markdown excerpt 的 text-prefix 断言。
    cases = [
        ("default-entry", "homepage", route("home"), [visible(home)], []),
        ("homepage-recommendation", "homepage", route("home"),
         [*base, reveal(article["title"]), visible(article["title"])], []),
        ("premium-video-book", "video", route("videoBook"), open_video, exit_video),
        ("article-detail", "article", route("workBrowserPathTemplate", workId=article["postId"]),
         [*base, reveal(article["title"]), tap(article["title"]), visible("works-top-back")], [step("back", home)]),
        ("image-detail", "image", route("workBrowserPathTemplate", workId=image["postId"]),
         [*open_image, visible(success[1])], [step("back", home)]),
        ("homepage-video-playback", "video", route("workBrowserPathTemplate", workId=home_video["postId"]),
         [*base, reveal(home_video["title"]), tap(home_video["title"]), visible(progress), step("playback", progress)],
         [step("back", home)]),
        ("homepage-tab-roundtrip", "homepage", route("home"),
         [*base, visible(following), step("tab-roundtrip", recommend + "|" + following)], []),
        ("creator-avatar", "image", route("userProfilePathTemplate", userHandle=image["authorId"]),
         [*base, reveal("creator-avatar:" + image["authorId"]), tap("creator-avatar:" + image["authorId"]),
          visible("creator-profile-avatar:" + image["authorId"])], [step("back", home)]),
        ("video-complete", "video", route("videoBook"), [*open_video, step("playback", progress)], exit_video),
        ("video-seek", "video", route("videoBook"), [*open_video, step("seek", progress)], exit_video),
        ("empty-state", "homepage", route("home"), [*base, tap(empty_channel), visible(completed)], []),
        ("pagination-end", "homepage", route("home"), [*base, reveal(completed), visible(completed)], []),
        ("login-cancel", "homepage", route("home"),
         [tap(text("ui_text_constants_foundation", "bottomNavGuestProfile")),
          visible(text("ui_text_constants_foundation", "loginDismissSemanticLabel")),
          tap(text("ui_text_constants_foundation", "loginDismissSemanticLabel")),
          visible(home), visible(text("ui_text_constants_foundation", "bottomNavGuestProfile"))], []),
    ]
    # 全部 required 格都生成可执行计划；GWT-008 经 launcher-only relay 取 AUT snapshot，不由 runner 合成 actual。
    identity_entry = [tap(text("ui_text_constants_foundation", "bottomNavGuestProfile")), visible(text("ui_text_constants_foundation", "syntheticLoginTitle"))]
    login_success = [*identity_entry, tap(text("ui_text_constants_foundation", "syntheticLoginBegin")),
        step("input-otp", text("ui_text_constants_foundation", "syntheticLoginConfirmation")),
        tap(text("ui_text_constants_foundation", "syntheticLoginConfirm")), visible(text("app_concept_constants", "profile"))]
    cases.extend([
        ("login-success", "homepage", route("home"), login_success, []),
        ("login-error", "homepage", route("home"), [*identity_entry,
         tap(text("ui_text_constants_foundation", "syntheticLoginBegin")),
         {**step("input-otp", text("ui_text_constants_foundation", "syntheticLoginConfirmation")), "mode": "incorrect"},
         tap(text("ui_text_constants_foundation", "syntheticLoginConfirm")), visible(text("ui_text_constants_foundation", "syntheticLoginMismatch"))], []),
        ("private-continuation", "homepage", route("home"), [*login_success, tap("post-like:" + home_video["postId"]), visible("post-like:" + home_video["postId"])], []),
        ("local-write", "homepage", route("home"), [*base, reveal(home_video["title"]), tap("post-like:" + home_video["postId"]), visible("post-like:" + home_video["postId"])], []),
        ("otp-expiry", "homepage", route("home"), [*identity_entry, tap(text("ui_text_constants_foundation", "syntheticLoginBegin")),
         {"operation": "wait", "seconds": 300, "clock": "monotonic-real-time-no-adjustment"},
         step("input-otp", text("ui_text_constants_foundation", "syntheticLoginConfirmation")),
         tap(text("ui_text_constants_foundation", "syntheticLoginConfirm")), visible(text("ui_text_constants_foundation", "syntheticLoginUnavailable"))], []),
        ("identity-restart", "homepage", route("home"),
         [visible(home)] if int(launch.get("generation") or 1) >= 2 else
         [*login_success, {"operation": "restart", "mode": "cold-new-attempt"}, visible(home)], []),
    ])
    refusal_sources = {
        "network-refusal": "native-network-attempt", "otp-refusal": "native-otp-delivery-attempt",
        "push-refusal": "native-push-registration-attempt", "remote-refusal": "native-remote-transport-attempt",
        "outbox-refusal": "native-connected-outbox-attempt",
    }
    for case_id in OFFLINE_REQUIRED_CASES[len(cases):]:
        cases.append((case_id, "homepage", route("home"),
                      [{"operation": "observe", "selector": refusal_sources[case_id]}], []))
    plans: list[dict[str, Any]] = []
    restore: list[dict[str, str]] = []
    for case_id, carrier, route_path, steps, next_restore in cases:
        plan = {
            "schema": "quwoquan_ops.offline_page_case.v1", "caseId": case_id,
            "specRef": offline_case_spec_ref(case_id), "executionBlocker": offline_case_blocker(case_id),
            "candidateDigest": launch["candidateDigest"], "artifactDigest": launch["artifactDigest"],
            "deviceId": launch["deviceId"], "applicationId": launch["applicationId"],
            "canonicalProcessId": launch["canonicalProcessId"], "platform": launch["platform"],
            "launchAttemptId": launch["launchAttemptId"], "snapshotDigest": document_digest(snapshot),
            **{key: launch[key] for key in ("generation", "sessionId", "observationBinding") if key in launch},
            "route": route_path, "carrier": carrier, "steps": [*([] if fresh_launch else restore), *steps],
        }
        if case_id in {"login-success", "login-error", "private-continuation", "local-write", "otp-expiry", "identity-restart", "network-refusal", "otp-refusal", "push-refusal", "remote-refusal", "outbox-refusal"}:
            from quwoquan_ops.cli.commands.app_preflight_uat_offline_native_contract import build_native_case_contract
            plan["nativeContract"] = build_native_case_contract(case_id, plan)
        plan["planDigest"] = document_digest(plan)
        validate_page_plan(plan)
        plans.append(plan)
        restore = next_restore
    return plans


def _offline_pub_command_environment(
    environment: Mapping[str, str], *, lock_path: Path
) -> dict[str, str]:
    """Seal offline pub get to the lock's hosted cache namespace, not pub.dev."""

    return seal_lock_hosted_url(environment, lock_path=lock_path)


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


def _launch_between_page_locks(*, owned: ExitStack, device_id: str, application_id: str,
                               launch_case: Callable[[str, int], Mapping[str, Any]],
                               case_id: str, generation: int) -> Mapping[str, Any]:
    """先释放页锁供 launcher 独占；成功后重新获锁，再允许任何页面读写。"""
    owned.close()
    successor = launch_case(case_id, generation)
    owned.enter_context(_acquire_page_device_lock(device_id, application_id))
    if successor.get("deviceId") != device_id or successor.get("applicationId") != application_id:
        raise ValueError("APP.UAT.page_artifact_binding_missing: successor device/application drifted")
    return successor


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
    platform = device["targetPlatform"]
    if platform not in {"android", "ios"}:
        raise ValueError("APP.LAUNCH.receipt_invalid: native driver platform is unknown")
    with acquire_patrol_execution_lock(env_name="alpha", target="offline-native-pages", platforms=(platform,)):
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
        environment = _offline_pub_command_environment(environment, lock_path=host / "pubspec.lock")
        production_environment = _offline_pub_command_environment(
            dependencies.production_environment,
            lock_path=root / "quwoquan_app/pubspec.lock",
        )
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
                cwd=root / "quwoquan_app", environment=production_environment,
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
            commands.append(_run_native_command(
                ios_native_driver_xcodebuild_command(host=host, device_id=device["id"]),
                cwd=host, environment=environment, log_path=report_dir / "native-build.log", timeout=900))
        source = {"root": "quwoquan_app/test_host/patrol", "rootIdentityDigest": document_digest({"root": str(host)}),
                  "sourceDigest": native_projection["sourceProjectionDigest"], "sourceFileCount": native_projection["sourceProjectionFileCount"]}
        context = {"host": host, "environment": environment, "adb": adb, "source": source, "device": device,
                   "commands": commands, "expectation": expectation, "projection": native_projection}
        # relay secret/admission只在launcher进程内闭包捕获，不进入argv/env/file/log。
        from quwoquan_ops.cli.lib.external_uat_relay_transport import (
            AndroidAdbForwardRelayTransport, IosSimulatorAppGroupRelayTransport,
        )
        from quwoquan_ops.cli.commands.package_app_artifact_identity import signing_digest
        context["autSigningDigest"] = signing_digest(
            "android" if launch["platform"] == "android" else "ios", artifact)
        def relay_factory(*, plan, launch, session):
            token = session.admission["admissionDigest"].removeprefix("sha256:")[:24]
            if launch["platform"] == "android":
                return AndroidAdbForwardRelayTransport(
                    adb=adb, device_id=launch["deviceId"], local_socket="localabstract:qwq-launcher-" + token,
                    package_socket="qwq.gwt008." + launch["applicationId"])
            return IosSimulatorAppGroupRelayTransport(
                device_id=launch["deviceId"], app_group_id="group.com.leadwise.quwoquan.alpha.uat",
                socket_name=_verified_ios_socket_name(launch))
        context["relayFactory"] = relay_factory
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


def _verified_ios_socket_name(launch: Mapping[str, Any]) -> str:
    from quwoquan_app.scripts.device.startup_terminal_receipt import read_startup_terminal_receipt
    terminal = read_startup_terminal_receipt(Path(launch['startupTerminalEvidenceRef']),
        launch_attempt=json.loads(Path(launch['launchAttemptRef']).read_bytes()))
    native = terminal.get('nativeRendezvous')
    if (not isinstance(native, dict) or native != launch.get('nativeRendezvous')
            or native['launcherPid'] != os.getpid() or native['processId'] != launch['canonicalProcessId']
            or native['sessionId'] != launch.get('sessionId')):
        raise ValueError('APP.UAT.relay_admission_mismatch: exact native rendezvous readback drifted')
    return native['socketName']


def _relay_runtime(*, plan: Mapping[str, Any], launch: Mapping[str, Any], context: Mapping[str, Any],
                   terminal: Mapping[str, Any]):
    from quwoquan_ops.cli.commands.app_preflight_uat_offline_native_contract import (
        TerminalReference, admit_launch,
    )
    relay_factory = context.get("relayFactory")
    if not callable(relay_factory):
        raise ValueError("APP.UAT.relay_peer_rejected: launcher platform adapter is unavailable")
    if any(not launch.get(key) or launch.get(key) != plan["nativeContract"].get(key)
           for key in ("generation", "sessionId", "observationBinding")):
        raise ValueError("APP.UAT.relay_scope_mismatch: canonical launch lacks exact relay session/generation binding")
    lifecycle = str(launch.get("startupTerminalEvidenceDigest") or launch.get("launchAttemptDigest") or "")
    session = admit_launch(plan["nativeContract"], launch, signing_digest=str(context.get("autSigningDigest") or ""),
                           lifecycle_digest=lifecycle)
    return session, TerminalReference(terminal), relay_factory(plan=plan, launch=launch, session=session)


def _terminate_aut_process(*, launch: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    command = ([context["adb"], "-s", launch["deviceId"], "shell", "am", "kill", launch["applicationId"]]
               if launch["platform"] == "android" else
               ["xcrun", "simctl", "terminate", launch["deviceId"], launch["applicationId"]])
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
    if result.returncode != 0:
        raise ValueError("APP.UAT.teardown_pid_alive: canonical termination failed")


def _process_table_dead(*, launch: Mapping[str, Any]) -> bool:
    from quwoquan_ops.cli.commands.app_preflight_uat_process import (
        confirm_canonical_app_process_absent,
        confirm_host_process_table_absent,
    )
    if launch["platform"] in {"ios", "ios-simulator"}:
        return confirm_host_process_table_absent(process_id=int(launch["canonicalProcessId"]))
    return confirm_canonical_app_process_absent(
        platform=launch["platform"], device_id=launch["deviceId"],
        application_id=launch["applicationId"], expected_pid=int(launch["canonicalProcessId"]))


def _platform_lifecycle_dead(*, launch: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    from quwoquan_ops.cli.commands.app_preflight_uat_process import (
        confirm_android_lifecycle_absent,
        confirm_canonical_app_process_absent,
    )
    if launch["platform"] == "android":
        from quwoquan_ops.ci.device_matrix.android import resolve_android_debug_bridge
        return confirm_android_lifecycle_absent(
            device_id=launch["deviceId"], application_id=launch["applicationId"],
            expected_pid=int(launch["canonicalProcessId"]),
            adb_resolver=lambda: str(context.get("adb") or resolve_android_debug_bridge() or ""))
    return confirm_canonical_app_process_absent(
        platform=launch["platform"], device_id=launch["deviceId"],
        application_id=launch["applicationId"], expected_pid=int(launch["canonicalProcessId"]))


def _broker_peer_absent(*, transport: Any) -> bool:
    probe = getattr(transport, "peer_absent", None)
    if not callable(probe):
        raise ValueError("APP.UAT.relay_process_died: broker death probe is unavailable")
    try:
        absent = probe()
    except (BrokenPipeError, ConnectionError, EOFError, OSError, TimeoutError, ValueError) as error:
        raise ValueError("APP.UAT.teardown_pid_alive: broker readback failed") from error
    if absent is not True and absent is not False:
        raise ValueError("APP.UAT.teardown_pid_alive: broker readback is invalid")
    return absent


def _execute_native_page(*, plan: Mapping[str, Any], launch: Mapping[str, Any],
                         context: Mapping[str, Any], case_dir: Path,
                         consume_relay: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    from quwoquan_ops.cli.smoke.environment_patrol_smoke.external_aut_driver_artifact import _ios_runner_configuration
    require_executable_page_plan(plan)
    if any(plan.get(key) != launch.get(key) for key in (
            "candidateDigest", "artifactDigest", "deviceId", "applicationId", "canonicalProcessId", "platform", "launchAttemptId")):
        raise ValueError("APP.UAT.page_artifact_binding_missing: native input launch binding drifted")
    screenshot_path = case_dir / "screenshot.png"
    if screenshot_path.exists() or screenshot_path.is_symlink():
        raise ValueError("APP.UAT.page_artifact_binding_missing: native screenshot path must be fresh")
    encoded = base64.b64encode(json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).decode()
    temporary: Path | None = None
    environment = dict(context["environment"])
    relay_scope = None
    try:
        if "nativeContract" in plan and consume_relay:
            from quwoquan_ops.cli.commands.app_preflight_uat_offline_native_contract import arm_launcher_relay
            relay_scope = _relay_runtime(plan=plan, launch=launch, context=context, terminal={})
            arm_launcher_relay(session=relay_scope[0], transport=relay_scope[2])
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
        if "nativeContract" in plan and consume_relay:
            from quwoquan_ops.cli.commands.app_preflight_uat_offline_native_contract import execute_launcher_relay
            from quwoquan_ops.cli.commands.app_preflight_uat_offline_native_contract import TerminalReference
            session, _, transport = relay_scope
            terminal_ref = TerminalReference(evidence)
            comparison = execute_launcher_relay(
                session=session, plan=plan, terminal_ref=terminal_ref, transport=transport,
                expected=plan["nativeContract"]["expectedObservation"],
                timeout_seconds=float(plan["nativeContract"]["runnerTimeoutSeconds"]),
            )
            if comparison.get("status") != "passed":
                raise ValueError(str(comparison.get("errorCode") or "APP.UAT.relay_contract_drift"))
            result = {**result, "launcherComparison": comparison}
        screenshot = native_page_screenshot(output, evidence)
        with screenshot_path.open("xb") as destination:
            destination.write(screenshot)
        return evidence, result
    finally:
        if relay_scope is not None and not relay_scope[0].revoked:
            relay_scope[0].revoke()
            relay_scope[2].close()
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
                                   receipt: Mapping[str, Any],
                                   launch_case: Callable[[str, int], Mapping[str, Any]] | None = None) -> tuple[dict[str, str], str]:
    plan_ref = _reference(write_create_once_json(case_dir / "plan.json", plan), output_root)
    started = datetime.now(timezone.utc).isoformat()
    before = _read_aut_binding(artifact=artifact, launch=launch, context=context)
    after_launch = launch
    successor_refs: dict[str, Any] = {}
    if plan["caseId"] == "identity-restart":
        if launch_case is None:
            raise ValueError("APP.UAT.restart_identity_mismatch: canonical generation-2 launcher is unavailable")
        from quwoquan_ops.cli.commands.app_preflight_uat_offline_native_contract import (
            TerminalReference, arm_launcher_relay, supervise_identity_restart,
        )
        session1, _, transport1 = _relay_runtime(plan=plan, launch=launch, context=context, terminal={})
        arm_launcher_relay(session=session1, transport=transport1)
        native, command = _execute_native_page(plan=plan, launch=launch, context=context, case_dir=case_dir,
                                                consume_relay=False)
        def launch_next(case_id: str, generation: int) -> Mapping[str, Any]:
            nonlocal after_launch
            successor = dict(launch_case(case_id, generation))
            if successor.get("generation") != generation or successor.get("caseId") != case_id:
                raise ValueError("APP.UAT.restart_identity_mismatch: successor lifecycle binding missing")
            after_launch = successor
            successor["continuityDigest"] = document_digest({key: successor[key] for key in
                ("candidateDigest", "artifactDigest", "applicationId", "deviceId")})
            return successor
        def prepare_attempt2(successor: Mapping[str, Any]):
            second_dir = case_dir / "generation-2"
            second_dir.mkdir(parents=True, exist_ok=False)
            _read_aut_binding(artifact=artifact, launch=successor, context=context)
            attempt_path = Path(successor["launchAttemptRef"])
            if document_digest(json.loads(attempt_path.read_bytes())) != successor["launchAttemptDigest"]:
                raise ValueError("APP.UAT.restart_identity_mismatch: successor attempt digest drifted")
            successor_refs["launchBinding"] = _reference(write_create_once_json(second_dir / "launch-binding.json", successor), output_root)
            successor_refs["launchAttempt"] = _copy_evidence(attempt_path, second_dir / "launch-attempt.json", output_root)
            second_plans = build_offline_page_plans(snapshot=read_artifact_snapshot(
                artifact=artifact, platform="android" if successor["platform"] == "android" else "ios",
                expected_artifact_digest=successor["artifactDigest"], app_root=Path(projection["sourceProjectionRoot"]) / "quwoquan_app"),
                app_root=Path(projection["sourceProjectionRoot"]) / "quwoquan_app", launch=successor)
            selected = next(item for item in second_plans if item["caseId"] == "identity-restart")
            session, _, transport = _relay_runtime(plan=selected, launch=successor, context=context, terminal={})
            arm_launcher_relay(session=session, transport=transport)
            value, second_command = _execute_native_page(plan=selected, launch=successor, context=context,
                                            case_dir=second_dir, consume_relay=False)
            successor_refs.update(
                plan=_reference(write_create_once_json(second_dir / "plan.json", selected), output_root),
                nativeResult=_reference(write_create_once_json(second_dir / "native-result.json", value), output_root),
                screenshot=_reference(second_dir / "screenshot.png", output_root),
                log=_reference(second_dir / "native.log", output_root), command=second_command)
            return selected, session, TerminalReference(value), transport
        continuity = document_digest({key: launch[key] for key in
            ("candidateDigest", "artifactDigest", "applicationId", "deviceId")})
        supervision = supervise_identity_restart(
            attempt1_session=session1, attempt1_plan=plan, attempt1_terminal=TerminalReference(native),
            attempt1_transport=transport1, expected_attempt1=plan["nativeContract"]["expectedObservation"],
            terminate_aut=lambda admission: _terminate_aut_process(launch=launch, context=context),
            death_readbacks=[
                lambda: _process_table_dead(launch=launch),
                lambda: _platform_lifecycle_dead(launch=launch, context=context),
                lambda: _broker_peer_absent(transport=transport1),
            ],
            launch_next=launch_next, prepare_attempt2=prepare_attempt2,
            expected_attempt2=plan["nativeContract"]["expectedObservation"], continuity_digest=continuity)
        command = {**command, "launcherSupervision": supervision, "successorEvidence": successor_refs}
    else:
        native, command = _execute_native_page(plan=plan, launch=launch, context=context, case_dir=case_dir)
    screenshot_path = case_dir / "screenshot.png"
    if _file_digest(screenshot_path) != native["screenshotDigest"]:
        raise ValueError("APP.UAT.page_artifact_binding_missing: native screenshot artifact drifted")
    after = _read_aut_binding(artifact=artifact, launch=after_launch, context=context)
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
    require_executable_page_plan(plan)
    raw = {"objectId": "app_runtime", "specRef": plan["specRef"], "caseId": plan["caseId"],
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
        "entrySurface": "feed" if plan["caseId"] in {"default-entry", "homepage-recommendation", "homepage-video-playback", "homepage-tab-roundtrip", "image-detail", "empty-state", "pagination-end"} else "direct_or_object_route",
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
                               projection: Mapping[str, Any], report_dir: Path, output_root: Path,
                               launch_case: Callable[[str, int], Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """单平台 required 格；所有 ref 均 output_root 相对，rawResultRefs 可直接交 acceptance。

    对象边界是设备解析、制品 readback 与原生命令；无 test-only execution 分支。
    失败保留已产出的 raw refs 与第一个 typed blocker，不制造剩余用例的 PASS。
    """
    from quwoquan_ops.cli.commands.app_preflight_uat_offline import first_typed_blocker
    receipt: dict[str, Any] = {"status": "gate_block", "exitCode": 2, "firstBlocker": "", "details": [],
        "rawResultRefs": {"alpha-local": []}, "rawResultDigests": {"alpha-local": []},
        "targetUatBindingRefs": {}, "pageResultRefs": [], "runs": [],
        "rawCoverage": {"alpha-local": {"expected": len(OFFLINE_REQUIRED_CASES), "present": 0, "missing": len(OFFLINE_REQUIRED_CASES)}}}
    results: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    owned = ExitStack()
    def launch_unlocked(case_id: str, generation: int) -> Mapping[str, Any]:
        assert launch_case is not None
        successor = dict(_launch_between_page_locks(owned=owned, device_id=args.device_id,
            application_id=launch["applicationId"], launch_case=launch_case, case_id=case_id, generation=generation))
        _validate_offline_launch_identity(args=args, candidate=candidate, launch=successor, projection=projection)
        if successor.get("artifactDigest") != launch.get("artifactDigest"):
            raise ValueError("APP.UAT.page_artifact_binding_missing: successor artifact changed; fresh run required")
        return successor
    try:
        platform = _validate_offline_launch_identity(args=args, candidate=candidate, launch=launch, projection=projection)
        _verify_page_projection(projection)
        owned.enter_context(_acquire_page_device_lock(args.device_id, launch["applicationId"]))
        root = Path(projection["sourceProjectionRoot"])
        app_root = root / "quwoquan_app"
        artifact = app_root / ("build/app/outputs/flutter-apk/app-nonprod-debug.apk" if platform == "android" else "build/ios/iphonesimulator/Runner.app")
        snapshot = read_artifact_snapshot(artifact=artifact, platform=platform, expected_artifact_digest=launch["artifactDigest"], app_root=app_root)
        plans = build_offline_page_plans(snapshot=snapshot, app_root=app_root, launch=launch)
        from quwoquan_ops.cli.commands.app_preflight_uat_offline import selected_offline_cases
        selected = selected_offline_cases(args)
        diagnostic = getattr(args, "offline_cases", None) is not None
        if tuple(plan["caseId"] for plan in plans) != OFFLINE_REQUIRED_CASES:
            raise ValueError("APP.UAT.page_plan_invalid: required cases drifted")
        device = _device(args)
        report_dir.mkdir(parents=True, exist_ok=True)
        context = _prepare_native_driver(args=args, projection=projection, launch=launch, artifact=artifact,
                                         report_dir=report_dir, output_root=output_root, device=device)
        binding = _write_offline_run_bindings(candidate=candidate, launch=launch, root=root, context=context,
            report_dir=report_dir, output_root=output_root, receipt=receipt)
        receipt["blockedCases"] = [{"caseId": plan["caseId"], "specRef": plan["specRef"],
                                    "firstBlocker": plan["executionBlocker"]}
                                   for plan in plans if plan["executionBlocker"]]
        for seed_plan in plans:
            if seed_plan["caseId"] not in selected:
                continue
            if seed_plan["executionBlocker"]:
                continue
            case_id = seed_plan["caseId"]
            case_launch = launch
            # generation-1 复用 seed 制品后，native driver 只 Activate 同一 AUT。
            # iOS 会恢复上一格终态（视频书藏底栏），因此必须保留上一格 restore。
            # identity-restart 的 generation-2 仍经 launch_case 冷启动。
            case_plans = build_offline_page_plans(snapshot=snapshot, app_root=app_root, launch=case_launch,
                                                  fresh_launch=False)
            plan = next(item for item in case_plans if item["caseId"] == case_id)
            require_executable_page_plan(plan)
            case_dir = report_dir / "pages" / case_id
            case_receipt = dict(receipt)
            if launch_case is not None:
                binding = _write_offline_run_bindings(candidate=candidate, launch=case_launch, root=root,
                    context=context, report_dir=case_dir, output_root=output_root, receipt=case_receipt)
            if binding not in bindings:
                bindings.append(binding)
            evidence_ref, started = _collect_offline_page_evidence(plan=plan, launch=case_launch, projection=projection,
                artifact=artifact, context=context, device=device, case_dir=case_dir, output_root=output_root,
                receipt=case_receipt, launch_case=launch_unlocked if launch_case is not None else None)
            raw = _write_offline_case_result(plan=plan, candidate=candidate, launch=case_launch, binding=binding,
                evidence_ref=evidence_ref, started=started, case_dir=case_dir, output_root=output_root, receipt=case_receipt)
            results.append(raw)
        if diagnostic:
            if tuple(row["caseId"] for row in results) != selected:
                raise ValueError("APP.UAT.page_artifact_binding_missing: diagnostic selection is incomplete")
            by_id = _offline_binding_index(bindings, candidate)
            for row in results:
                _validate_offline_result_binding(row, binding=by_id[row["targetUatBindingDigest"]], candidate=candidate)
            receipt.update(status="diagnostic_passed", diagnostic=True, profile="diagnostic", selectedCases=list(selected),
                           exitCode=0, summary="Selected offline diagnostics passed; full acceptance remains incomplete")
        else:
            validate_offline_page_coverage(results=results, bindings=bindings, candidate=candidate, platforms=[platform])
            receipt.update(status="passed", exitCode=0, summary="Offline native page cases passed for " + platform)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as error:
        receipt.update(firstBlocker=first_typed_blocker(error), details=[str(error)], summary="Offline native page cases are GATE_BLOCK")
    finally:
        _close_offline_page_resources(owned, receipt)
    present = len(results)
    receipt["rawCoverage"]["alpha-local"].update(present=present, missing=len(OFFLINE_REQUIRED_CASES) - present)
    return receipt
