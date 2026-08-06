import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_view_data.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

/// App-facing read port for the canonical ChatInboxView projection.
abstract interface class ChatInboxRepository {
  Future<List<ChatInboxViewData>> listInbox({
    String? cursor,
    int limit = ChatListInboxQuery.defaultLimit,
  });
}
