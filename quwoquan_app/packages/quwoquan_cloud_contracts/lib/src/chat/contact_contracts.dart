import 'chat_operation_contracts.g.dart';

export 'chat_operation_contracts.g.dart';

abstract interface class ChatContactQuery {
  Future<ContactPageSlice> listContacts(ChatListContactsQuery query);

  Future<ContactHomePageSlice> listContactHome(ChatListContactHomeQuery query);

  Future<GroupCandidatePageSlice> listGroupCandidates(
    ChatListGroupCandidatesQuery query,
  );

  Future<SelectableGroupConversationPageSlice> listSelectableGroupConversations(
    ChatListSelectableGroupConversationsQuery query,
  );

  Future<SelectableGroupContactPageSlice> listSelectableGroupContactMembers(
    ChatListSelectableGroupContactMembersQuery query,
  );
}

abstract interface class ChatInboxQuery {
  Future<ChatInboxPageSlice> listInbox(ChatListInboxQuery query);
}
