// ignore_for_file: prefer_initializing_formals

import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/chat_inbox_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Object-scoped App adapter for the canonical ChatInboxView projection.
final class RemoteChatInboxRepository implements ChatInboxRepository {
  const RemoteChatInboxRepository({required ChatInboxQuery query})
    : _query = query;

  final ChatInboxQuery _query;

  @override
  Future<List<ChatInboxViewData>> listInbox({
    String? cursor,
    int limit = ChatListInboxQuery.defaultLimit,
  }) async {
    final page = await _query.listInbox(
      ChatListInboxQuery(cursor: cursor, limit: limit),
    );
    return page.items.map(ChatInboxViewData.fromWire).toList(growable: false);
  }
}
