import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 评论输入载荷。
///
/// Comment 的 mention 从输入态、登录续接到 generated operation request 始终使用
/// pure-contract [CommentMention]，不再维护 UI wire map 或第二套候选 DTO。

/// 评论提交载荷：正文 + 图片附件 mediaId + 强类型 @ 候选。
class CommentComposerPayload {
  const CommentComposerPayload({
    required this.content,
    this.attachmentMediaIds = const <String>[],
    this.mentions = const <CommentMention>[],
  });

  final String content;
  final List<String> attachmentMediaIds;
  final List<CommentMention> mentions;
}
