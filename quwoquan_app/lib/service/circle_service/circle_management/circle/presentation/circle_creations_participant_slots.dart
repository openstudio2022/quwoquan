import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CircleRecordPostCardBuilder =
    Widget Function({
      Key? key,
      required ContentPostViewData post,
      required bool isDark,
      required VoidCallback onTap,
      required bool showAuthor,
      required ReferralSource referralSource,
    });

typedef CircleIntersectionReasonSlotBuilder =
    Widget? Function(
      List<IntersectionReason>? reasons, {
      required bool isDark,
      required ReferralSource referralSource,
      required String contextObjectName,
      required IntersectionTarget contextObjectTarget,
    });

typedef CircleRecommendedArticleTemplates =
    List<String> Function(String circleCategoryId);
typedef CircleArticleSummaryLineLimit = int Function();

typedef CircleCreationsFeedLoader =
    Future<CircleFeedPageSlice> Function(WidgetRef ref, CircleFeedQuery query);
typedef CircleCreationsDetailLoader =
    Future<Circle> Function(WidgetRef ref, CircleDetailQuery query);
typedef CirclePostPinnedUpdater =
    Future<CirclePostPlacementCommandResult> Function(
      WidgetRef ref,
      PinCirclePostCommand command,
    );
typedef CirclePostFeaturedUpdater =
    Future<CirclePostPlacementCommandResult> Function(
      WidgetRef ref,
      FeatureCirclePostCommand command,
    );
typedef CirclePostRemover =
    Future<CirclePostPlacementCommandResult> Function(
      WidgetRef ref,
      RemoveCirclePostCommand command,
    );
typedef CircleMediaViewerSnapshotBuilder =
    MediaViewerInteractionSnapshot Function({
      required WidgetRef ref,
      required Iterable<ContentPostViewData> posts,
    });
typedef CircleMediaViewerSnapshotPrimer =
    void Function(WidgetRef ref, MediaViewerInteractionSnapshot snapshot);
typedef CircleMediaViewerResultApplier =
    void Function(WidgetRef ref, MediaViewerResult result);
typedef CircleFeedRequestIdFactory = String Function(WidgetRef ref);
typedef CircleContentSurfaceMapper =
    ContentSurfaceView Function(ContentPostViewData post);

/// Circle source owner 对 Content/Recommendation presentation 的 typed slots。
///
/// 圈内创作保留 Circle 自己的管理与布局状态；Post 卡和交集句的具体 Widget、
/// Content authoring 的文章配置只在 runtime/di 绑定，避免私有 presentation 横穿对象。
final class CircleCreationsParticipantSlots {
  const CircleCreationsParticipantSlots({
    required this.buildRecordPostCard,
    required this.buildIntersectionReason,
    required this.articleSummaryLineLimit,
    required this.recommendedArticleTemplates,
    required this.loadFeed,
    required this.loadCircle,
    required this.setPostPinned,
    required this.setPostFeatured,
    required this.removePost,
    required this.buildMediaViewerSnapshot,
    required this.primeMediaViewerSnapshot,
    required this.applyMediaViewerResult,
    required this.newFeedRequestId,
    required this.mapContentSurface,
  });

  final CircleRecordPostCardBuilder buildRecordPostCard;
  final CircleIntersectionReasonSlotBuilder buildIntersectionReason;
  final CircleArticleSummaryLineLimit articleSummaryLineLimit;
  final CircleRecommendedArticleTemplates recommendedArticleTemplates;
  final CircleCreationsFeedLoader loadFeed;
  final CircleCreationsDetailLoader loadCircle;
  final CirclePostPinnedUpdater setPostPinned;
  final CirclePostFeaturedUpdater setPostFeatured;
  final CirclePostRemover removePost;
  final CircleMediaViewerSnapshotBuilder buildMediaViewerSnapshot;
  final CircleMediaViewerSnapshotPrimer primeMediaViewerSnapshot;
  final CircleMediaViewerResultApplier applyMediaViewerResult;
  final CircleFeedRequestIdFactory newFeedRequestId;
  final CircleContentSurfaceMapper mapContentSurface;
}
