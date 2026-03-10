import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/rtc/callkit_service.dart';
import 'package:quwoquan_app/cloud/rtc/rtc_signaling_client.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

final callKitServiceProvider = Provider<CallKitService>((ref) {
  final service = CallKitService();
  service.startListening();
  ref.onDispose(() => service.dispose());
  return service;
});

final rtcSignalingProvider = Provider<RtcSignalingClient>((ref) {
  final client = RtcSignalingClient();
  ref.onDispose(() => client.dispose());
  return client;
});

class IncomingCallCoordinator {
  IncomingCallCoordinator({required this.ref, required this.router});

  final Ref ref;
  final GoRouter router;

  StreamSubscription<RtcSignalEvent>? _signalSub;
  StreamSubscription<CallKitAction>? _callKitSub;

  String? _pendingCallId;
  String? _pendingCallType;

  void start(String userId) {
    final signaling = ref.read(rtcSignalingProvider);
    final callKit = ref.read(callKitServiceProvider);

    signaling.connect(userId);

    _signalSub = signaling.incomingCalls.listen((event) {
      _pendingCallId = event.callId;
      _pendingCallType = event.payload['callType'] as String? ?? 'voice';
      final callerName =
          event.payload['callerName'] as String? ?? event.actorId ?? '';
      () async {
        final settings = await ref.read(callSettingsRepositoryProvider)
            .getCallSettings();
        final initiatorRingtoneId =
            event.payload['initiatorRingtoneId'] as String?;
        final ringtoneId = settings.allowCallerRingtoneOverride &&
                initiatorRingtoneId != null &&
                initiatorRingtoneId.isNotEmpty
            ? initiatorRingtoneId
            : settings.defaultIncomingCallRingtoneId;
        await callKit.showIncomingCall(
          callId: event.callId,
          callerName: callerName,
          isVideo: _pendingCallType == 'video',
          ringtoneId: ringtoneId,
        );
      }();
    });

    _callKitSub = callKit.actions.listen((action) {
      final callId = _pendingCallId;
      if (callId == null) return;

      switch (action) {
        case CallKitAction.accept:
          router.push('/rtc/incoming/$callId');
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

    signaling.callEnded.listen((event) {
      if (event.callId == _pendingCallId) {
        callKit.endCall();
        _pendingCallId = null;
      }
    });
  }

  void stop() {
    _signalSub?.cancel();
    _callKitSub?.cancel();
    ref.read(rtcSignalingProvider).disconnect();
    _pendingCallId = null;
  }

  void dispose() {
    stop();
  }
}

final incomingCallCoordinatorProvider = Provider<IncomingCallCoordinator>((
  ref,
) {
  final coordinator = IncomingCallCoordinator(
    ref: ref,
    router: ref.read(goRouterProvider),
  );
  ref.onDispose(() => coordinator.dispose());
  return coordinator;
});

final goRouterProvider = Provider<GoRouter>((ref) {
  throw UnimplementedError('goRouterProvider must be overridden');
});
