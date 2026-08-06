import 'package:quwoquan_app/runtime/transport/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ChatInboxInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteChatInboxQuery implements ChatInboxQuery {
  const RemoteChatInboxQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ChatInboxInvocationContextFactory invocationContext;

  @override
  Future<ChatInboxPageSlice> listInbox(ChatListInboxQuery query) {
    return client.chatChatInboxViewListInbox(
      query,
      context: invocationContext(ChatRequestPageIds.listInbox),
    );
  }
}
