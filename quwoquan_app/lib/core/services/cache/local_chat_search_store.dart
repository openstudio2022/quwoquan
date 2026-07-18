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

/// Named façade over a single sqflite row (`Map<String, Object?>`), used where
/// id-ordered reads return raw driver maps.
final class LocalChatSearchSqliteRow {
  LocalChatSearchSqliteRow(this.values);

  final Map<String, Object?> values;

  Object? operator [](String key) => values[key];
}
