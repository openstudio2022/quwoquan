import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ChatContactInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteChatContactQuery implements ChatContactQuery, ChatInboxQuery {
  const RemoteChatContactQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ChatContactInvocationContextFactory invocationContext;

  @override
  Future<ContactHomePageSlice> listContactHome(ChatListContactHomeQuery query) {
    return client.chatConversationListContactHome(
      query,
      context: invocationContext(ChatRequestPageIds.listContactHome),
    );
  }

  @override
  Future<ContactPageSlice> listContacts(ChatListContactsQuery query) {
    return client.chatConversationListContacts(
      query,
      context: invocationContext(ChatRequestPageIds.listContacts),
    );
  }

  @override
  Future<GroupCandidatePageSlice> listGroupCandidates(
    ChatListGroupCandidatesQuery query,
  ) {
    return client.chatConversationListGroupCandidates(
      query,
      context: invocationContext(ChatRequestPageIds.listGroupCandidates),
    );
  }

  @override
  Future<ChatInboxPageSlice> listInbox(ChatListInboxQuery query) {
    return client.chatChatInboxViewListInbox(
      query,
      context: invocationContext(ChatRequestPageIds.listInbox),
    );
  }

  @override
  Future<SelectableGroupContactPageSlice> listSelectableGroupContactMembers(
    ChatListSelectableGroupContactMembersQuery query,
  ) {
    return client.chatConversationListSelectableGroupContactMembers(
      query,
      context: invocationContext(
        ChatRequestPageIds.listSelectableGroupContactMembers,
      ),
    );
  }

  @override
  Future<SelectableGroupConversationPageSlice> listSelectableGroupConversations(
    ChatListSelectableGroupConversationsQuery query,
  ) {
    return client.chatConversationListSelectableGroupConversations(
      query,
      context: invocationContext(
        ChatRequestPageIds.listSelectableGroupConversations,
      ),
    );
  }
}
