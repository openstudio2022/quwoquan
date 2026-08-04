import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/message_sync_view_data.dart';
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

  ChatMessageSyncViewData toMessageSyncViewData(ChatMessageSyncSlice slice) {
    return ChatMessageSyncViewData(
      messages: slice.messages
          .map(ChatMessageViewData.fromWire)
          .toList(growable: false),
      hasMore: slice.hasMore,
    );
  }
}
