import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

/// App-owned conversation state used by local cache and presentation.
///
/// Cloud decoding is exclusively owned by [ChatConversation].
final class ConversationViewData {
  const ConversationViewData({
    required this.id,
    required this.type,
    this.title,
    this.avatarUrl,
    this.groupAvatarVersion = 0,
    this.groupAvatarSourceHash,
    required this.creatorId,
    this.circleId,
    this.circleGroupId,
    this.originType = 'direct_init',
    this.originIntersectionSnapshot,
    required this.maxSeq,
    required this.memberCount,
    required this.maxGroupSize,
    required this.receiptEnabled,
    this.lastMessageId,
    this.lastMessagePreview,
    required this.lastMessageType,
    this.lastMessageTime,
    required this.messageCount,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    this.membersRosterRevision,
  });

  factory ConversationViewData.fromWire(ChatConversation source) {
    return ConversationViewData(
      id: source.id,
      type: source.type,
      title: _optional(source.title),
      avatarUrl: _optional(source.avatarUrl),
      groupAvatarVersion: source.groupAvatarVersion,
      groupAvatarSourceHash: source.groupAvatarSourceHash == null
          ? null
          : _optional(source.groupAvatarSourceHash!),
      creatorId: source.creatorId,
      circleId: _optional(source.circleId),
      circleGroupId: _optional(source.circleGroupId),
      originType: source.originType,
      originIntersectionSnapshot: source.originIntersectionSnapshot,
      maxSeq: source.maxSeq,
      memberCount: source.memberCount,
      maxGroupSize: source.maxGroupSize,
      receiptEnabled: source.receiptEnabled,
      lastMessageId: _optional(source.lastMessageId),
      lastMessagePreview: _optional(source.lastMessagePreview),
      lastMessageType: source.lastMessageType,
      lastMessageTime: source.lastMessageTime,
      messageCount: source.messageCount,
      status: source.status,
      createdAt: source.createdAt,
      updatedAt: source.updatedAt,
      membersRosterRevision: source.membersRosterRevision,
    );
  }

  final String id;
  final String type;
  final String? title;
  final String? avatarUrl;
  final int groupAvatarVersion;
  final String? groupAvatarSourceHash;
  final String creatorId;
  final String? circleId;
  final String? circleGroupId;
  final String originType;
  final GreetingIntersectionSnapshot? originIntersectionSnapshot;
  final int maxSeq;
  final int memberCount;
  final int maxGroupSize;
  final bool receiptEnabled;
  final String? lastMessageId;
  final String? lastMessagePreview;
  final MessageType lastMessageType;
  final DateTime? lastMessageTime;
  final int messageCount;
  final String status;
  final DateTime createdAt;
  final DateTime updatedAt;
  final int? membersRosterRevision;
}

String? _optional(String value) {
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}
