import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:livekit_client/livekit_client.dart' as lk;
import 'package:quwoquan_app/cloud/rtc/models/call_participant_dto.dart';
import 'package:quwoquan_app/cloud/rtc/livekit_room_service.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
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

  /// Merges the server-side participant roster (metadata: displayName, role,
  /// trust) with the live LiveKit room (real connection/track/speaking state),
  /// keyed on userId == LiveKit participant identity. This is the single bind
  /// point that turns the placeholder grid into real video; see design REV-5 S2.
  void syncFromLiveKit(LiveKitRoomService room, List<CallParticipantDto> dtos) {
    final byId = <String, CallParticipantDto>{
      for (final dto in dtos) dto.userId: dto,
    };

    final live = <CallParticipant>[];

    final local = room.localParticipant;
    if (local != null) {
      live.add(_mergeParticipant(local, byId[local.identity], isLocal: true));
    }
    for (final remote in room.remoteParticipants) {
      live.add(_mergeParticipant(remote, byId[remote.identity], isLocal: false));
    }

    // Include roster entries that have not yet established media (invited /
    // ringing / connecting) so the grid can show waiting tiles.
    final liveIds = live.map((p) => p.userId).toSet();
    for (final dto in dtos) {
      if (!liveIds.contains(dto.userId)) {
        live.add(CallParticipant.fromDto(dto));
      }
    }

    state = state.copyWith(
      participants: live,
      activeSpeakerId: room.activeSpeaker.value,
    );
  }

  CallParticipant _mergeParticipant(
    lk.Participant participant,
    CallParticipantDto? dto, {
    required bool isLocal,
  }) {
    final cameraPub = participant.videoTrackPublications
        .where((pub) => pub.source == lk.TrackSource.camera)
        .firstOrNull;
    final videoTrack = cameraPub?.track is lk.VideoTrack
        ? cameraPub!.track as lk.VideoTrack
        : null;
    final isCameraOn = videoTrack != null && !(cameraPub?.muted ?? true);
    final isMuted = participant.isMuted;

    final base = dto != null
        ? CallParticipant.fromDto(dto)
        : CallParticipant(
            userId: participant.identity,
            displayName: participant.name.isNotEmpty
                ? participant.name
                : participant.identity,
          );

    return base.copyWith(
      status: ParticipantStatus.connected,
      isMuted: isMuted,
      isCameraOn: isCameraOn,
      isSpeaking: participant.isSpeaking,
      audioLevel: participant.audioLevel,
      videoTrack: videoTrack,
      clearVideoTrack: videoTrack == null,
      isLocal: isLocal,
    );
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
