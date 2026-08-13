// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-002
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-002.t1
//
// IncomingCallPage 接听/拒接完整交互 journey：
// 来电页首帧渲染 → 权限预检 → AnswerCall 进入通话页 / RejectCall 安全收尾。
// 断言消费真实 CallSessionNotifier 主链（非 override 状态机），页面导航与
// CallSession 命令效果必须一致。
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/platform/permissions/app_permission_coordinator.dart';
import 'package:quwoquan_app/runtime/platform/rtc_room_service.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_timer_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/incoming_call_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/rtc_service/rtc/call_session/call_session_typed_double.dart';

/// CallSessionTypedDouble 的 seed 中处于 ringing 的 1v1 语音来电。
const String _ringingCallId = '11111111-1111-4111-8111-111111111111';

class _NoopCallTimerNotifier extends CallTimerNotifier {
  @override
  CallTimerState build() => const CallTimerState();

  @override
  void start() {
    state = state.copyWith(isRunning: true);
  }

  @override
  void stop() {
    state = state.copyWith(isRunning: false);
  }

  @override
  void reset() {
    state = const CallTimerState();
  }
}

final class _NoopRtcRoomService extends RtcRoomService {
  @override
  Future<void> connect({
    required String accessToken,
    bool enableVideo = false,
    bool enableAudio = true,
  }) async {}

  @override
  Future<void> disconnect() async {}

  @override
  void dispose() {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late AppPermissionCoordinator permissions;

  setUp(() {
    permissions = AppPermissionCoordinator.createForTest();
    AppPermissionCoordinator.debugInstance = permissions;
    // 先 attach（触发 _registerDefaultAdapters），再注入测试 reader；
    // 顺序反了默认适配器会覆盖注入，权限判定静默走真实 permission_handler。
    permissions.ensureLifecycleAttached();
    permissions.phaseReaders[AppPermissionKind.microphone] = () async =>
        AppPermissionPhase.granted;
    permissions.grantCheckers[AppPermissionKind.microphone] = () async => true;
  });

  tearDown(() {
    WidgetsBinding.instance.removeObserver(permissions);
    AppPermissionCoordinator.debugInstance = null;
  });

  Future<GoRouter> pumpIncomingCallApp(
    WidgetTester tester, {
    required CallSessionTypedDouble callSessions,
  }) async {
    final router = GoRouter(
      initialLocation: AppRoutePaths.rtcIncoming(callId: _ringingCallId),
      routes: [
        GoRoute(
          path: AppRoutePaths.rtcIncomingPathTemplate.replaceFirst(
            '{callId}',
            ':callId',
          ),
          builder: (context, state) =>
              IncomingCallPage(callId: state.pathParameters['callId']!),
        ),
        GoRoute(
          path: AppRoutePaths.rtcVoicePathTemplate.replaceFirst(
            '{callId}',
            ':callId',
          ),
          builder: (context, state) =>
              const Center(child: Text('voice-call-stub')),
        ),
        GoRoute(
          path: AppRoutePaths.rtcVideoPathTemplate.replaceFirst(
            '{callId}',
            ':callId',
          ),
          builder: (context, state) =>
              const Center(child: Text('video-call-stub')),
        ),
        GoRoute(
          path: AppRoutePaths.chat,
          builder: (context, state) => const Center(child: Text('chat-stub')),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          rtcCallQueryProvider.overrideWith((ref, surface) => callSessions),
          rtcCallLifecycleCommandWriterProvider.overrideWith(
            (ref, surface) => callSessions,
          ),
          rtcCallParticipantCommandWriterProvider.overrideWith(
            (ref, surface) => callSessions,
          ),
          rtcRoomServiceProvider.overrideWithValue(_NoopRtcRoomService()),
          callTimerProvider.overrideWith(_NoopCallTimerNotifier.new),
        ],
        child: CupertinoApp.router(routerConfig: router),
      ),
    );
    // 首帧 + refreshIncomingCall（GetCall）回填。
    await tester.pump();
    await tester.pump();
    return router;
  }

  Future<void> drainAnimations(WidgetTester tester) async {
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 2));
  }

  testWidgets('来电页首帧渲染接听/拒接双动作并回填来电会话', (tester) async {
    final callSessions = CallSessionTypedDouble();
    await pumpIncomingCallApp(tester, callSessions: callSessions);

    expect(find.text(CallText.callAccept), findsOneWidget);
    expect(find.text(CallText.callReject), findsOneWidget);
    // GetCall 回填后 caller 身份可见（无 presentation 时回退 initiatorId）。
    expect(find.textContaining('fixture_user_friend'), findsWidgets);

    await drainAnimations(tester);
  });

  testWidgets('接听 journey：权限通过 → AnswerCall → 进入语音通话页', (tester) async {
    final callSessions = CallSessionTypedDouble();
    final router = await pumpIncomingCallApp(tester, callSessions: callSessions);

    await tester.tap(find.text(CallText.callAccept));
    // 权限预检 + AnswerCall + 状态监听导航，各推一帧。
    await tester.pump();
    await tester.pump();
    await tester.pump();

    final answered = await callSessions.getCall(
      RtcGetCallQuery(callId: _ringingCallId),
    );
    expect(answered.status, CallStatus.inCall, reason: '接听必须提交 AnswerCall');
    expect(
      router.state.uri.toString(),
      AppRoutePaths.rtcVoice(callId: _ringingCallId),
      reason: '语音来电接听后必须进入语音通话页',
    );
    expect(find.text('voice-call-stub'), findsOneWidget);

    await drainAnimations(tester);
  });

  testWidgets('拒接 journey：RejectCall → 会话 rejected 收尾 → 安全回到消息页', (
    tester,
  ) async {
    final callSessions = CallSessionTypedDouble();
    final router = await pumpIncomingCallApp(tester, callSessions: callSessions);

    await tester.tap(find.text(CallText.callReject));
    await tester.pump();
    await tester.pump();
    await tester.pump();

    final rejected = await callSessions.getCall(
      RtcGetCallQuery(callId: _ringingCallId),
    );
    expect(rejected.status, CallStatus.ended, reason: '拒接必须提交 RejectCall');
    expect(rejected.endReason, EndReason.rejected);
    expect(
      router.state.uri.toString(),
      AppRoutePaths.chat,
      reason: '无返回栈时拒接必须回到消息安全态，不得停留来电页',
    );
    expect(find.text('chat-stub'), findsOneWidget);

    await drainAnimations(tester);
  });

  testWidgets('麦克风权限不可用时接听被阻断且不提交 AnswerCall', (tester) async {
    permissions.phaseReaders[AppPermissionKind.microphone] = () async =>
        AppPermissionPhase.requestable;
    permissions.requesters[AppPermissionKind.microphone] = () async => false;
    permissions.grantCheckers[AppPermissionKind.microphone] = () async => false;

    final callSessions = CallSessionTypedDouble();
    final router = await pumpIncomingCallApp(tester, callSessions: callSessions);

    await tester.tap(find.text(CallText.callAccept));
    await tester.pump();
    await tester.pump();

    final unchanged = await callSessions.getCall(
      RtcGetCallQuery(callId: _ringingCallId),
    );
    expect(
      unchanged.status,
      CallStatus.ringing,
      reason: '权限被拒时不得提交 AnswerCall',
    );
    expect(
      router.state.uri.toString(),
      AppRoutePaths.rtcIncoming(callId: _ringingCallId),
      reason: '权限被拒时保持来电页，用户仍可拒接或重试',
    );

    // 权限软提示 toast 有 3s 自动关闭 timer，推进时钟让其到期。
    await tester.pump(const Duration(seconds: 4));
    await drainAnimations(tester);
  });
}
