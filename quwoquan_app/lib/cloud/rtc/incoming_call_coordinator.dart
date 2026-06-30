import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/app_router_module.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/rtc/callkit_service.dart';
import 'package:quwoquan_app/cloud/rtc/models/rtc_signal_payloads.dart';
import 'package:quwoquan_app/cloud/rtc/rtc_signaling_client.dart';
import 'package:quwoquan_app/cloud/runtime/startup_deferred_plugins.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

final callKitServiceProvider = Provider<CallKitService>((ref) {
  final service = CallKitService();
  ref.onDispose(() => service.dispose());
  return service;
});

final rtcSignalingProvider = Provider<RtcSignalingClient>((ref) {
  final client = RtcSignalingClient();
  ref.onDispose(() => client.dispose());
  return client;
});

class IncomingCallCoordinator {
  IncomingCallCoordinator({required this.ref, required this.readRouter});

  final Ref ref;
  final GoRouter Function() readRouter;

  GoRouter get router => readRouter();

  StreamSubscription<RtcSignalEvent>? _signalSub;
  StreamSubscription<CallKitAction>? _callKitSub;
  StreamSubscription<RtcSignalEvent>? _endedSub;

  /// 启动时缓存信令客户端，避免在 [stop]/[dispose] 生命周期内再 `ref.read`
  /// （Riverpod 禁止在 dispose 回调里读取其它 provider）。
  RtcSignalingClient? _signaling;
  CallKitService? _callKit;
  int _startGeneration = 0;

  String? _pendingCallId;
  String? _pendingCallType;

  void start(String userId) {
    final channel = resolveIncomingCallChannel(
      ref.read(platformCapabilitiesProvider),
    );

    // 实时通话能力不可用（如初始 ohos / desktop）：不建立来电监听，由入口
    // 能力位隐藏发起按钮，二者一致降级（R-XP1/R-XP5）。
    if (channel == IncomingCallChannel.unsupported) {
      return;
    }

    final signaling = ref.read(rtcSignalingProvider);
    final callKit = channel == IncomingCallChannel.nativeCallKit
        ? ref.read(callKitServiceProvider)
        : null;
    final generation = ++_startGeneration;
    _signaling = signaling;
    _callKit = callKit;
    if (callKit != null) {
      unawaited(_startCallKitListening(callKit, generation));
    }

    signaling.connect(userId);

    _signalSub = signaling.incomingCalls.listen((event) {
      final wrap = event.payload as RtcCallRingingWsPayload;
      final ringing = wrap.data;
      _pendingCallId = event.callId;
      _pendingCallType = ringing.callType;
      final callerName =
          ringing.callerName ?? ringing.initiatorId ?? event.actorId ?? '';
      switch (channel) {
        case IncomingCallChannel.nativeCallKit:
          () async {
            final nativeCallKit = callKit;
            if (nativeCallKit == null) {
              router.push(AppRoutePaths.rtcIncoming(callId: event.callId));
              return;
            }
            await StartupDeferredPlugins.ensureRtcPlugins();
            nativeCallKit.startListening();
            final settings = await ref
                .read(callSettingsRepositoryProvider)
                .getCallSettings();
            final initiatorRingtoneId = ringing.initiatorRingtoneId;
            final ringtoneId =
                settings.allowCallerRingtoneOverride &&
                    initiatorRingtoneId != null &&
                    initiatorRingtoneId.isNotEmpty
                ? initiatorRingtoneId
                : settings.defaultIncomingCallRingtoneId;
            final shown = await nativeCallKit.showIncomingCall(
              callId: event.callId,
              callerName: callerName,
              isVideo: _pendingCallType == 'video',
              ringtoneId: ringtoneId,
            );
            if (!shown) {
              router.push(AppRoutePaths.rtcIncoming(callId: event.callId));
            }
          }();
          break;
        case IncomingCallChannel.webPushInApp:
        case IncomingCallChannel.inAppOnly:
          // 无原生来电屏（web/前台或降级）：直接路由到站内来电页响铃。
          router.push(AppRoutePaths.rtcIncoming(callId: event.callId));
          break;
        case IncomingCallChannel.unsupported:
          break;
      }
    });

    if (callKit != null) {
      _callKitSub = callKit.actions.listen((action) {
        final callId = _pendingCallId;
        if (callId == null) return;

        switch (action) {
          case CallKitAction.accept:
            router.push(AppRoutePaths.rtcIncoming(callId: callId));
            break;
          case CallKitAction.decline:
            _pendingCallId = null;
            _pendingCallType = null;
            break;
          case CallKitAction.end:
            _pendingCallId = null;
            _pendingCallType = null;
            break;
          case CallKitAction.timeout:
            _pendingCallId = null;
            _pendingCallType = null;
            break;
        }
      });
    }

    _endedSub = signaling.callEnded.listen((event) {
      if (event.callId == _pendingCallId) {
        callKit?.endCall();
        _pendingCallId = null;
      }
    });
  }

  Future<void> _startCallKitListening(
    CallKitService callKit,
    int generation,
  ) async {
    await StartupDeferredPlugins.ensureRtcPlugins();
    if (_startGeneration != generation || _callKit != callKit) {
      return;
    }
    callKit.startListening();
  }

  void stop() {
    _startGeneration += 1;
    _signalSub?.cancel();
    _signalSub = null;
    _callKitSub?.cancel();
    _callKitSub = null;
    _endedSub?.cancel();
    _endedSub = null;
    _callKit?.stopListening();
    _callKit = null;
    _signaling?.disconnect();
    _signaling = null;
    _pendingCallId = null;
    _pendingCallType = null;
  }

  void dispose() {
    stop();
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
  );
  ref.onDispose(() => coordinator.dispose());
  return coordinator;
});
