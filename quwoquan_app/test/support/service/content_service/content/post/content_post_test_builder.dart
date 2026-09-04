import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const String testContentAvatarUrl =
    'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png';
const String testContentImageUrl =
    'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png';
const String testContentVideoUrl =
    'media/video/s/video-primary-0001/post/video-content-0001/v1/source.mp4';

const String _testArticleDigest =
    'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

/// 构造一个对象级 Post 展示投影，不维护场景 Map 或 wire 字段副本。
ContentPostViewData contentPostViewDataBuilder({
  String postId = 'post-1',
  String contentType = 'micro',
  String? contentIdentity,
  String authorId = 'author-1',
  String authorDisplayName = '测试作者',
  String authorAvatarUrl = testContentAvatarUrl,
  String? authorAvatarAssetId,
  MediaDeliveryAccessMode? authorAvatarAccessMode =
      MediaDeliveryAccessMode.public,
  String? authorBackgroundUrl = testContentImageUrl,
  String title = '',
  String body = '测试正文',
  String summary = '',
  List<String>? mediaUrls,
  String? coverUrl,
  String? thumbnailUrl,
  String? videoUrl,
  String? mediaAssetId,
  int? mediaAssetVersion,
  List<PostMediaItem>? mediaItems,
  int? width,
  int? height,
  int? durationMs,
  String articleTemplate = '',
  String articleFontPreset = '',
  int likeCount = 0,
  int commentCount = 0,
  int shareCount = 0,
  DateTime? createdAt,
  String? supplySource,
}) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: postId,
      contentType: contentType,
      contentIdentity:
          contentIdentity ?? (contentType == 'micro' ? 'moment' : 'work'),
      assistantUsePolicy: AssistantUsePolicy.inherit,
      authorId: authorId,
      authorDisplayName: authorDisplayName,
      authorAvatarUrl: authorAvatarUrl,
      authorAvatarAssetId: authorAvatarAssetId,
      authorAvatarAccessMode: authorAvatarAccessMode,
      authorBackgroundUrl: authorBackgroundUrl,
      authorRoleLabel: '',
      authorIdentityTags: const <String>[],
      authorVerified: false,
      title: title,
      body: body,
      summary: summary,
      mediaUrls: mediaUrls,
      coverUrl: coverUrl,
      thumbnailUrl: thumbnailUrl,
      videoUrl: videoUrl,
      mediaAssetId: mediaAssetId,
      mediaAssetVersion: mediaAssetVersion,
      mediaItems:
          mediaItems ??
          _previousPublicMediaItems(
            mediaUrls: mediaUrls,
            coverUrl: coverUrl,
            thumbnailUrl: thumbnailUrl,
            videoUrl: videoUrl,
            durationMs: durationMs,
          ),
      width: width,
      height: height,
      durationMs: durationMs,
      articleTemplate: articleTemplate,
      articleFontPreset: articleFontPreset,
      likeCount: likeCount,
      commentCount: commentCount,
      shareCount: shareCount,
      createdAt: createdAt ?? DateTime.utc(2026, 1, 1),
      supplySource: supplySource,
    ),
  );
}

/// 按单个 suite 所需数量生成同类型 Post；调用方显式决定数量和用途。
List<ContentPostViewData> contentPostListBuilder({
  required String contentType,
  required int count,
  String idPrefix = 'post',
  String authorId = 'author-1',
}) {
  if (count < 0) {
    throw ArgumentError.value(count, 'count', 'must not be negative');
  }
  return List<ContentPostViewData>.generate(count, (index) {
    final position = index + 1;
    final isImage = contentType == 'image';
    final isVideo = contentType == 'video';
    final isArticle = contentType == 'article';
    return contentPostViewDataBuilder(
      postId: '${idPrefix}_$position',
      contentType: contentType,
      authorId: authorId,
      title: isArticle ? '测试文章 $position' : '',
      body: '测试内容 $position',
      summary: isArticle ? '测试文章摘要 $position' : '',
      mediaUrls: isImage ? const <String>[testContentImageUrl] : null,
      coverUrl: isImage || isArticle ? testContentImageUrl : null,
      thumbnailUrl: isVideo ? testContentImageUrl : null,
      videoUrl: isVideo ? testContentVideoUrl : null,
      width: isVideo
          ? 540
          : isImage
          ? 960
          : null,
      height: isVideo
          ? 960
          : isImage
          ? 800
          : null,
      durationMs: isVideo ? 15000 : null,
      articleTemplate: isArticle ? 'journal' : '',
      articleFontPreset: isArticle ? 'clean' : '',
      createdAt: DateTime.utc(2026, 1, 1).add(Duration(minutes: index)),
    );
  }, growable: false);
}

/// 构造一个 typed GetPost payload；文章正文只由本用例传入的 Markdown 决定。
///
/// [articleAssets] 供 canonical `asset://` 引用的用例注入 manifest 资产
/// （对齐真实发布物形态：assetId + publicSliceKey）。
ContentPostDetailPayload contentPostDetailPayloadBuilder({
  required ContentPostViewData post,
  String? articleMarkdown,
  List<PostArticleAsset> articleAssets = const <PostArticleAsset>[],
}) {
  final markdown = articleMarkdown?.trim();
  final hasMarkdown = markdown != null && markdown.isNotEmpty;
  final updatedAt = post.updatedAt ?? post.createdAt;
  return ContentPostDetailPayload.fromWire(
    ContentPostDetailSlice(
      postId: post.id,
      contentType: post.type,
      contentIdentity: post.identity,
      assistantUsePolicy: post.assistantUsePolicy,
      authorId: post.authorId,
      authorDisplayName: post.displayName,
      authorAvatarUrl: post.avatarUrl,
      title: post.title,
      body: post.body,
      summary: post.summary,
      mediaAssetIds: post.mediaAssetId == null
          ? null
          : <String>[post.mediaAssetId!],
      mediaUrls: post.imageUrls,
      coverUrl: post.coverUrl,
      thumbnailUrl: post.thumbnailUrl,
      videoUrl: post.videoUrl,
      width: post.width,
      height: post.height,
      durationMs: post.durationMs,
      articleMarkdown: hasMarkdown ? markdown : null,
      markdownDialect: hasMarkdown ? 'qwq-rich-md' : null,
      articleMarkdownDigest: hasMarkdown ? _testArticleDigest : null,
      articleAssetManifest: hasMarkdown
          ? PostArticleAssetManifest(
              schema: 'article-asset-manifest',
              articleMarkdownDigest: _testArticleDigest,
              documentSha256: _testArticleDigest,
              assetManifestSha256: _testArticleDigest,
              documentVersionSha256: _testArticleDigest,
              assets: articleAssets,
            )
          : null,
      articleRenderProfile: post.type == 'article'
          ? PostArticleRenderProfile(
              template: post.articleTemplate.isEmpty
                  ? 'journal'
                  : post.articleTemplate,
              fontPreset: post.articleFontPreset.isEmpty
                  ? 'clean'
                  : post.articleFontPreset,
            )
          : null,
      articleTemplate: post.articleTemplate,
      articleFontPreset: post.articleFontPreset,
      status: 'published',
      visibility: 'public',
      likeCount: post.likeCount,
      commentCount: post.commentCount,
      shareCount: post.shareCount,
      viewCount: 0,
      createdAt: post.createdAt,
      updatedAt: updatedAt,
      publishedAt: post.publishedAt,
    ),
  );
}

/// 已确认 previous contract fixture 的媒体条目适配器。
///
/// 本 helper 只服务测试夹具：旧夹具以顶层 URL 表达公开交付，因此在这里显式
/// 补成 typed public；生产 decoder 与正常契约路径不得据 URL 缺省猜 public。
List<PostMediaItem> _previousPublicMediaItems({
  required List<String>? mediaUrls,
  required String? coverUrl,
  required String? thumbnailUrl,
  required String? videoUrl,
  required int? durationMs,
}) {
  final items = <PostMediaItem>[];
  final normalizedVideo = videoUrl?.trim() ?? '';
  if (normalizedVideo.isNotEmpty) {
    final normalizedThumbnail = thumbnailUrl?.trim() ?? '';
    final normalizedCover = coverUrl?.trim() ?? '';
    items.add(
      PostMediaItem(
        kind: 'video',
        url: normalizedVideo,
        accessMode: MediaDeliveryAccessMode.public,
        coverUrl: normalizedThumbnail.isNotEmpty
            ? normalizedThumbnail
            : (normalizedCover.isEmpty ? null : normalizedCover),
        durationMs: durationMs,
      ),
    );
  }
  for (final raw in mediaUrls ?? const <String>[]) {
    final url = raw.trim();
    if (url.isEmpty || url == normalizedVideo) continue;
    items.add(
      PostMediaItem(
        kind: 'image',
        url: url,
        accessMode: MediaDeliveryAccessMode.public,
      ),
    );
  }
  return List<PostMediaItem>.unmodifiable(items);
}
