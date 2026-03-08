import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/rtc/models/call_participant_dto.dart';

class ActiveCallState {
  final String? callId;
  final String? callType;
  final bool isInCall;
  final bool isPipMode;
  final Duration elapsed;
  final List<CallParticipantDto> participants;

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
    List<CallParticipantDto>? participants,
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
  ActiveCallState build() => const ActiveCallState();

  void startCall({
    required String callId,
    required String callType,
    List<CallParticipantDto> participants = const [],
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
  }

  void endCall() {
    _stopTimer();
    state = const ActiveCallState();
  }

  void enterPipMode() {
    if (!state.isInCall) return;
    state = state.copyWith(isPipMode: true);
  }

  void exitPipMode() {
    if (!state.isInCall) return;
    state = state.copyWith(isPipMode: false);
  }

  void updateParticipants(List<CallParticipantDto> participants) {
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
