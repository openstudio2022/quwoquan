import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers_circle_facets.dart'
    show
        circleDetailFeedQueryProvider,
        circleDetailPostPlacementCommandWriterProvider,
        circleDetailQueryProvider;
import 'package:quwoquan_app/runtime/di/content_surface_view_mapper.dart';
import 'package:quwoquan_app/runtime/di/feed_session_provider.dart';
import 'package:quwoquan_app/runtime/di/media_viewer_interaction_facade.dart';
import 'package:quwoquan_app/runtime/di/post_interaction_state_dependencies.dart';
import 'package:quwoquan_app/runtime/di/recommendation_presentation_slots.dart'
    show profileRecommendationSlots;
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_creations_participant_slots.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/record_post_card.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

ArticleDistributionProfileConfig get _circleArticleDistributionProfile =>
    ContentUIConfig.articleDistributionProfiles.singleWhere(
      (profile) => profile.surface == 'circle_dual_column',
    );

int _circleArticleSummaryLineLimit() =>
    _circleArticleDistributionProfile.summaryLineLimit;

Widget _buildCircleRecordPostCard({
  Key? key,
  required ContentPostViewData post,
  required bool isDark,
  required VoidCallback onTap,
  required bool showAuthor,
  required ReferralSource referralSource,
}) => RecordPostCard(
  key: key,
  post: post,
  isDark: isDark,
  onTap: onTap,
  buildIntersectionReason: profileRecommendationSlots.buildIntersectionReason,
  resolveLikeCount: _resolvePostLikeCount,
  showAuthor: showAuthor,
  referralSource: referralSource,
);

int _resolvePostLikeCount(
  WidgetRef ref,
  String postId, {
  required int fallback,
}) {
  ref.watch(postInteractionStateProvider);
  return effectivePostLikeCount(ref, postId, fallback: fallback);
}

Widget? _buildCircleIntersectionReason(
  List<IntersectionReason>? reasons, {
  required bool isDark,
  required ReferralSource referralSource,
  required String contextObjectName,
  required IntersectionTarget contextObjectTarget,
}) => profileRecommendationSlots.buildIntersectionReason(
  reasons,
  isDark: isDark,
  referralSource: referralSource,
  contextObjectName: contextObjectName,
  contextObjectTarget: contextObjectTarget,
);

List<String> _recommendedArticleTemplates(String circleCategoryId) =>
    ContentUIConfig.articleTemplateRecommendations
        .where(
          (recommendation) => recommendation.categoryId == circleCategoryId,
        )
        .expand((recommendation) => recommendation.recommendedArticleTemplates)
        .toList(growable: false);

Future<CircleFeedPageSlice> _loadCircleFeed(
  WidgetRef ref,
  CircleFeedQuery query,
) => ref.read(circleDetailFeedQueryProvider).feed(query);

Future<Circle> _loadCircle(WidgetRef ref, CircleDetailQuery query) =>
    ref.read(circleDetailQueryProvider).get(query);

Future<CirclePostPlacementCommandResult> _setPostPinned(
  WidgetRef ref,
  PinCirclePostCommand command,
) =>
    ref.read(circleDetailPostPlacementCommandWriterProvider).setPinned(command);

Future<CirclePostPlacementCommandResult> _setPostFeatured(
  WidgetRef ref,
  FeatureCirclePostCommand command,
) => ref
    .read(circleDetailPostPlacementCommandWriterProvider)
    .setFeatured(command);

Future<CirclePostPlacementCommandResult> _removePost(
  WidgetRef ref,
  RemoveCirclePostCommand command,
) => ref
    .read(circleDetailPostPlacementCommandWriterProvider)
    .removePost(command);

String _newFeedRequestId(WidgetRef ref) =>
    ref.read(feedSessionProvider.notifier).newFeedRequestId();

const CircleCreationsParticipantSlots circleCreationsParticipantSlots =
    CircleCreationsParticipantSlots(
      buildRecordPostCard: _buildCircleRecordPostCard,
      buildIntersectionReason: _buildCircleIntersectionReason,
      articleSummaryLineLimit: _circleArticleSummaryLineLimit,
      recommendedArticleTemplates: _recommendedArticleTemplates,
      loadFeed: _loadCircleFeed,
      loadCircle: _loadCircle,
      setPostPinned: _setPostPinned,
      setPostFeatured: _setPostFeatured,
      removePost: _removePost,
      buildMediaViewerSnapshot: buildMediaViewerInteractionSnapshot,
      primeMediaViewerSnapshot: primeMediaViewerInteractionSnapshot,
      applyMediaViewerResult: applyMediaViewerResultToInteractionState,
      newFeedRequestId: _newFeedRequestId,
      mapContentSurface: ContentSurfaceViewMapper.fromDto,
    );
