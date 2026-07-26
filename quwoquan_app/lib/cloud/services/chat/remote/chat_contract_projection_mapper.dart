import 'package:quwoquan_app/cloud/chat/models/chat_conversation_timestamp_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_message_receipt_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/sync_response.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_group_settings_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_card_attribute_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_card_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/contact_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/group_home_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/message_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/selectable_group_conversation_row_dto.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Chat pure contract projection 到现有 App typed DTO 的唯一映射器。
///
/// Remote 只在这里跨越 contracts package 与 App ViewData 边界，页面与 Provider
/// 不接触 wire JSON，也不维护第二套字段解码。
final class ChatContractProjectionMapper {
  const ChatContractProjectionMapper();

  ChatInboxDto toInbox(ChatInboxItem item) {
    return ChatInboxDto(
      id: item.id,
      type: item.type,
      title: item.title,
      avatarUrl: item.avatarUrl,
      groupAvatarVersion: item.groupAvatarVersion,
      lastMessagePreview: item.lastMessagePreview,
      lastMessageType: item.lastMessageType,
      lastMessageTime: item.lastMessageTime,
      lastSeq: item.lastSeq,
      unreadCount: item.unreadCount,
      mentionUnreadCount: item.mentionUnreadCount,
      muted: item.muted,
      pinned: item.pinned,
      circleId: item.circleId ?? '',
    );
  }

  ChatInboxDto conversationToInbox(ChatConversation item) {
    return ChatInboxDto(
      id: item.id,
      type: item.type,
      title: item.title,
      avatarUrl: item.avatarUrl,
      groupAvatarVersion: item.groupAvatarVersion,
      lastMessagePreview: item.lastMessagePreview,
      lastMessageType: '',
      lastMessageTime: item.lastMessageTime,
      lastSeq: item.maxSeq,
      unreadCount: 0,
      mentionUnreadCount: 0,
      muted: false,
      pinned: false,
      circleId: item.circleId,
    );
  }

  MessageHomeRowDto toMessageHome(ChatMessageHomeItem item) {
    return MessageHomeRowDto(
      id: item.id,
      kind: item.kind,
      conversationId: item.conversationId,
      notificationId: item.notificationId,
      conversationType: item.conversationType,
      title: item.title,
      summary: item.summary,
      avatarUrl: item.avatarUrl,
      groupAvatarVersion: item.groupAvatarVersion,
      lastActiveAt: item.lastActiveAt,
      unreadCount: item.unreadCount,
      mentionUnreadCount: item.mentionUnreadCount,
      muted: item.muted,
      pinned: item.pinned,
      notificationType: item.notificationType,
      read: item.read,
    );
  }

  ChatConversationCreatedDto toCreated(ChatConversation conversation) {
    return ChatConversationCreatedDto(
      conversationId: conversation.conversationId,
    );
  }

  ConversationDto toConversation(ChatConversation item) {
    return ConversationDto(
      id: item.id,
      type: item.type,
      title: _optional(item.title),
      avatarUrl: _optional(item.avatarUrl),
      groupAvatarVersion: item.groupAvatarVersion,
      creatorId: item.creatorId,
      circleId: _optional(item.circleId),
      circleGroupId: _optional(item.circleGroupId),
      originType: item.originType,
      bindingType: item.bindingType,
      lifecyclePolicy: item.lifecyclePolicy,
      maxSeq: item.maxSeq,
      memberCount: item.memberCount,
      maxGroupSize: item.maxGroupSize,
      receiptEnabled: item.receiptEnabled,
      lastMessageId: _optional(item.lastMessageId),
      lastMessagePreview: _optional(item.lastMessagePreview),
      lastMessageTime: item.lastMessageTime,
      messageCount: item.messageCount,
      status: item.status,
      createdAt: item.createdAt,
      updatedAt: item.updatedAt,
      membersRosterRevision: item.membersRosterRevision,
    );
  }

  ChatGroupSettingsDto toGroupSettings(ChatConversation item) {
    return ChatGroupSettingsDto(
      nameEditableByAdminOnly: item.nameEditableByAdminOnly,
      conversationType: item.type,
      circleId: item.circleId,
      circleGroupId: item.circleGroupId,
    );
  }

  GroupHomeDto toGroupHome(ChatGroupHome item) {
    return GroupHomeDto(
      conversationId: item.conversationId,
      title: item.title,
      avatarUrl: item.avatarUrl,
      groupAvatarVersion: item.groupAvatarVersion,
      circleId: item.circleId,
      circleGroupId: item.circleGroupId,
      entityId: item.entityId,
      sourceEntityTitle: item.sourceEntityTitle,
      sourceCircleTitle: item.sourceCircleTitle,
      memberCount: item.memberCount,
      announcement: item.announcement,
      capabilities: item.capabilities,
      originType: item.originType,
      bindingType: item.bindingType,
      lifecyclePolicy: item.lifecyclePolicy,
      canManageMembers: item.canManageMembers,
      canDissolve: item.canDissolve,
    );
  }

  ChatContactRowDto toContact(ChatContact item) {
    return ChatContactRowDto(
      userId: item.userId ?? item.contactId,
      displayName: item.displayName,
      avatarUrl: item.avatarUrl,
      bio: item.bio,
      metFrom: item.metFrom,
      lastInteraction: item.lastInteraction,
      relationState: item.relationState,
      source: item.source,
      isStarred: item.isStarred,
    );
  }

  ContactHomeRowDto toContactHome(ChatContactHomeItem item) {
    return ContactHomeRowDto(
      id: item.id,
      kind: item.kind,
      objectId: item.objectId,
      userId: item.userId ?? '',
      conversationId: item.conversationId ?? '',
      circleId: item.circleId ?? '',
      circleGroupId: item.circleGroupId ?? '',
      entityId: item.entityId ?? '',
      title: item.title,
      subtitle: item.subtitle,
      avatarUrl: item.avatarUrl,
      relationState: item.relationState ?? 'not_following',
      summaryIntersections: item.summaryIntersections,
      sourceEntityTitle: item.sourceEntityTitle ?? '',
      sourceCircleTitle: item.sourceCircleTitle ?? '',
      memberCount: item.memberCount ?? 0,
      contactCount: item.contactCount,
      lastActiveAt: item.lastActiveAt,
      sortKey: item.sortKey,
      isStarred: item.isStarred ?? false,
    );
  }

  SelectableGroupConversationRowDto toSelectableGroup(
    ChatSelectableGroupConversation item,
  ) {
    return SelectableGroupConversationRowDto(
      conversationId: item.conversationId,
      title: item.title,
      avatarUrl: item.avatarUrl,
      circleId: item.circleId,
      friendMemberCount: item.friendMemberCount,
      memberCount: item.memberCount,
    );
  }

  ChatConversationMemberDto toMember(ChatConversationMember item) {
    return ChatConversationMemberDto(
      userId: item.userId,
      displayName: item.displayName,
      avatarUrl: item.avatarUrl,
      role: item.role,
      memberType: item.memberType,
      assistantSkillId: item.assistantSkillId,
      joinedAt: item.joinedAt,
      isCurrentUser: item.isCurrentUser,
    );
  }

  ChatMessageDto toMessage(ChatMessage item) {
    final card = item.card;
    return ChatMessageDto(
      id: item.id,
      conversationId: item.conversationId,
      seq: item.seq,
      clientMsgId: item.clientMsgId,
      senderId: item.senderId,
      senderName: item.senderName,
      senderAvatar: item.senderAvatar,
      type: item.type,
      content: item.content,
      mediaAssetId: item.mediaAssetId,
      mediaDeliveryUrl: item.mediaDeliveryUrl,
      mediaType: item.mediaType,
      mediaContentType: item.mediaContentType,
      mediaFileSizeBytes: item.mediaFileSizeBytes,
      card: card == null
          ? null
          : ChatMessageCardDto(
              kind: card.kind,
              title: card.title,
              subtitle: card.subtitle,
              thumbnailUrl: card.thumbnailUrl,
              deeplink: card.deeplink,
              landingUrl: card.landingUrl,
              shareText: card.shareText,
              message: card.message,
              attributes: card.attributes
                  .map(
                    (attribute) => ChatMessageCardAttributeDto(
                      name: attribute.name,
                      value: attribute.value,
                    ),
                  )
                  .toList(growable: false),
            ),
      replyToMessageId: item.replyToMessageId,
      mentions: item.mentions,
      status: item.status,
      recalledAt: item.recalledAt,
      timestamp: item.timestamp,
    );
  }

  SyncResponse toSyncResponse(ChatMessageSyncSlice slice) {
    return SyncResponse(
      messages: slice.messages.map(toMessage).toList(growable: false),
      hasMore: slice.hasMore,
    );
  }

  ChatConversationTimestampDto toTimestamp(ChatConversationTimestamp item) {
    return ChatConversationTimestampDto(
      conversationId: item.conversationId,
      updatedAt: item.updatedAt.toIso8601String(),
      settingsUpdatedAt: item.settingsUpdatedAt.toIso8601String(),
      lastMessageAt: item.lastMessageAt?.toIso8601String(),
      lastMessageTime: item.lastMessageTime?.toIso8601String(),
      lastMessagePreview: item.lastMessagePreview,
      unreadCount: item.unreadCount,
      type: item.type,
    );
  }

  ChatMessageReceiptDto toReceipt(ChatMessageReceipt item) {
    return ChatMessageReceiptDto(userId: item.userId, readAt: item.readAt);
  }

  String? _optional(String value) {
    final normalized = value.trim();
    return normalized.isEmpty ? null : normalized;
  }
}
