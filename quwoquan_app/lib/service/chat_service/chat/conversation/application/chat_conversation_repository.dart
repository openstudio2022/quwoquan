import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/domain/conversation_dto.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/conversation_dissolver.dart';
import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

abstract interface class ChatConversationRepository {
  Future<List<MessageHomeRow>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<ChatInboxViewData>> listConversations({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<ChatConversationCreatedViewData> createConversation({
    required String type,
    String? title,
    int? maxGroupSize,
    List<String>? initialMemberIds,
    String? idempotencyKey,
  });

  Future<ConversationViewData> getConversation(String conversationId);

  Future<void> updateConversationTitle(String conversationId, String title);

  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  });

  Future<List<ChatConversationTimestamp>> getConversationTimestamps();

  Future<List<ConversationViewData>> batchGetConversations(List<String> ids);
}

abstract interface class ChatContactRepository {
  Future<CursorPage<ChatContactRowViewData>> listContacts({
    String? cursor,
    int limit = ChatListContactsQuery.defaultLimit,
  });

  Future<List<ContactHomeRow>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<ChatContactRowViewData>> listGroupCandidates({
    String? conversationId,
    int limit = ChatListGroupCandidatesQuery.defaultLimit,
  });
}

enum ChatSelectableGroupSource {
  all,
  group,
  circle;

  String? get wireValue => this == ChatSelectableGroupSource.all ? null : name;
}

abstract interface class ChatGroupSelectionRepository {
  Future<CursorPage<SelectableGroupConversationRow>>
  listSelectableGroupConversations({
    String? query,
    ChatSelectableGroupSource source = ChatSelectableGroupSource.all,
    String? cursor,
    int limit = ChatListSelectableGroupConversationsQuery.defaultLimit,
  });

  Future<CursorPage<ChatContactRowViewData>> listSelectableGroupContactMembers({
    required String conversationId,
    String? query,
    String? cursor,
    int limit = ChatListSelectableGroupContactMembersQuery.defaultLimit,
  });
}

abstract interface class ChatGroupAdminRepository
    implements ConversationDissolver {
  Future<ChatGroupSettingsViewData> getGroupSettings(String conversationId);

  Future<GroupHome> getGroupHome(String conversationId);

  Future<void> updateGroupSettings(
    String conversationId,
    ChatGroupSettingsViewData settings,
  );

  Future<void> updateAnnouncement(String conversationId, String announcement);

  Future<void> transferOwnership(String conversationId, String newOwnerId);

  Future<void> updateGroupAdmins(String conversationId, List<String> adminIds);

  @override
  Future<void> dissolveConversation(String conversationId);
}
