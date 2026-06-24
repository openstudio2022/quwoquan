part of 'local_chat_search_store.dart';

extension LocalChatSearchStoreQueries on LocalChatSearchStore {
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
        'avatar_composite_urls_json': jsonEncode(const <String>[]),
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
    required List<LocalChatSearchMessageRecord> messages,
    ConversationCacheRecord? conversation,
  }) async {
    if (messages.isEmpty) {
      return;
    }
    final database = await _database;
    final batch = database.batch();
    final now = DateTime.now().toIso8601String();
    _upsertNamespace(batch, namespace, updatedAt: now);
    final fallbackConversationId = conversation?.id ?? '';
    final fallbackConversationType = conversation?.type ?? '';
    final fallbackConversationTitle = conversation?.title ?? '';
    final fallbackConversationAvatar = conversation?.avatarUrl ?? '';
    var maxSeq = 0;
    for (final message in messages) {
      final messageId = message.messageId.trim();
      if (messageId.isEmpty) {
        continue;
      }
      final recalledAt = message.recalledAt.trim();
      final status = message.status.trim();
      final deleted = message.deleted;
      if (deleted) {
        _deleteMessageInBatch(
          batch,
          namespace: namespace,
          messageId: messageId,
        );
        continue;
      }
      final conversationId = _firstNonEmpty(<Object?>[
        message.conversationId,
        fallbackConversationId,
      ]);
      if (conversationId.isEmpty) {
        continue;
      }
      final seq = message.seq;
      if (seq > maxSeq) {
        maxSeq = seq;
      }
      final conversationType = _firstNonEmpty(<Object?>[
        message.conversationType,
        fallbackConversationType,
      ]);
      final conversationTitle = _firstNonEmpty(<Object?>[
        message.conversationTitle,
        fallbackConversationTitle,
      ]);
      final conversationAvatarUrl = _firstNonEmpty(<Object?>[
        message.conversationAvatarUrl,
        fallbackConversationAvatar,
      ]);
      final senderSubAccountId = _firstNonEmpty(<Object?>[
        message.senderSubAccountId,
      ]);
      final senderDisplayName = _firstNonEmpty(<Object?>[
        message.senderDisplayName,
      ]);
      final senderAvatarUrl = _firstNonEmpty(<Object?>[
        message.senderAvatarUrl,
      ]);
      final messageType = _firstNonEmpty(<Object?>[
        message.messageType,
        'text',
      ]);
      final contentPreview = _firstNonEmpty(<Object?>[message.contentPreview]);
      final timestamp = _firstNonEmpty(<Object?>[message.timestamp, now]);
      final payload = message
          .copyWith(
            conversationId: conversationId,
            conversationType: conversationType,
            conversationTitle: conversationTitle,
            conversationAvatarUrl: conversationAvatarUrl,
            senderSubAccountId: senderSubAccountId,
            senderDisplayName: senderDisplayName,
            senderAvatarUrl: senderAvatarUrl,
            messageType: messageType,
            contentPreview: contentPreview,
            timestamp: timestamp,
            status: status.isEmpty ? 'sent' : status,
            recalledAt: recalledAt,
            deleted: deleted,
          )
          .toWireMap();
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
        'sender_sub_account_id': senderSubAccountId,
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

  Future<void> _onCreate(Database database, int version) async {
    await database.execute('''
      CREATE TABLE search_namespaces (
        namespace_key TEXT PRIMARY KEY,
        owner_user_id TEXT NOT NULL,
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
        sender_sub_account_id TEXT NOT NULL,
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
}
