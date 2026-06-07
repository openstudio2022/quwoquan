import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show BehaviorAction, ReferralSource;
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_state.dart';
import 'package:quwoquan_app/ui/discovery/services/home_feed_media_viewer_wiring.dart';

/// 首页 / 精品 / 发现内容流统一的「点击 post → 沉浸 viewer」打开动作。
///
/// 抽取自 `HomePage._openFeedPost`，移动端与 Web 宽屏壳共用同一实现，保证
/// `referralSource` / `feedRequestId` 归因链与 [MediaViewerExtra] 构造同源，
/// 不在 Web 侧另起第二套数据链（见 .cursor/rules/13-coding-discipline R24/R25）。
Future<void> openHomeFeedPost(
  BuildContext context,
  WidgetRef ref, {
  required PostBaseDto post,
  required int mediaIndex,
  List<PostBaseDto>? feedPosts,
}) async {
  final viewerPosts = (feedPosts ?? const <PostBaseDto>[])
      .where((candidate) => candidate.supportsUnifiedViewer)
      .toList(growable: false);
  if (viewerPosts.isEmpty) {
    return;
  }

  final navFeedRequestId = ref
      .read(feedSessionProvider.notifier)
      .newFeedRequestId();
  // 入口 post 在 feed 中的位置（推荐归因；-1 → null 不上报）。
  final feedPosition = (feedPosts ?? const <PostBaseDto>[]).indexWhere(
    (item) => item.id == post.id,
  );
  ref
      .read(behaviorRepositoryProvider)
      .reportSingle(
        contentId: post.id,
        action: BehaviorAction.click,
        authorId: post.authorId,
        referralSource: ReferralSource.organicFeed,
        feedRequestId: navFeedRequestId,
        position: feedPosition >= 0 ? feedPosition : null,
      );

  final rawPostsById = homeFollowingMediaViewerRaws(
    content: ref.read(contentRepositoryProvider),
    viewerPosts: viewerPosts,
  );
  final postViews = viewerPosts
      .map(
        (dto) => ContentSurfaceViewMapper.fromDto(
          dto,
          wire: rawPostsById[dto.id]!.toDynamicMap(),
        ),
      )
      .toList(growable: false);
  final initialIndex = viewerPosts
      .indexWhere((item) => item.id == post.id)
      .clamp(0, viewerPosts.length - 1);
  final interactionSnapshot = buildMediaViewerInteractionSnapshot(
    posts: viewerPosts,
    discoveryState: ref.read(discoveryStateProvider),
    relationshipState: ref.read(userRelationshipStateProvider),
    postInteractionState: ref.read(postInteractionStateProvider),
  );
  primeMediaViewerInteractionSnapshot(ref, interactionSnapshot);
  final result = await context.push<Object?>(
    post.isVideoLike
        ? '/video-viewer/$initialIndex'
        : '/media-viewer/photo/$initialIndex',
    extra: MediaViewerExtra(
      posts: postViews,
      dtoPosts: viewerPosts,
      initialIndex: initialIndex,
      category: 'following',
      source: 'following',
      initialImageIndex: mediaIndex,
      rawPostsById: rawPostsById,
      interactionSnapshot: interactionSnapshot,
      feedRequestId: navFeedRequestId,
      position: feedPosition >= 0 ? feedPosition : null,
    ),
  );
  if (result is MediaViewerResult) {
    applyMediaViewerResultToInteractionState(ref, result);
  }
}
