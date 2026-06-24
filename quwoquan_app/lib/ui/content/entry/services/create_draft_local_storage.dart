import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';

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
/// V1 使用单个 `create_drafts_list` JSON 字符串保存全部草稿；本轮升级到
/// `create_drafts_v2:<scope>:*` 命名空间后，仍保留旧 key 常量用于迁移和测试基线。
class CreateDraftLocalStorage {
  CreateDraftLocalStorage._();

  static const String draftsKey = 'create_drafts_list';
  static const String currentDraftIdKey = 'create_current_draft_id';
  static const String _v2Prefix = 'create_drafts_v2';

  static String scopeKeyForUser(String? currentUserId) {
    final trimmed = currentUserId?.trim() ?? '';
    if (trimmed.isEmpty) {
      return 'guest';
    }
    return 'user:$trimmed';
  }

  static String scopedIndexKey(String scopeKey) => '$_v2Prefix:$scopeKey:index';

  static String scopedCurrentDraftIdKey(String scopeKey) =>
      '$_v2Prefix:$scopeKey:current_draft_id';

  static String scopedDraftPayloadKey(String scopeKey, String draftId) =>
      '$_v2Prefix:$scopeKey:draft:$draftId';

  static Future<({List<CreateDraft> drafts, String? currentId})>
      loadDraftsWithCurrentId() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(draftsKey);
    var drafts = const <CreateDraft>[];
    if (raw != null && raw.isNotEmpty) {
      try {
        final decoded = jsonDecode(raw);
        drafts = decodeCreateDraftsList(decoded);
      } catch (_) {
        drafts = const <CreateDraft>[];
      }
    }
    return (drafts: drafts, currentId: prefs.getString(currentDraftIdKey));
  }

  static Future<CreateDraftScopedSnapshot> loadScopedDraftsWithCurrentId(
    String scopeKey,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    await migrateStoredDraftsIfNeeded(scopeKey);
    final ids = _decodeIdList(prefs.getString(scopedIndexKey(scopeKey)));
    final drafts = <CreateDraft>[];
    for (final id in ids) {
      final draft = _decodeDraftPayload(
        prefs.getString(scopedDraftPayloadKey(scopeKey, id)),
      );
      if (draft == null) {
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

  static Future<void> persistDrafts(
    List<CreateDraft> drafts,
    String? currentId,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      draftsKey,
      jsonEncode(
        drafts.map((d) => d.toStorageMap()).toList(growable: false),
      ),
    );
    if (currentId == null || currentId.isEmpty) {
      await prefs.remove(currentDraftIdKey);
    } else {
      await prefs.setString(currentDraftIdKey, currentId);
    }
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
      await prefs.setString(
        scopedDraftPayloadKey(scopeKey, id),
        jsonEncode(draft.toStorageMap()),
      );
    }
    await prefs.setString(scopedIndexKey(scopeKey), jsonEncode(ids));
    if (currentId == null || currentId.trim().isEmpty) {
      await prefs.remove(scopedCurrentDraftIdKey(scopeKey));
    } else {
      await prefs.setString(scopedCurrentDraftIdKey(scopeKey), currentId.trim());
    }
  }

  static Future<void> persistScopedCurrentDraftId(
    String scopeKey,
    String? currentId,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    if (currentId == null || currentId.trim().isEmpty) {
      await prefs.remove(scopedCurrentDraftIdKey(scopeKey));
      return;
    }
    await prefs.setString(scopedCurrentDraftIdKey(scopeKey), currentId.trim());
  }

  static Future<CreateDraft?> loadScopedDraft(
    String scopeKey,
    String draftId,
  ) async {
    final prefs = await SharedPreferences.getInstance();
    await migrateStoredDraftsIfNeeded(scopeKey);
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
    await migrateStoredDraftsIfNeeded(scopeKey);
    final indexKey = scopedIndexKey(scopeKey);
    final ids = _decodeIdList(
      prefs.getString(indexKey),
    ).toList(growable: true)..removeWhere((id) => id == normalizedId);
    await prefs.remove(scopedDraftPayloadKey(scopeKey, normalizedId));
    await prefs.setString(indexKey, jsonEncode(ids));
    if (prefs.getString(scopedCurrentDraftIdKey(scopeKey)) == normalizedId) {
      await prefs.remove(scopedCurrentDraftIdKey(scopeKey));
    }
  }

  static Future<void> removeDraftById(String draftId) async {
    final loaded = await loadDraftsWithCurrentId();
    final next = loaded.drafts
        .where((d) => d.id != draftId)
        .toList(growable: false);
    final nextCurrent =
        loaded.currentId == draftId ? null : loaded.currentId;
    await persistDrafts(next, nextCurrent);
  }

  static Future<void> migrateStoredDraftsIfNeeded(String scopeKey) async {
    final prefs = await SharedPreferences.getInstance();
    if (prefs.containsKey(scopedIndexKey(scopeKey))) {
      return;
    }
    final raw = prefs.getString(draftsKey);
    if (raw == null || raw.isEmpty) {
      return;
    }
    var drafts = const <CreateDraft>[];
    try {
      drafts = decodeCreateDraftsList(jsonDecode(raw));
    } catch (_) {
      drafts = const <CreateDraft>[];
    }
    await persistScopedDrafts(
      scopeKey,
      drafts,
      currentId: prefs.getString(currentDraftIdKey),
    );
    await prefs.remove(draftsKey);
    await prefs.remove(currentDraftIdKey);
  }

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
    } catch (_) {
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
    } catch (_) {
      return null;
    }
  }
}
