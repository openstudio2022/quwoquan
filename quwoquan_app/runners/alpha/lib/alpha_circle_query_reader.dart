import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

/// Alpha runner 对 Circle typed query contracts 的 fixture 适配器。
///
/// 旧 alpha repository 仅作为 runner 内 fixture authority；页面与 production
/// composition 始终消费 pure-Dart typed query contracts。
final class AlphaCircleQueryReader
    implements CircleFeedQueryReader, CircleDiscoveryFeedQueryReader {
  const AlphaCircleQueryReader(this._repository, this._placements);

  final CircleRepository _repository;
  final AlphaCirclePostPlacementStore _placements;

  @override
  Future<CircleFeedPageSlice> feed(CircleFeedQuery query) async {
    final posts = await _repository.getCircleFeed(
      query.circleId,
      identity: query.identity,
      type: query.type,
      cursor: query.cursor,
      limit: query.limit,
      sort: query.sort,
    );
    return CircleFeedPageSlice(
      items: posts
          .map((post) => _feedProjection(query.circleId, post))
          .whereType<CircleFeedPostProjection>(),
    );
  }

  @override
  Future<CircleDiscoveryFeedPageSlice> listDiscoveryFeed(
    CircleDiscoveryFeedQuery query,
  ) async {
    final circles = await _repository.listCircles(
      category: query.category,
      subCategory: query.subCategory,
      cursor: query.cursor,
      limit: query.limit,
      sort: query.sort,
    );
    final items = <CircleFeedPostProjection>[];
    for (final circle in circles) {
      if (items.length >= query.limit) {
        break;
      }
      final posts = await _repository.getCircleFeed(
        circle.id,
        limit: query.limit - items.length,
        sort: query.sort,
      );
      items.addAll(
        posts
            .map((post) => _feedProjection(circle.id, post))
            .whereType<CircleFeedPostProjection>(),
      );
    }
    return CircleDiscoveryFeedPageSlice(
      circles: circles.map(_circleProjection),
      items: items,
    );
  }

  CircleFeedPostProjection? _feedProjection(
    String circleId,
    PostBaseDto post,
  ) {
    final placementId = 'alpha-placement-$circleId-${post.id}';
    final presentation = _placements.presentation(placementId);
    if (presentation.removed) {
      return null;
    }
    return CircleFeedPostProjection(
      circleId: circleId,
      placementId: placementId,
      post: _postProjection(post),
      pinned: presentation.pinned,
      featured: presentation.featured,
    );
  }
}

CircleProjection _circleProjection(CircleDto circle) {
  return CircleProjection(
    circleId: circle.id,
    name: circle.name,
    description: circle.description,
    coverUrl: circle.coverUrl,
    iconUrl: circle.iconUrl,
    ownerId: circle.ownerId,
    category: circle.category,
    tags: circle.tags,
    memberCount: circle.memberCount,
    postCount: circle.postCount,
    weeklyActiveCount: circle.weeklyActiveCount,
    status: circle.status,
    visibility: circle.visibility,
    joinPolicy: circle.joinPolicy,
    kind: circle.kind,
    displaySubjectType: circle.displaySubjectType,
    followEnabled: circle.followEnabled,
    defaultPublicGroupId: circle.defaultPublicGroupId,
    conversationId: circle.conversationId,
    autoSyncChat: circle.autoSyncChat,
    storageUsedBytes: circle.storageUsedBytes,
    storageQuotaBytes: circle.storageQuotaBytes,
    domainId: circle.domainId,
    subCategory: circle.subCategory,
    createdAt: circle.createdAt,
    updatedAt: circle.updatedAt,
  );
}

ContentPostProjection _postProjection(PostBaseDto post) {
  return ContentPostProjection(
    postId: post.id,
    contentType: post.type,
    contentIdentity: _optional(post.identity),
    assistantUsePolicy: post.assistantUsePolicy,
    authorId: _optional(post.authorId),
    authorDisplayName: _optional(post.displayName),
    authorAvatarUrl: _optional(post.avatarUrl),
    authorBackgroundUrl: _optional(post.authorBackgroundUrl),
    authorRoleLabel: _optional(post.authorRoleLabel),
    authorIdentityTags: post.authorIdentityTags,
    authorVerified: post.authorVerified,
    title: _optional(post.normalizedTitle),
    body: _optional(post.normalizedBody),
    summary: _optional(post.summary),
    coverUrl: _optional(post.mediaCoverUrl),
    articleTemplate: _optional(post.articleTemplate),
    articleFontPreset: _optional(post.articleFontPreset),
    imageUrls: post.mediaImageUrls,
    videoUrl: _optional(post.mediaVideoUrl),
    thumbnailUrl: _optional(post.mediaThumbnailUrl),
    durationMs: post.durationMs,
    likeCount: post.likeCount,
    commentCount: post.commentCount,
    shareCount: post.shareCount,
    createdAt: post.createdAt,
    updatedAt: post.updatedAt,
    publishedAt: post.publishedAt,
    contentVertical: _optional(post.contentVertical),
    recallPath: _optional(post.recallPath),
    supplySource: _optional(post.supplySource),
    intersectionReasons: post.intersectionReasons?.map(
      (reason) => ContentPostIntersectionReason(
        kind: reason.kind,
        primaryText: reason.primaryText,
        secondaryText: reason.secondaryText,
        strength: reason.strength,
      ),
    ),
  );
}

String? _optional(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}
