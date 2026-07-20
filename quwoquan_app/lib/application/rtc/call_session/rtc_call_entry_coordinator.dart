import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

enum RtcCallEntryMediaType {
  audio,
  video;

  static RtcCallEntryMediaType fromWireValue(String value) =>
      value.trim().toLowerCase() == video.name ? video : audio;

  String get wireValue => name;
}

enum RtcCallEntryContextKind { direct, conversation, circle }

enum RtcCallEntryUnavailableReason {
  notMutual,
  blocked,
  capabilityDenied,
  missingTarget,
  missingConversationContext,
  missingCircleContext,
  noParticipants,
  participantLimitExceeded,
}

final class RtcCallEntryAvailability {
  const RtcCallEntryAvailability.available() : reason = null;

  const RtcCallEntryAvailability.unavailable(this.reason);

  final RtcCallEntryUnavailableReason? reason;

  bool get isAvailable => reason == null;
}

/// 发起通话的对象级 typed intent。
///
/// 1v1 只消费 relationship capability；多人只消费合法 Conversation/Circle
/// 上下文。交集、推荐或 presence 不进入授权判断。
final class RtcCallEntryIntent {
  const RtcCallEntryIntent._({
    required this.mediaType,
    required this.contextKind,
    this.targetUserId,
    this.relationshipCapability,
    this.conversationId,
    this.circleId,
    this.participantCount = 0,
    this.maxParticipants = 32,
  });

  factory RtcCallEntryIntent.direct({
    required RtcCallEntryMediaType mediaType,
    required String targetUserId,
    required RelationshipCapabilityDto? capability,
  }) {
    return RtcCallEntryIntent._(
      mediaType: mediaType,
      contextKind: RtcCallEntryContextKind.direct,
      targetUserId: targetUserId.trim(),
      relationshipCapability: capability,
      maxParticipants: 2,
    );
  }

  factory RtcCallEntryIntent.conversation({
    required RtcCallEntryMediaType mediaType,
    required String conversationId,
    required int participantCount,
    int maxParticipants = 32,
  }) {
    return RtcCallEntryIntent._(
      mediaType: mediaType,
      contextKind: RtcCallEntryContextKind.conversation,
      conversationId: conversationId.trim(),
      participantCount: participantCount,
      maxParticipants: maxParticipants,
    );
  }

  factory RtcCallEntryIntent.circle({
    required RtcCallEntryMediaType mediaType,
    required String circleId,
    required String conversationId,
    required int participantCount,
    int maxParticipants = 32,
  }) {
    return RtcCallEntryIntent._(
      mediaType: mediaType,
      contextKind: RtcCallEntryContextKind.circle,
      circleId: circleId.trim(),
      conversationId: conversationId.trim(),
      participantCount: participantCount,
      maxParticipants: maxParticipants,
    );
  }

  final RtcCallEntryMediaType mediaType;
  final RtcCallEntryContextKind contextKind;
  final String? targetUserId;
  final RelationshipCapabilityDto? relationshipCapability;
  final String? conversationId;
  final String? circleId;
  final int participantCount;
  final int maxParticipants;

  bool get requiresParticipantPicker =>
      contextKind != RtcCallEntryContextKind.direct;

  /// 0 表示人数未知，未知时 fail-closed 为不默认选择。
  bool get defaultSelectAll => participantCount > 0 && participantCount <= 8;

  /// CallSession 总人数包含发起人，因此初始发起最多选择 `maxParticipants - 1` 人。
  int get initialInviteeLimit {
    final remaining = maxParticipants - 1;
    return remaining < 0 ? 0 : remaining;
  }

  RtcCallEntryAvailability get availability {
    switch (contextKind) {
      case RtcCallEntryContextKind.direct:
        final targetId = targetUserId?.trim() ?? '';
        if (targetId.isEmpty) {
          return const RtcCallEntryAvailability.unavailable(
            RtcCallEntryUnavailableReason.missingTarget,
          );
        }
        final capability = relationshipCapability;
        if (capability == null) {
          return const RtcCallEntryAvailability.unavailable(
            RtcCallEntryUnavailableReason.capabilityDenied,
          );
        }
        if (capability.isBlocked || capability.isBlockedBy) {
          return const RtcCallEntryAvailability.unavailable(
            RtcCallEntryUnavailableReason.blocked,
          );
        }
        if (!capability.isMutual) {
          return const RtcCallEntryAvailability.unavailable(
            RtcCallEntryUnavailableReason.notMutual,
          );
        }
        final capabilityTargetId = capability.targetSubAccountId.trim();
        if (capabilityTargetId.isNotEmpty && capabilityTargetId != targetId) {
          return const RtcCallEntryAvailability.unavailable(
            RtcCallEntryUnavailableReason.capabilityDenied,
          );
        }
        final enabled = mediaType == RtcCallEntryMediaType.video
            ? capability.canStartVideoCall
            : capability.canStartVoiceCall;
        return enabled
            ? const RtcCallEntryAvailability.available()
            : const RtcCallEntryAvailability.unavailable(
                RtcCallEntryUnavailableReason.capabilityDenied,
              );
      case RtcCallEntryContextKind.conversation:
        if ((conversationId?.trim() ?? '').isEmpty) {
          return const RtcCallEntryAvailability.unavailable(
            RtcCallEntryUnavailableReason.missingConversationContext,
          );
        }
        return const RtcCallEntryAvailability.available();
      case RtcCallEntryContextKind.circle:
        if ((circleId?.trim() ?? '').isEmpty) {
          return const RtcCallEntryAvailability.unavailable(
            RtcCallEntryUnavailableReason.missingCircleContext,
          );
        }
        if ((conversationId?.trim() ?? '').isEmpty) {
          return const RtcCallEntryAvailability.unavailable(
            RtcCallEntryUnavailableReason.missingConversationContext,
          );
        }
        return const RtcCallEntryAvailability.available();
    }
  }

  RtcCallEntryIntent withMediaType(RtcCallEntryMediaType nextMediaType) {
    return RtcCallEntryIntent._(
      mediaType: nextMediaType,
      contextKind: contextKind,
      targetUserId: targetUserId,
      relationshipCapability: relationshipCapability,
      conversationId: conversationId,
      circleId: circleId,
      participantCount: participantCount,
      maxParticipants: maxParticipants,
    );
  }
}

final class RtcCallEntryRejected implements Exception {
  const RtcCallEntryRejected(this.reason);

  final RtcCallEntryUnavailableReason reason;

  @override
  String toString() => 'RtcCallEntryRejected(${reason.name})';
}

/// 所有发起入口共用的 application 主线：校验 typed intent，并只经
/// [CallLifecycleCommandWriter] 创建 CallSession。
final class RtcCallEntryCoordinator {
  const RtcCallEntryCoordinator({required this.lifecycleWriter});

  final CallLifecycleCommandWriter lifecycleWriter;

  Future<RtcInitiateCallResultDto> initiate(
    RtcCallEntryIntent intent, {
    List<String> selectedInviteeIds = const <String>[],
  }) async {
    final availability = intent.availability;
    if (!availability.isAvailable) {
      throw RtcCallEntryRejected(availability.reason!);
    }
    final inviteeIds = intent.contextKind == RtcCallEntryContextKind.direct
        ? <String>[intent.targetUserId!.trim()]
        : _normalizeInviteeIds(selectedInviteeIds);
    if (inviteeIds.isEmpty) {
      throw const RtcCallEntryRejected(
        RtcCallEntryUnavailableReason.noParticipants,
      );
    }
    if (inviteeIds.length > intent.initialInviteeLimit) {
      throw const RtcCallEntryRejected(
        RtcCallEntryUnavailableReason.participantLimitExceeded,
      );
    }
    return lifecycleWriter.initiateCall(
      RtcInitiateCallCommand(
        callType: intent.mediaType.wireValue,
        inviteeIds: inviteeIds,
        conversationId: _nonEmpty(intent.conversationId),
        circleId: _nonEmpty(intent.circleId),
        maxParticipants: intent.maxParticipants,
      ),
    );
  }

  static List<String> _normalizeInviteeIds(List<String> rawIds) {
    final result = <String>[];
    final seen = <String>{};
    for (final rawId in rawIds) {
      final id = rawId.trim();
      if (id.isNotEmpty && seen.add(id)) {
        result.add(id);
      }
    }
    return List<String>.unmodifiable(result);
  }

  static String? _nonEmpty(String? value) {
    final normalized = value?.trim() ?? '';
    return normalized.isEmpty ? null : normalized;
  }
}
