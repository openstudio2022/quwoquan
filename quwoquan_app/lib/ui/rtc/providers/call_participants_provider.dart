import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/application/rtc/call_session/call_participant_presentation.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/platform/rtc_room_service.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class CallParticipantsState {
  const CallParticipantsState({
    this.participants = const <CallParticipantViewData>[],
    this.activeSpeakerId,
    this.lockedSpeakerId,
  });

  final List<CallParticipantViewData> participants;
  final String? activeSpeakerId;
  final String? lockedSpeakerId;

  List<CallParticipantViewData> get connectedParticipants =>
      participants.where((participant) => participant.isConnected).toList();

  CallParticipantViewData? get activeSpeaker {
    final preferredId = lockedSpeakerId ?? activeSpeakerId;
    if (preferredId != null) {
      for (final participant in participants) {
        if (participant.userId == preferredId) return participant;
      }
    }
    return participants.firstOrNull;
  }

  CallParticipantsState copyWith({
    List<CallParticipantViewData>? participants,
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
    List<CallParticipant> wires, {
    String? conversationId,
    CallParticipantPresentation? callerFallback,
  }) async {
    var resolved = <String, CallParticipantPresentation>{};
    final id = conversationId?.trim() ?? '';
    if (id.isNotEmpty && wires.isNotEmpty) {
      try {
        resolved = Map<String, CallParticipantPresentation>.from(
          await ref
              .read(callParticipantPresentationResolverProvider)
              .resolve(
                conversationId: id,
                userIds: wires.map((wire) => wire.userId).toSet(),
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
    final currentById = <String, CallParticipantViewData>{
      for (final participant in state.participants)
        participant.userId: participant,
    };
    state = state.copyWith(
      participants: wires
          .map((wire) {
            final presentation = _presentations[wire.userId];
            final current = currentById[wire.userId];
            final base = CallParticipantViewData.fromWire(
              wire,
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

  /// 以平台 RTC 运行态为媒体真相，以已组合 roster 为展示真相。
  void syncFromRtcRoom(RtcRoomService room, List<CallParticipant> wires) {
    final wireById = <String, CallParticipant>{
      for (final wire in wires) wire.userId: wire,
    };
    final live = <CallParticipantViewData>[];
    final local = room.localParticipant;
    if (local != null) {
      live.add(_mergeParticipant(local, wireById[local.identity]));
    }
    for (final remote in room.remoteParticipants) {
      live.add(_mergeParticipant(remote, wireById[remote.identity]));
    }
    final liveIds = live.map((participant) => participant.userId).toSet();
    for (final wire in wires) {
      if (!liveIds.contains(wire.userId)) {
        live.add(_fromWire(wire));
      }
    }
    state = state.copyWith(
      participants: live,
      activeSpeakerId: room.activeSpeaker.value,
    );
  }

  CallParticipantViewData _mergeParticipant(
    RtcParticipantSnapshot participant,
    CallParticipant? wire,
  ) {
    final base = wire == null
        ? CallParticipantViewData(
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
        : _fromWire(wire);
    return base.copyWith(
      status: ParticipantStatus.connected,
      isMuted: participant.isMuted,
      isCameraOn: participant.isCameraOn,
      isSpeaking: participant.isSpeaking,
      audioLevel: participant.audioLevel,
      videoTrack: participant.cameraTrack,
      clearVideoTrack: participant.cameraTrack == null,
      screenShareTrack: participant.screenShareTrack,
      clearScreenShareTrack: participant.screenShareTrack == null,
      isLocal: participant.isLocal,
    );
  }

  CallParticipantViewData _fromWire(CallParticipant wire) {
    final presentation = _presentations[wire.userId];
    return CallParticipantViewData.fromWire(
      wire,
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
