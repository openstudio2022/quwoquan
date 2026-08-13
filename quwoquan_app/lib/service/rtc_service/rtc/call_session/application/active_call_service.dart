import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_cloud_contracts/generated/rtc_contracts.dart'
    show CallParticipant;

class ActiveCallState {
  final String? callId;
  final String? callType;
  final bool isInCall;
  final bool isPipMode;
  final Duration elapsed;
  final List<CallParticipant> participants;

  const ActiveCallState({
    this.callId,
    this.callType,
    this.isInCall = false,
    this.isPipMode = false,
    this.elapsed = Duration.zero,
    this.participants = const [],
  });

  ActiveCallState copyWith({
    String? callId,
    String? callType,
    bool? isInCall,
    bool? isPipMode,
    Duration? elapsed,
    List<CallParticipant>? participants,
  }) {
    return ActiveCallState(
      callId: callId ?? this.callId,
      callType: callType ?? this.callType,
      isInCall: isInCall ?? this.isInCall,
      isPipMode: isPipMode ?? this.isPipMode,
      elapsed: elapsed ?? this.elapsed,
      participants: participants ?? this.participants,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ActiveCallState &&
          runtimeType == other.runtimeType &&
          callId == other.callId &&
          callType == other.callType &&
          isInCall == other.isInCall &&
          isPipMode == other.isPipMode &&
          elapsed == other.elapsed &&
          participants.length == other.participants.length;

  @override
  int get hashCode => Object.hash(
    callId,
    callType,
    isInCall,
    isPipMode,
    elapsed,
    participants.length,
  );
}

class ActiveCallNotifier extends Notifier<ActiveCallState> {
  Timer? _elapsedTimer;

  @override
  ActiveCallState build() {
    final screenWake = ref.read(screenWakeGatewayProvider);
    ref.onDispose(() {
      _stopTimer();
      // notifier 被回收时不得让屏幕停留在常亮态（onDispose 内禁止 ref.read，
      // 构造期捕获 gateway 引用）。
      unawaited(screenWake.release());
    });
    return const ActiveCallState();
  }

  void startCall({
    required String callId,
    required String callType,
    List<CallParticipant> participants = const [],
  }) {
    _stopTimer();
    state = ActiveCallState(
      callId: callId,
      callType: callType,
      isInCall: true,
      isPipMode: false,
      elapsed: Duration.zero,
      participants: participants,
    );
    _startTimer();
    // 通话期间保持屏幕常亮；PiP 最小化仍处于通话中，不释放。
    unawaited(ref.read(screenWakeGatewayProvider).acquire());
  }

  void endCall() {
    _stopTimer();
    state = const ActiveCallState();
    unawaited(ref.read(screenWakeGatewayProvider).release());
  }

  void enterPipMode() {
    if (!state.isInCall) return;
    state = state.copyWith(isPipMode: true);
  }

  void exitPipMode() {
    if (!state.isInCall) return;
    state = state.copyWith(isPipMode: false);
  }

  void updateParticipants(List<CallParticipant> participants) {
    if (!state.isInCall) return;
    state = state.copyWith(participants: participants);
  }

  void _startTimer() {
    _elapsedTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!state.isInCall) {
        _stopTimer();
        return;
      }
      state = state.copyWith(
        elapsed: state.elapsed + const Duration(seconds: 1),
      );
    });
  }

  void _stopTimer() {
    _elapsedTimer?.cancel();
    _elapsedTimer = null;
  }
}

final activeCallProvider =
    NotifierProvider<ActiveCallNotifier, ActiveCallState>(
      ActiveCallNotifier.new,
    );
