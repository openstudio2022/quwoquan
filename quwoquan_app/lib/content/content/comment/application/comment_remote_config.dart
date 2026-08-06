import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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

  factory CommentRemoteConfig.fromAppConfig(
    ContentAppConfig config, {
    CommentRemoteConfig fallback = CommentRemoteConfig.fallback,
  }) {
    final comment = config.comment;
    if (comment == null) return fallback;
    return CommentRemoteConfig(
      maxLength: _positiveOrFallback(comment.maxLength, fallback.maxLength),
      replyPreviewCount: _positiveOrFallback(
        comment.replyPreviewCount,
        fallback.replyPreviewCount,
      ),
      replyFirstExpandPageSize: _positiveOrFallback(
        comment.replyFirstExpandPageSize,
        fallback.replyFirstExpandPageSize,
      ),
      replyExpandPageSize: _positiveOrFallback(
        comment.replyExpandPageSize,
        fallback.replyExpandPageSize,
      ),
      foldLineCount: _positiveOrFallback(
        comment.foldLineCount,
        fallback.foldLineCount,
      ),
      maxImageAttachments: _positiveOrFallback(
        comment.attachment?.maxImages,
        fallback.maxImageAttachments,
      ),
      enabled: comment.enabled ?? fallback.enabled,
    );
  }

  static int _positiveOrFallback(int? value, int fallback) {
    if (value == null || value <= 0) return fallback;
    return value;
  }
}
