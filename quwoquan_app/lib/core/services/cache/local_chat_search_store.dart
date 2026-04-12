import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

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

class LocalChatSearchStore {
  LocalChatSearchStore({String? databasePath, DatabaseFactory? databaseFactory})
    : _databasePath = databasePath,
      _databaseFactory = databaseFactory;

  static final LocalChatSearchStore shared = LocalChatSearchStore();
  static bool _ffiInitialized = false;

  final String? _databasePath;
  final DatabaseFactory? _databaseFactory;
  Future<Database>? _databaseFuture;

  Future<void> ensureReady() async {
    await _database;
  }

  Future<void> upsertContacts({
    required LocalSearchNamespace namespace,
    required List<LocalChatSearchContactWire> contacts,
  }) async {
    if (contacts.isEmpty) {
      return;
    }
    final database = await _database;
    final batch = database.batch();
    final now = DateTime.now().toIso8601String();
    _upsertNamespace(batch, namespace, updatedAt: now);
    for (final contact in contacts) {
      final contactId = _contactId(contact);
      if (contactId.isEmpty) {
        continue;
      }
      final displayName = _firstNonEmpty(<Object?>[
        contact['displayName'],
        contact['nickname'],
        contact['username'],
        contactId,
      ]);
      final nickname = _string(contact['nickname']);
      final username = _string(contact['username']);
      final subtitle = _string(contact['subtitle']);
      final headline = _firstNonEmpty(<Object?>[
        contact['headline'],
        contact['bio'],
      ]);
      final remark = _string(contact['remark']);
      final conversationId = _string(
        contact['conversationId'] ?? contact['directConversationId'],
      );
      final payload = <String, Object?>{
        ...contact,
        'contactId': contactId,
        'displayName': displayName,
        if (conversationId.isNotEmpty) 'conversationId': conversationId,
      };
      final searchableText = _searchableText(<Object?>[
        displayName,
        nickname,
        username,
        subtitle,
        headline,
        remark,
        contactId,
      ]);
      batch.insert('chat_contacts', <String, Object?>{
        'namespace_key': namespace.key,
        'contact_id': contactId,
        'display_name': displayName,
        'nickname': nickname,
        'username': username,
        'subtitle': subtitle,
        'headline': headline,
        'remark': remark,
        'conversation_id': conversationId,
        'searchable_text': searchableText,
        'payload_json': jsonEncode(payload),
        'updated_at': _string(contact['updatedAt']).isNotEmpty
            ? _string(contact['updatedAt'])
            : now,
      }, conflictAlgorithm: ConflictAlgorithm.replace);
      batch.delete(
        'chat_contacts_fts',
        where: 'namespace_key = ? AND contact_id = ?',
        whereArgs: <Object?>[namespace.key, contactId],
      );
      batch.insert('chat_contacts_fts', <String, Object?>{
        'namespace_key': namespace.key,
        'contact_id': contactId,
        'searchable_text': searchableText,
      });
    }
    await batch.commit(noResult: true);
  }

  Future<void> upsertConversations({
    required LocalSearchNamespace namespace,
    required List<LocalChatSearchConversationWire> conversations,
  }) async {
    if (conversations.isEmpty) {
      return;
    }
    final database = await _database;
    final batch = database.batch();
    final now = DateTime.now().toIso8601String();
    _upsertNamespace(batch, namespace, updatedAt: now);
    for (final conversation in conversations) {
      final conversationId = _conversationId(
        Map<String, Object?>.from(conversation),
      );
      if (conversationId.isEmpty) {
        continue;
      }
      final type = _string(conversation['type']).isNotEmpty
          ? _string(conversation['type'])
          : 'direct';
      final title = _firstNonEmpty(<Object?>[
        conversation['title'],
        conversation['conversationTitle'],
        conversationId,
      ]);
      final avatarUrl = _string(conversation['avatarUrl']);
      final avatarCompositeUrls = _stringList(
        conversation['avatarCompositeUrls'] ?? conversation['memberAvatars'],
      );
      final lastMessagePreview = _firstNonEmpty(<Object?>[
        conversation['lastMessagePreview'],
        conversation['highlightText'],
      ]);
      final lastMessageAt = _firstNonEmpty(<Object?>[
        conversation['lastMessageAt'],
        conversation['lastMessageTime'],
      ]);
      final circleId = _string(conversation['circleId']);
      final circleGroupId = _string(conversation['circleGroupId']);
      final settingsUpdatedAt = _firstNonEmpty(<Object?>[
        conversation['settingsUpdatedAt'],
        conversation['updatedAt'],
        now,
      ]);
      final payload = <String, dynamic>{
        ...conversation,
        'conversationId': conversationId,
        'id': conversationId,
        '_id': conversationId,
        'title': title,
        'type': type,
        'avatarUrl': avatarUrl,
        'avatarCompositeUrls': avatarCompositeUrls,
        'lastMessagePreview': lastMessagePreview,
        'lastMessageAt': lastMessageAt,
        'lastMessageTime': lastMessageAt,
        'settingsUpdatedAt': settingsUpdatedAt,
        if (circleId.isNotEmpty) 'circleId': circleId,
        if (circleGroupId.isNotEmpty) 'circleGroupId': circleGroupId,
      };
      final searchableText = _searchableText(<Object?>[
        title,
        lastMessagePreview,
        circleId,
        circleGroupId,
      ]);
      batch.insert('chat_conversations', <String, Object?>{
        'namespace_key': namespace.key,
        'conversation_id': conversationId,
        'type': type,
        'title': title,
        'avatar_url': avatarUrl,
        'avatar_composite_urls_json': jsonEncode(avatarCompositeUrls),
        'last_message_preview': lastMessagePreview,
        'last_message_at': lastMessageAt,
        'member_count': (conversation['memberCount'] as num?)?.toInt() ?? 0,
        'circle_id': circleId,
        'circle_group_id': circleGroupId,
        'settings_updated_at': settingsUpdatedAt,
        'searchable_text': searchableText,
        'payload_json': jsonEncode(payload),
        'updated_at': _firstNonEmpty(<Object?>[
          conversation['updatedAt'],
          settingsUpdatedAt,
          now,
        ]),
      }, conflictAlgorithm: ConflictAlgorithm.replace);
      batch.delete(
        'chat_conversations_fts',
        where: 'namespace_key = ? AND conversation_id = ?',
        whereArgs: <Object?>[namespace.key, conversationId],
      );
      batch.insert('chat_conversations_fts', <String, Object?>{
        'namespace_key': namespace.key,
        'conversation_id': conversationId,
        'searchable_text': searchableText,
      });
    }
    await batch.commit(noResult: true);
  }

  Future<void> upsertMessages({
    required LocalSearchNamespace namespace,
    required List<Map<String, dynamic>> messages,
    Map<String, dynamic>? conversation,
  }) async {
    if (messages.isEmpty) {
      return;
    }
    final database = await _database;
    final batch = database.batch();
    final now = DateTime.now().toIso8601String();
    _upsertNamespace(batch, namespace, updatedAt: now);
    final fallbackConversationId = _conversationId(
      conversation == null ? null : Map<String, Object?>.from(conversation),
    );
    final fallbackConversationType = _string(conversation?['type']);
    final fallbackConversationTitle = _firstNonEmpty(<Object?>[
      conversation?['title'],
      conversation?['conversationTitle'],
    ]);
    final fallbackConversationAvatar = _string(conversation?['avatarUrl']);
    var maxSeq = 0;
    for (final message in messages) {
      final messageId = _string(
        message['messageId'] ?? message['id'] ?? message['_id'],
      );
      if (messageId.isEmpty) {
        continue;
      }
      final recalledAt = _string(message['recalledAt']);
      final status = _string(message['status']);
      final deleted =
          recalledAt.isNotEmpty ||
          status == 'recalled' ||
          status == 'deleted' ||
          message['deleted'] == true ||
          message['isDeleted'] == true;
      if (deleted) {
        _deleteMessageInBatch(
          batch,
          namespace: namespace,
          messageId: messageId,
        );
        continue;
      }
      final conversationId = _firstNonEmpty(<Object?>[
        message['conversationId'],
        fallbackConversationId,
      ]);
      if (conversationId.isEmpty) {
        continue;
      }
      final seq = (message['seq'] as num?)?.toInt() ?? 0;
      if (seq > maxSeq) {
        maxSeq = seq;
      }
      final conversationType = _firstNonEmpty(<Object?>[
        message['conversationType'],
        fallbackConversationType,
      ]);
      final conversationTitle = _firstNonEmpty(<Object?>[
        message['conversationTitle'],
        fallbackConversationTitle,
      ]);
      final conversationAvatarUrl = _firstNonEmpty(<Object?>[
        message['conversationAvatarUrl'],
        fallbackConversationAvatar,
      ]);
      final senderProfileSubjectId = _firstNonEmpty(<Object?>[
        message['senderProfileSubjectId'],
        message['senderId'],
      ]);
      final senderDisplayName = _firstNonEmpty(<Object?>[
        message['senderDisplayName'],
        message['senderDisplayNameSnapshot'],
        message['senderName'],
      ]);
      final senderAvatarUrl = _firstNonEmpty(<Object?>[
        message['senderAvatarUrl'],
        message['senderAvatarUrlSnapshot'],
      ]);
      final messageType = _firstNonEmpty(<Object?>[
        message['messageType'],
        message['type'],
        'text',
      ]);
      final contentPreview = _firstNonEmpty(<Object?>[
        message['contentPreview'],
        message['content'],
      ]);
      final timestamp = _firstNonEmpty(<Object?>[
        message['timestamp'],
        message['createdAt'],
        now,
      ]);
      final payload = <String, dynamic>{
        ...message,
        'messageId': messageId,
        'id': messageId,
        '_id': messageId,
        'conversationId': conversationId,
        'conversationType': conversationType,
        'conversationTitle': conversationTitle,
        'conversationAvatarUrl': conversationAvatarUrl,
        'senderProfileSubjectId': senderProfileSubjectId,
        'senderDisplayName': senderDisplayName,
        'senderAvatarUrl': senderAvatarUrl,
        'messageType': messageType,
        'contentPreview': contentPreview,
        'timestamp': timestamp,
      };
      final searchableText = _searchableText(<Object?>[
        contentPreview,
        senderDisplayName,
        conversationTitle,
      ]);
      batch.insert('chat_messages', <String, Object?>{
        'namespace_key': namespace.key,
        'message_id': messageId,
        'conversation_id': conversationId,
        'conversation_type': conversationType,
        'conversation_title': conversationTitle,
        'conversation_avatar_url': conversationAvatarUrl,
        'sender_profile_subject_id': senderProfileSubjectId,
        'sender_display_name': senderDisplayName,
        'sender_avatar_url': senderAvatarUrl,
        'message_type': messageType,
        'content_preview': contentPreview,
        'searchable_text': searchableText,
        'seq': seq,
        'timestamp': timestamp,
        'payload_json': jsonEncode(payload),
        'updated_at': now,
      }, conflictAlgorithm: ConflictAlgorithm.replace);
      batch.delete(
        'chat_messages_fts',
        where: 'namespace_key = ? AND message_id = ?',
        whereArgs: <Object?>[namespace.key, messageId],
      );
      batch.insert('chat_messages_fts', <String, Object?>{
        'namespace_key': namespace.key,
        'message_id': messageId,
        'searchable_text': searchableText,
      });
      if (conversationId.isNotEmpty) {
        batch.insert('chat_sync_state', <String, Object?>{
          'namespace_key': namespace.key,
          'conversation_id': conversationId,
          'last_seq': seq,
          'updated_at': now,
        }, conflictAlgorithm: ConflictAlgorithm.replace);
      }
    }
    if (fallbackConversationId.isNotEmpty && maxSeq > 0) {
      batch.insert('chat_sync_state', <String, Object?>{
        'namespace_key': namespace.key,
        'conversation_id': fallbackConversationId,
        'last_seq': maxSeq,
        'updated_at': now,
      }, conflictAlgorithm: ConflictAlgorithm.replace);
    }
    await batch.commit(noResult: true);
  }

  Future<List<Map<String, dynamic>>> searchContacts({
    required LocalSearchNamespace namespace,
    required String query,
    int limit = 20,
  }) async {
    final database = await _database;
    final ids = await _searchIds(
      database: database,
      table: 'chat_contacts',
      ftsTable: 'chat_contacts_fts',
      idColumn: 'contact_id',
      namespace: namespace,
      query: query,
      limit: limit,
      orderBy: 'updated_at DESC',
    );
    final rows = await _rowsForIds(
      database: database,
      table: 'chat_contacts',
      idColumn: 'contact_id',
      ids: ids,
    );
    return rows
        .map((row) {
          final payload = _decodePayload(row['payload_json']);
          final matchedField = _matchedField(query, <String, String>{
            'displayName': _string(row['display_name']),
            'nickname': _string(row['nickname']),
            'username': _string(row['username']),
            'subtitle': _string(row['subtitle']),
            'headline': _string(row['headline']),
            'remark': _string(row['remark']),
          });
          return <String, dynamic>{
            ...payload,
            'matchedField': matchedField,
            'highlightText': _highlightText(payload, matchedField),
          };
        })
        .toList(growable: false);
  }

  Future<List<Map<String, dynamic>>> listConversationPayloads({
    required LocalSearchNamespace namespace,
    int limit = 200,
  }) async {
    final database = await _database;
    final rows = await database.query(
      'chat_conversations',
      where: 'namespace_key = ?',
      whereArgs: <Object?>[namespace.key],
      orderBy: 'updated_at DESC',
      limit: limit,
    );
    return rows
        .map((row) => _decodePayload(row['payload_json']))
        .where((row) => row.isNotEmpty)
        .toList(growable: false);
  }

  Future<List<ConversationSearchItemView>> listConversationViews({
    required LocalSearchNamespace namespace,
    int limit = 200,
  }) async {
    final payloads = await listConversationPayloads(
      namespace: namespace,
      limit: limit,
    );
    return payloads
        .map(ConversationSearchItemView.fromMap)
        .where((item) => item.conversationId.isNotEmpty)
        .toList(growable: false);
  }

  Future<List<ConversationSearchItemView>> searchConversations({
    required LocalSearchNamespace namespace,
    required String query,
    String? conversationType,
    int limit = 20,
  }) async {
    final database = await _database;
    final ids = await _searchIds(
      database: database,
      table: 'chat_conversations',
      ftsTable: 'chat_conversations_fts',
      idColumn: 'conversation_id',
      namespace: namespace,
      query: query,
      limit: limit,
      orderBy: 'last_message_at DESC, updated_at DESC',
    );
    final rows = await _rowsForIds(
      database: database,
      table: 'chat_conversations',
      idColumn: 'conversation_id',
      ids: ids,
    );
    final normalizedType = _normalize(conversationType);
    return rows
        .map((row) {
          final payload = _decodePayload(row['payload_json']);
          payload['matchedField'] = _matchedField(query, <String, String>{
            'title': _string(row['title']),
            'lastMessagePreview': _string(row['last_message_preview']),
          });
          payload['highlightText'] = _highlightText(
            payload,
            payload['matchedField']?.toString(),
          );
          return ConversationSearchItemView.fromMap(payload);
        })
        .where((item) {
          if (item.conversationId.isEmpty) {
            return false;
          }
          if (normalizedType == null) {
            return true;
          }
          return _normalize(item.type) == normalizedType;
        })
        .take(limit)
        .toList(growable: false);
  }

  Future<List<MessageSearchItemView>> searchMessages({
    required LocalSearchNamespace namespace,
    required String query,
    String? conversationType,
    int limit = 20,
  }) async {
    final database = await _database;
    final ids = await _searchIds(
      database: database,
      table: 'chat_messages',
      ftsTable: 'chat_messages_fts',
      idColumn: 'message_id',
      namespace: namespace,
      query: query,
      limit: limit,
      orderBy: 'timestamp DESC',
    );
    final rows = await _rowsForIds(
      database: database,
      table: 'chat_messages',
      idColumn: 'message_id',
      ids: ids,
    );
    final normalizedType = _normalize(conversationType);
    final results = <MessageSearchItemView>[];
    for (final row in rows) {
      final payloadConversationType = _normalize(
        row['conversation_type']?.toString(),
      );
      if (normalizedType != null && payloadConversationType != normalizedType) {
        continue;
      }
      final payload = _decodePayload(row['payload_json']);
      payload['matchedField'] = _matchedField(query, <String, String>{
        'content': _string(row['content_preview']),
        'senderDisplayName': _string(row['sender_display_name']),
        'conversationTitle': _string(row['conversation_title']),
      });
      payload['highlightText'] = _highlightText(
        payload,
        payload['matchedField']?.toString(),
      );
      final item = MessageSearchItemView.fromMap(payload);
      if (item.messageId.isEmpty) {
        continue;
      }
      results.add(item);
      if (results.length >= limit) {
        break;
      }
    }
    return results;
  }

  Future<int> lastSeqForConversation({
    required LocalSearchNamespace namespace,
    required String conversationId,
  }) async {
    if (conversationId.trim().isEmpty) {
      return 0;
    }
    final database = await _database;
    final rows = await database.query(
      'chat_sync_state',
      columns: const <String>['last_seq'],
      where: 'namespace_key = ? AND conversation_id = ?',
      whereArgs: <Object?>[namespace.key, conversationId.trim()],
      limit: 1,
    );
    if (rows.isEmpty) {
      return 0;
    }
    return (rows.first['last_seq'] as num?)?.toInt() ?? 0;
  }

  Future<bool> hasConversation({
    required LocalSearchNamespace namespace,
    required String conversationId,
  }) async {
    if (conversationId.trim().isEmpty) {
      return false;
    }
    final database = await _database;
    final rows = await database.query(
      'chat_conversations',
      columns: const <String>['conversation_id'],
      where: 'namespace_key = ? AND conversation_id = ?',
      whereArgs: <Object?>[namespace.key, conversationId.trim()],
      limit: 1,
    );
    return rows.isNotEmpty;
  }

  Future<bool> hasAnyData(LocalSearchNamespace namespace) async {
    final database = await _database;
    final counts = await Future.wait<int>(<Future<int>>[
      _countRows(database, 'chat_contacts', namespace),
      _countRows(database, 'chat_conversations', namespace),
      _countRows(database, 'chat_messages', namespace),
    ]);
    return counts.any((count) => count > 0);
  }

  Future<void> removeMessage({
    required LocalSearchNamespace namespace,
    required String messageId,
  }) async {
    if (messageId.trim().isEmpty) {
      return;
    }
    final database = await _database;
    final batch = database.batch();
    _deleteMessageInBatch(batch, namespace: namespace, messageId: messageId);
    await batch.commit(noResult: true);
  }

  Future<void> removeConversation({
    required LocalSearchNamespace namespace,
    required String conversationId,
  }) async {
    if (conversationId.trim().isEmpty) {
      return;
    }
    final database = await _database;
    final messageRows = await database.query(
      'chat_messages',
      columns: const <String>['message_id'],
      where: 'namespace_key = ? AND conversation_id = ?',
      whereArgs: <Object?>[namespace.key, conversationId.trim()],
    );
    final messageIds = messageRows
        .map((row) => _string(row['message_id']))
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
    final batch = database.batch();
    batch.delete(
      'chat_conversations',
      where: 'namespace_key = ? AND conversation_id = ?',
      whereArgs: <Object?>[namespace.key, conversationId.trim()],
    );
    batch.delete(
      'chat_conversations_fts',
      where: 'namespace_key = ? AND conversation_id = ?',
      whereArgs: <Object?>[namespace.key, conversationId.trim()],
    );
    batch.delete(
      'chat_messages',
      where: 'namespace_key = ? AND conversation_id = ?',
      whereArgs: <Object?>[namespace.key, conversationId.trim()],
    );
    for (final messageId in messageIds) {
      batch.delete(
        'chat_messages_fts',
        where: 'namespace_key = ? AND message_id = ?',
        whereArgs: <Object?>[namespace.key, messageId],
      );
    }
    batch.delete(
      'chat_sync_state',
      where: 'namespace_key = ? AND conversation_id = ?',
      whereArgs: <Object?>[namespace.key, conversationId.trim()],
    );
    await batch.commit(noResult: true);
  }

  Future<void> deleteNamespace(LocalSearchNamespace namespace) async {
    final database = await _database;
    final batch = database.batch();
    for (final table in const <String>[
      'chat_contacts',
      'chat_contacts_fts',
      'chat_conversations',
      'chat_conversations_fts',
      'chat_messages',
      'chat_messages_fts',
      'chat_sync_state',
      'search_namespaces',
    ]) {
      batch.delete(
        table,
        where: 'namespace_key = ?',
        whereArgs: <Object?>[namespace.key],
      );
    }
    await batch.commit(noResult: true);
  }

  Future<int> _countRows(
    Database database,
    String table,
    LocalSearchNamespace namespace,
  ) async {
    final result = await database.rawQuery(
      'SELECT COUNT(*) AS count FROM $table WHERE namespace_key = ?',
      <Object?>[namespace.key],
    );
    return (result.first['count'] as num?)?.toInt() ?? 0;
  }

  Future<List<String>> _searchIds({
    required Database database,
    required String table,
    required String ftsTable,
    required String idColumn,
    required LocalSearchNamespace namespace,
    required String query,
    required int limit,
    required String orderBy,
  }) async {
    final normalizedQuery = _normalize(query);
    if (normalizedQuery == null) {
      return const <String>[];
    }
    final ids = <String>[];
    final seen = <String>{};
    final ftsQuery = _buildFtsQuery(normalizedQuery);
    if (ftsQuery != null) {
      try {
        final ftsRows = await database.rawQuery(
          'SELECT $idColumn FROM $ftsTable WHERE namespace_key = ? AND $ftsTable MATCH ? LIMIT ?',
          <Object?>[namespace.key, ftsQuery, limit],
        );
        for (final row in ftsRows) {
          final id = _string(row[idColumn]);
          if (id.isNotEmpty && seen.add(id)) {
            ids.add(id);
          }
        }
      } catch (_) {}
    }
    final likeRows = await database.rawQuery(
      'SELECT $idColumn FROM $table WHERE namespace_key = ? AND searchable_text LIKE ? ORDER BY $orderBy LIMIT ?',
      <Object?>[namespace.key, '%$normalizedQuery%', limit],
    );
    for (final row in likeRows) {
      final id = _string(row[idColumn]);
      if (id.isNotEmpty && seen.add(id)) {
        ids.add(id);
      }
    }
    return ids.take(limit).toList(growable: false);
  }

  Future<List<LocalChatSearchSqliteRow>> _rowsForIds({
    required Database database,
    required String table,
    required String idColumn,
    required List<String> ids,
  }) async {
    if (ids.isEmpty) {
      return const <LocalChatSearchSqliteRow>[];
    }
    final placeholders = List<String>.filled(ids.length, '?').join(',');
    final rows = await database.rawQuery(
      'SELECT * FROM $table WHERE $idColumn IN ($placeholders)',
      ids,
    );
    final byId = <String, Map<String, Object?>>{
      for (final row in rows) _string(row[idColumn]): row,
    };
    return ids
        .map((id) => byId[id])
        .whereType<Map<String, Object?>>()
        .map(LocalChatSearchSqliteRow.new)
        .toList(growable: false);
  }

  void _upsertNamespace(
    Batch batch,
    LocalSearchNamespace namespace, {
    required String updatedAt,
  }) {
    batch.insert('search_namespaces', <String, Object?>{
      'namespace_key': namespace.key,
      'owner_user_id': namespace.ownerUserId,
      'profile_subject_id': namespace.profileSubjectId,
      'sub_account_id': namespace.subAccountId,
      'subject_type': namespace.subjectType,
      'persona_context_version': namespace.personaContextVersion,
      'updated_at': updatedAt,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  void _deleteMessageInBatch(
    Batch batch, {
    required LocalSearchNamespace namespace,
    required String messageId,
  }) {
    batch.delete(
      'chat_messages',
      where: 'namespace_key = ? AND message_id = ?',
      whereArgs: <Object?>[namespace.key, messageId.trim()],
    );
    batch.delete(
      'chat_messages_fts',
      where: 'namespace_key = ? AND message_id = ?',
      whereArgs: <Object?>[namespace.key, messageId.trim()],
    );
  }

  Map<String, dynamic> _decodePayload(Object? rawJson) {
    final text = _string(rawJson);
    if (text.isEmpty) {
      return const <String, dynamic>{};
    }
    try {
      final decoded = jsonDecode(text);
      if (decoded is Map) {
        return decoded.cast<String, dynamic>();
      }
    } catch (_) {}
    return const <String, dynamic>{};
  }

  Future<Database> get _database async {
    return _databaseFuture ??= _openDatabase();
  }

  Future<Database> _openDatabase() async {
    _configureFactory();
    final path = await _resolveDatabasePath();
    final factory = _databaseFactory;
    if (factory != null) {
      return factory.openDatabase(
        path,
        options: OpenDatabaseOptions(version: 1, onCreate: _onCreate),
      );
    }
    return openDatabase(path, version: 1, onCreate: _onCreate);
  }

  Future<String> _resolveDatabasePath() async {
    if (_databasePath != null && _databasePath.trim().isNotEmpty) {
      final path = _databasePath.trim();
      final lastSeparator = path.lastIndexOf(Platform.pathSeparator);
      if (lastSeparator > 0) {
        await Directory(
          path.substring(0, lastSeparator),
        ).create(recursive: true);
      }
      return path;
    }
    final factory = _databaseFactory;
    final basePath = factory != null
        ? await factory.getDatabasesPath()
        : await getDatabasesPath();
    await Directory(basePath).create(recursive: true);
    return '$basePath${Platform.pathSeparator}quwoquan_local_chat_search.db';
  }

  void _configureFactory() {
    if (_databaseFactory != null || _ffiInitialized) {
      return;
    }
    if (Platform.isAndroid || Platform.isIOS) {
      _ffiInitialized = true;
      return;
    }
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
    _ffiInitialized = true;
  }

  Future<void> _onCreate(Database database, int version) async {
    await database.execute('''
      CREATE TABLE search_namespaces (
        namespace_key TEXT PRIMARY KEY,
        owner_user_id TEXT NOT NULL,
        profile_subject_id TEXT NOT NULL,
        sub_account_id TEXT NOT NULL,
        subject_type TEXT NOT NULL,
        persona_context_version TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    ''');
    await database.execute('''
      CREATE TABLE chat_contacts (
        namespace_key TEXT NOT NULL,
        contact_id TEXT NOT NULL,
        display_name TEXT NOT NULL,
        nickname TEXT NOT NULL,
        username TEXT NOT NULL,
        subtitle TEXT NOT NULL,
        headline TEXT NOT NULL,
        remark TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        searchable_text TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (namespace_key, contact_id)
      )
    ''');
    await database.execute('''
      CREATE VIRTUAL TABLE chat_contacts_fts
      USING fts5(
        namespace_key UNINDEXED,
        contact_id UNINDEXED,
        searchable_text,
        tokenize = 'unicode61'
      )
    ''');
    await database.execute('''
      CREATE TABLE chat_conversations (
        namespace_key TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        avatar_url TEXT NOT NULL,
        avatar_composite_urls_json TEXT NOT NULL,
        last_message_preview TEXT NOT NULL,
        last_message_at TEXT NOT NULL,
        member_count INTEGER NOT NULL DEFAULT 0,
        circle_id TEXT NOT NULL,
        circle_group_id TEXT NOT NULL,
        settings_updated_at TEXT NOT NULL,
        searchable_text TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (namespace_key, conversation_id)
      )
    ''');
    await database.execute('''
      CREATE VIRTUAL TABLE chat_conversations_fts
      USING fts5(
        namespace_key UNINDEXED,
        conversation_id UNINDEXED,
        searchable_text,
        tokenize = 'unicode61'
      )
    ''');
    await database.execute('''
      CREATE TABLE chat_messages (
        namespace_key TEXT NOT NULL,
        message_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        conversation_type TEXT NOT NULL,
        conversation_title TEXT NOT NULL,
        conversation_avatar_url TEXT NOT NULL,
        sender_profile_subject_id TEXT NOT NULL,
        sender_display_name TEXT NOT NULL,
        sender_avatar_url TEXT NOT NULL,
        message_type TEXT NOT NULL,
        content_preview TEXT NOT NULL,
        searchable_text TEXT NOT NULL,
        seq INTEGER NOT NULL DEFAULT 0,
        timestamp TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (namespace_key, message_id)
      )
    ''');
    await database.execute('''
      CREATE VIRTUAL TABLE chat_messages_fts
      USING fts5(
        namespace_key UNINDEXED,
        message_id UNINDEXED,
        searchable_text,
        tokenize = 'unicode61'
      )
    ''');
    await database.execute('''
      CREATE TABLE chat_sync_state (
        namespace_key TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        last_seq INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (namespace_key, conversation_id)
      )
    ''');
    await database.execute(
      'CREATE INDEX idx_chat_contacts_namespace_updated ON chat_contacts(namespace_key, updated_at DESC)',
    );
    await database.execute(
      'CREATE INDEX idx_chat_conversations_namespace_updated ON chat_conversations(namespace_key, updated_at DESC)',
    );
    await database.execute(
      'CREATE INDEX idx_chat_messages_namespace_time ON chat_messages(namespace_key, timestamp DESC)',
    );
    await database.execute(
      'CREATE INDEX idx_chat_messages_namespace_conversation ON chat_messages(namespace_key, conversation_id)',
    );
  }

  String _highlightText(Map<String, dynamic> payload, String? matchedField) {
    switch (matchedField) {
      case 'displayName':
        return _firstNonEmpty(<Object?>[
          payload['displayName'],
          payload['nickname'],
          payload['username'],
        ]);
      case 'nickname':
        return _string(payload['nickname']);
      case 'username':
        return _string(payload['username']);
      case 'headline':
        return _firstNonEmpty(<Object?>[payload['headline'], payload['bio']]);
      case 'remark':
        return _string(payload['remark']);
      case 'title':
        return _firstNonEmpty(<Object?>[
          payload['title'],
          payload['conversationTitle'],
        ]);
      case 'lastMessagePreview':
        return _firstNonEmpty(<Object?>[
          payload['lastMessagePreview'],
          payload['highlightText'],
        ]);
      case 'content':
        return _firstNonEmpty(<Object?>[
          payload['contentPreview'],
          payload['content'],
        ]);
      case 'senderDisplayName':
        return _firstNonEmpty(<Object?>[
          payload['senderDisplayName'],
          payload['senderDisplayNameSnapshot'],
          payload['senderName'],
        ]);
      case 'conversationTitle':
        return _firstNonEmpty(<Object?>[
          payload['conversationTitle'],
          payload['title'],
        ]);
      default:
        return '';
    }
  }

  String _matchedField(String query, Map<String, String> fields) {
    final normalizedQuery = _normalize(query);
    if (normalizedQuery == null) {
      return '';
    }
    for (final entry in fields.entries) {
      final value = _normalize(entry.value);
      if (value != null && value.contains(normalizedQuery)) {
        return entry.key;
      }
    }
    return '';
  }

  String? _buildFtsQuery(String query) {
    if (_containsCjk(query)) {
      return null;
    }
    final tokens = query
        .split(RegExp(r'\s+'))
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
    if (tokens.isEmpty) {
      return null;
    }
    return tokens
        .map((token) => '"${token.replaceAll('"', '""')}"*')
        .join(' OR ');
  }

  bool _containsCjk(String input) {
    return RegExp(r'[\u3400-\u9fff]').hasMatch(input);
  }

  String _searchableText(List<Object?> values) {
    return values
        .map((item) => _normalize(item?.toString()) ?? '')
        .where((item) => item.isNotEmpty)
        .join(' ');
  }

  List<String> _stringList(Object? raw) {
    if (raw is List) {
      return raw
          .map((item) => item.toString().trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }
    return const <String>[];
  }

  String _contactId(Map<String, Object?>? contact) {
    return _string(
      contact?['contactId'] ??
          contact?['userId'] ??
          contact?['profileSubjectId'] ??
          '',
    );
  }

  String _conversationId(Map<String, Object?>? conversation) {
    return _string(
      conversation?['conversationId'] ??
          conversation?['id'] ??
          conversation?['_id'],
    );
  }

  String _firstNonEmpty(List<Object?> values) {
    for (final value in values) {
      final text = _string(value);
      if (text.isNotEmpty) {
        return text;
      }
    }
    return '';
  }

  String _string(Object? value) {
    return value?.toString().trim() ?? '';
  }

  String? _normalize(String? value) {
    final normalized = value?.trim().toLowerCase();
    if (normalized == null || normalized.isEmpty) {
      return null;
    }
    return normalized;
  }
}
