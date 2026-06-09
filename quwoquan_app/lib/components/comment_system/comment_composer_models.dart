/// 评论输入载荷与 @ 候选数据契约。
///
/// 统一输入态由 [CommentInputOverlay]（见 `comment_input_overlay.dart`）承载；
/// 本文件仅保留跨宿主共享的强类型数据结构。`mentions` 在 UI / Provider 全程保持
/// 强类型 [CommentMentionCandidate]，仅在 Repository 边界经 [toWire] 落到云侧
/// codegen 契约（`CommentDto.mentions` 为 `List<CloudJsonMap>`）。
class CommentMentionCandidate {
  const CommentMentionCandidate({
    required this.subjectType,
    required this.subjectId,
    required this.displayName,
  });

  /// 被 @ 主体类型：`assistant`（小趣）/ `user`（联系人）等。
  final String subjectType;

  /// 被 @ 主体 id（账号态 subAccountId 或助手固定 id）。
  final String subjectId;

  /// 展示名（不含前导 `@`）。
  final String displayName;

  Map<String, dynamic> toWire() => <String, dynamic>{
    'subjectType': subjectType,
    'subjectId': subjectId,
    'displayName': displayName,
  };

  @override
  bool operator ==(Object other) =>
      other is CommentMentionCandidate &&
      other.subjectType == subjectType &&
      other.subjectId == subjectId &&
      other.displayName == displayName;

  @override
  int get hashCode => Object.hash(subjectType, subjectId, displayName);
}

/// 评论提交载荷：正文 + 图片附件 mediaId + 强类型 @ 候选。
class CommentComposerPayload {
  const CommentComposerPayload({
    required this.content,
    this.attachmentMediaIds = const <String>[],
    this.mentions = const <CommentMentionCandidate>[],
  });

  final String content;
  final List<String> attachmentMediaIds;
  final List<CommentMentionCandidate> mentions;

  /// 落到云侧 codegen 契约的 mention wire 列表。
  List<Map<String, dynamic>> mentionsWire() =>
      mentions.map((m) => m.toWire()).toList(growable: false);
}
