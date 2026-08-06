import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

ContentPostViewData contentCachePostFixture(
  String id, {
  String authorId = 'user_1',
  String avatarUrl = '',
  String body = '缓存内容',
  List<IntersectionReason>? intersectionReasons,
}) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: id,
      contentType: 'micro',
      contentIdentity: 'moment',
      assistantUsePolicy: 'inherit',
      authorId: authorId,
      authorDisplayName: '用户一',
      authorAvatarUrl: avatarUrl,
      body: body,
      mediaUrls: const <String>[],
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
      createdAt: DateTime.utc(2026, 5, 19),
      updatedAt: DateTime.utc(2026, 5, 19),
      intersectionReasons: intersectionReasons,
    ),
  );
}

ContentPostDetailPayload contentCacheDetailPayloadFixture(
  String id, {
  ContentPostViewData? post,
}) {
  final resolvedPost = post ?? contentCachePostFixture(id);
  return ContentPostDetailPayload.fromWire(
    ContentPostDetailSlice(
      postId: id,
      contentType: resolvedPost.type,
      contentIdentity: resolvedPost.identity,
      assistantUsePolicy: resolvedPost.assistantUsePolicy,
      authorId: resolvedPost.authorId,
      authorDisplayName: resolvedPost.displayName,
      authorAvatarUrl: resolvedPost.avatarUrl,
      body: resolvedPost.body,
      mediaUrls: resolvedPost.mediaImageUrls,
      coverUrl: resolvedPost.coverUrl,
      videoUrl: resolvedPost.videoUrl,
      thumbnailUrl: resolvedPost.thumbnailUrl,
      durationMs: resolvedPost.durationMs,
      status: 'published',
      visibility: 'public',
      likeCount: resolvedPost.likeCount,
      commentCount: resolvedPost.commentCount,
      shareCount: resolvedPost.shareCount,
      viewCount: 0,
      createdAt: resolvedPost.createdAt,
      updatedAt: resolvedPost.updatedAt ?? resolvedPost.createdAt,
    ),
  );
}
