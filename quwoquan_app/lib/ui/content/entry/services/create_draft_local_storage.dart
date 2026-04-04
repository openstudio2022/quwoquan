import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';

/// 创作草稿本地清单（与 [CreatePage] 写入的 SharedPreferences 键一致）。
class CreateDraftLocalStorage {
  CreateDraftLocalStorage._();

  static const String draftsKey = 'create_drafts_list';
  static const String currentDraftIdKey = 'create_current_draft_id';

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

  static Future<void> removeDraftById(String draftId) async {
    final loaded = await loadDraftsWithCurrentId();
    final next = loaded.drafts
        .where((d) => d.id != draftId)
        .toList(growable: false);
    final nextCurrent =
        loaded.currentId == draftId ? null : loaded.currentId;
    await persistDrafts(next, nextCurrent);
  }
}
