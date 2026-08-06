import 'dart:convert';
import 'dart:developer' as developer;

import 'package:shared_preferences/shared_preferences.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_terminal_account_purgers.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';

@pragma('vm:entry-point')
class CreateDraftScopedSnapshot {
  const CreateDraftScopedSnapshot({
    required this.drafts,
    required this.currentId,
  });

  final List<CreateDraft> drafts;
  final String? currentId;
}

/// 创作草稿本地清单。
///
/// 每个 actor scope 只有一份 canonical 索引、当前草稿指针和独立草稿载荷。
class CreateDraftLocalStorage implements CreateDraftTerminalAccountPurger {
  const CreateDraftLocalStorage.forTerminalAccountClosure(
    this._terminalActorId,
  );

  final String _terminalActorId;

  static const String _storagePrefix = 'create_drafts';

  /// 损坏 payload 的侧位保留前缀：解码失败不静默清零，原始字节移入
  /// `create_drafts_corrupt:<原 key>` 供诊断与人工恢复。
  static const String corruptSidelinePrefix = 'create_drafts_corrupt';

  /// 本进程内观测到的草稿损坏次数（结构化日志伴随每次递增）。
  static int corruptPayloadCount = 0;

  static String corruptSidelineKey(String originalKey) =>
      '$corruptSidelinePrefix:$originalKey';

  static Future<void> _sidelineCorruptPayload(
    SharedPreferences prefs,
    String originalKey,
    String rawPayload,
    Object error,
  ) async {
    corruptPayloadCount += 1;
    developer.log(
      'create draft payload corrupted; sidelined for recovery '
      '(key=$originalKey, corruptCount=$corruptPayloadCount)',
      name: 'CreateDraftLocalStorage',
      error: error,
    );
    await prefs.setString(corruptSidelineKey(originalKey), rawPayload);
  }

  static String scopeKeyForUser(String? currentUserId) {
    final trimmed = currentUserId?.trim() ?? '';
    if (trimmed.isEmpty) {
      return 'guest';
    }
    return 'user:$trimmed';
  }

  static String scopedIndexKey(String scopeKey) =>
      '$_storagePrefix:$scopeKey:index';

  static String scopedCurrentDraftIdKey(String scopeKey) =>
      '$_storagePrefix:$scopeKey:current_draft_id';

  static String scopedDraftPayloadKey(String scopeKey, String draftId) =>
      '$_storagePrefix:$scopeKey:draft:$draftId';

  static Future<CreateDraftScopedSnapshot> loadScopedDraftsWithCurrentId(
    String scopeKey,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    final indexedIds = _decodeIdList(prefs.getString(scopedIndexKey(scopeKey)));
    final ids = <String>[...indexedIds];
    final knownIds = indexedIds.toSet();
    final payloadPrefix = '$_storagePrefix:$scopeKey:draft:';
    final recoverableKeys =
        prefs.getKeys().where((key) => key.startsWith(payloadPrefix)).toList()
          ..sort();
    for (final key in recoverableKeys) {
      final id = key.substring(payloadPrefix.length).trim();
      if (id.isNotEmpty && knownIds.add(id)) {
        ids.add(id);
      }
    }
    final drafts = <CreateDraft>[];
    for (final id in ids) {
      final payloadKey = scopedDraftPayloadKey(scopeKey, id);
      final rawPayload = prefs.getString(payloadKey);
      final draft = _decodeDraftPayload(rawPayload);
      if (draft == null) {
        if (rawPayload != null && rawPayload.isNotEmpty) {
          await _sidelineCorruptPayload(
            prefs,
            payloadKey,
            rawPayload,
            StateError('create draft payload failed to decode'),
          );
        }
        continue;
      }
      drafts.add(draft);
    }
    drafts.sort((a, b) => b.updatedAtMs.compareTo(a.updatedAtMs));
    final currentId = prefs.getString(scopedCurrentDraftIdKey(scopeKey));
    return CreateDraftScopedSnapshot(
      drafts: drafts,
      currentId: currentId?.trim().isEmpty ?? true ? null : currentId,
    );
  }

  static Future<void> persistScopedDrafts(
    String scopeKey,
    List<CreateDraft> drafts, {
    String? currentId,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final normalized = List<CreateDraft>.from(drafts)
      ..sort((a, b) => b.updatedAtMs.compareTo(a.updatedAtMs));
    final ids = <String>[];
    for (final draft in normalized) {
      final id = draft.id.trim();
      if (id.isEmpty) {
        continue;
      }
      ids.add(id);
      final payloadKey = scopedDraftPayloadKey(scopeKey, id);
      await _requirePersisted(
        prefs.setString(payloadKey, jsonEncode(draft.toStorageMap())),
        payloadKey,
      );
    }
    final indexKey = scopedIndexKey(scopeKey);
    await _requirePersisted(
      prefs.setString(indexKey, jsonEncode(ids)),
      indexKey,
    );
    final currentKey = scopedCurrentDraftIdKey(scopeKey);
    if (currentId == null || currentId.trim().isEmpty) {
      await _requirePersisted(prefs.remove(currentKey), currentKey);
    } else {
      await _requirePersisted(
        prefs.setString(currentKey, currentId.trim()),
        currentKey,
      );
    }
  }

  static Future<void> persistScopedCurrentDraftId(
    String scopeKey,
    String? currentId,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    final currentKey = scopedCurrentDraftIdKey(scopeKey);
    if (currentId == null || currentId.trim().isEmpty) {
      await _requirePersisted(prefs.remove(currentKey), currentKey);
      return;
    }
    await _requirePersisted(
      prefs.setString(currentKey, currentId.trim()),
      currentKey,
    );
  }

  static Future<CreateDraft?> loadScopedDraft(
    String scopeKey,
    String draftId,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    return _decodeDraftPayload(
      prefs.getString(scopedDraftPayloadKey(scopeKey, draftId.trim())),
    );
  }

  static Future<void> removeScopedDraftById(
    String scopeKey,
    String draftId,
  ) async {
    final normalizedId = draftId.trim();
    if (normalizedId.isEmpty) {
      return;
    }
    final prefs = await SharedPreferences.getInstance();
    final indexKey = scopedIndexKey(scopeKey);
    final ids = _decodeIdList(prefs.getString(indexKey)).toList(growable: true)
      ..removeWhere((id) => id == normalizedId);
    final payloadKey = scopedDraftPayloadKey(scopeKey, normalizedId);
    await _requirePersisted(prefs.remove(payloadKey), payloadKey);
    await _requirePersisted(
      prefs.setString(indexKey, jsonEncode(ids)),
      indexKey,
    );
    final currentKey = scopedCurrentDraftIdKey(scopeKey);
    if (prefs.getString(currentKey) == normalizedId) {
      await _requirePersisted(prefs.remove(currentKey), currentKey);
    }
  }

  static Future<void> clearForTerminalAccountClosure(
    String currentActorId,
  ) async {
    final preferences = await SharedPreferences.getInstance();
    final scopeKey = scopeKeyForUser(currentActorId);
    final scopedPrefix = '$_storagePrefix:$scopeKey:';
    final corruptScopedPrefix = '$corruptSidelinePrefix:$scopedPrefix';
    final keys = preferences
        .getKeys()
        .where(
          (key) =>
              key.startsWith(scopedPrefix) ||
              key.startsWith(corruptScopedPrefix),
        )
        .toList(growable: false);
    for (final key in keys) {
      await _requirePersisted(preferences.remove(key), key);
    }
    if (preferences.getKeys().any(
      (key) =>
          key.startsWith(scopedPrefix) || key.startsWith(corruptScopedPrefix),
    )) {
      throw StateError('create draft cleanup verification failed');
    }
  }

  @override
  Future<void> purgeForTerminalAccountClosure() =>
      clearForTerminalAccountClosure(_terminalActorId);

  static List<String> _decodeIdList(String? raw) {
    if (raw == null || raw.isEmpty) {
      return <String>[];
    }
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) {
        return <String>[];
      }
      return decoded
          .map((entry) => entry.toString().trim())
          .where((entry) => entry.isNotEmpty)
          .toList(growable: false);
    } catch (error) {
      // index 损坏不丢数据：调用方会按 payload key 前缀扫描重建 id 列表。
      corruptPayloadCount += 1;
      developer.log(
        'create draft index corrupted; ids will be rebuilt from payload keys '
        '(corruptCount=$corruptPayloadCount)',
        name: 'CreateDraftLocalStorage',
        error: error,
      );
      return <String>[];
    }
  }

  static CreateDraft? _decodeDraftPayload(String? raw) {
    if (raw == null || raw.isEmpty) {
      return null;
    }
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) {
        return null;
      }
      return CreateDraft.fromStorageMap(Map<String, dynamic>.from(decoded));
    } catch (error, stackTrace) {
      developer.log(
        'create draft payload decode failed; corrupt entry ignored',
        name: 'CreateDraftLocalStorage',
        error: error,
        stackTrace: stackTrace,
      );
      return null;
    }
  }

  static Future<void> _requirePersisted(
    Future<bool> operation,
    String storageKey,
  ) async {
    if (!await operation) {
      throw StateError('local draft persistence failed for $storageKey');
    }
  }
}
