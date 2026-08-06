import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentCommentInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

/// Comment / ContentReaction 的 production Remote。只做 generated client 的
/// 强类型薄映射，不持有 path、operation id、HTTP client 或 decoder。
final class RemoteContentCommentFacet implements ContentCommentFacet {
  const RemoteContentCommentFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ContentCommentInvocationContextFactory invocationContext;

  @override
  Future<CommentPageSlice> listComments({
    required String postId,
    String? cursor,
    int limit = ListContentCommentsQuery.defaultLimit,
    CommentSort sort = CommentSort.hot,
  }) => client.contentCommentListComments(
    ListContentCommentsQuery(
      postId: postId,
      cursor: cursor,
      limit: limit,
      sort: sort,
    ),
    context: invocationContext(
      ContentRequestPageIds.listComments,
      command: false,
    ),
  );

  @override
  Future<ReplyPageSlice> listReplies({
    required String postId,
    required String commentId,
    String? cursor,
    int limit = ListContentCommentRepliesQuery.defaultLimit,
  }) => client.contentCommentListCommentReplies(
    ListContentCommentRepliesQuery(
      postId: postId,
      commentId: commentId,
      cursor: cursor,
      limit: limit,
    ),
    context: invocationContext(
      ContentRequestPageIds.listCommentReplies,
      command: false,
    ),
  );

  @override
  Future<AuthorCommentPageSlice> listByAuthor({
    String? cursor,
    int limit = ContentCommentPageQuery.defaultLimit,
  }) => client.contentCommentListCommentsByAuthor(
    ContentCommentPageQuery(cursor: cursor, limit: limit),
    context: invocationContext(
      ContentRequestPageIds.listCommentsByAuthor,
      command: false,
    ),
  );

  @override
  Future<ReceivedCommentPageSlice> listReceived({
    String? cursor,
    int limit = ContentCommentPageQuery.defaultLimit,
  }) => client.contentCommentListCommentsForPostAuthor(
    ContentCommentPageQuery(cursor: cursor, limit: limit),
    context: invocationContext(
      ContentRequestPageIds.listCommentsForPostAuthor,
      command: false,
    ),
  );

  @override
  Future<CommentCommandResult> createComment(
    CreateContentCommentCommand command,
  ) => client.contentCommentCreateComment(
    command,
    context: invocationContext(
      ContentRequestPageIds.createComment,
      command: true,
    ),
  );

  @override
  Future<CommentCommandResult> deleteComment(
    DeleteContentCommentCommand command,
  ) => client.contentCommentDeleteComment(
    command,
    context: invocationContext(
      ContentRequestPageIds.deleteComment,
      command: true,
    ),
  );

  @override
  Future<CommentCommandResult> pinComment(
    ChangeContentCommentPinCommand command,
  ) => client.contentCommentPinComment(
    command,
    context: invocationContext(ContentRequestPageIds.pinComment, command: true),
  );

  @override
  Future<CommentCommandResult> unpinComment(
    ChangeContentCommentPinCommand command,
  ) => client.contentCommentUnpinComment(
    command,
    context: invocationContext(
      ContentRequestPageIds.unpinComment,
      command: true,
    ),
  );

  @override
  Future<CommentCommandResult> bindAttachments(
    BindContentCommentAttachmentsCommand command,
  ) => client.contentCommentBindMediaAssetsToComment(
    command,
    context: invocationContext(
      ContentRequestPageIds.bindMediaAssetsToComment,
      command: true,
    ),
  );

  @override
  Future<ContentCommentReactionCommandResult> reactToComment(
    ReactToContentCommentCommand command,
  ) => client.contentContentReactionReactToComment(
    command,
    context: invocationContext(
      ContentRequestPageIds.reactToComment,
      command: true,
    ),
  );
}
