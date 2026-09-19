import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

abstract interface class ContentCommentReactionCoordinator {
  Future<ContentCommentReactionCommandResult> react(
    String commentId,
    CommentReactionType reaction,
  );
}
