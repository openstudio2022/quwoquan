part of 'local_chat_search_store.dart';

class LocalChatSearchStore
    implements
        LocalChatSearchReader,
        ChatMessageTimelineCache,
        ConversationAvatarSearchIndex {
  LocalChatSearchStore({
    required LocalDatabasePathResolver databasePathResolver,
    String? databasePath,
    DatabaseFactory? databaseFactory,
  }) : this._internal(
         databasePathResolver: databasePathResolver,
         databasePath: databasePath,
         databaseFactory: databaseFactory,
       );

  LocalChatSearchStore._internal({
    required this._databasePathResolver,
    this._databasePath,
    this._databaseFactory,
  });

  static bool _ffiInitialized = false;
  static const int _schemaVersion = 2;

  final LocalDatabasePathResolver _databasePathResolver;
  final String? _databasePath;
  final DatabaseFactory? _databaseFactory;
  Future<Database>? _databaseFuture;

  Future<void> ensureReady() async {
    await _database;
  }

  @override
  Future<void> ensureConversationAvatarIndexReady() => ensureReady();

  @override
  Future<int> lastConversationAvatarSyncSeq({
    required SearchActorScope scope,
  }) => lastUserSyncSeq(namespace: _namespaceFromAvatarScope(scope));

  @override
  Future<void> saveConversationAvatarSyncSeq({
    required SearchActorScope scope,
    required int syncSeq,
  }) => saveUserSyncSeq(
    namespace: _namespaceFromAvatarScope(scope),
    syncSeq: syncSeq,
  );

  @override
  Future<void> updateConversationAvatarProjection({
    required SearchActorScope scope,
    required String conversationId,
    required String avatarUrl,
    int? groupAvatarVersion,
    String? groupAvatarSourceHash,
  }) => updateConversationAvatar(
    namespace: _namespaceFromAvatarScope(scope),
    conversationId: conversationId,
    avatarUrl: avatarUrl,
    groupAvatarVersion: groupAvatarVersion,
    groupAvatarSourceHash: groupAvatarSourceHash,
  );

  @override
  Future<void> updateContactAvatarProjection({
    required SearchActorScope scope,
    required String userId,
    required String avatarUrl,
    required int avatarVersion,
  }) => updateContactAvatar(
    namespace: _namespaceFromAvatarScope(scope),
    userId: userId,
    avatarUrl: avatarUrl,
    avatarVersion: avatarVersion,
  );

  LocalSearchNamespace _namespaceFromAvatarScope(SearchActorScope scope) {
    return LocalSearchNamespace(
      ownerUserId: scope.ownerUserId,
      personaId: scope.personaId,
      subjectType: scope.subjectType,
      personaContextVersion: scope.personaContextVersion,
    );
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
      _queueContactUpsert(
        batch: batch,
        namespace: namespace,
        contact: contact,
        updatedAt: now,
      );
    }
    await batch.commit(noResult: true);
  }

  /// Applies a completed remote contact snapshot atomically: rows absent from
  /// [contacts] are removed only after every page has been read successfully.
  Future<void> replaceContacts({
    required LocalSearchNamespace namespace,
    required List<LocalChatSearchContactRecord> contacts,
  }) async {
    final database = await _database;
    final existingRows = await database.query(
      'chat_contacts',
      columns: const <String>['contact_id'],
      where: 'namespace_key = ?',
      whereArgs: <Object?>[namespace.key],
    );
    final remoteIDs = contacts
        .map((contact) => contact.contactId.trim())
        .where((contactId) => contactId.isNotEmpty)
        .toSet();
    final staleIDs = existingRows
        .map((row) => _string(row['contact_id']))
        .where((contactId) => !remoteIDs.contains(contactId))
        .toList(growable: false);

    final batch = database.batch();
    final now = DateTime.now().toIso8601String();
    _upsertNamespace(batch, namespace, updatedAt: now);
    for (final contact in contacts) {
      _queueContactUpsert(
        batch: batch,
        namespace: namespace,
        contact: contact,
        updatedAt: now,
      );
    }
    for (final contactId in staleIDs) {
      batch.delete(
        'chat_contacts',
        where: 'namespace_key = ? AND contact_id = ?',
        whereArgs: <Object?>[namespace.key, contactId],
      );
      batch.delete(
        'chat_contacts_fts',
        where: 'namespace_key = ? AND contact_id = ?',
        whereArgs: <Object?>[namespace.key, contactId],
      );
    }
    await batch.commit(noResult: true);
  }

  void _queueContactUpsert({
    required Batch batch,
    required LocalSearchNamespace namespace,
    required LocalChatSearchContactRecord contact,
    required String updatedAt,
  }) {
    final contactId = contact.contactId.trim();
    if (contactId.isEmpty) {
      return;
    }
    final displayNameRaw = contact.displayName.trim();
    final displayName = displayNameRaw.isNotEmpty ? displayNameRaw : contactId;
    final nickname = contact.nickname.trim();
    final subtitle = contact.subtitle.trim();
    final headline = contact.headline.trim();
    final remark = contact.remark.trim();
    final conversationId = contact.conversationId.trim();
    final payload = <String, Object?>{
      ...contact.toStorageMap(),
      'displayName': displayName,
    };
    final searchableText = _searchableText(<Object?>[
      displayName,
      nickname,
      subtitle,
      headline,
      remark,
      contact.userHandle,
      contactId,
    ]);
    batch.insert('chat_contacts', <String, Object?>{
      'namespace_key': namespace.key,
      'contact_id': contactId,
      'display_name': displayName,
      'nickname': nickname,
      'subtitle': subtitle,
      'headline': headline,
      'remark': remark,
      'conversation_id': conversationId,
      'searchable_text': searchableText,
      'payload_json': jsonEncode(payload),
      'updated_at': updatedAt,
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
            'subtitle': _string(row['subtitle']),
            'headline': _string(row['headline']),
            'remark': _string(row['remark']),
          });
          final record = LocalChatSearchContactRecord.fromStorageMap(payload);
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
  Future<CacheReadResult<List<ChatMessageViewData>>> readTimeline({
    required LocalSearchNamespace namespace,
    required String conversationId,
    int beforeSeq = 0,
    int limit = 50,
  }) async {
    final normalizedConversationId = conversationId.trim();
    if (normalizedConversationId.isEmpty || limit <= 0) {
      return const CacheReadResult<List<ChatMessageViewData>>(
        value: <ChatMessageViewData>[],
        source: CacheReadSource.disk,
        freshness: CacheFreshness.unknown,
        syncState: CacheSyncState.idle,
        cacheClass: CacheClass.recent,
        diagnostics: CacheDiagnostics(hitLayer: 'disk'),
      );
    }
    final database = await _database;
    final where = StringBuffer(
      'namespace_key = ? AND conversation_id = ? AND seq > 0',
    );
    final whereArgs = <Object?>[namespace.key, normalizedConversationId];
    if (beforeSeq > 0) {
      where.write(' AND seq < ?');
      whereArgs.add(beforeSeq);
    }
    final rows = await database.query(
      'chat_messages',
      columns: const <String>['payload_json'],
      where: where.toString(),
      whereArgs: whereArgs,
      orderBy: 'seq DESC',
      limit: limit,
    );
    final messages = rows
        .map((row) => _decodePayload(row['payload_json']))
        .map(LocalChatSearchMessageRecord.fromProjectionMap)
        .map((record) => record.toMessageViewData())
        .toList(growable: false)
        .reversed
        .toList(growable: false);
    return CacheReadResult<List<ChatMessageViewData>>(
      value: messages,
      source: CacheReadSource.disk,
      freshness: CacheFreshness.unknown,
      syncState: CacheSyncState.idle,
      cacheClass: CacheClass.recent,
      objectVersion: messages.isEmpty ? null : messages.last.seq.toString(),
      diagnostics: const CacheDiagnostics(hitLayer: 'disk'),
    );
  }

  @override
  Future<List<ChatMessageViewData>> readMessages({
    required ChatMessageTimelineScope scope,
    required String conversationId,
    int beforeSeq = 0,
    int limit = 50,
  }) async {
    final result = await readTimeline(
      namespace: _chatMessageNamespace(scope),
      conversationId: conversationId,
      beforeSeq: beforeSeq,
      limit: limit,
    );
    return result.value;
  }

  @override
  Future<void> writeMessages({
    required ChatMessageTimelineScope scope,
    required List<ChatMessageViewData> messages,
  }) {
    return upsertMessages(
      namespace: _chatMessageNamespace(scope),
      messages: messages
          .map(LocalChatSearchMessageRecord.fromMessageViewData)
          .toList(growable: false),
    );
  }

  @override
  Future<void> removeCachedMessage({
    required ChatMessageTimelineScope scope,
    required String messageId,
  }) {
    return removeMessage(
      namespace: _chatMessageNamespace(scope),
      messageId: messageId,
    );
  }

  LocalSearchNamespace _chatMessageNamespace(ChatMessageTimelineScope scope) {
    return LocalSearchNamespace(
      ownerUserId: scope.ownerUserId,
      personaId: scope.personaId,
      subjectType: scope.subjectType,
      personaContextVersion: scope.contextVersion,
    );
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
    final updatedPayload = LocalChatSearchContactRecord.fromStorageMap(
      payload,
    ).copyWith(avatarUrl: resolvedAvatarUrl).toStorageMap();
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
          version: _schemaVersion,
          onCreate: _onCreate,
          onUpgrade: _onUpgrade,
        ),
      );
    }
    return openDatabase(
      path,
      version: _schemaVersion,
      onCreate: _onCreate,
      onUpgrade: _onUpgrade,
    );
  }

  Future<void> _onUpgrade(
    Database database,
    int oldVersion,
    int newVersion,
  ) async {
    if (oldVersion >= newVersion) return;
    // 搜索/时间线库是可重建投影。shape 变化时清除旧 schema，禁止长期双读。
    const tables = <String>[
      'chat_contacts_fts',
      'chat_messages_fts',
      'chat_conversations_fts',
      'chat_sync_state',
      'chat_messages',
      'chat_conversations',
      'chat_contacts',
      'search_namespaces',
    ];
    for (final table in tables) {
      await database.execute('DROP TABLE IF EXISTS $table');
    }
    await _onCreate(database, newVersion);
  }

  Future<String> _resolveDatabasePath() async {
    final factory = _databaseFactory;
    return _databasePathResolver.resolve(
      explicitPath: _databasePath,
      fileName: 'quwoquan_local_chat_search.db',
      loadDefaultDirectory: () =>
          factory != null ? factory.getDatabasesPath() : getDatabasesPath(),
    );
  }

  void _configureFactory() {
    if (_databaseFactory != null || _ffiInitialized) {
      return;
    }
    // 移动端 / macOS 使用 sqflite 插件原生实现；VM 单测通过构造函数注入 databaseFactory。
    _ffiInitialized = true;
  }
}
