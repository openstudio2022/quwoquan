import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_api_query_defaults.dart';
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
  Future<ContentCommentPageSlice> listComments({
    required String postId,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    ContentCommentSort sort = ContentCommentSort.hot,
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
  Future<ContentCommentReplyPageSlice> listReplies({
    required String postId,
    required String commentId,
    String? cursor,
    int limit = CloudApiQueryDefaults.commentRepliesLimit,
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
  Future<ContentAuthorCommentPageSlice> listByAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) => client.contentCommentListCommentsByAuthor(
    ContentCommentPageQuery(cursor: cursor, limit: limit),
    context: invocationContext(
      ContentRequestPageIds.listCommentsByAuthor,
      command: false,
    ),
  );

  @override
  Future<ContentReceivedCommentPageSlice> listReceived({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) => client.contentCommentListCommentsForPostAuthor(
    ContentCommentPageQuery(cursor: cursor, limit: limit),
    context: invocationContext(
      ContentRequestPageIds.listCommentsForPostAuthor,
      command: false,
    ),
  );

  @override
  Future<ContentCommentCommandResult> createComment(
    CreateContentCommentCommand command,
  ) => client.contentCommentCreateComment(
    command,
    context: invocationContext(
      ContentRequestPageIds.createComment,
      command: true,
    ),
  );

  @override
  Future<ContentCommentCommandResult> deleteComment(
    DeleteContentCommentCommand command,
  ) => client.contentCommentDeleteComment(
    command,
    context: invocationContext(
      ContentRequestPageIds.deleteComment,
      command: true,
    ),
  );

  @override
  Future<ContentCommentCommandResult> pinComment(
    ChangeContentCommentPinCommand command,
  ) => client.contentCommentPinComment(
    command,
    context: invocationContext(ContentRequestPageIds.pinComment, command: true),
  );

  @override
  Future<ContentCommentCommandResult> unpinComment(
    ChangeContentCommentPinCommand command,
  ) => client.contentCommentUnpinComment(
    command,
    context: invocationContext(
      ContentRequestPageIds.unpinComment,
      command: true,
    ),
  );

  @override
  Future<ContentCommentCommandResult> bindAttachments(
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
