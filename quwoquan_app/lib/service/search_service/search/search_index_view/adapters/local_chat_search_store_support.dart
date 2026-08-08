part of 'local_chat_search_store.dart';

/// SQLite row, FTS and payload helpers shared by the local chat search facets.
extension _LocalChatSearchStoreSupport on LocalChatSearchStore {
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
      'persona_id': namespace.personaId,
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

  String _highlightText(Map<String, Object?> payload, String? matchedField) {
    switch (matchedField) {
      case 'displayName':
        return _string(payload['displayName']);
      case 'nickname':
        return _string(payload['nickname']);
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
