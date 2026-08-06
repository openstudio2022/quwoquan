import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_publication_status_reader.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_projection_mapper.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentPostReaderInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// Content Post 详情与作者作品的正式远端 Reader。
///
/// 仅接收生成客户端与调用上下文；App DTO 的转换被限制在本适配器，业务消费者
/// 不接触 HTTP、header、decoder 或 URL path。
final class RemoteContentPostReaderAdapter
    implements
        ContentPostDetailReader,
        ContentEntityWishlistStateReader,
        ContentAuthorPostsReader,
        ContentPostPublicationStatusReader {
  const RemoteContentPostReaderAdapter({
    required this.client,
    required this.invocationContext,
    this.projectionMapper = const ContentPostProjectionMapper(),
  });

  final GeneratedCloudOperationClient client;
  final ContentPostReaderInvocationContextFactory invocationContext;
  final ContentPostProjectionMapper projectionMapper;

  @override
  Future<ContentPostDetailPayload> getPost({
    required String postId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    return _detailPayloadFromSlice(
      await _getPostSlice(
        postId,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      ),
    );
  }

  @override
  Future<ContentPostPublicationStatus> getPostPublicationStatus(
    String postId,
  ) async {
    final response = await _getPostSlice(postId);
    return ContentPostPublicationStatus(
      postId: response.postId,
      state: ContentPostPublicationState.fromWire(response.status),
      moderationStatus: null,
      updatedAt: response.updatedAt,
    );
  }

  @override
  Future<EntityWishlistState> getEntityWishlistState({
    required String objectId,
    required String objectKind,
  }) {
    return client.contentPostGetEntityWishlistState(
      EntityWishlistStateQuery(objectId: objectId, objectKind: objectKind),
      context: invocationContext(ContentRequestPageIds.getEntityWishlistState),
    );
  }

  @override
  Future<CursorPage<ContentPostViewData>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? visibility,
    String? cursor,
    int limit = ContentAuthorPostsQuery.defaultLimit,
  }) async {
    final response = await client.contentPostListUserPosts(
      ContentAuthorPostsQuery(
        personaId: userId,
        identity: identity,
        type: type,
        visibility: visibility,
        cursor: cursor,
        limit: limit,
      ),
      context: invocationContext(ContentRequestPageIds.listUserPosts),
    );
    return CursorPage<ContentPostViewData>(
      items: response.items.map(projectionMapper.toDto).toList(growable: false),
      nextCursor: response.nextCursor,
    );
  }

  Future<ContentPostDetailSlice> _getPostSlice(
    String postId, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    final baseContext = invocationContext(ContentRequestPageIds.getPost);
    return client.contentPostGetPost(
      ContentPostDetailQuery(postId: postId),
      context: CloudOperationInvocationContext(
        surfaceId: baseContext.surfaceId,
        clientPageId: baseContext.clientPageId,
        actor: baseContext.actor,
        routeId: baseContext.routeId,
        referralSource: baseContext.referralSource,
        feedRequestId: baseContext.feedRequestId,
        shareId: baseContext.shareId,
        modelId: baseContext.modelId,
        experimentBucket: baseContext.experimentBucket,
        idempotencyKey: baseContext.idempotencyKey,
        deadlineAt: _earliestDeadline(baseContext.deadlineAt, deadlineAt),
        cancellation: cancellation ?? baseContext.cancellation,
      ),
    );
  }

  DateTime? _earliestDeadline(DateTime? left, DateTime? right) {
    if (left == null) return right;
    if (right == null) return left;
    return left.isBefore(right) ? left : right;
  }

  ContentPostDetailPayload _detailPayloadFromSlice(
    ContentPostDetailSlice slice,
  ) => ContentPostDetailPayload.fromWire(slice);
}
