import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_contact_record.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_message_record.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:sqflite/sqflite.dart';
part 'local_chat_search_store_impl.dart';
part 'local_chat_search_store_queries.dart';

/// 同步摄入的联系人行（与 `ChatContactDto.toMap()` 等 wire 对齐；值为 JSON 叶子或嵌套结构）。
typedef LocalChatSearchContactWire = Map<String, Object?>;

/// 会话同步 wire（与 inbox / 会话 DTO `toMap` 等对齐）。
typedef LocalChatSearchConversationWire = Map<String, dynamic>;

/// Named façade over a single sqflite row (`Map<String, Object?>`), used where
/// id-ordered reads return raw driver maps.
final class LocalChatSearchSqliteRow {
  LocalChatSearchSqliteRow(this.values);

  final Map<String, Object?> values;

  Object? operator [](String key) => values[key];
}
