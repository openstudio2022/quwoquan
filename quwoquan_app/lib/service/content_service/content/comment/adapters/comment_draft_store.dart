import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/service/content_service/content/comment/application/public/comment_draft_terminal_account_purger.dart';
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
    List<String> stringList(Object? raw) => raw is List
        ? raw.map((e) => e.toString()).toList(growable: false)
        : const <String>[];
    return CommentDraft(
      content: (json['content'] ?? '').toString(),
      attachmentMediaIds: stringList(json['attachmentMediaIds']),
      mentionSubjectIds: stringList(json['mentionSubjectIds']),
    );
  }
}

class CommentDraftStore implements CommentDraftTerminalAccountPurger {
  const CommentDraftStore({required String actorScope})
    : _terminalActorScope = actorScope;

  final String _terminalActorScope;

  // 单轨:本地持久化 key 使用稳定语义名,禁止 v1/v2 第二条存储轨。
  static const String _keyPrefix = 'comment_draft:';

  static String _actorPrefix(String actorScope) {
    final normalized = actorScope.trim().isEmpty ? 'guest' : actorScope.trim();
    final digest = sha256.convert(utf8.encode(normalized)).toString();
    return '$_keyPrefix${digest.substring(0, 24)}:';
  }

  static String _key(
    String actorScope,
    String postId,
    String? replyToCommentId,
  ) => '${_actorPrefix(actorScope)}$postId:${replyToCommentId ?? ''}';

  static Future<CommentDraft?> load(
    String postId, {
    required String actorScope,
    String? replyToCommentId,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key(actorScope, postId, replyToCommentId));
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
    required String actorScope,
    String? replyToCommentId,
    required CommentDraft draft,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    final key = _key(actorScope, postId, replyToCommentId);
    if (draft.isEmpty) {
      await prefs.remove(key);
      return;
    }
    await prefs.setString(key, jsonEncode(draft.toJson()));
  }

  static Future<void> clear(
    String postId, {
    required String actorScope,
    String? replyToCommentId,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_key(actorScope, postId, replyToCommentId));
  }

  static Future<void> clearForTerminalAccountClosure(String actorScope) async {
    final preferences = await SharedPreferences.getInstance();
    final actorPrefix = _actorPrefix(actorScope);
    final keys = preferences
        .getKeys()
        .where((key) => key.startsWith(actorPrefix))
        .toList(growable: false);
    for (final key in keys) {
      await preferences.remove(key);
    }
    if (preferences.getKeys().any((key) => key.startsWith(actorPrefix))) {
      throw StateError('comment draft cleanup verification failed');
    }
  }

  @override
  Future<void> purgeForTerminalAccountClosure() =>
      clearForTerminalAccountClosure(_terminalActorScope);
}
