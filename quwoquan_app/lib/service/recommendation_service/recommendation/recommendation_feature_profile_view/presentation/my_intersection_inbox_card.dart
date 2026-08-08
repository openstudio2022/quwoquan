import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/runtime/di/navigation/intersection_target_navigator.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart';
import 'package:quwoquan_app/runtime/di/my_intersection_inbox_provider.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/object_insight_primitives.dart';

/// 我的主页「我的交集」预览卡（高保版）。
///
/// 只展示真实 fact 交集 item：低饱和语义图标 + 单行主文案。
/// 端侧只读 [IntersectionReason.primaryText]/[IntersectionReason.primarySpans]，
/// 不渲染 secondaryText、样本头像、胶囊解释或 affinity 推荐。
class MyIntersectionInboxCard extends ConsumerStatefulWidget {
  const MyIntersectionInboxCard({super.key, required this.isDark});

  static const Key cardKey = ValueKey<String>('my-intersection-inbox-card');

  final bool isDark;

  @override
  ConsumerState<MyIntersectionInboxCard> createState() =>
      _MyIntersectionInboxCardState();
}

class _MyIntersectionInboxCardState
    extends ConsumerState<MyIntersectionInboxCard> {
  @override
  void initState() {
    super.initState();
    Future<void>.microtask(
      () => ref.read(myIntersectionPreviewProvider.notifier).load(),
    );
  }

  IntersectionTargetNavigator get _navigator => IntersectionTargetNavigator(
    onTrack: (target, attribution) {
      final id = target.objectId.trim();
      if (id.isEmpty) {
        return;
      }
      ref
          .read(contentBehaviorTrackerProvider)
          .trackClick(
            id,
            referralSource: ReferralSource.myIntersections,
            intersectionDimension: attribution.dimension,
            intersectionSourceRef: attribution.sourceRef,
            intersectionClass: attribution.intersectionClass,
            intersectionTagRefs: attribution.tagRefs,
            intersectionEvidenceId: attribution.evidenceId,
          );
    },
  );

  void _openList({String intersectionId = ''}) {
    context.push(
      AppRoutePaths.myIntersections(
        filter: 'fact',
        intersectionId: intersectionId.isEmpty ? null : intersectionId,
      ),
    );
  }

  void _onSpanTap(IntersectionReason reason, IntersectionTextSpan span) {
    final target = span.target;
    if (target == null) {
      return;
    }
    _navigator.open(
      context,
      target,
      sourceRef: span.role == 'count'
          ? profileIntersectionSourceRef(reason)
          : '',
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
  Widget build(BuildContext context) {
    final state = ref.watch(myIntersectionPreviewProvider);
    final visible = state.items
        .where((item) => item.intersectionClass == 'fact')
        .map(displayReadyIntersectionReason)
        .whereType<IntersectionReason>()
        .take(3)
        .toList(growable: false);
    return ProfileInsightSectionCard(
      key: MyIntersectionInboxCard.cardKey,
      title: DiscoveryFeedText.myIntersectionsTitle,
      actionLabel: DiscoveryFeedText.intersectionViewAll,
      onAction: () => _openList(),
      topPadding: true,
      child: state.isLoading && visible.isEmpty
          ? const ProfileIntersectionSkeletonList()
          : visible.isEmpty
          ? const ProfileIntersectionEmptyState(
              text: ProfileText.profileIntersectionEmptyGuidance,
            )
          : Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                for (var index = 0; index < visible.length; index += 1) ...[
                  if (index > 0) const ProfileInsightDivider(),
                  ProfileIntersectionPreviewRow(
                    reason: visible[index],
                    onTap: () => _openList(
                      intersectionId: visible[index].intersectionId,
                    ),
                    onSpanTap: (span) => _onSpanTap(visible[index], span),
                  ),
                ],
              ],
            ),
    );
  }
}
