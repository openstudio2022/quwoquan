import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/transport/generated/client_content_presentation_contract.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_publication_status_reader.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_list_item_decoder.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_list_item_skew_observer.dart';
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
        ContentGatheringPostsReader,
        ContentGatheringSocialProofReader,
        ContentPostPublicationStatusReader {
  const RemoteContentPostReaderAdapter({
    required this.client,
    required this.invocationContext,
    this.projectionMapper = const ContentPostProjectionMapper(),
    this.listItemDecoder = const ContentListItemDecoder(),
    this.skewObserver = const ContentListItemSkewObserver(),
  });

  final GeneratedCloudOperationClient client;
  final ContentPostReaderInvocationContextFactory invocationContext;
  final ContentPostProjectionMapper projectionMapper;
  final ContentListItemDecoder listItemDecoder;
  final ContentListItemSkewObserver skewObserver;

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
    String? type,
    String? visibility,
    String? cursor,
    int limit = ContentAuthorPostsQuery.defaultLimit,
  }) async {
    final response = await client.contentPostListUserPosts(
      ContentAuthorPostsQuery(
        // 能力闭集与端侧编译期真实支持同源生成；不手写数组或摘要。
        clientPresentationContract: compiledContentPresentationContract,
        personaId: userId,
        type: type,
        visibility: visibility,
        cursor: cursor,
        limit: limit,
      ),
      context: invocationContext(ContentRequestPageIds.listUserPosts),
    );
    // 作者作品面只消费 post 投影；实体主页项在此面没有目的面边，逐项隔离。
    final decoding = listItemDecoder.decode(response.items);
    skewObserver.record(
      <ContentListItemIsolation>[
        ...decoding.isolated,
        for (final card in decoding.objectCards)
          ContentListItemIsolation(
            reason: ContentListItemIsolationReason.unsupportedObjectKind,
            deliveryIndex: card.anchorIndex,
            objectKind: card.objectKind,
            objectId: card.objectId,
          ),
      ],
      operationId: AppCloudOperationIds.contentPostListUserPosts,
    );
    return CursorPage<ContentPostViewData>(
      items: decoding.posts,
      nextCursor: response.nextCursor,
    );
  }

  @override
  Future<CursorPage<ContentPostViewData>> listPostsByGathering({
    required String gatheringId,
    String? cursor,
    int limit = ContentGatheringPostsQuery.defaultLimit,
  }) async {
    final response = await client.contentPostListPostsByGathering(
      ContentGatheringPostsQuery(
        gatheringId: gatheringId,
        cursor: cursor,
        limit: limit,
      ),
      context: invocationContext(ContentRequestPageIds.listPostsByGathering),
    );
    return CursorPage<ContentPostViewData>(
      items: response.items.map(projectionMapper.toDto).toList(growable: false),
      nextCursor: response.nextCursor,
    );
  }

  @override
  Future<GatheringSocialProofSummary> getGatheringSocialProof({
    required String anchorKind,
    required String objectId,
  }) {
    return client.contentPostGetGatheringSocialProof(
      GetGatheringSocialProofQuery(anchorKind: anchorKind, objectId: objectId),
      context: invocationContext(
        ContentRequestPageIds.getGatheringSocialProof,
      ),
    );
  }

  Future<ContentPostDetailSlice> _getPostSlice(
    String postId, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    final baseContext = invocationContext(ContentRequestPageIds.getPost);
    return client.contentPostGetPost(
      ContentPostDetailQuery(
        // 能力闭集与端侧编译期真实支持同源生成；不手写数组或摘要。
        clientPresentationContract: compiledContentPresentationContract,
        postId: postId,
      ),
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
