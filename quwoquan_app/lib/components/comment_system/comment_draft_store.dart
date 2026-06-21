import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// 评论草稿本地态：按「帖 + 被回复评论」维度持久化，关闭输入态不丢未发内容，
/// 重新打开同一目标的输入浮层时自动续写（对标小红书等成熟评论体验）。
///
/// 仅保存用户正在编写、尚未提交的内容；提交成功后必须清除，避免脏草稿回灌。
class CommentDraft {
  const CommentDraft({
    required this.content,
    this.attachmentMediaIds = const <String>[],
    this.mentionSubjectIds = const <String>[],
  });

  final String content;
  final List<String> attachmentMediaIds;
  final List<String> mentionSubjectIds;

  bool get isEmpty =>
      content.trim().isEmpty &&
      attachmentMediaIds.isEmpty &&
      mentionSubjectIds.isEmpty;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'content': content,
        'attachmentMediaIds': attachmentMediaIds,
        'mentionSubjectIds': mentionSubjectIds,
      };

  factory CommentDraft.fromJson(Map<String, dynamic> json) {
    List<String> stringList(Object? raw) =>
        raw is List ? raw.map((e) => e.toString()).toList(growable: false) : const <String>[];
    return CommentDraft(
      content: (json['content'] ?? '').toString(),
      attachmentMediaIds: stringList(json['attachmentMediaIds']),
      mentionSubjectIds: stringList(json['mentionSubjectIds']),
    );
  }
}

class CommentDraftStore {
  CommentDraftStore._();

  static const String _keyPrefix = 'comment_draft:v1:';

  static String _key(String postId, String? replyToCommentId) =>
      '$_keyPrefix$postId:${replyToCommentId ?? ''}';

  static Future<CommentDraft?> load(
    String postId, {
    String? replyToCommentId,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key(postId, replyToCommentId));
    if (raw == null || raw.isEmpty) {
      return null;
    }
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map<String, dynamic>) {
        final draft = CommentDraft.fromJson(decoded);
        return draft.isEmpty ? null : draft;
      }
    } catch (_) {
      return null;
    }
    return null;
  }

  static Future<void> save(
    String postId, {
    String? replyToCommentId,
    required CommentDraft draft,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final key = _key(postId, replyToCommentId);
    if (draft.isEmpty) {
      await prefs.remove(key);
      return;
    }
    await prefs.setString(key, jsonEncode(draft.toJson()));
  }

  static Future<void> clear(
    String postId, {
    String? replyToCommentId,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key(postId, replyToCommentId));
  }
}
