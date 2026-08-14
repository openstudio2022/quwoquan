import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

abstract interface class ChatMessageRepository {
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<void> recallMessage({
    required String conversationId,
    required String messageId,
  });

  Future<ChatMessageSyncViewData> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = ChatSyncMessagesQuery.defaultLimit,
  });

  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  });

  Future<List<ChatMessageReceipt>> getReceipts({
    required String conversationId,
    required String messageId,
  });

  /// 群空间相册/文件宫格的会话媒体索引（kind=image|file，按 seq DESC 分页）。
  Future<ConversationAssetPage> listConversationAssets({
    required String conversationId,
    required String kind,
    int? beforeSeq,
    int limit = 60,
  });
}
