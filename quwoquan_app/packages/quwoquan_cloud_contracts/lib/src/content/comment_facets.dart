import 'content_operation_contracts.g.dart';

abstract interface class ContentCommentQuery {
  Future<CommentPageSlice> listComments({
    required String postId,
    String? cursor,
    int limit = 20,
    CommentSort sort = CommentSort.hot,
  });

  Future<ReplyPageSlice> listReplies({
    required String postId,
    required String commentId,
    String? cursor,
    int limit = 10,
  });

  Future<AuthorCommentPageSlice> listByAuthor({String? cursor, int limit = 20});

  Future<ReceivedCommentPageSlice> listReceived({
    String? cursor,
    int limit = 20,
  });
}

abstract interface class ContentCommentCommandWriter {
  Future<CommentCommandResult> createComment(
    CreateContentCommentCommand command,
  );

  Future<CommentCommandResult> deleteComment(
    DeleteContentCommentCommand command,
  );

  Future<CommentCommandResult> pinComment(
    ChangeContentCommentPinCommand command,
  );

  Future<CommentCommandResult> unpinComment(
    ChangeContentCommentPinCommand command,
  );

  Future<CommentCommandResult> bindAttachments(
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
