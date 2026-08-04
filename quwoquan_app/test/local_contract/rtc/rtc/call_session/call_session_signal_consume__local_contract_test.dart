import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/application/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/app/shell/flows/pip_call_hangup_flow.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/application/rtc_signal_events.dart';
import 'package:quwoquan_app/core/platform/rtc_room_service.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/application/active_call_service.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/domain/call_state.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import '../../../../support/rtc/rtc/call_session/rtc_contract_test_builders.dart';

/// A4 契约：realtime 信令（call.ended / call.answered / screen_share.*）是
/// 会话状态的权威事实源；对端挂断/取消在任意阶段（含 connecting）都必须收尾，
/// 不再依赖 LiveKit 断连兜底。
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  CallSession session({
    String callId = 'call_signal_001',
    CallStatus status = CallStatus.inCall,
  }) {
    final now = DateTime.utc(2026, 7, 20);
    return buildCallSessionContract(
      id: callId,
      callType: CallType.audio,
      status: status,
      initiatorId: 'user_a',
      roomId: 'rtc-room-$callId',
      maxParticipants: 2,
      participantCount: 2,
      participants: <CallParticipant>[
        buildCallParticipantContract(
          userId: 'user_a',
          role: ParticipantRole.initiator,
          status: ParticipantStatus.connected,
        ),
        buildCallParticipantContract(
          userId: 'user_b',
          role: ParticipantRole.invitee,
          status: ParticipantStatus.connected,
        ),
      ],
      createdAt: now,
      updatedAt: now,
    );
  }

  (ProviderContainer, RtcSignalEventBus) createHarness({
    CallQuery? query,
    CallLifecycleCommandWriter? lifecycle,
    CallParticipantCommandWriter? participantWriter,
    CallMediaControlWriter? mediaWriter,
    CallScreenShareWriter? screenShareWriter,
    RtcRoomService? liveKit,
  }) {
    final container = ProviderContainer(
      overrides: [
        if (query != null)
          rtcCallQueryProvider.overrideWith((ref, surface) => query),
        if (lifecycle != null)
          rtcCallLifecycleCommandWriterProvider.overrideWith(
            (ref, surface) => lifecycle,
          ),
        if (participantWriter != null)
          rtcCallParticipantCommandWriterProvider.overrideWith(
            (ref, surface) => participantWriter,
          ),
        if (mediaWriter != null)
          rtcCallMediaControlWriterProvider.overrideWith(
            (ref, surface) => mediaWriter,
          ),
        if (screenShareWriter != null)
          rtcCallScreenShareWriterProvider.overrideWith(
            (ref, surface) => screenShareWriter,
          ),
        if (liveKit != null) rtcRoomServiceProvider.overrideWithValue(liveKit),
      ],
    );
    addTearDown(container.dispose);
    final bus = container.read(rtcSignalEventBusProvider);
    return (container, bus);
  }

  Future<void> pumpEventQueue() => Future<void>.delayed(Duration.zero);

  group('A4 callEnded 信令全阶段收尾', () {
    test('in_call 阶段对端挂断：状态收尾 + endReason 写入 + activeCall 清理', () async {
      final (container, bus) = createHarness();
      final notifier = container.read(callSessionProvider.notifier);
      notifier.loadFromSession(session());
      container
          .read(activeCallProvider.notifier)
          .startCall(callId: 'call_signal_001', callType: 'audio');

      bus.emitCanonicalFixture(<String, dynamic>{
        'type': 'call.ended',
        'callId': 'call_signal_001',
        'payload': <String, dynamic>{
          'callId': 'call_signal_001',
          'endReason': 'normal',
        },
      });
      await pumpEventQueue();

      final state = container.read(callSessionProvider);
      expect(state.status, CallStatus.ended);
      expect(state.session?.endReason, EndReason.normal);
      expect(container.read(activeCallProvider).isInCall, isFalse);
    });

    test('connecting 阶段对端取消：无媒体连接也必须收尾（悬挂修复）', () async {
      final (container, bus) = createHarness();
      final notifier = container.read(callSessionProvider.notifier);
      notifier.loadFromSession(session(status: CallStatus.connecting));
      expect(container.read(callSessionProvider).status, CallStatus.connecting);

      bus.emitCanonicalFixture(<String, dynamic>{
        'type': 'call.ended',
        'callId': 'call_signal_001',
        'payload': <String, dynamic>{
          'callId': 'call_signal_001',
          'endReason': 'cancelled',
        },
      });
      await pumpEventQueue();

      final state = container.read(callSessionProvider);
      expect(state.status, CallStatus.ended);
      expect(state.session?.endReason, EndReason.cancelled);
    });

    test('服务端 no_answer 超时信令映射到未接终态语义', () async {
      final (container, bus) = createHarness();
      container
          .read(callSessionProvider.notifier)
          .loadFromSession(session(status: CallStatus.ringing));

      bus.emitCanonicalFixture(<String, dynamic>{
        'type': 'call.ended',
        'callId': 'call_signal_001',
        'payload': <String, dynamic>{
          'callId': 'call_signal_001',
          'endReason': 'no_answer',
        },
      });
      await pumpEventQueue();

      final state = container.read(callSessionProvider);
      expect(state.status, CallStatus.ended);
      expect(state.session?.endReason, EndReason.noAnswer);
      expect(
        resolveCallStage(
          status: state.status,
          connectedPeerCount: 0,
          endReason: state.session?.endReason,
        ),
        CallStage.peerNoAnswer,
      );
    });

    test('无关 callId 的 ended 信令不影响当前会话', () async {
      final (container, bus) = createHarness();
      container.read(callSessionProvider.notifier).loadFromSession(session());

      bus.emitCanonicalFixture(<String, dynamic>{
        'type': 'call.ended',
        'callId': 'call_other_999',
        'payload': <String, dynamic>{
          'callId': 'call_other_999',
          'endReason': 'normal',
        },
      });
      await pumpEventQueue();

      expect(container.read(callSessionProvider).status, CallStatus.inCall);
    });

    testWidgets('客户端振铃截止只刷新服务端 no_answer，不误发 CancelCall', (tester) async {
      final lifecycle = _RecordingCallLifecycle();
      final participantWriter = _RecordingParticipantWriter(
        reportStatus: CallStatus.ringing,
      );
      final ended = session(
        status: CallStatus.ended,
      ).copyWith(endReason: EndReason.noAnswer);
      final query = _RecordingCallQuery(response: ended);
      final (container, _) = createHarness(
        lifecycle: lifecycle,
        participantWriter: participantWriter,
        query: query,
        liveKit: _ConnectedRtcRoomService(),
      );
      final notifier = container.read(callSessionProvider.notifier);

      await notifier.initiateCall(
        intent: RtcCallEntryIntent.conversation(
          mediaType: RtcCallEntryMediaType.audio,
          conversationId: 'conversation-timeout',
          participantCount: 2,
        ),
        selectedInviteeIds: const <String>['user_b'],
        sourceSurface: AppUiSurfaces.rtcVoice,
      );
      await tester.pump(const Duration(seconds: 35));
      await tester.pump();

      expect(lifecycle.cancelCount, 0);
      expect(query.requestedCallIds, <String>['call_signal_001']);
      expect(container.read(callSessionProvider).status, CallStatus.ended);
      expect(
        container.read(callSessionProvider).session?.endReason,
        EndReason.noAnswer,
      );
    });
  });

  group('A4 callAnswered 信令推进呼出方过程态', () {
    test('ringing 收到 call.answered：进入 connecting（对端已接听）', () async {
      final (container, bus) = createHarness();
      container
          .read(callSessionProvider.notifier)
          .loadFromSession(session(status: CallStatus.ringing));

      bus.emitCanonicalFixture(<String, dynamic>{
        'type': 'call.answered',
        'callId': 'call_signal_001',
        'actorId': 'user_b',
        'payload': <String, dynamic>{
          'callId': 'call_signal_001',
          'userId': 'user_b',
        },
      });
      await pumpEventQueue();

      expect(container.read(callSessionProvider).status, CallStatus.connecting);
    });

    test('in_call 阶段的 answered 信令不回退状态', () async {
      final (container, bus) = createHarness();
      container.read(callSessionProvider.notifier).loadFromSession(session());

      bus.emitCanonicalFixture(<String, dynamic>{
        'type': 'call.answered',
        'callId': 'call_signal_001',
        'payload': <String, dynamic>{'callId': 'call_signal_001'},
      });
      await pumpEventQueue();

      expect(container.read(callSessionProvider).status, CallStatus.inCall);
    });
  });

  group('A4 connected/participant 信令刷新聚合事实', () {
    test('call.connected 立即推进 in_call，并按 active callId 刷新一次', () async {
      final query = _RecordingCallQuery(
        response: session(
          status: CallStatus.inCall,
        ).copyWith(participantCount: 3),
      );
      final (container, bus) = createHarness(query: query);
      container
          .read(callSessionProvider.notifier)
          .loadFromSession(session(status: CallStatus.connecting));

      bus.emitCanonicalFixture(<String, dynamic>{
        'type': 'call.connected',
        'callId': 'call_signal_001',
        'payload': <String, dynamic>{
          'callId': 'call_signal_001',
          'userId': 'user_b',
          'participantCount': 3,
        },
      });
      await pumpEventQueue();
      await pumpEventQueue();

      expect(container.read(callSessionProvider).status, CallStatus.inCall);
      expect(query.requestedCallIds, <String>['call_signal_001']);
    });

    test('participant.joined/left 均刷新 roster，无关 callId 不触发查询', () async {
      final query = _RecordingCallQuery(response: session());
      final (container, bus) = createHarness(query: query);
      container.read(callSessionProvider.notifier).loadFromSession(session());

      for (final type in <String>['participant.joined', 'participant.left']) {
        bus.emitCanonicalFixture(<String, dynamic>{
          'type': type,
          'callId': 'call_signal_001',
          'payload': <String, dynamic>{
            'callId': 'call_signal_001',
            'userId': 'user_c',
            'participantCount': type.endsWith('joined') ? 3 : 2,
          },
        });
        await pumpEventQueue();
      }
      bus.emitCanonicalFixture(<String, dynamic>{
        'type': 'participant.joined',
        'callId': 'call_other_999',
        'payload': <String, dynamic>{
          'callId': 'call_other_999',
          'userId': 'user_z',
          'participantCount': 4,
        },
      });
      await pumpEventQueue();

      expect(query.requestedCallIds, <String>[
        'call_signal_001',
        'call_signal_001',
      ]);
    });
  });

  group('A4 screen_share 信令对齐会话共享事实', () {
    test('started/stopped 更新 session 共享状态与共享者', () async {
      final (container, bus) = createHarness();
      container.read(callSessionProvider.notifier).loadFromSession(session());

      bus.emitCanonicalFixture(<String, dynamic>{
        'type': 'screen_share.started',
        'callId': 'call_signal_001',
        'payload': <String, dynamic>{
          'callId': 'call_signal_001',
          'userId': 'user_b',
        },
      });
      await pumpEventQueue();
      var state = container.read(callSessionProvider);
      expect(state.session?.isScreenSharing, isTrue);
      expect(state.session?.screenShareUserId, 'user_b');
      expect(state.isLocalScreenSharing, isFalse);

      bus.emitCanonicalFixture(<String, dynamic>{
        'type': 'screen_share.stopped',
        'callId': 'call_signal_001',
        'payload': <String, dynamic>{
          'callId': 'call_signal_001',
          'userId': 'user_b',
        },
      });
      await pumpEventQueue();
      state = container.read(callSessionProvider);
      expect(state.session?.isScreenSharing, isFalse);
      expect(state.session?.screenShareUserId, isNull);
      expect(state.isLocalScreenSharing, isFalse);
    });

    test('控制入口同步调用 LiveKit 与 typed ScreenShare Facet', () async {
      final eventOrder = <String>[];
      final writer = _RecordingScreenShareWriter(events: eventOrder);
      final liveKit = _ScreenShareRtcRoomService(events: eventOrder);
      final (container, _) = createHarness(
        screenShareWriter: writer,
        liveKit: liveKit,
      );
      final notifier = container.read(callSessionProvider.notifier);
      notifier.loadFromSession(session().copyWith(callType: CallType.video));

      await notifier.startScreenShare();
      var state = container.read(callSessionProvider);
      expect(writer.startCount, 1);
      expect(liveKit.startCount, 1);
      expect(eventOrder.take(2), <String>['command.start', 'media.start']);
      expect(state.session?.isScreenSharing, isTrue);
      expect(state.isLocalScreenSharing, isTrue);

      await notifier.stopScreenShare();
      state = container.read(callSessionProvider);
      expect(writer.stopCount, 1);
      expect(liveKit.stopCount, 1);
      expect(state.session?.isScreenSharing, isFalse);
      expect(state.isLocalScreenSharing, isFalse);
    });

    test('LiveKit 发布失败会补偿已成功的聚合共享命令', () async {
      final eventOrder = <String>[];
      final writer = _RecordingScreenShareWriter(events: eventOrder);
      final liveKit = _ScreenShareRtcRoomService(
        events: eventOrder,
        shouldFailStart: true,
      );
      final (container, _) = createHarness(
        screenShareWriter: writer,
        liveKit: liveKit,
      );
      final notifier = container.read(callSessionProvider.notifier);
      notifier.loadFromSession(session().copyWith(callType: CallType.video));

      await notifier.startScreenShare();

      expect(eventOrder, <String>[
        'command.start',
        'media.start',
        'media.stop',
        'command.stop',
      ]);
      expect(liveKit.stopCount, 1);
      final state = container.read(callSessionProvider);
      expect(state.session?.isScreenSharing, isFalse);
      expect(state.session?.screenShareUserId, isNull);
      expect(state.isLocalScreenSharing, isFalse);
      expect(state.failure, isA<RuntimeFailureBase>());
    });
  });

  group('媒体控制隐私顺序与补偿', () {
    test('静音先停本地采集；聚合提交失败也不擅自重新开麦', () async {
      final events = <String>[];
      final mediaWriter = _RecordingMediaControlWriter(
        events: events,
        shouldFailMute: true,
      );
      final liveKit = _MediaControlRtcRoomService(events: events);
      final (container, _) = createHarness(
        mediaWriter: mediaWriter,
        liveKit: liveKit,
      );
      final notifier = container.read(callSessionProvider.notifier);
      notifier.loadFromSession(session());

      await notifier.toggleMute();

      expect(events, <String>['media.microphone:false', 'command.mute:true']);
      expect(container.read(callSessionProvider).isMuted, isTrue);
      expect(
        container.read(callSessionProvider).failure,
        isA<RuntimeFailureBase>(),
      );
    });

    test('开启摄像头先提交聚合；本地开启失败会关闭并补偿聚合', () async {
      final events = <String>[];
      final mediaWriter = _RecordingMediaControlWriter(events: events);
      final liveKit = _MediaControlRtcRoomService(events: events);
      final (container, _) = createHarness(
        mediaWriter: mediaWriter,
        liveKit: liveKit,
      );
      final notifier = container.read(callSessionProvider.notifier);
      notifier.loadFromSession(
        session().copyWith(callType: CallType.video, status: CallStatus.inCall),
      );

      await notifier.toggleCamera();
      expect(container.read(callSessionProvider).isCameraOn, isFalse);
      events.clear();
      liveKit.shouldFailCameraEnable = true;

      await notifier.toggleCamera();

      expect(events, <String>[
        'command.camera:true',
        'media.camera:true',
        'media.camera:false',
        'command.camera:false',
      ]);
      expect(container.read(callSessionProvider).isCameraOn, isFalse);
      expect(
        container.read(callSessionProvider).failure,
        isA<RuntimeFailureBase>(),
      );
    });
  });

  group('A3 PiP 挂断装配防回退', () {
    test('shell 等待 hangup 成功回执后才清 active call', () async {
      final command = Completer<CallSessionActionResult>();
      var clearCount = 0;

      final flow = runPipHangupFlow(
        hangup: () => command.future,
        clearActiveCall: () => clearCount++,
      );
      expect(clearCount, 0);

      command.complete(const CallSessionActionResult.succeeded());
      final result = await flow;
      expect(result.succeeded, isTrue);
      expect(clearCount, 1);
    });

    test('PiP 流程提交一次 HangupCall，成功后清理 active call', () async {
      final lifecycle = _RecordingCallLifecycle();
      final (container, _) = createHarness(lifecycle: lifecycle);
      container.read(callSessionProvider.notifier).loadFromSession(session());
      final activeCall = container.read(activeCallProvider.notifier);
      activeCall.startCall(callId: 'call_signal_001', callType: 'audio');

      final result = await runPipHangupFlow(
        hangup: () => container
            .read(callSessionProvider.notifier)
            .hangupCall(clearActiveCall: false),
        clearActiveCall: activeCall.endCall,
      );

      expect(result.succeeded, isTrue);
      expect(lifecycle.hangupCount, 1);
      expect(container.read(callSessionProvider).status, CallStatus.ended);
      expect(container.read(activeCallProvider).isInCall, isFalse);
    });

    test('hangup 失败保留 PiP/active call，不伪装成功', () async {
      final lifecycle = _RecordingCallLifecycle(shouldFailHangup: true);
      final (container, _) = createHarness(lifecycle: lifecycle);
      container.read(callSessionProvider.notifier).loadFromSession(session());
      container
          .read(activeCallProvider.notifier)
          .startCall(callId: 'call_signal_001', callType: 'audio');

      final result = await container
          .read(callSessionProvider.notifier)
          .hangupCall();

      expect(result.succeeded, isFalse);
      expect(result.failure, isA<RuntimeFailureBase>());
      expect(container.read(callSessionProvider).status, CallStatus.inCall);
      expect(container.read(callSessionProvider).failure, same(result.failure));
      expect(container.read(activeCallProvider).isInCall, isTrue);
    });

    test('cancel/reject 失败均保留权威会话，不能本地伪装 ended', () async {
      for (final action in <String>['cancel', 'reject']) {
        final lifecycle = _RecordingCallLifecycle(
          shouldFailCancel: action == 'cancel',
          shouldFailReject: action == 'reject',
        );
        final (container, _) = createHarness(lifecycle: lifecycle);
        final notifier = container.read(callSessionProvider.notifier);
        notifier.loadFromSession(session(status: CallStatus.ringing));
        container
            .read(activeCallProvider.notifier)
            .startCall(callId: 'call_signal_001', callType: 'audio');

        if (action == 'cancel') {
          await notifier.cancelCall();
        } else {
          await notifier.rejectCall('call_signal_001');
        }

        expect(
          container.read(callSessionProvider).status,
          CallStatus.ringing,
          reason: action,
        );
        expect(
          container.read(callSessionProvider).failure,
          isA<RuntimeFailureBase>(),
          reason: action,
        );
        expect(container.read(activeCallProvider).isInCall, isTrue);
      }
    });

    test('leave 失败保留通话与 active-call，允许用户重试', () async {
      final participantWriter = _RecordingParticipantWriter(
        shouldFailLeave: true,
      );
      final (container, _) = createHarness(
        participantWriter: participantWriter,
      );
      final notifier = container.read(callSessionProvider.notifier);
      notifier.loadFromSession(session());
      container
          .read(activeCallProvider.notifier)
          .startCall(callId: 'call_signal_001', callType: 'audio');

      await notifier.leaveCall();

      expect(container.read(callSessionProvider).status, CallStatus.inCall);
      expect(
        container.read(callSessionProvider).failure,
        isA<RuntimeFailureBase>(),
      );
      expect(container.read(activeCallProvider).isInCall, isTrue);
    });
  });

  group('ReportMediaConnected Facet 契约', () {
    test('CallParticipantCommandWriter 暴露 reportMediaConnected 能力', () {
      // Facet 契约存在性：Remote/Mock 都必须实现（Mock parity 由
      // alpha facets local_contract 覆盖）。
      expect(CallParticipantCommandWriter, isNotNull);
      final surface = AppUiSurfaces.rtcVoice;
      expect(surface.operationIds, contains('ReportMediaConnected'));
      expect(
        AppUiSurfaces.rtcVideo.operationIds,
        contains('ReportMediaConnected'),
      );
    });

    test('同一 call 首次 LiveKit connected 后只上报一次', () async {
      final lifecycle = _RecordingCallLifecycle();
      final participantWriter = _RecordingParticipantWriter();
      final (container, _) = createHarness(
        lifecycle: lifecycle,
        participantWriter: participantWriter,
        liveKit: _ConnectedRtcRoomService(),
      );
      final notifier = container.read(callSessionProvider.notifier);
      notifier.seedIncomingCall(
        callId: 'call_signal_001',
        callType: 'audio',
        initiatorId: 'user_a',
      );

      await notifier.answerCall('call_signal_001');
      await notifier.answerCall('call_signal_001');
      await pumpEventQueue();
      await pumpEventQueue();

      expect(participantWriter.reportedCallIds, <String>['call_signal_001']);
    });
  });
}

CallSession _fixtureSession({
  String callId = 'call_signal_001',
  CallStatus status = CallStatus.inCall,
}) {
  final now = DateTime.utc(2026, 7, 20);
  return buildCallSessionContract(
    id: callId,
    callType: CallType.audio,
    status: status,
    initiatorId: 'user_a',
    roomId: 'rtc-room-$callId',
    maxParticipants: 2,
    participantCount: 2,
    participants: <CallParticipant>[
      buildCallParticipantContract(
        userId: 'user_a',
        role: ParticipantRole.initiator,
        status: ParticipantStatus.connected,
      ),
      buildCallParticipantContract(
        userId: 'user_b',
        role: ParticipantRole.invitee,
        status: ParticipantStatus.connected,
      ),
    ],
    createdAt: now,
    updatedAt: now,
  );
}

final class _RecordingCallQuery implements CallQuery {
  _RecordingCallQuery({required this.response});

  final CallSession response;
  final List<String> requestedCallIds = <String>[];

  @override
  Future<CallSession> getCall(RtcGetCallQuery query) async {
    requestedCallIds.add(query.callId);
    return response;
  }

  @override
  Future<RtcCallHistoryPage> listCalls(RtcListCallsQuery query) =>
      throw UnimplementedError();
}

final class _RecordingCallLifecycle implements CallLifecycleCommandWriter {
  _RecordingCallLifecycle({
    this.shouldFailHangup = false,
    this.shouldFailCancel = false,
    this.shouldFailReject = false,
  });

  final bool shouldFailHangup;
  final bool shouldFailCancel;
  final bool shouldFailReject;
  int hangupCount = 0;
  int cancelCount = 0;

  @override
  Future<RtcAnswerCallResult> answerCall(RtcCallIdCommand command) async {
    return RtcAnswerCallResult(
      session: _fixtureSession(
        callId: command.callId,
        status: CallStatus.connecting,
      ),
      mediaAccess: const RtcMediaSessionAccess(
        accessToken: 'fixture-media-access',
      ),
    );
  }

  @override
  Future<CallSession> hangupCall(RtcCallIdCommand command) async {
    hangupCount += 1;
    if (shouldFailHangup) {
      throw StateError('fixture hangup failure');
    }
    return _fixtureSession(
      callId: command.callId,
      status: CallStatus.ended,
    ).copyWith(endReason: EndReason.normal);
  }

  @override
  Future<CallSession> cancelCall(RtcCallIdCommand command) async {
    cancelCount += 1;
    if (shouldFailCancel) {
      throw StateError('fixture cancel failure');
    }
    return _fixtureSession(
      callId: command.callId,
      status: CallStatus.ended,
    ).copyWith(endReason: EndReason.cancelled);
  }

  @override
  Future<RtcInitiateCallResult> initiateCall(
    RtcInitiateCallCommand command,
  ) async {
    return RtcInitiateCallResult(
      session: _fixtureSession(status: CallStatus.ringing).copyWith(
        callType: command.callType,
        conversationId: command.conversationId,
      ),
      mediaAccess: const RtcMediaSessionAccess(
        accessToken: 'fixture-media-access',
      ),
    );
  }

  @override
  Future<CallSession> rejectCall(RtcCallIdCommand command) async {
    if (shouldFailReject) {
      throw StateError('fixture reject failure');
    }
    return _fixtureSession(
      callId: command.callId,
      status: CallStatus.ended,
    ).copyWith(endReason: EndReason.rejected);
  }
}

final class _RecordingParticipantWriter
    implements CallParticipantCommandWriter {
  _RecordingParticipantWriter({
    this.shouldFailLeave = false,
    this.reportStatus = CallStatus.inCall,
  });

  final bool shouldFailLeave;
  final CallStatus reportStatus;
  final List<String> reportedCallIds = <String>[];

  @override
  Future<CallSession> reportMediaConnected(RtcCallIdCommand command) async {
    reportedCallIds.add(command.callId);
    return _fixtureSession(callId: command.callId, status: reportStatus);
  }

  @override
  Future<RtcJoinCredentials> joinCall(RtcCallIdCommand command) =>
      throw UnimplementedError();

  @override
  Future<CallSession> leaveCall(RtcCallIdCommand command) async {
    if (shouldFailLeave) {
      throw StateError('fixture leave failure');
    }
    return _fixtureSession(
      callId: command.callId,
      status: CallStatus.ended,
    ).copyWith(endReason: EndReason.lastLeave);
  }

  @override
  Future<CallSession> inviteToCall(RtcInviteToCallCommand command) =>
      throw UnimplementedError();
}

final class _ConnectedRtcRoomService extends RtcRoomService {
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

final class _RecordingMediaControlWriter implements CallMediaControlWriter {
  _RecordingMediaControlWriter({
    required this.events,
    this.shouldFailMute = false,
  });

  final List<String> events;
  bool shouldFailMute;

  @override
  Future<CallSession> toggleMute(RtcToggleMuteCommand command) async {
    events.add('command.mute:${command.muted}');
    if (shouldFailMute) {
      throw StateError('fixture mute command failure');
    }
    return _fixtureSession(callId: command.callId);
  }

  @override
  Future<CallSession> toggleCamera(RtcToggleCameraCommand command) async {
    events.add('command.camera:${command.cameraOn}');
    return _fixtureSession(
      callId: command.callId,
    ).copyWith(callType: CallType.video);
  }
}

final class _MediaControlRtcRoomService extends RtcRoomService {
  _MediaControlRtcRoomService({required this.events});

  final List<String> events;
  bool shouldFailMicrophoneEnable = false;
  bool shouldFailCameraEnable = false;

  @override
  Future<void> setMicrophoneEnabled(bool enabled) async {
    events.add('media.microphone:$enabled');
    if (enabled && shouldFailMicrophoneEnable) {
      throw StateError('fixture microphone enable failure');
    }
  }

  @override
  Future<void> setCameraEnabled(bool enabled) async {
    events.add('media.camera:$enabled');
    if (enabled && shouldFailCameraEnable) {
      throw StateError('fixture camera enable failure');
    }
  }

  @override
  Future<void> disconnect() async {}

  @override
  void dispose() {}
}

final class _RecordingScreenShareWriter implements CallScreenShareWriter {
  _RecordingScreenShareWriter({this.events});

  final List<String>? events;
  int startCount = 0;
  int stopCount = 0;

  @override
  Future<CallSession> startScreenShare(RtcCallIdCommand command) async {
    startCount += 1;
    events?.add('command.start');
    return _fixtureSession(callId: command.callId).copyWith(
      callType: CallType.video,
      isScreenSharing: true,
      screenShareUserId: 'user_b',
    );
  }

  @override
  Future<CallSession> stopScreenShare(RtcCallIdCommand command) async {
    stopCount += 1;
    events?.add('command.stop');
    return _fixtureSession(
      callId: command.callId,
    ).copyWith(callType: CallType.video);
  }
}

final class _ScreenShareRtcRoomService extends RtcRoomService {
  _ScreenShareRtcRoomService({this.events, this.shouldFailStart = false});

  final List<String>? events;
  final bool shouldFailStart;
  int startCount = 0;
  int stopCount = 0;

  @override
  Future<void> startScreenShare() async {
    startCount += 1;
    events?.add('media.start');
    if (shouldFailStart) {
      throw StateError('fixture screen-share publication failure');
    }
  }

  @override
  Future<void> stopScreenShare() async {
    stopCount += 1;
    events?.add('media.stop');
  }

  @override
  Future<void> disconnect() async {}

  @override
  void dispose() {}
}

extension on RtcSignalEventBus {
  void emitCanonicalFixture(Map<String, dynamic> event) {
    final payload = Map<String, Object?>.from(
      event['payload'] as Map<String, dynamic>,
    );
    emit(
      RealtimeEventEnvelope.fromWire(<String, Object?>{
        'type': event['type'],
        if (payload['eventId'] != null) 'eventId': payload['eventId'],
        'occurredAt': '2026-08-04T10:00:00Z',
        'payload': payload,
      }),
    );
  }
}
