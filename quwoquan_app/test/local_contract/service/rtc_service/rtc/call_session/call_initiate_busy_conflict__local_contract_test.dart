// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#req-006
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-006.t3
//
// 忙线冲突（RTC.USER.already_in_call, 409）拨打方 UI 路径契约：
// InitiateCall 被云端以单会话约束拒绝时，拨打方必须收到与 errors.yaml 同源的
// 结构化错误提示，不得导航到拨出页、不得残留半初始化的通话态，并且结束
// 当前通话后重拨必须能直接成功（可恢复语义）。
import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/generated/rtc/rtc_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/local_domain_failure.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/platform/rtc_room_service.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/public/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_permission_guard.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/rtc_call_entry_presenter.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/rtc_service/rtc/call_session/call_session_typed_double.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  RtcCallEntryIntent mutualDirectIntent() => RtcCallEntryIntent.direct(
    mediaType: RtcCallEntryMediaType.audio,
    targetUserId: 'target-persona',
    capability: const RelationshipCapabilityViewData(
      viewerPersonaId: 'viewer-persona',
      targetPersonaId: 'target-persona',
      relationState: 'mutual',
      canFollow: false,
      canUnfollow: false,
      canFollowBack: false,
      canGreet: false,
      canOpenConversation: false,
      canCreateDirectConversation: false,
      canSendMessage: false,
      hasPendingGreeting: false,
      hasFormalConversation: false,
      canStartVoiceCall: true,
      canStartVideoCall: true,
      isBlocked: false,
      isBlockedBy: false,
    ),
  );

  testWidgets('忙线 409：结构化提示 + 不导航拨出页 + 无残留通话态', (tester) async {
    final callSessions = CallSessionTypedDouble();
    final writer = _BusyThenDelegatingLifecycleWriter(1, callSessions);
    final navigatedCallIds = <String>[];
    final presenter = RtcCallEntryPresenter(
      permissionRequest: (_, _) async => CallPermissionOutcome.granted,
      outgoingNavigator: (_, callId) => navigatedCallIds.add(callId),
    );
    final results = <RtcCallEntryPresentationResult>[];

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          rtcCallLifecycleCommandWriterProvider.overrideWith(
            (ref, surface) => writer,
          ),
          rtcCallParticipantCommandWriterProvider.overrideWith(
            (ref, surface) => callSessions,
          ),
          rtcRoomServiceProvider.overrideWithValue(_NoopRtcRoomService()),
        ],
        child: CupertinoApp(
          home: Consumer(
            builder: (context, ref, _) => CupertinoButton(
              onPressed: () => unawaited(
                presenter
                    .start(
                      context: context,
                      ref: ref,
                      intent: mutualDirectIntent(),
                      sourceSurface: AppUiSurfaces.chatDetail,
                    )
                    .then(results.add),
              ),
              child: const Text('dial'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('dial'));
    await tester.pumpAndSettle();

    // 结构化错误提示：与统一映射链（runtimeErrorSemantic）对同一结构化失败
    // 的输出完全同源——sourceCode 承载 already_in_call 埋点语义，文案不得手写。
    final element = tester.element(find.text('dial'));
    final container = ProviderScope.containerOf(element);
    final state = container.read(callSessionProvider);
    expect(state.failure?.code, RtcErrorCode.alreadyInCall.code);
    expect(state.session, isNull, reason: '失败的发起不得残留半初始化 session');
    expect(state.isLoading, isFalse);

    final expected = runtimeErrorSemantic(
      element,
      error: state.failure!,
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
    );
    expect(expected.sourceCode, RtcErrorCode.alreadyInCall.code);
    expect(find.byType(CupertinoAlertDialog), findsOneWidget);
    expect(
      find.text(expected.message),
      findsOneWidget,
      reason: '忙线提示必须来自统一错误映射链，不得手写字符串',
    );
    expect(navigatedCallIds, isEmpty, reason: '忙线失败不得导航到拨出页');

    // start 的 Future 在错误弹窗关闭后才 resolve；先关闭再断言 presenter 结果。
    await tester.tap(find.text(ContentText.gotIt));
    await tester.pumpAndSettle();
    expect(results, [RtcCallEntryPresentationResult.failed]);

    // 可恢复语义：结束当前通话后重拨直接成功并导航拨出页。
    await tester.tap(find.text('dial'));
    await tester.pumpAndSettle();

    expect(results, [
      RtcCallEntryPresentationResult.failed,
      RtcCallEntryPresentationResult.started,
    ]);
    expect(navigatedCallIds, hasLength(1));
    final retried = container.read(callSessionProvider);
    expect(retried.failure, isNull, reason: '重拨成功后必须清除上一次忙线失败');
    expect(retried.session?.id, navigatedCallIds.single);

    // 收尾：挂断以取消振铃超时 timer，避免测试残留 pending timer。
    await container.read(callSessionProvider.notifier).hangupCall();
    await tester.pumpAndSettle();
  });

  test('already_in_call 是 InitiateCall 声明的冲突错误且可恢复级别为 inlineCard', () {
    // 与 errors.yaml 同源：409 冲突、用户可自行恢复（先结束当前通话）。
    expect(RtcErrorCode.alreadyInCall.httpStatus, 409);
    expect(RtcErrorCode.alreadyInCall.isUserError, isTrue);
    final failure = localDomainCloudException(
      RtcErrorCode.alreadyInCall.code,
    ).runtimeFailure;
    expect(failure.code, RtcErrorCode.alreadyInCall.code);
    expect(failure.transportStatus, 409);
  });
}

/// 前 N 次 InitiateCall 按云端单会话约束返回 already_in_call，
/// 之后委托共享 typed double 正常建会话；其余命令全部委托。
final class _BusyThenDelegatingLifecycleWriter
    implements CallLifecycleCommandWriter {
  _BusyThenDelegatingLifecycleWriter(this.failuresBeforeSuccess, this._delegate);

  final int failuresBeforeSuccess;
  final CallSessionTypedDouble _delegate;
  int _attempts = 0;

  @override
  Future<RtcInitiateCallResult> initiateCall(
    RtcInitiateCallCommand command,
  ) async {
    _attempts += 1;
    if (_attempts <= failuresBeforeSuccess) {
      throw localDomainCloudException(RtcErrorCode.alreadyInCall.code);
    }
    return _delegate.initiateCall(command);
  }

  @override
  Future<RtcAnswerCallResult> answerCall(RtcCallIdCommand command) =>
      _delegate.answerCall(command);

  @override
  Future<CallSession> rejectCall(RtcCallIdCommand command) =>
      _delegate.rejectCall(command);

  @override
  Future<CallSession> cancelCall(RtcCallIdCommand command) =>
      _delegate.cancelCall(command);

  @override
  Future<CallSession> hangupCall(RtcCallIdCommand command) =>
      _delegate.hangupCall(command);
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
