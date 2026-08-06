import 'package:quwoquan_app/service/chat_service/chat/message_receipt_fact/application/public/message_receipt_fact_query.dart';
import 'package:quwoquan_app/runtime/transport/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef MessageReceiptFactInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// MessageReceiptFact 的唯一 production generated-client adapter。
final class RemoteMessageReceiptFactQuery implements MessageReceiptFactQuery {
  const RemoteMessageReceiptFactQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final MessageReceiptFactInvocationContextFactory invocationContext;

  @override
  Future<MessageReceiptPageSlice> getReceipts(
    ChatGetMessageReceiptsQuery query,
  ) => client.chatMessageReceiptFactGetReceipts(
    query,
    context: invocationContext(ChatRequestPageIds.getReceipts),
  );
}
