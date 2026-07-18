import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentPostReaderInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// Content Post 详情与作者作品的正式远端 Reader。
///
/// 仅接收生成客户端与调用上下文；App DTO 的转换被限制在本适配器，业务消费者
/// 不接触 HTTP、header、decoder 或 URL path。
final class RemoteContentPostReaderAdapter
    implements ContentPostDetailReader, ContentAuthorPostsReader {
  const RemoteContentPostReaderAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ContentPostReaderInvocationContextFactory invocationContext;

  @override
  Future<ContentPostDetailPayload> getPost({required String postId}) async {
    final response = await client.contentPostGetPost(
      ContentPostDetailQuery(postId: postId),
      context: invocationContext(ContentRequestPageIds.getPost),
    );
    return _detailPayloadFromSlice(response);
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
        subAccountId: userId,
        identity: identity,
        type: type,
        visibility: visibility,
        cursor: cursor,
        limit: limit,
      ),
      context: invocationContext(ContentRequestPageIds.listUserPosts),
    );
    return CursorPage<PostBaseDto>(
      items: response.items.map(_postDtoFromProjection).toList(growable: false),
      nextCursor: response.nextCursor,
      totalCount: response.totalCount,
    );
  }

  ContentPostDetailPayload _detailPayloadFromSlice(
    ContentPostDetailSlice slice,
  ) {
    final wire = _postWireFromProjection(slice.post)
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
        if (slice.visibility != null) 'visibility': slice.visibility,
      });
    return ContentPostDetailPayload.fromWire(wire);
  }

  PostBaseDto _postDtoFromProjection(ContentPostProjection projection) {
    return postBaseDtoFromMap(_postWireFromProjection(projection));
  }

  /// 唯一 DTO projection boundary：纯合同投影在这里映射到 App DTO。
  Map<String, dynamic> _postWireFromProjection(
    ContentPostProjection projection,
  ) {
    return <String, dynamic>{
      'id': projection.postId,
      'type': projection.contentType,
      if (projection.contentIdentity != null)
        'identity': projection.contentIdentity,
      'assistantUsePolicy': projection.assistantUsePolicy,
      if (projection.authorId != null) 'authorId': projection.authorId,
      if (projection.authorDisplayName != null)
        'displayName': projection.authorDisplayName,
      if (projection.authorAvatarUrl != null)
        'avatarUrl': projection.authorAvatarUrl,
      if (projection.authorBackgroundUrl != null)
        'authorBackgroundUrl': projection.authorBackgroundUrl,
      if (projection.authorRoleLabel != null)
        'authorRoleLabel': projection.authorRoleLabel,
      'authorIdentityTags': projection.authorIdentityTags,
      'authorVerified': projection.authorVerified,
      if (projection.title != null) 'title': projection.title,
      if (projection.body != null) 'body': projection.body,
      if (projection.summary != null) 'summary': projection.summary,
      if (projection.coverUrl != null) 'coverUrl': projection.coverUrl,
      'imageUrls': projection.imageUrls,
      if (projection.videoUrl != null) 'videoUrl': projection.videoUrl,
      if (projection.thumbnailUrl != null)
        'thumbnailUrl': projection.thumbnailUrl,
      if (projection.width != null) 'width': projection.width,
      if (projection.height != null) 'height': projection.height,
      if (projection.durationMs != null) 'durationMs': projection.durationMs,
      'likeCount': projection.likeCount,
      'commentCount': projection.commentCount,
      'shareCount': projection.shareCount,
      if (projection.createdAt != null)
        'createdAt': projection.createdAt!.toUtc().toIso8601String(),
      if (projection.updatedAt != null)
        'updatedAt': projection.updatedAt!.toUtc().toIso8601String(),
      if (projection.publishedAt != null)
        'publishedAt': projection.publishedAt!.toUtc().toIso8601String(),
      if (projection.contentVertical != null)
        'contentVertical': projection.contentVertical,
      if (projection.recallPath != null) 'recallPath': projection.recallPath,
      if (projection.supplySource != null)
        'supplySource': projection.supplySource,
      if (projection.intersectionReasons != null)
        'intersectionReasons': projection.intersectionReasons!
            .map(
              (reason) => <String, dynamic>{
                'kind': reason.kind,
                'primaryText': reason.primaryText,
                'secondaryText': reason.secondaryText,
                'strength': reason.strength,
              },
            )
            .toList(growable: false),
    };
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
