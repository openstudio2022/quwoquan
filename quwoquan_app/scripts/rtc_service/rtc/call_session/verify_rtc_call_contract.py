#!/usr/bin/env python3
"""RTC 通话商用契约静态门禁。

阻断回退回归：
1. 铃声第二真相源：设置页绕过 OfficialCallRingtoneCatalog 重新硬编码
   `official.*` 铃声 ID（曾导致选项与 CallKit 呈现资源脱钩、选择静默失效）。
2. 前后台保活补偿回退：CallSessionNotifier 丢失 realtime 通道恢复监听，
   通道断开期间错过的挂断/参与者事实无法在回前台后对齐。
3. 来电呈现旁路：CallKit 呈现不再经 OfficialCallRingtoneCatalog resolve。
4. 通话页动效第二套节奏：presentation 重新引入 Duration 字面量绕过
   CallSurfaceMotion token。
5. 证据链退化：RTC 商用关键 local_contract 测试被删除，或丢失指向
   realtime-call 规格的 spec_ref。
6. 屏幕常亮回退：ActiveCall 生命周期不再经 ScreenWakeGateway 取得/释放
   常亮（长通话屏幕熄灭）。
7. 音频会话回退：媒体建连不再激活 CallAudioSessionGateway 或收尾不释放
   （来电/其他 App 抢占音频后体验不可控）。
8. 无障碍语义回退：通话核心按钮丢失 Semantics 包装。
9. 通话中来电安全行为回退：coordinator 忙线分支被移除，第二来电重新
   篡夺活跃通话。
10. 计时/镜像第二真相源：presentation 重新自写 `_formatDuration`，或
    渲染侧绕过 shouldMirrorLocalPreview 各自判断镜像。
11. 结局遥测粒度回退：_reportCallOutcome 不再消费 endReason 事实。
12. 重建面回退：shell bindings 整对象 watch activeCallProvider（elapsed
    每秒 tick 整树重建 MainAppShell），或呼出页顶层 watch callTimerProvider
    （每秒整页重建）。
13. 终态反馈回退：ended 跳离前不再经 callEndedFeedbackText 提示超时/被拒。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import REPO_ROOT

ROOT = REPO_ROOT

CALL_SESSION_LIB = "quwoquan_app/lib/service/rtc_service/rtc/call_session"
CALL_SESSION_TESTS = (
    "quwoquan_app/test/local_contract/service/rtc_service/rtc/call_session"
)

# RTC 商用准出的关键行为测试：文件必须存在且绑定 realtime-call 规格锚点。
REQUIRED_TESTS = (
    f"{CALL_SESSION_TESTS}/call_initiate_busy_conflict__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/incoming_call_page_journey__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/call_signal_outage_recovery__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/call_media_controls_effectiveness__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/call_session_provider_lifecycle__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/call_session_signal_consume__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/rtc_call_entry_coordinator__functional__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/rtc_errors__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/call_screen_wake__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/call_controls_semantics__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/call_waiting_second_incoming__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/call_audio_session__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/call_outcome_telemetry__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/call_duration_format__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/local_preview_mirror__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/call_controls_sfu_chain__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/call_lifecycle_edge_cases__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/callkit_cold_start_pending__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/outgoing_call_page_rebuild__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/call_ended_timeout_feedback__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/call_invite_journey__local_contract_test.dart",
    f"{CALL_SESSION_TESTS}/video_grid_reflow__local_contract_test.dart",
)

# shell 重建面契约测试（runtime/shell 树内）。
SHELL_REBUILD_TEST = (
    "quwoquan_app/test/local_contract/runtime/shell/"
    "main_app_shell_bindings_rebuild__local_contract_test.dart"
)

DURATION_LITERAL_RE = re.compile(r"\bDuration\(")


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def main() -> int:
    errors: list[str] = []

    # 1. 铃声单一真相源：设置页只消费 OfficialCallRingtoneCatalog。
    settings_calls = read(
        "quwoquan_app/lib/service/user_service/account/user_settings/"
        "presentation/settings_calls_page.dart"
    )
    require(
        "OfficialCallRingtoneCatalog" in settings_calls,
        "settings_calls_page 必须消费 OfficialCallRingtoneCatalog 渲染铃声选项",
        errors,
    )
    require(
        not re.search(r"'official\.[a-z-]+'", settings_calls),
        "settings_calls_page 禁止硬编码 official.* 铃声 ID（catalog 是唯一真相源）",
        errors,
    )

    # 2. 信令通道恢复补偿：回前台/重连后必须从 CallQuery 对齐错过的事实。
    provider = read(f"{CALL_SESSION_LIB}/application/call_session_provider.dart")
    require(
        "realtimeConnectionManagerProvider" in provider
        and "TransportState.disconnected" in provider,
        "CallSessionNotifier 必须监听 realtime 通道恢复并触发 retryCurrentCall 补偿",
        errors,
    )
    require(
        "retryCurrentCall" in provider,
        "CallSessionNotifier 必须保留 retryCurrentCall 显式恢复入口",
        errors,
    )

    # 3. 来电呈现铃声 resolve 单轨。
    callkit = read("quwoquan_app/lib/runtime/platform/callkit_service.dart")
    require(
        "OfficialCallRingtoneCatalog.resolveCallkitPath" in callkit,
        "CallKit 呈现必须经 OfficialCallRingtoneCatalog resolve 铃声资源",
        errors,
    )

    # 4. 通话页动效节奏单一来源：presentation 禁止 Duration 字面量。
    presentation = ROOT / CALL_SESSION_LIB / "presentation"
    for dart in sorted(presentation.glob("*.dart")):
        text = dart.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("///"):
                continue
            if DURATION_LITERAL_RE.search(line):
                errors.append(
                    f"{dart.relative_to(ROOT)}:{line_no}: 通话页动效时长必须"
                    "复用 CallSurfaceMotion token，禁止 Duration 字面量"
                )

    # 5. 关键行为测试存在且绑定 realtime-call 规格。
    for rel in REQUIRED_TESTS:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"缺少 RTC 商用关键测试：{rel}")
            continue
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:12])
        require(
            "spec_ref:" in head and "realtime-call" in head,
            f"{rel}: 必须在文件头以 spec_ref 绑定 realtime-call 规格锚点",
            errors,
        )

    # 6. 屏幕常亮：ActiveCall 生命周期必须经 ScreenWakeGateway。
    active_call = read(f"{CALL_SESSION_LIB}/application/active_call_service.dart")
    require(
        active_call.count("screenWakeGatewayProvider") >= 3,
        "ActiveCallNotifier 必须在 startCall/endCall/onDispose 经 "
        "screenWakeGatewayProvider 取得与释放屏幕常亮",
        errors,
    )

    # 7. 音频会话：媒体建连激活、收尾释放、中断事实消费。
    runtime = read(
        f"{CALL_SESSION_LIB}/application/call_session_provider_runtime.dart"
    )
    require(
        "_activateCallAudioSession" in runtime
        and "callAudioSessionGatewayProvider" in runtime,
        "媒体建连后必须经 callAudioSessionGatewayProvider 激活通话音频会话",
        errors,
    )
    require(
        "_deactivateCallAudioSession" in runtime
        and "_deactivateCallAudioSession()" in runtime.split("_endCallState", 1)[1][:400],
        "_endCallState 必须释放通话音频会话",
        errors,
    )
    require(
        "CallAudioSessionEvent.interruptionBegan" in runtime
        and "CallAudioSessionEvent.interruptionEndedShouldResume" in runtime,
        "CallSessionNotifier 必须消费音频中断 began/endedShouldResume 事实",
        errors,
    )
    media_device = read(f"{CALL_SESSION_LIB}/application/media_device_provider.dart")
    require(
        "CallAudioSessionEvent.becameNoisy" in media_device,
        "MediaDeviceNotifier 必须消费 becomingNoisy 事实切回听筒",
        errors,
    )

    # 8. 无障碍语义：核心按钮必须有 Semantics 包装。
    for rel, min_count in (
        (f"{CALL_SESSION_LIB}/presentation/call_controls_bar.dart", 2),
        (f"{CALL_SESSION_LIB}/presentation/incoming_call_page.dart", 1),
        (f"{CALL_SESSION_LIB}/presentation/pip_call_overlay.dart", 1),
    ):
        require(
            read(rel).count("Semantics(") >= min_count,
            f"{rel}: 通话核心动作必须保留 Semantics 语义节点",
            errors,
        )

    # 9. 通话中来电安全行为：coordinator 忙线分支 + 通话页轻提示消费。
    coordinator = read(f"{CALL_SESSION_LIB}/application/incoming_call_coordinator.dart")
    require(
        "secondIncomingCallProvider" in coordinator
        and "busyWithAnotherCall" in coordinator,
        "IncomingCallCoordinator 必须保留忙线分支：第二来电不篡夺活跃通话，"
        "降级为 secondIncomingCallProvider 轻提示",
        errors,
    )
    for rel in (
        f"{CALL_SESSION_LIB}/presentation/voice_call_page.dart",
        f"{CALL_SESSION_LIB}/presentation/video_call_page.dart",
    ):
        require(
            "secondIncomingCallProvider" in read(rel),
            f"{rel}: 通话页必须消费第二来电轻提示状态",
            errors,
        )

    # 10. 计时与镜像单一真相源。
    for dart in sorted(presentation.glob("*.dart")):
        text = dart.read_text(encoding="utf-8")
        require(
            "_formatDuration" not in text,
            f"{dart.relative_to(ROOT)}: 禁止 presentation 自写 _formatDuration，"
            "必须消费 formatCallDuration",
            errors,
        )
    require(
        "formatCallDuration" in read(f"{CALL_SESSION_LIB}/presentation/active_call_bar.dart"),
        "ActiveCallBar 计时必须消费 formatCallDuration 单一真相源",
        errors,
    )
    require(
        "formatCallDuration" in read(f"{CALL_SESSION_LIB}/presentation/pip_call_overlay.dart"),
        "PiP 浮窗计时必须消费 formatCallDuration 单一真相源",
        errors,
    )
    for rel in (
        f"{CALL_SESSION_LIB}/presentation/participant_tile.dart",
        f"{CALL_SESSION_LIB}/presentation/pip_call_overlay.dart",
    ):
        require(
            "shouldMirrorLocalPreview" in read(rel),
            f"{rel}: 本地预览镜像必须消费 shouldMirrorLocalPreview 单一决策",
            errors,
        )

    # 11. 结局遥测粒度：_reportCallOutcome 必须消费 endReason 事实。
    require(
        "EndReason.rejected" in runtime and "EndReason.noAnswer" in runtime,
        "_reportCallOutcome 必须按 endReason 区分 rejected/no_answer 等结局，"
        "禁止回退到仅按本地 status 三分",
        errors,
    )

    # 12. 重建面：shell bindings 只允许 select 结构字段；呼出页计时必须隔离。
    shell_bindings = read(
        "quwoquan_app/lib/runtime/di/main_app_shell_dependencies.dart"
    )
    require(
        "activeCallProvider.select(" in shell_bindings,
        "mainAppShellBindingsProvider 必须以 select 订阅 activeCallProvider "
        "的结构字段（callId/callType）",
        errors,
    )
    require(
        not re.search(r"ref\.watch\(activeCallProvider\)(?!\.select)", shell_bindings),
        "mainAppShellBindingsProvider 禁止整对象 watch activeCallProvider"
        "（elapsed 每秒 tick 会整树重建 MainAppShell）",
        errors,
    )
    require(
        not re.search(r"ref\.watch\(callParticipantsProvider\)(?!\.)", shell_bindings),
        "shell bindings 禁止整对象 watch callParticipantsProvider；"
        "activeSpeaker 经局部 Consumer select 注入 PiP",
        errors,
    )
    outgoing = read(f"{CALL_SESSION_LIB}/presentation/outgoing_call_page.dart")
    require(
        not re.search(r"ref\.watch\(callTimerProvider\)", outgoing.split("class _OutgoingCallElapsedText", 1)[0]),
        "呼出页顶层禁止 watch callTimerProvider（每秒整页重建）；"
        "计时必须下沉到隔离子组件",
        errors,
    )
    require(
        "_OutgoingCallElapsedText" in outgoing,
        "呼出页必须保留 _OutgoingCallElapsedText 隔离计时子组件",
        errors,
    )
    shell_rebuild_test = ROOT / SHELL_REBUILD_TEST
    require(
        shell_rebuild_test.is_file()
        and "spec_ref:" in shell_rebuild_test.read_text(encoding="utf-8")[:400],
        f"缺少 shell 重建面契约测试：{SHELL_REBUILD_TEST}",
        errors,
    )

    # 13. 终态反馈：ended 跳离前必须经 callEndedFeedbackText 单一真相源。
    incoming = read(f"{CALL_SESSION_LIB}/presentation/incoming_call_page.dart")
    for rel, text in (
        (f"{CALL_SESSION_LIB}/presentation/outgoing_call_page.dart", outgoing),
        (f"{CALL_SESSION_LIB}/presentation/incoming_call_page.dart", incoming),
    ):
        require(
            "callEndedFeedbackText(" in text,
            f"{rel}: ended 跳离前必须经 callEndedFeedbackText 给出终态反馈",
            errors,
        )

    if errors:
        print("BLOCK: RTC 通话商用契约回归")
        for item in errors:
            print(f"- {item}")
        return 1
    print(
        "OK: RTC 通话商用契约一致（铃声单轨/通道恢复补偿/动效 token/常亮/"
        "音频会话/无障碍/通话中来电/计时镜像单轨/结局粒度/重建面/终态反馈/"
        "证据链完整）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
