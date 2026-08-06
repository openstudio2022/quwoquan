import 'package:quwoquan_app/runtime/transport/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ChatMessageHomeInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteChatMessageHomeQuery implements ChatMessageHomeQuery {
  const RemoteChatMessageHomeQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ChatMessageHomeInvocationContextFactory invocationContext;

  @override
  Future<MessageHomePageSlice> listMessageHome(ChatListMessageHomeQuery query) {
    return client.chatConversationListMessageHome(
      query,
      context: invocationContext(ChatRequestPageIds.listMessageHome),
    );
  }
}
