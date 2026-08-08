import 'dart:convert';

import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline_cache.dart';
import 'package:quwoquan_app/runtime/platform/storage/local_database_path_resolver.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_contact_record.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/conversation_cache_record.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_read_result.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_message_record.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_search_namespace.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_local_hit_views.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/conversation_avatar_search_index.dart';
import 'package:sqflite/sqflite.dart';
part 'local_chat_search_store_impl.dart';
part 'local_chat_search_store_queries.dart';
part 'local_chat_search_store_support.dart';

abstract interface class LocalChatSearchReader {
  Future<List<LocalChatSearchContactRecord>> searchContacts({
    required LocalSearchNamespace namespace,
    required String query,
    int limit = 20,
  });

  Future<List<ConversationSearchItemView>> searchConversations({
    required LocalSearchNamespace namespace,
    required String query,
    String? conversationType,
    int limit = 20,
  });

  Future<List<MessageSearchItemView>> searchMessages({
    required LocalSearchNamespace namespace,
    required String query,
    String? conversationType,
    int limit = 20,
  });

  Future<CacheReadResult<List<ChatMessageViewData>>> readTimeline({
    required LocalSearchNamespace namespace,
    required String conversationId,
    int beforeSeq = 0,
    int limit = 50,
  });
}

/// Named façade over a single sqflite row (`Map<String, Object?>`), used where
/// id-ordered reads return raw driver maps.
final class LocalChatSearchSqliteRow {
  LocalChatSearchSqliteRow(this.values);

  final Map<String, Object?> values;

  Object? operator [](String key) => values[key];
}
