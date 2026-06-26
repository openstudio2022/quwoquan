import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_intersection_insight_primitives.dart';

/// TA 主页「我与TA的交集」预览卡。
///
/// 视觉与我的主页交集入口同源：单列预览句 + 弱入口「查看全部」。
/// 无交集时不再整块消失，而是展示克制空态，避免主页 IA 断层。
class OtherProfileIntersectionCard extends ConsumerWidget {
  const OtherProfileIntersectionCard({super.key, required this.userId});

  static const Key cardKey = ValueKey<String>(
    'other-profile-intersection-card',
  );
  static const Key emptyKey = ValueKey<String>(
    'other-profile-intersection-empty',
  );

  final String userId;

  IntersectionTargetNavigator _navigator(WidgetRef ref) =>
      IntersectionTargetNavigator(
        onTrack: (target, attribution) {
          final id = target.objectId.trim();
          if (id.isEmpty) {
            return;
          }
          ref
              .read(contentBehaviorTrackerProvider)
              .trackClick(
                id,
                referralSource: ReferralSource.authorProfile,
                intersectionId: attribution.intersectionId,
                intersectionDimension: attribution.dimension,
                intersectionClass: attribution.intersectionClass,
                intersectionSourceRef: attribution.sourceRef,
                intersectionTagRefs: attribution.tagRefs,
                intersectionEvidenceId: attribution.evidenceId,
              );
        },
      );

  void _openList(BuildContext context) {
    context.push(
      AppRoutePaths.objectIntersections(
        objectId: userId,
        objectType: 'user',
        title: UITextConstants.profileWhyRecommendTitle,
      ),
    );
  }

  void _onSpanTap(
    BuildContext context,
    WidgetRef ref,
    IntersectionReason reason,
    IntersectionTextSpan span,
  ) {
    if (span.role == 'count') {
      _openList(context);
      return;
    }
    final target = span.target;
    if (target == null) {
      return;
    }
    _navigator(ref).open(
      context,
      target,
      sourceRef: profileIntersectionSourceRef(reason),
      attribution: IntersectionNavAttribution(
        intersectionId: reason.intersectionId,
        dimension: reason.dimension,
        intersectionClass: reason.intersectionClass,
        sourceRef: profileIntersectionSourceRef(reason),
        tagRefs: reason.tagRefs,
        evidenceId: reason.pointSummarySnapshotId,
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final title = UITextConstants.profileWhyRecommendTitle;
    final viewerId = ref.watch(currentUserIdProvider);
    final query = ObjectIntersectionQuery(
      objectAId: viewerId,
      objectAType: 'user',
      objectBId: userId,
      objectBType: 'user',
    );
    if (!query.isResolvable) {
      return _buildCard(
        context: context,
        title: title,
        showAction: false,
        child: const ProfileIntersectionEmptyState(
          key: emptyKey,
          text: UITextConstants.profileIntersectionEmptyOther,
        ),
      );
    }
    final async = ref.watch(objectSharedReasonsProvider(query));
    return async.when(
      loading: () => _buildCard(
        context: context,
        title: title,
        showAction: false,
        child: const ProfileIntersectionSkeletonList(),
      ),
      error: (_, _) => _buildCard(
        context: context,
        title: title,
        showAction: false,
        child: const ProfileIntersectionEmptyState(
          key: emptyKey,
          text: UITextConstants.profileIntersectionEmptyOther,
        ),
      ),
      data: (reasons) {
        final visible = reasons
            .where((item) => item.primaryText.trim().isNotEmpty)
            .take(3)
            .toList(growable: false);
        return _buildCard(
          context: context,
          title: title,
          showAction: visible.isNotEmpty,
          child: visible.isEmpty
              ? const ProfileIntersectionEmptyState(
                  key: emptyKey,
                  text: UITextConstants.profileIntersectionEmptyOther,
                )
              : Column(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    for (var index = 0; index < visible.length; index += 1) ...[
                      if (index > 0) const ProfileInsightDivider(),
                      ProfileIntersectionPreviewRow(
                        reason: visible[index],
                        onTap: () => _openList(context),
                        onSpanTap: (span) =>
                            _onSpanTap(context, ref, visible[index], span),
                      ),
                    ],
                  ],
                ),
        );
      },
    );
  }

  Widget _buildCard({
    required BuildContext context,
    required String title,
    required Widget child,
    required bool showAction,
  }) {
    return ProfileInsightSectionCard(
      key: cardKey,
      title: title,
      actionLabel: showAction ? DiscoveryFeedText.intersectionViewAll : null,
      onAction: showAction ? () => _openList(context) : null,
      topPadding: true,
      child: child,
    );
  }
}
