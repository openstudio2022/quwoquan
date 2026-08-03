import 'package:quwoquan_app/cloud/chat/models/chat_conversation_timestamp_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_message_receipt_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/sync_response.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_view_data.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

/// The only Chat boundary mapper in the App.
///
/// Canonical wire values remain generated contract values. Mapping is limited
/// to explicit App-owned cache/presentation state and existing local sync
/// records; there is no JSON decoder or second wire model here.
final class ChatContractProjectionMapper {
  const ChatContractProjectionMapper();

  ChatInboxViewData toInbox(ChatInboxItemView item) =>
      ChatInboxViewData.fromWire(item);

  ChatInboxViewData conversationToInbox(ChatConversation item) =>
      ChatInboxViewData.fromConversation(item);

  ChatConversationCreatedViewData toCreated(ChatConversation item) =>
      ChatConversationCreatedViewData.fromWire(item);

  ConversationViewData toConversation(ChatConversation item) {
    return ConversationViewData.fromWire(item);
  }

  ChatGroupSettingsViewData toGroupSettings(ChatConversation item) =>
      ChatGroupSettingsViewData.fromWire(item);

  ChatContactRowViewData toContact(ChatContactListRow item) =>
      ChatContactRowViewData.fromWire(item);

  ChatContactRowViewData groupCandidateToContact(GroupCandidateRow item) {
    return ChatContactRowViewData(
      userId: item.userId,
      userHandle: item.userHandle,
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

  ChatContactRowViewData selectableContactToContact(
    SelectableGroupContactMemberRow item,
  ) {
    return ChatContactRowViewData(
      userId: item.userId,
      userHandle: item.userHandle,
      displayName: item.displayName,
      avatarUrl: item.avatarUrl,
      relationState: item.relationState,
      source: item.source,
    );
  }

  SyncResponse toSyncResponse(ChatMessageSyncSlice slice) {
    return SyncResponse(
      messages: slice.messages
          .map(ChatMessageViewData.fromWire)
          .toList(growable: false),
      hasMore: slice.hasMore,
    );
  }

  ChatConversationTimestampDto toTimestamp(ChatConversationTimestamp item) {
    return ChatConversationTimestampDto(
      conversationId: item.conversationId,
      updatedAt: item.updatedAt.toIso8601String(),
      settingsUpdatedAt: item.settingsUpdatedAt.toIso8601String(),
      lastMessageAt: item.lastMessageAt.toIso8601String(),
      lastMessageTime: item.lastMessageTime.toIso8601String(),
      lastMessagePreview: item.lastMessagePreview,
      unreadCount: item.unreadCount,
      type: item.type,
    );
  }

  ChatMessageReceiptDto toReceipt(ChatMessageReceipt item) {
    return ChatMessageReceiptDto(userId: item.userId, readAt: item.readAt);
  }
}
