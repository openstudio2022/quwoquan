import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/application/content/post/post_publication_status_reader.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart';
import 'package:quwoquan_app/cloud/services/content/remote/content_post_projection_mapper.dart';
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
      postId: response.post.postId,
      state: ContentPostPublicationState.fromWire(response.status),
      moderationStatus: response.moderationStatus,
      updatedAt:
          response.post.updatedAt ??
          response.post.createdAt ??
          DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
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
  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? visibility,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
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
    return CursorPage<PostBaseDto>(
      items: response.items.map(projectionMapper.toDto).toList(growable: false),
      nextCursor: response.nextCursor,
      totalCount: response.totalCount,
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
  ) {
    final wire = projectionMapper.toWire(slice.post)
      ..addAll(<String, dynamic>{
        if (slice.isOfficial != null) 'isOfficial': slice.isOfficial,
        if (slice.badge != null) 'badge': slice.badge,
        if (slice.articleTemplate != null)
          'articleTemplate': slice.articleTemplate,
        if (slice.articleFontPreset != null)
          'articleFontPreset': slice.articleFontPreset,
        if (slice.articleMarkdown != null)
          'articleMarkdown': slice.articleMarkdown,
        if (slice.markdownDialect != null)
          'markdownDialect': slice.markdownDialect,
        if (slice.articleMarkdownDigest != null)
          'articleMarkdownDigest': slice.articleMarkdownDigest,
        if (slice.articleAssetManifest != null)
          'articleAssetManifest': _structuredValueToWire(
            slice.articleAssetManifest!,
          ),
        if (slice.articleRenderProfile != null)
          'articleRenderProfile': _structuredValueToWire(
            slice.articleRenderProfile!,
          ),
        if (slice.mediaItems.isNotEmpty)
          'mediaItems': slice.mediaItems
              .map(
                (item) => <String, dynamic>{
                  'kind': item.kind,
                  'url': item.url,
                  if (item.mediaAssetId != null)
                    'mediaAssetId': item.mediaAssetId,
                  if (item.mediaAssetVersion != null)
                    'mediaAssetVersion': item.mediaAssetVersion,
                  if (item.hlsCmafMasterManifestUrl != null)
                    'hlsCmafMasterManifestUrl': item.hlsCmafMasterManifestUrl,
                  if (item.hlsCmafDescriptorVersion != null)
                    'hlsCmafDescriptorVersion': item.hlsCmafDescriptorVersion,
                  if (item.coverUrl != null) 'coverUrl': item.coverUrl,
                  if (item.durationMs != null) 'durationMs': item.durationMs,
                  if (item.width != null) 'width': item.width,
                  if (item.height != null) 'height': item.height,
                  if (item.title != null) 'title': item.title,
                },
              )
              .toList(growable: false),
        if (slice.contentVertical != null)
          'contentVertical': slice.contentVertical,
        if (slice.paperThemeMode != null)
          'paperThemeMode': slice.paperThemeMode,
        if (slice.paperTexture != null) 'paperTexture': slice.paperTexture,
        if (slice.entityMentions.isNotEmpty)
          'entityMentions': slice.entityMentions
              .map(
                (mention) => <String, dynamic>{
                  'subjectType': mention.subjectType,
                  'subjectId': mention.subjectId,
                  'displayName': mention.displayName,
                  'rangeStart': mention.rangeStart,
                  'rangeEnd': mention.rangeEnd,
                },
              )
              .toList(growable: false),
        if (slice.coverUrl != null) 'coverUrl': slice.coverUrl,
        if (slice.tagRefs != null) 'tagRefs': slice.tagRefs,
        'status': slice.status,
        if (slice.moderationStatus != null)
          'moderationStatus': slice.moderationStatus,
        if (slice.visibility != null) 'visibility': slice.visibility,
      });
    return ContentPostDetailPayload.fromWire(wire);
  }

  Object? _structuredValueToWire(ContentPostStructuredValue value) {
    return switch (value) {
      ContentPostStructuredObject() => value.fields.map(
        (key, child) => MapEntry(key, _structuredValueToWire(child)),
      ),
      ContentPostStructuredArray() =>
        value.values.map(_structuredValueToWire).toList(growable: false),
      ContentPostStructuredText() => value.value,
      ContentPostStructuredNumber() => value.value,
      ContentPostStructuredBoolean() => value.value,
      ContentPostStructuredNull() => null,
    };
  }
}
