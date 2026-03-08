import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/rtc/models/call_participant_dto.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';

class CallParticipantsState {
  final List<CallParticipant> participants;
  final String? activeSpeakerId;
  final String? lockedSpeakerId;
  final Map<String, double> audioLevels;

  const CallParticipantsState({
    this.participants = const [],
    this.activeSpeakerId,
    this.lockedSpeakerId,
    this.audioLevels = const {},
  });

  List<CallParticipant> get connectedParticipants =>
      participants.where((p) => p.isConnected).toList();

  CallParticipant? get activeSpeaker {
    if (lockedSpeakerId != null) {
      final locked = participants
          .where((p) => p.userId == lockedSpeakerId)
          .toList();
      if (locked.isNotEmpty) return locked.first;
    }
    if (activeSpeakerId != null) {
      final active = participants
          .where((p) => p.userId == activeSpeakerId)
          .toList();
      if (active.isNotEmpty) return active.first;
    }
    return participants.isNotEmpty ? participants.first : null;
  }

  CallParticipantsState copyWith({
    List<CallParticipant>? participants,
    String? activeSpeakerId,
    String? lockedSpeakerId,
    Map<String, double>? audioLevels,
  }) {
    return CallParticipantsState(
      participants: participants ?? this.participants,
      activeSpeakerId: activeSpeakerId ?? this.activeSpeakerId,
      lockedSpeakerId: lockedSpeakerId ?? this.lockedSpeakerId,
      audioLevels: audioLevels ?? this.audioLevels,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is CallParticipantsState &&
          runtimeType == other.runtimeType &&
          participants.length == other.participants.length &&
          activeSpeakerId == other.activeSpeakerId &&
          lockedSpeakerId == other.lockedSpeakerId;

  @override
  int get hashCode =>
      Object.hash(participants.length, activeSpeakerId, lockedSpeakerId);
}

class CallParticipantsNotifier extends Notifier<CallParticipantsState> {
  Timer? _speakerDebounce;
  String? _pendingSpeakerId;

  @override
  CallParticipantsState build() => const CallParticipantsState();

  void updateFromDtos(List<CallParticipantDto> dtos) {
    final participants = dtos
        .map((dto) => CallParticipant.fromDto(dto))
        .toList();
    state = state.copyWith(participants: participants);
  }

  void updateAudioLevel(String userId, double level) {
    final newLevels = Map<String, double>.from(state.audioLevels);
    newLevels[userId] = level;

    final updated = state.participants.map((p) {
      if (p.userId == userId) {
        return p.copyWith(
          audioLevel: level,
          isSpeaking: level > 0.1,
        );
      }
      return p;
    }).toList();

    state = state.copyWith(
      participants: updated,
      audioLevels: newLevels,
    );

    if (level > 0.1) {
      _debouncedSetActiveSpeaker(userId);
    }
  }

  void _debouncedSetActiveSpeaker(String userId) {
    _pendingSpeakerId = userId;
    _speakerDebounce?.cancel();
    _speakerDebounce = Timer(const Duration(milliseconds: 500), () {
      if (_pendingSpeakerId == userId) {
        state = state.copyWith(activeSpeakerId: userId);
      }
    });
  }

  void lockSpeaker(String userId) {
    if (state.lockedSpeakerId == userId) {
      state = CallParticipantsState(
        participants: state.participants,
        activeSpeakerId: state.activeSpeakerId,
        lockedSpeakerId: null,
        audioLevels: state.audioLevels,
      );
    } else {
      state = state.copyWith(lockedSpeakerId: userId);
    }
  }

  void refreshParticipants() {
    final session = ref.read(callSessionProvider).session;
    if (session != null) {
      updateFromDtos(session.participants);
    }
  }
}

final callParticipantsProvider =
    NotifierProvider<CallParticipantsNotifier, CallParticipantsState>(
  CallParticipantsNotifier.new,
);
