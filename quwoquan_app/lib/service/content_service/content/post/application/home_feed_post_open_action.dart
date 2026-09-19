import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/di/navigation/content_open_surface_navigation.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/content_presentation_terminal.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show BehaviorEvent, ReferralSource, ReferralSourceExt;
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/media_viewer_interaction_facade.dart';
import 'package:quwoquan_app/runtime/di/content_surface_view_mapper.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show BehaviorEventType;

/// 首页 / 精品 / 发现内容流统一的「点击 post → 沉浸 viewer」打开动作。
///
/// 抽取自 `HomePage._openFeedPost`，移动端与 Web 宽屏壳共用同一实现，保证
/// `referralSource` / `feedRequestId` 归因链与 [MediaViewerExtra] 构造同源，
/// 不在 Web 侧另起第二套数据链。
Future<void> openHomeFeedPost(
  BuildContext context,
  WidgetRef ref, {
  required ContentPostViewData post,
  required int mediaIndex,
  required String channelId,
  List<ContentPostViewData>? feedPosts,
}) async {
  final viewerPosts = (feedPosts ?? const <ContentPostViewData>[])
      .where((candidate) => candidate.supportsUnifiedViewer)
      .toList(growable: false);
  if (viewerPosts.isEmpty) {
    return;
  }

  // 从被点击频道自己的状态读取同源归因，禁止跨频道复用全局最后一次摘要。
  final feedAttribution = ref.read(discoveryFeedProvider(channelId)).value;
  final navFeedRequestId = feedAttribution?.feedRequestId;
  final navPolicyDigest = feedAttribution?.policyDigest;
  // 入口 post 在 feed 中的位置（推荐归因；-1 → null 不上报）。
  final feedPosition = (feedPosts ?? const <ContentPostViewData>[]).indexWhere(
    (item) => item.id == post.id,
  );
  ref
      .read(behaviorReporterProvider)
      .reportEvents(
        events: <BehaviorEvent>[
          BehaviorEvent(
            contentId: post.id,
            action: BehaviorEventType.click,
            state: 'click',
            clientEventId:
                'home_click:${post.id}:${DateTime.now().toUtc().microsecondsSinceEpoch}',
            authorId: post.authorId,
            referralSource: ReferralSource.organicFeed,
            feedRequestId: navFeedRequestId,
            policyDigest: navPolicyDigest,
            position: feedPosition >= 0 ? feedPosition : null,
          ),
        ],
      );

  final postViews = viewerPosts
      .map(ContentSurfaceViewMapper.fromDto)
      .toList(growable: false);
  final initialIndex = viewerPosts
      .indexWhere((item) => item.id == post.id)
      .clamp(0, viewerPosts.length - 1);
  // 目的地只来自云物化的 openSurface；内容类型只在目的面内选媒体槽。
  final openSurface = post.openSurface;
  final destination = ContentOpenSurfaceNavigation.canOpen(openSurface)
      ? ContentOpenSurfaceNavigation.pathFor(
          openSurface: openSurface!,
          objectId: post.id,
          source: ReferralSource.organicFeed.value,
          index: '$initialIndex',
          sourceTheme: uiErrorAppearanceRouteValueFor(context),
        )
      : null;
  if (destination == null) {
    await showContentPresentationUnsupportedTerminal(
      context,
      objectId: post.id,
      openSurface: openSurface,
    );
    return;
  }
  final interactionSnapshot = buildMediaViewerInteractionSnapshot(
    ref: ref,
    posts: viewerPosts,
  );
  primeMediaViewerInteractionSnapshot(ref, interactionSnapshot);
  final result = await context.push<Object?>(
    destination,
    extra: MediaViewerExtra(
      posts: postViews,
      dtoPosts: viewerPosts,
      initialIndex: initialIndex,
      referralSource: ReferralSource.organicFeed,
      initialImageIndex: mediaIndex,
      interactionSnapshot: interactionSnapshot,
      feedRequestId: navFeedRequestId,
      policyDigest: navPolicyDigest,
      position: feedPosition >= 0 ? feedPosition : null,
    ),
  );
  if (result is MediaViewerResult) {
    applyMediaViewerResultToInteractionState(ref, result);
  }
}
