import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_contact_record.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';
import 'package:quwoquan_app/core/services/cache/cache_read_result.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_message_record.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:sqflite/sqflite.dart';
part 'local_chat_search_store_impl.dart';
part 'local_chat_search_store_queries.dart';

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

  Future<CacheReadResult<List<MessageDto>>> readTimeline({
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
