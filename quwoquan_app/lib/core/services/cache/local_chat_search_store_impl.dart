part of 'local_chat_search_store.dart';

class LocalChatSearchStore implements LocalChatSearchReader {
  LocalChatSearchStore({String? databasePath, DatabaseFactory? databaseFactory})
    : this._internal(
        databasePath: databasePath,
        databaseFactory: databaseFactory,
      );

  LocalChatSearchStore._internal({this._databasePath, this._databaseFactory});

  static final LocalChatSearchStore shared = LocalChatSearchStore();
  static bool _ffiInitialized = false;

  final String? _databasePath;
  final DatabaseFactory? _databaseFactory;
  Future<Database>? _databaseFuture;

  Future<void> ensureReady() async {
    await _database;
  }

  Future<void> close() async {
    final databaseFuture = _databaseFuture;
    _databaseFuture = null;
    if (databaseFuture == null) {
      return;
    }
    final database = await databaseFuture;
    if (database.isOpen) {
      await database.close();
    }
  }

  Future<void> upsertContacts({
    required LocalSearchNamespace namespace,
    required List<LocalChatSearchContactRecord> contacts,
  }) async {
    if (contacts.isEmpty) {
      return;
    }
    final database = await _database;
    final batch = database.batch();
    final now = DateTime.now().toIso8601String();
    _upsertNamespace(batch, namespace, updatedAt: now);
    for (final contact in contacts) {
      final contactId = contact.contactId.trim();
      if (contactId.isEmpty) {
        continue;
      }
      final displayNameRaw = contact.displayName.trim();
      final displayName = displayNameRaw.isNotEmpty
          ? displayNameRaw
          : contactId;
      final nickname = contact.nickname.trim();
      final username = contact.username.trim();
      final subtitle = contact.subtitle.trim();
      final headline = contact.headline.trim();
      final remark = contact.remark.trim();
      final conversationId = contact.conversationId.trim();
      final payload = <String, Object?>{
        ...contact.toWireMap(),
        'displayName': displayName,
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
        'updated_at': now,
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

  @override
  Future<List<LocalChatSearchContactRecord>> searchContacts({
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
          final record = LocalChatSearchContactRecord.fromWireMap(payload);
          return record.copyWith(
            matchedField: matchedField,
            highlightText: _highlightText(payload, matchedField),
          );
        })
        .where((item) => item.contactId.isNotEmpty)
        .toList(growable: false);
  }

  Future<List<ConversationSearchItemView>> listConversationViews({
    required LocalSearchNamespace namespace,
    int limit = 200,
  }) async {
    final records = await listConversationRecords(
      namespace: namespace,
      limit: limit,
    );
    return records
        .map((record) => record.toConversationSearchItemView())
        .where((item) => item.conversationId.isNotEmpty)
        .toList(growable: false);
  }

  Future<List<ConversationCacheRecord>> listConversationRecords({
    required LocalSearchNamespace namespace,
    int? limit = 200,
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
        .map(
          (row) => _conversationRecordFromPayload(
            _decodePayload(row['payload_json']),
          ),
        )
        .where((item) => item.id.isNotEmpty)
        .toList(growable: false);
  }

  @override
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
          final matchedField = _matchedField(query, <String, String>{
            'title': _string(row['title']),
            'lastMessagePreview': _string(row['last_message_preview']),
          });
          final record = _conversationRecordFromPayload(payload);
          return record.toConversationSearchItemView(
            matchedField: matchedField,
            highlightText: _highlightText(payload, matchedField),
          );
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

  @override
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
      final matchedField = _matchedField(query, <String, String>{
        'content': _string(row['content_preview']),
        'senderDisplayName': _string(row['sender_display_name']),
        'conversationTitle': _string(row['conversation_title']),
      });
      final item = LocalChatSearchMessageRecord.fromProjectionMap(payload)
          .copyWith(
            matchedField: matchedField,
            highlightText: _highlightText(payload, matchedField),
          )
          .toMessageSearchItemView();
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

  Future<int> lastUserSyncSeq({required LocalSearchNamespace namespace}) async {
    return lastSeqForConversation(
      namespace: namespace,
      conversationId: '__user_sync__',
    );
  }

  Future<void> saveUserSyncSeq({
    required LocalSearchNamespace namespace,
    required int syncSeq,
  }) async {
    final database = await _database;
    await database.insert('chat_sync_state', <String, Object?>{
      'namespace_key': namespace.key,
      'conversation_id': '__user_sync__',
      'last_seq': syncSeq,
      'updated_at': DateTime.now().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> updateConversationAvatar({
    required LocalSearchNamespace namespace,
    required String conversationId,
    required String avatarUrl,
    int? groupAvatarVersion,
    String? groupAvatarSourceHash,
    bool propagateToMessages = false,
  }) async {
    if (conversationId.trim().isEmpty) {
      return;
    }
    final database = await _database;
    final rows = await database.query(
      'chat_conversations',
      columns: const <String>['payload_json'],
      where: 'namespace_key = ? AND conversation_id = ?',
      whereArgs: <Object?>[namespace.key, conversationId.trim()],
      limit: 1,
    );
    if (rows.isNotEmpty) {
      final payload = _decodePayload(rows.first['payload_json']);
      final updatedPayload = _conversationRecordFromPayload(payload)
          .copyWith(
            avatarUrl: avatarUrl,
            groupAvatarVersion: groupAvatarVersion,
            groupAvatarSourceHash: groupAvatarSourceHash,
          )
          .toCacheMap();
      await database.update(
        'chat_conversations',
        <String, Object?>{
          'avatar_url': avatarUrl,
          'payload_json': jsonEncode(updatedPayload),
          'updated_at': DateTime.now().toIso8601String(),
        },
        where: 'namespace_key = ? AND conversation_id = ?',
        whereArgs: <Object?>[namespace.key, conversationId.trim()],
      );
    }
    if (propagateToMessages) {
      await database.update(
        'chat_messages',
        <String, Object?>{'conversation_avatar_url': avatarUrl},
        where: 'namespace_key = ? AND conversation_id = ?',
        whereArgs: <Object?>[namespace.key, conversationId.trim()],
      );
    }
  }

  Future<List<String>> listConversationIds({
    required LocalSearchNamespace namespace,
  }) async {
    final database = await _database;
    final rows = await database.query(
      'chat_conversations',
      columns: const <String>['conversation_id'],
      where: 'namespace_key = ?',
      whereArgs: <Object?>[namespace.key],
      orderBy: 'updated_at DESC',
    );
    return rows
        .map((row) => row['conversation_id']?.toString().trim() ?? '')
        .where((id) => id.isNotEmpty)
        .toList(growable: false);
  }

  Future<void> updateContactAvatar({
    required LocalSearchNamespace namespace,
    required String userId,
    required String avatarUrl,
    int? avatarVersion,
  }) async {
    if (userId.trim().isEmpty || avatarUrl.trim().isEmpty) {
      return;
    }
    final resolvedAvatarUrl = resolveAvatarImageUrl(
      avatarUrl,
      avatarVersion: avatarVersion,
    );
    final database = await _database;
    final rows = await database.query(
      'chat_contacts',
      columns: const <String>['contact_id', 'payload_json'],
      where: 'namespace_key = ? AND contact_id = ?',
      whereArgs: <Object?>[namespace.key, userId.trim()],
      limit: 1,
    );
    if (rows.isEmpty) {
      return;
    }
    final payload = _decodePayload(rows.first['payload_json']);
    final updatedPayload = LocalChatSearchContactRecord.fromWireMap(
      payload,
    ).copyWith(avatarUrl: resolvedAvatarUrl).toWireMap();
    await database.update(
      'chat_contacts',
      <String, Object?>{
        'payload_json': jsonEncode(updatedPayload),
        'updated_at': DateTime.now().toIso8601String(),
      },
      where: 'namespace_key = ? AND contact_id = ?',
      whereArgs: <Object?>[namespace.key, userId.trim()],
    );
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

  /// 不可逆账号终态专用：清除本机全部账号/Persona 的聊天搜索投影。
  Future<void> clearAllNamespaces() async {
    final database = await _database;
    const tables = <String>[
      'chat_contacts',
      'chat_contacts_fts',
      'chat_conversations',
      'chat_conversations_fts',
      'chat_messages',
      'chat_messages_fts',
      'chat_sync_state',
      'search_namespaces',
    ];
    await database.transaction((transaction) async {
      final batch = transaction.batch();
      for (final table in tables) {
        batch.delete(table);
      }
      await batch.commit(noResult: true);
    });
    for (final table in tables) {
      final rows = await database.rawQuery(
        'SELECT COUNT(*) AS count FROM $table',
      );
      if (((rows.first['count'] as num?)?.toInt() ?? 0) != 0) {
        throw StateError('local chat search cleanup left rows in $table');
      }
    }
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

  Map<String, Object?> _decodePayload(Object? rawJson) {
    final text = _string(rawJson);
    if (text.isEmpty) {
      throw const FormatException('local chat search payload is empty');
    }
    final Object? decoded = jsonDecode(text);
    if (decoded is! Map) {
      throw const FormatException(
        'local chat search payload must be an object',
      );
    }
    final payload = <String, Object?>{};
    for (final entry in decoded.entries) {
      if (entry.key is! String) {
        throw const FormatException(
          'local chat search payload keys must be strings',
        );
      }
      payload[entry.key as String] = entry.value;
    }
    return payload;
  }

  ConversationCacheRecord _conversationRecordFromPayload(
    Map<String, Object?> payload,
  ) {
    return ConversationCacheRecord.fromCacheMap(payload);
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
        options: OpenDatabaseOptions(
          version: 3,
          onCreate: _onCreate,
          onUpgrade: _onUpgrade,
        ),
      );
    }
    return openDatabase(
      path,
      version: 3,
      onCreate: _onCreate,
      onUpgrade: _onUpgrade,
    );
  }

  Future<void> _onUpgrade(
    Database database,
    int oldVersion,
    int newVersion,
  ) async {
    if (oldVersion >= 3) {
      return;
    }
    await _dropAllTables(database);
    await _onCreate(database, newVersion);
  }

  Future<void> _dropAllTables(Database database) async {
    await database.execute('DROP TABLE IF EXISTS chat_sync_state');
    await database.execute('DROP TABLE IF EXISTS chat_messages_fts');
    await database.execute('DROP TABLE IF EXISTS chat_messages');
    await database.execute('DROP TABLE IF EXISTS chat_conversations_fts');
    await database.execute('DROP TABLE IF EXISTS chat_conversations');
    await database.execute('DROP TABLE IF EXISTS chat_contacts_fts');
    await database.execute('DROP TABLE IF EXISTS chat_contacts');
    await database.execute('DROP TABLE IF EXISTS search_namespaces');
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
    // 移动端 / macOS 使用 sqflite 插件原生实现；VM 单测通过构造函数注入 databaseFactory。
    _ffiInitialized = true;
  }

  String _highlightText(Map<String, Object?> payload, String? matchedField) {
    switch (matchedField) {
      case 'displayName':
        return _string(payload['displayName']);
      case 'nickname':
        return _string(payload['nickname']);
      case 'username':
        return _string(payload['username']);
      case 'headline':
        return _string(payload['headline']);
      case 'remark':
        return _string(payload['remark']);
      case 'title':
        return _string(payload['title']);
      case 'lastMessagePreview':
        return _string(payload['lastMessagePreview']);
      case 'content':
        return _string(payload['contentPreview']);
      case 'senderDisplayName':
        return _string(payload['senderDisplayName']);
      case 'conversationTitle':
        return _string(payload['conversationTitle']);
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
