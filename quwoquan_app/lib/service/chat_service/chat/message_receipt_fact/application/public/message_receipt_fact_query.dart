import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ChatGetMessageReceiptsQuery, MessageReceiptPageSlice;

/// MessageReceiptFact 对象的公开查询端口。
abstract interface class MessageReceiptFactQuery {
  Future<MessageReceiptPageSlice> getReceipts(
    ChatGetMessageReceiptsQuery query,
  );
}
