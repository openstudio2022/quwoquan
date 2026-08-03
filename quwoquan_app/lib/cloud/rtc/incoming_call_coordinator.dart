import 'dart:async';
import 'dart:collection';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/app_router_module.dart';
import 'package:quwoquan_app/app/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/rtc/call_session/incoming_call_presentation_acknowledger.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/cloud/rtc/models/rtc_signal_payloads.dart';
import 'package:quwoquan_app/cloud/rtc/rtc_signal_events.dart';
import 'package:quwoquan_app/core/platform/firebase_incoming_call_runtime.dart';
import 'package:quwoquan_app/core/platform/callkit_service.dart';
import 'package:quwoquan_app/core/platform/incoming_call_envelope.dart';
import 'package:quwoquan_app/core/platform/incoming_call_native_bridge.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final callKitServiceProvider = Provider<CallKitService>((ref) {
  final service = CallKitService(
    nativeBridge: ref.watch(incomingCallNativeBridgeProvider),
  );
  ref.onDispose(() => service.dispose());
  return service;
});

final incomingCallDeliveryDedupeProvider = Provider<BoundedIncomingCallDedupe>(
  (ref) => BoundedIncomingCallDedupe(),
);

class IncomingCallCoordinator {
  IncomingCallCoordinator({
    required this.ref,
    required this.readRouter,
    required this.firebaseRuntime,
    required this.nativeBridge,
  });

  final Ref ref;
  final GoRouter Function() readRouter;
  final FirebaseIncomingCallRuntime firebaseRuntime;
  final IncomingCallNativeBridge nativeBridge;

  GoRouter get router => readRouter();

  StreamSubscription<RtcSignalEvent>? _signalSub;
  StreamSubscription<CallKitActionEvent>? _callKitSub;
  StreamSubscription<RtcSignalEvent>? _endedSub;
  StreamSubscription<RtcSignalEvent>? _answeredSub;
  StreamSubscription<IncomingCallEnvelope>? _foregroundPushSub;
  StreamSubscription<IncomingCallPushEnvelope>? _foregroundCancelSub;

  CallKitService? _callKit;
  int _startGeneration = 0;
  String _boundPersonaId = '';
  final Map<String, IncomingCallEnvelope> _pendingByCallId =
      <String, IncomingCallEnvelope>{};
  final Set<String> _actionDedupe = <String>{};
  final Queue<String> _actionDedupeOrder = Queue<String>();

  void start(String personaId) {
    final normalizedPersonaId = personaId.trim();
    if (normalizedPersonaId.isEmpty) {
      return;
    }
    final channel = resolveIncomingCallChannel(
      ref.read(platformCapabilitiesProvider),
    );

    // 实时通话能力不可用（如初始 ohos / desktop）：不建立来电监听，由入口
    // 能力位隐藏发起按钮，二者一致降级（R-XP1/R-XP5）。
    if (channel == IncomingCallChannel.unsupported) {
      return;
    }
    _boundPersonaId = normalizedPersonaId;

    // 来电事件经 realtime 单通道（rt:rtc:user）由 RealtimeMessageHandler
    // 投递到事件总线；不再维护独立信令 WebSocket。
    final signals = ref.read(rtcSignalEventBusProvider);
    final callKit = channel == IncomingCallChannel.nativeCallKit
        ? ref.read(callKitServiceProvider)
        : null;
    final generation = ++_startGeneration;
    _callKit = callKit;
    if (callKit != null) {
      // CallKit 已是 startup-critical；这里只订阅事件，不再等待 RTC media 插件组。
      callKit.startListening();
      _callKitSub = callKit.actions.listen((event) {
        unawaited(_handleCallKitAction(event));
      });
      unawaited(_consumeNativeState(generation, channel));
    }
    unawaited(_startPushEndpointSync(generation, channel));

    _signalSub = signals.incomingCalls.listen((event) {
      final wrap = event.payload as RtcCallRingingWsPayload;
      final ringing = wrap.data;
      final initiatorId = event.actorId?.trim() ?? '';
      final callerName = ringing.callerName?.trim().isNotEmpty == true
          ? ringing.callerName!.trim()
          : (initiatorId.isEmpty ? '' : initiatorId);
      final targetPersonaId = ringing.targetPersonaId?.trim() ?? '';
      final sourceLabel = ringing.sourceLabel?.trim() ?? '';
      final trustRelation = ringing.trustRelation?.trim() ?? '';
      final expiresAt = DateTime.tryParse(ringing.expiresAt ?? '')?.toUtc();
      final deliveryKey = ringing.deliveryKey?.trim().isNotEmpty == true
          ? ringing.deliveryKey!.trim()
          : (ringing.eventId?.trim() ?? '');
      if (targetPersonaId != _boundPersonaId ||
          sourceLabel.isEmpty ||
          trustRelation.isEmpty ||
          expiresAt == null ||
          deliveryKey.isEmpty) {
        return;
      }
      late final IncomingCallEnvelope envelope;
      try {
        envelope = IncomingCallEnvelope(
          callId: ringing.callId ?? event.callId,
          deliveryKey: deliveryKey,
          targetPersonaId: targetPersonaId,
          callType: ringing.callType.wireName,
          callerName: callerName,
          sourceLabel: sourceLabel,
          trustRelation: trustRelation,
          expiresAt: expiresAt,
          callerPersonaId: initiatorId.isEmpty ? null : initiatorId,
        );
      } on FormatException {
        return;
      }
      unawaited(
        _present(
          envelope,
          channel: channel,
          source: IncomingCallPresentationSource.realtime,
          alreadyPresentedByNative: false,
          callerAvatarUrl: ringing.callerAvatarUrl,
        ),
      );
    });

    _endedSub = signals.callEnded.listen((event) {
      ref.read(incomingCallDeliveryDedupeProvider).suppressCallId(event.callId);
      unawaited(_closeNativeSurface(event.callId));
    });
    _answeredSub = signals.callAnswered.listen((event) {
      ref.read(incomingCallDeliveryDedupeProvider).suppressCallId(event.callId);
      unawaited(_closeNativeSurface(event.callId));
    });
  }

  Future<void> _consumeNativeState(
    int generation,
    IncomingCallChannel channel,
  ) async {
    final bridge = nativeBridge;
    await bridge.setFlutterReady(true);
    final envelopes = await bridge.readPendingEnvelopes();
    if (_startGeneration != generation) {
      return;
    }
    for (final envelope in envelopes) {
      if (envelope.targetPersonaId != _boundPersonaId) {
        await bridge.endNativeCall(envelope.callId);
        continue;
      }
      await _present(
        envelope,
        channel: channel,
        source: IncomingCallPresentationSource.nativePush,
        alreadyPresentedByNative: true,
      );
    }
    final actions = await bridge.consumePendingActions();
    if (_startGeneration != generation) {
      return;
    }
    for (final action in actions) {
      await _handleNativeAction(action);
    }
  }

  Future<void> _startPushEndpointSync(
    int generation,
    IncomingCallChannel channel,
  ) async {
    try {
      await _foregroundPushSub?.cancel();
      _foregroundPushSub = firebaseRuntime.foregroundIncomingCalls.listen((
        envelope,
      ) {
        if (envelope.targetPersonaId != _boundPersonaId) {
          return;
        }
        unawaited(
          _present(
            envelope,
            channel: channel,
            source: IncomingCallPresentationSource.nativePush,
            alreadyPresentedByNative: false,
          ),
        );
      });
      await _foregroundCancelSub?.cancel();
      _foregroundCancelSub = firebaseRuntime.foregroundCancellations.listen((
        push,
      ) {
        if (push.call.targetPersonaId != _boundPersonaId) {
          return;
        }
        ref.read(incomingCallDeliveryDedupeProvider).suppress(push.call);
        unawaited(_closeNativeSurface(push.call.callId));
      });
      await firebaseRuntime.start();
      if (_startGeneration != generation) {
        return;
      }
      await ref.read(devicePushEndpointCoordinatorProvider).syncAfterLogin();
    } catch (error, stack) {
      _reportAsyncFailure(
        error,
        stack,
        operationId:
            AppCloudOperationIds.userDeviceRegistrationUpsertDevicePushEndpoint,
      );
    }
  }

  Future<void> _removePushEndpointsForLogout() async {
    try {
      await ref.read(devicePushEndpointCoordinatorProvider).removeForLogout();
    } catch (error, stack) {
      _reportAsyncFailure(
        error,
        stack,
        operationId:
            AppCloudOperationIds.userDeviceRegistrationRemoveDevicePushEndpoint,
      );
    }
  }

  Future<void> _present(
    IncomingCallEnvelope envelope, {
    required IncomingCallChannel channel,
    required IncomingCallPresentationSource source,
    required bool alreadyPresentedByNative,
    String? callerAvatarUrl,
  }) async {
    if (source == IncomingCallPresentationSource.nativePush &&
        !await _isIncomingPresentationActive(envelope.callId)) {
      if (alreadyPresentedByNative) {
        await nativeBridge.endNativeCall(envelope.callId);
      }
      return;
    }
    final claim = ref.read(incomingCallDeliveryDedupeProvider).claim(envelope);
    switch (claim) {
      case IncomingCallClaimResult.expired:
        if (alreadyPresentedByNative) {
          await nativeBridge.endNativeCall(envelope.callId);
        }
        return;
      case IncomingCallClaimResult.duplicate:
        return;
      case IncomingCallClaimResult.accepted:
        break;
    }

    _pendingByCallId[envelope.callId] = envelope;
    ref
        .read(callSessionProvider.notifier)
        .seedIncomingCall(
          callId: envelope.callId,
          callType: envelope.callType,
          initiatorId: envelope.callerPersonaId ?? '',
          callerName: envelope.callerName,
          callerAvatarUrl: callerAvatarUrl,
          conversationId: null,
          sourceLabel: envelope.sourceLabel,
          trustRelation: envelope.trustRelation,
          expiresAt: envelope.expiresAt.toIso8601String(),
        );

    var presented = false;
    switch (channel) {
      case IncomingCallChannel.nativeCallKit:
        if (alreadyPresentedByNative) {
          presented = true;
          break;
        }
        final nativeCallKit = _callKit;
        if (nativeCallKit == null) {
          router.push(AppRoutePaths.rtcIncoming(callId: envelope.callId));
          presented = true;
          break;
        }
        final settings = await ref
            .read(userSettingsQueryReaderProvider)
            .getCallSettings();
        final ringtoneId = settings.defaultIncomingCallRingtoneId;
        final result = await nativeCallKit.showIncomingCall(
          envelope: envelope,
          ringtoneId: ringtoneId,
        );
        presented = result.presented;
        if (!presented) {
          router.push(AppRoutePaths.rtcIncoming(callId: envelope.callId));
          presented = true;
        }
      case IncomingCallChannel.webPushInApp:
      case IncomingCallChannel.inAppOnly:
        router.push(AppRoutePaths.rtcIncoming(callId: envelope.callId));
        presented = true;
      case IncomingCallChannel.unsupported:
        return;
    }

    if (presented) {
      await _acknowledgePresentation(envelope, source);
    }
  }

  Future<bool> _isIncomingPresentationActive(String callId) async {
    try {
      final session = await ref
          .read(rtcCallQueryProvider(AppUiSurfaces.rtcIncoming))
          .getCall(RtcGetCallQuery(callId: callId));
      return isIncomingPresentationActiveStatus(session.status);
    } catch (error, stack) {
      // Provider 临时不可用时保留系统来电面，避免网络故障直接造成漏接；后续
      // AnswerCall 仍由服务端状态机/CAS 拒绝已结束的通话。
      _reportAsyncFailure(
        error,
        stack,
        operationId: AppCloudOperationIds.rtcCallSessionGetCall,
      );
      return true;
    }
  }

  Future<void> _acknowledgePresentation(
    IncomingCallEnvelope envelope,
    IncomingCallPresentationSource source,
  ) async {
    try {
      await ref
          .read(incomingCallPresentationAcknowledgerProvider)
          .acknowledge(
            IncomingCallPresentationReceipt(
              callId: envelope.callId,
              deliveryKey: envelope.deliveryKey,
              source: source,
              presentedAt: DateTime.now().toUtc(),
            ),
          );
    } catch (error, stack) {
      _reportAsyncFailure(
        error,
        stack,
        operationId: AppCloudOperationIds
            .notificationNotificationDeliveryJobAckIncomingCallPresentation,
      );
    }
  }

  Future<void> _handleNativeAction(IncomingCallNativeAction action) {
    final mapped = switch (action.type) {
      IncomingCallNativeActionType.accept => CallKitAction.accept,
      IncomingCallNativeActionType.decline => CallKitAction.decline,
      IncomingCallNativeActionType.end => CallKitAction.end,
      IncomingCallNativeActionType.timeout => CallKitAction.timeout,
    };
    return _handleCallKitAction(
      CallKitActionEvent(callId: action.callId, action: mapped),
    );
  }

  Future<void> _handleCallKitAction(CallKitActionEvent event) async {
    final callId = event.callId.trim();
    final envelope = _pendingByCallId[callId];
    if (callId.isEmpty || envelope == null || !_claimAction(event)) {
      return;
    }
    switch (event.action) {
      case CallKitAction.accept:
        final notifier = ref.read(callSessionProvider.notifier);
        await notifier.answerCall(callId);
        final session = ref.read(callSessionProvider);
        if (session.failure != null || session.status == CallStatus.ended) {
          router.push(AppRoutePaths.rtcIncoming(callId: callId));
          return;
        }
        router.push(
          envelope.isVideo
              ? AppRoutePaths.rtcVideo(callId: callId)
              : AppRoutePaths.rtcVoice(callId: callId),
        );
      case CallKitAction.decline:
        await ref.read(callSessionProvider.notifier).rejectCall(callId);
        await _closeNativeSurface(callId);
      case CallKitAction.end:
        final state = ref.read(callSessionProvider);
        if (state.session?.id == callId &&
            (state.status == CallStatus.connecting ||
                state.status == CallStatus.inCall)) {
          await ref.read(callSessionProvider.notifier).hangupCall();
        } else {
          await ref.read(callSessionProvider.notifier).rejectCall(callId);
        }
        await _closeNativeSurface(callId);
      case CallKitAction.timeout:
        // no_answer 由服务端 CAS sweeper 形成唯一终态，客户端不把系统超时误写成 reject。
        await _closeNativeSurface(callId);
    }
  }

  bool _claimAction(CallKitActionEvent event) {
    final key = '${event.action.name}:${event.callId}';
    if (!_actionDedupe.add(key)) {
      return false;
    }
    _actionDedupeOrder.addLast(key);
    while (_actionDedupeOrder.length > 256) {
      _actionDedupe.remove(_actionDedupeOrder.removeFirst());
    }
    return true;
  }

  Future<void> _closeNativeSurface(String callId) async {
    _pendingByCallId.remove(callId);
    final callKit = _callKit;
    if (callKit != null) {
      await callKit.endCall(callId);
      return;
    }
    await nativeBridge.endNativeCall(callId);
  }

  void _reportAsyncFailure(
    Object error,
    StackTrace stackTrace, {
    required String operationId,
  }) {
    const surface = AppUiSurfaces.rtcIncoming;
    unawaited(
      AppExceptionTelemetryService.instance.recordHandledException(
        source: 'rtc.incoming_call_coordinator',
        error: error,
        stackTrace: stackTrace,
        pageId: surface.id,
        pageName: PageNames.rtcIncoming,
        surfaceId: surface.id,
        routeId: surface.routeId,
        operationId: operationId,
      ),
    );
  }

  void stop({bool removePushEndpoints = true}) {
    _startGeneration += 1;
    _signalSub?.cancel();
    _signalSub = null;
    _callKitSub?.cancel();
    _callKitSub = null;
    _endedSub?.cancel();
    _endedSub = null;
    _answeredSub?.cancel();
    _answeredSub = null;
    _foregroundPushSub?.cancel();
    _foregroundPushSub = null;
    _foregroundCancelSub?.cancel();
    _foregroundCancelSub = null;
    _callKit?.stopListening();
    _callKit = null;
    _pendingByCallId.clear();
    _actionDedupe.clear();
    _actionDedupeOrder.clear();
    _boundPersonaId = '';
    unawaited(firebaseRuntime.stop());
    unawaited(nativeBridge.setFlutterReady(false));
    if (removePushEndpoints) {
      unawaited(_removePushEndpointsForLogout());
    }
  }

  void dispose() {
    stop(removePushEndpoints: false);
  }
}

/// 登录态 -> 来电协调器目标动作。纯函数，便于在 widget 外做幂等性单测。
///
/// - [boundUserId] 当前已绑定用户（空串表示未启动）；
/// - [nextUserId] 期望绑定用户（登出为空串）。
///
/// 返回新的绑定用户与是否需要 stop 旧、start 新，shell 据此唯一地驱动协调器，
/// 杜绝重复 start（多次来电监听）与漏 stop（登出后仍响铃）。
IncomingCallSyncDecision resolveIncomingCallSync({
  required String boundUserId,
  required String nextUserId,
}) {
  if (boundUserId == nextUserId) {
    return IncomingCallSyncDecision(
      boundUserId: boundUserId,
      shouldStop: false,
      shouldStart: false,
    );
  }
  return IncomingCallSyncDecision(
    boundUserId: nextUserId,
    shouldStop: boundUserId.isNotEmpty,
    shouldStart: nextUserId.isNotEmpty,
  );
}

bool isIncomingPresentationActiveStatus(CallStatus status) =>
    status == CallStatus.initiated || status == CallStatus.ringing;

class IncomingCallSyncDecision {
  const IncomingCallSyncDecision({
    required this.boundUserId,
    required this.shouldStop,
    required this.shouldStart,
  });

  final String boundUserId;
  final bool shouldStop;
  final bool shouldStart;
}

/// 来电唤醒通道：由平台能力位单一派生，决定来电如何呈现。
enum IncomingCallChannel {
  /// 原生来电屏（iOS CallKit / Android 全屏意图）。
  nativeCallKit,

  /// Web Push + 站内弹窗（后台通知点击进会，前台站内响铃）。
  webPushInApp,

  /// 仅站内弹窗（有 RTC 但无原生来电屏，也无 Web Push 的降级）。
  inAppOnly,

  /// 不支持实时通话，无来电（入口同步隐藏）。
  unsupported,
}

/// 依据平台能力位派生来电唤醒通道（纯函数，便于平台矩阵单测）。
///
/// 业务只读能力位（[PlatformCapabilities.realtimeCommunication] /
/// [PlatformCapabilities.incomingCallUi] / [PlatformCapabilities.webPushIncomingCall]），
/// 不做裸平台判断（R-XP1/R-XP2）。
IncomingCallChannel resolveIncomingCallChannel(PlatformCapabilities caps) {
  if (!caps.realtimeCommunication) {
    return IncomingCallChannel.unsupported;
  }
  if (caps.incomingCallUi) {
    return IncomingCallChannel.nativeCallKit;
  }
  if (caps.webPushIncomingCall) {
    return IncomingCallChannel.webPushInApp;
  }
  return IncomingCallChannel.inAppOnly;
}

final incomingCallRouterReaderProvider = Provider<GoRouter Function()>((ref) {
  return () {
    assert(
      isAppRouterLibraryLoaded,
      'Call ensureAppRouterLibraryLoaded() before reading incoming call router',
    );
    return ref.read(deferredAppRouterProvider);
  };
});

final incomingCallCoordinatorProvider = Provider<IncomingCallCoordinator>((
  ref,
) {
  final coordinator = IncomingCallCoordinator(
    ref: ref,
    readRouter: ref.watch(incomingCallRouterReaderProvider),
    firebaseRuntime: ref.watch(firebaseIncomingCallRuntimeProvider),
    nativeBridge: ref.watch(incomingCallNativeBridgeProvider),
  );
  ref.onDispose(() => coordinator.dispose());
  return coordinator;
});
