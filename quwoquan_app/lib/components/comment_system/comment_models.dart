/// 评论输入态（composer）的运行时约束。
///
/// 由 [CommentRemoteConfig.toComposerConfig] 派生，仅承载与输入态相关的最小配置：
/// 最大字数、单条最多图片附件、是否允许评论。列表行为（预览/展开页大小等）
/// 由 [CommentRemoteConfig] 承载，二者不重复维护同一来源。
class CommentConfig {
  final int maxLength;
  final int maxImageAttachments;
  final bool enabled;

  const CommentConfig({
    this.maxLength = 500,
    this.maxImageAttachments = 1,
    this.enabled = true,
  });
}

extension CommentConfigExtension on CommentConfig {
  bool get canUserComment => enabled;
}
