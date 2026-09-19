import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';

String? buildProfileInteractionCommentRoute({
  required String workId,
  required ReferralSource referralSource,
  required String entrySource,
  String? filter,
  required String commentId,
  String? parentCommentId,
  String? replyToCommentId,
}) {
  final cleanWorkId = workId.trim();
  final cleanCommentId = commentId.trim();
  if (cleanWorkId.isEmpty || cleanCommentId.isEmpty) {
    return null;
  }
  final cleanParentCommentId = parentCommentId?.trim() ?? '';
  final isReply = cleanParentCommentId.isNotEmpty;
  final cleanReplyToCommentId = replyToCommentId?.trim() ?? '';
  return AppRoutePaths.workBrowser(
    workId: cleanWorkId,
    filter: filter?.trim().isNotEmpty == true ? filter!.trim() : null,
    source: referralSource.value,
    openComments: 'true',
    commentEntrySource: entrySource.trim(),
    targetParentCommentId: isReply ? cleanParentCommentId : null,
    targetReplyId: isReply ? cleanCommentId : null,
    targetCommentId: isReply ? null : cleanCommentId,
    replyToCommentId: cleanReplyToCommentId.isEmpty
        ? null
        : cleanReplyToCommentId,
  );
}
