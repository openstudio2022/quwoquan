import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:livekit_client/livekit_client.dart' as lk;
import 'package:quwoquan_app/application/rtc/call_session/call_participant_presentation.dart';
import 'package:quwoquan_app/cloud/rtc/livekit_room_service.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class CallParticipantsState {
  const CallParticipantsState({
    this.participants = const <CallParticipant>[],
    this.activeSpeakerId,
    this.lockedSpeakerId,
  });

  final List<CallParticipant> participants;
  final String? activeSpeakerId;
  final String? lockedSpeakerId;

  List<CallParticipant> get connectedParticipants =>
      participants.where((participant) => participant.isConnected).toList();

  CallParticipant? get activeSpeaker {
    final preferredId = lockedSpeakerId ?? activeSpeakerId;
    if (preferredId != null) {
      for (final participant in participants) {
        if (participant.userId == preferredId) return participant;
      }
    }
    return participants.firstOrNull;
  }

  CallParticipantsState copyWith({
    List<CallParticipant>? participants,
    String? activeSpeakerId,
    String? lockedSpeakerId,
  }) => CallParticipantsState(
    participants: participants ?? this.participants,
    activeSpeakerId: activeSpeakerId ?? this.activeSpeakerId,
    lockedSpeakerId: lockedSpeakerId ?? this.lockedSpeakerId,
  );
}

class CallParticipantsNotifier extends Notifier<CallParticipantsState> {
  Map<String, CallParticipantPresentation> _presentations =
      const <String, CallParticipantPresentation>{};

  @override
  CallParticipantsState build() => const CallParticipantsState();

  /// 组合 CallSession roster 与 chat.ConversationMember 展示投影。
  ///
  /// 解析失败只降级为 userId，不阻断媒体通话；失败会进入开发日志便于定位。
  Future<void> syncRoster(
    List<CallParticipantDto> dtos, {
    String? conversationId,
    CallParticipantPresentation? callerFallback,
  }) async {
    var resolved = <String, CallParticipantPresentation>{};
    final id = conversationId?.trim() ?? '';
    if (id.isNotEmpty && dtos.isNotEmpty) {
      try {
        resolved = Map<String, CallParticipantPresentation>.from(
          await ref
              .read(callParticipantPresentationResolverProvider)
              .resolve(
                conversationId: id,
                userIds: dtos.map((dto) => dto.userId).toSet(),
              ),
        );
      } catch (error, stackTrace) {
        developer.log(
          'RTC participant presentation resolve failed',
          name: 'CallParticipantsNotifier',
          error: error,
          stackTrace: stackTrace,
        );
      }
    }
    if (!ref.mounted) return;
    if (callerFallback != null) {
      resolved.putIfAbsent(callerFallback.userId, () => callerFallback);
    }
    _presentations = Map<String, CallParticipantPresentation>.unmodifiable(
      resolved,
    );
    final currentById = <String, CallParticipant>{
      for (final participant in state.participants)
        participant.userId: participant,
    };
    state = state.copyWith(
      participants: dtos
          .map((dto) {
            final presentation = _presentations[dto.userId];
            final current = currentById[dto.userId];
            final base = CallParticipant.fromDto(
              dto,
              displayName: presentation?.displayName,
              avatarUrl: _avatarUrl(presentation?.avatarUrl),
              trustRelation: presentation?.knownInCurrentContext == true
                  ? TrustRelation.known
                  : TrustRelation.possiblyUnknown,
            );
            if (current == null) return base;
            return base.copyWith(
              status: current.status,
              isMuted: current.isMuted,
              isCameraOn: current.isCameraOn,
              isSpeaking: current.isSpeaking,
              audioLevel: current.audioLevel,
              videoTrack: current.videoTrack,
              screenShareTrack: current.screenShareTrack,
              isLocal: current.isLocal,
            );
          })
          .toList(growable: false),
    );
  }

  /// 以 LiveKit 为媒体运行态真相，以已组合 roster 为展示真相。
  void syncFromLiveKit(LiveKitRoomService room, List<CallParticipantDto> dtos) {
    final dtoById = <String, CallParticipantDto>{
      for (final dto in dtos) dto.userId: dto,
    };
    final live = <CallParticipant>[];
    final local = room.localParticipant;
    if (local != null) {
      live.add(
        _mergeParticipant(local, dtoById[local.identity], isLocal: true),
      );
    }
    for (final remote in room.remoteParticipants) {
      live.add(_mergeParticipant(remote, dtoById[remote.identity]));
    }
    final liveIds = live.map((participant) => participant.userId).toSet();
    for (final dto in dtos) {
      if (!liveIds.contains(dto.userId)) {
        live.add(_fromDto(dto));
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
    bool isLocal = false,
  }) {
    final cameraPublication = participant.videoTrackPublications
        .where((publication) => publication.source == lk.TrackSource.camera)
        .firstOrNull;
    final videoTrack = cameraPublication?.track is lk.VideoTrack
        ? cameraPublication!.track as lk.VideoTrack
        : null;
    final screenSharePublication = participant.videoTrackPublications
        .where(
          (publication) =>
              publication.source == lk.TrackSource.screenShareVideo,
        )
        .firstOrNull;
    final screenShareTrack = screenSharePublication?.track is lk.VideoTrack
        ? screenSharePublication!.track as lk.VideoTrack
        : null;
    final base = dto == null
        ? CallParticipant(
            userId: participant.identity,
            displayName:
                _presentations[participant.identity]?.displayName ??
                (participant.name.isNotEmpty
                    ? participant.name
                    : participant.identity),
            avatarUrl: _avatarUrl(
              _presentations[participant.identity]?.avatarUrl,
            ),
            trustRelation:
                _presentations[participant.identity]?.knownInCurrentContext ==
                    true
                ? TrustRelation.known
                : TrustRelation.possiblyUnknown,
          )
        : _fromDto(dto);
    return base.copyWith(
      status: ParticipantStatus.connected,
      isMuted: participant.isMuted,
      isCameraOn: videoTrack != null && !(cameraPublication?.muted ?? true),
      isSpeaking: participant.isSpeaking,
      audioLevel: participant.audioLevel,
      videoTrack: videoTrack,
      clearVideoTrack: videoTrack == null,
      screenShareTrack: screenShareTrack,
      clearScreenShareTrack:
          screenShareTrack == null || (screenSharePublication?.muted ?? true),
      isLocal: isLocal,
    );
  }

  CallParticipant _fromDto(CallParticipantDto dto) {
    final presentation = _presentations[dto.userId];
    return CallParticipant.fromDto(
      dto,
      displayName: presentation?.displayName,
      avatarUrl: _avatarUrl(presentation?.avatarUrl),
      trustRelation: presentation?.knownInCurrentContext == true
          ? TrustRelation.known
          : TrustRelation.possiblyUnknown,
    );
  }

  void lockSpeaker(String userId) {
    state = CallParticipantsState(
      participants: state.participants,
      activeSpeakerId: state.activeSpeakerId,
      lockedSpeakerId: state.lockedSpeakerId == userId ? null : userId,
    );
  }

  String? _avatarUrl(String? value) {
    final text = value?.trim() ?? '';
    return text.isEmpty ? null : resolveAvatarImageUrl(text);
  }
}

final callParticipantsProvider =
    NotifierProvider<CallParticipantsNotifier, CallParticipantsState>(
      CallParticipantsNotifier.new,
    );
