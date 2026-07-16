import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';

class CommentRemoteConfig {
  const CommentRemoteConfig({
    this.maxLength = 500,
    this.replyPreviewCount = 1,
    this.replyFirstExpandPageSize = 5,
    this.replyExpandPageSize = 10,
    this.foldLineCount = 3,
    this.maxImageAttachments = 1,
    this.enabled = true,
  });

  final int maxLength;
  final int replyPreviewCount;

  /// 首次点击「展开 N 条回复」时加载的最大回复数（对标小红书首屏 5 条）。
  final int replyFirstExpandPageSize;

  /// 后续点击「展开更多回复」时每页加载的最大回复数。
  final int replyExpandPageSize;
  final int foldLineCount;
  final int maxImageAttachments;
  final bool enabled;

  static const CommentRemoteConfig fallback = CommentRemoteConfig();

  factory CommentRemoteConfig.fromAppConfigRoot(
    ContentAppConfigWireRoot root, {
    CommentRemoteConfig fallback = CommentRemoteConfig.fallback,
  }) {
    final content = (root['content'] as Map?)?.cast<String, Object?>();
    final comment = (content?['comment'] as Map?)?.cast<String, Object?>();
    if (comment == null) return fallback;
    final attachment = (comment['attachment'] as Map?)?.cast<String, Object?>();
    return CommentRemoteConfig(
      maxLength: _positiveOrFallback(
        _asInt(comment['max_length']),
        fallback.maxLength,
      ),
      replyPreviewCount: _positiveOrFallback(
        _asInt(comment['reply_preview_count']),
        fallback.replyPreviewCount,
      ),
      replyFirstExpandPageSize: _positiveOrFallback(
        _asInt(comment['reply_first_expand_page_size']),
        fallback.replyFirstExpandPageSize,
      ),
      replyExpandPageSize: _positiveOrFallback(
        _asInt(comment['reply_expand_page_size']),
        fallback.replyExpandPageSize,
      ),
      foldLineCount: _positiveOrFallback(
        _asInt(comment['fold_line_count']),
        fallback.foldLineCount,
      ),
      maxImageAttachments: _positiveOrFallback(
        _asInt(attachment?['max_images']),
        fallback.maxImageAttachments,
      ),
      enabled: _asBool(comment['enabled'], fallback.enabled),
    );
  }

  static int? _asInt(Object? value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
  }

  static bool _asBool(Object? value, bool fallback) {
    if (value is bool) return value;
    if (value is String) {
      final normalized = value.trim().toLowerCase();
      if (normalized == 'true') return true;
      if (normalized == 'false') return false;
    }
    return fallback;
  }

  static int _positiveOrFallback(int? value, int fallback) {
    if (value == null || value <= 0) return fallback;
    return value;
  }
}
