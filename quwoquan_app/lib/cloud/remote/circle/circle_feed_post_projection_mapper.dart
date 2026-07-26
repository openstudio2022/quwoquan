import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 将 CircleFeedItemView 内嵌的 pure-Dart Post 投影一次映射为 App DTO。
///
/// 此处按 metadata 的 `contentType` 判别受限联合类型，避免 Circle Hub 将 Post
/// 序列化成动态 wire map 再由 generated factory 反向解析。
final class CircleFeedPostProjectionMapper {
  const CircleFeedPostProjectionMapper();

  PostBaseDto toDto(ContentPostProjection projection) {
    switch (projection.contentType) {
      case 'image':
        return _photo(projection);
      case 'video':
        return _video(projection);
      case 'article':
        return _article(projection);
      case 'micro':
        return _micro(projection);
      default:
        throw ArgumentError.value(
          projection.contentType,
          'contentType',
          'CircleFeedItemView only supports image|video|article|micro',
        );
    }
  }

  PhotoPostDto _photo(ContentPostProjection source) {
    return PhotoPostDto(
      id: source.postId,
      type: source.contentType,
      identity: _identity(source, fallback: 'work'),
      assistantUsePolicy: source.assistantUsePolicy,
      authorId: source.authorId ?? '',
      displayName: source.authorDisplayName ?? '',
      avatarUrl: source.authorAvatarUrl ?? '',
      authorBackgroundUrl: source.authorBackgroundUrl,
      authorRoleLabel: source.authorRoleLabel ?? '',
      authorIdentityTags: source.authorIdentityTags,
      authorVerified: source.authorVerified,
      body: source.body,
      coverUrl: source.coverUrl ?? '',
      imageUrls: source.mediaUrls,
      width: source.width,
      height: source.height,
      likeCount: source.likeCount,
      commentCount: source.commentCount,
      shareCount: source.shareCount,
      createdAt: _createdAt(source),
      updatedAt: source.updatedAt,
      publishedAt: source.publishedAt,
      contentVertical: source.contentVertical,
      recallPath: source.recallPath,
      supplySource: source.supplySource,
      intersectionReasons: _intersectionReasons(source),
    );
  }

  VideoPostDto _video(ContentPostProjection source) {
    final cover = source.coverUrl ?? source.thumbnailUrl ?? '';
    final explicitVideoUrl = source.videoUrl?.trim() ?? '';
    final videoUrl = explicitVideoUrl.isNotEmpty
        ? explicitVideoUrl
        : (source.mediaUrls.isEmpty ? '' : source.mediaUrls.first);
    return VideoPostDto(
      id: source.postId,
      type: source.contentType,
      identity: _identity(source, fallback: 'work'),
      assistantUsePolicy: source.assistantUsePolicy,
      authorId: source.authorId ?? '',
      displayName: source.authorDisplayName ?? '',
      avatarUrl: source.authorAvatarUrl ?? '',
      authorBackgroundUrl: source.authorBackgroundUrl,
      authorRoleLabel: source.authorRoleLabel ?? '',
      authorIdentityTags: source.authorIdentityTags,
      authorVerified: source.authorVerified,
      body: source.body,
      videoUrl: videoUrl,
      thumbnailUrl: source.thumbnailUrl ?? '',
      coverUrl: cover,
      width: source.width,
      height: source.height,
      durationMs: source.durationMs,
      likeCount: source.likeCount,
      commentCount: source.commentCount,
      shareCount: source.shareCount,
      createdAt: _createdAt(source),
      updatedAt: source.updatedAt,
      publishedAt: source.publishedAt,
      contentVertical: source.contentVertical,
      recallPath: source.recallPath,
      supplySource: source.supplySource,
      intersectionReasons: _intersectionReasons(source),
    );
  }

  ArticlePostDto _article(ContentPostProjection source) {
    return ArticlePostDto(
      id: source.postId,
      type: source.contentType,
      identity: _identity(source, fallback: 'work'),
      assistantUsePolicy: source.assistantUsePolicy,
      authorId: source.authorId ?? '',
      displayName: source.authorDisplayName ?? '',
      avatarUrl: source.authorAvatarUrl ?? '',
      authorBackgroundUrl: source.authorBackgroundUrl,
      authorRoleLabel: source.authorRoleLabel ?? '',
      authorIdentityTags: source.authorIdentityTags,
      authorVerified: source.authorVerified,
      title: source.title ?? '',
      body: source.body ?? '',
      summary: source.summary ?? '',
      coverUrl: source.coverUrl ?? '',
      articleTemplate: source.articleTemplate ?? 'gentle',
      articleFontPreset: source.articleFontPreset ?? 'clean',
      likeCount: source.likeCount,
      commentCount: source.commentCount,
      shareCount: source.shareCount,
      createdAt: _createdAt(source),
      updatedAt: source.updatedAt,
      publishedAt: source.publishedAt,
      contentVertical: source.contentVertical,
      recallPath: source.recallPath,
      supplySource: source.supplySource,
      intersectionReasons: _intersectionReasons(source),
    );
  }

  MicroPostDto _micro(ContentPostProjection source) {
    final videoUrl = source.videoUrl?.trim() ?? '';
    return MicroPostDto(
      id: source.postId,
      type: source.contentType,
      identity: _identity(source, fallback: 'moment'),
      assistantUsePolicy: source.assistantUsePolicy,
      authorId: source.authorId ?? '',
      displayName: source.authorDisplayName ?? '',
      avatarUrl: source.authorAvatarUrl ?? '',
      authorBackgroundUrl: source.authorBackgroundUrl,
      authorRoleLabel: source.authorRoleLabel ?? '',
      authorIdentityTags: source.authorIdentityTags,
      authorVerified: source.authorVerified,
      body: source.body ?? '',
      imageUrls: videoUrl.isEmpty ? source.mediaUrls : const <String>[],
      videoUrl: videoUrl.isEmpty ? null : videoUrl,
      durationMs: source.durationMs,
      likeCount: source.likeCount,
      commentCount: source.commentCount,
      shareCount: source.shareCount,
      createdAt: _createdAt(source),
      updatedAt: source.updatedAt,
      publishedAt: source.publishedAt,
      contentVertical: source.contentVertical,
      recallPath: source.recallPath,
      supplySource: source.supplySource,
      intersectionReasons: _intersectionReasons(source),
    );
  }

  String _identity(ContentPostProjection source, {required String fallback}) {
    final identity = source.contentIdentity?.trim() ?? '';
    return identity.isEmpty ? fallback : identity;
  }

  DateTime _createdAt(ContentPostProjection source) {
    return source.createdAt ??
        DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
  }

  List<IntersectionReason>? _intersectionReasons(ContentPostProjection source) {
    final reasons = source.intersectionReasons;
    if (reasons == null) {
      return null;
    }
    return reasons
        .map(
          (reason) => IntersectionReason(
            kind: reason.kind,
            primaryText: reason.primaryText,
            secondaryText: reason.secondaryText,
            strength: reason.strength,
          ),
        )
        .toList(growable: false);
  }
}
