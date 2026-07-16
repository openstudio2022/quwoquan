import 'comment_contracts.dart';
import 'content_reaction_contracts.dart';

abstract interface class ContentCommentQuery {
  Future<ContentCommentPageSlice> listComments({
    required String postId,
    String? cursor,
    int limit = 20,
  });

  Future<ContentCommentReplyPageSlice> listReplies({
    required String postId,
    required String commentId,
    String? cursor,
    int limit = 10,
  });

  Future<ContentAuthorCommentPageSlice> listByAuthor({
    String? cursor,
    int limit = 20,
  });

  Future<ContentReceivedCommentPageSlice> listReceived({
    String? cursor,
    int limit = 20,
  });
}

abstract interface class ContentCommentCommandWriter {
  Future<ContentCommentCommandResult> createComment(
    CreateContentCommentCommand command,
  );

  Future<ContentCommentCommandResult> deleteComment(
    DeleteContentCommentCommand command,
  );

  Future<ContentCommentCommandResult> pinComment(
    ChangeContentCommentPinCommand command,
  );

  Future<ContentCommentCommandResult> unpinComment(
    ChangeContentCommentPinCommand command,
  );

  Future<ContentCommentCommandResult> bindAttachments(
    BindContentCommentAttachmentsCommand command,
  );
}

abstract interface class ContentCommentReactionWriter {
  Future<ContentCommentReactionCommandResult> reactToComment(
    ReactToContentCommentCommand command,
  );
}

abstract interface class ContentCommentFacet
    implements
        ContentCommentQuery,
        ContentCommentCommandWriter,
        ContentCommentReactionWriter {}
