import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_actionable_reasons.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/runtime/di/navigation/intersection_target_navigator.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart';
import 'package:quwoquan_app/runtime/di/my_intersection_inbox_provider.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/object_insight_primitives.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

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
    Future<void>.microtask(() async {
      await Future.wait(<Future<void>>[
        ref.read(myIntersectionPreviewProvider.notifier).load(),
        ref.read(myIntersectionSummaryProvider.notifier).load(),
      ]);
    });
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

  void _openList({String intersectionId = '', String dimension = ''}) {
    context.push(
      AppRoutePaths.myIntersections(
        dimension: dimension.isEmpty ? null : dimension,
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
    final summaryState = ref.watch(myIntersectionSummaryProvider);
    final visible = state.items
        .where((item) => item.intersectionClass == 'fact')
        .map(displayReadyIntersectionReason)
        .whereType<IntersectionReason>()
        .take(3)
        .toList(growable: false);
    // 「可约 N」入口计数只来自已拉取预览（不伪造全量）；无可行动交集不渲染入口。
    final actionableCount = actionableIntersectionReasons(
      state.items
          .where((item) => item.intersectionClass == 'fact')
          .toList(growable: false),
    ).length;
    return ProfileInsightSectionCard(
      key: MyIntersectionInboxCard.cardKey,
      title: DiscoveryFeedText.myIntersectionsTitle,
      actionLabel: DiscoveryFeedText.intersectionViewAll,
      onAction: () => _openList(),
      topPadding: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (summaryState.summary case final summary?) ...<Widget>[
            _IntersectionInboxSummaryStrip(
              summary: summary,
              actionableCount: actionableCount,
              onActionableTap: () => _openList(),
              onDimensionTap: (dimension) => _openList(dimension: dimension),
            ),
            const ProfileInsightDivider(),
          ],
          if (state.isLoading && visible.isEmpty)
            const ProfileIntersectionSkeletonList()
          else if (visible.isEmpty)
            const ProfileIntersectionEmptyState(
              text: ProfileText.profileIntersectionEmptyGuidance,
            )
          else
            for (var index = 0; index < visible.length; index += 1) ...[
              if (index > 0) const ProfileInsightDivider(),
              ProfileIntersectionPreviewRow(
                reason: visible[index],
                onTap: () =>
                    _openList(intersectionId: visible[index].intersectionId),
                onSpanTap: (span) => _onSpanTap(visible[index], span),
              ),
            ],
        ],
      ),
    );
  }
}

class _IntersectionInboxSummaryStrip extends StatelessWidget {
  const _IntersectionInboxSummaryStrip({
    required this.summary,
    required this.onDimensionTap,
    this.actionableCount = 0,
    this.onActionableTap,
  });

  final IntersectionInboxSummary summary;
  final ValueChanged<String> onDimensionTap;

  /// 已拉取预览内的可行动交集数（REQ-008「可约 N」入口）；0 不渲染。
  final int actionableCount;
  final VoidCallback? onActionableTap;

  @override
  Widget build(BuildContext context) {
    final newDimensions = summary.dimensions
        .where((item) => item.newCount > 0)
        .take(3)
        .toList(growable: false);
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
      child: Row(
        children: <Widget>[
          Text(
            DiscoveryFeedText.intersectionEntrySummary(summary.totalCount),
            key: const ValueKey<String>('my-intersections-total-count'),
            style: TextStyle(
              color: AppColors.iosSecondaryLabel(context),
              fontSize: AppTypography.iosFootnote,
            ),
          ),
          if (actionableCount > 0 && onActionableTap != null) ...<Widget>[
            SizedBox(width: AppSpacing.intraGroupSm),
            CupertinoButton(
              key: const ValueKey<String>('my-intersections-actionable-entry'),
              padding: EdgeInsets.zero,
              minimumSize: Size.zero,
              onPressed: onActionableTap,
              child: Text(
                DiscoveryFeedText.intersectionActionableEntry(actionableCount),
                style: TextStyle(
                  color: AppColors.iosAccent(context),
                  fontSize: AppTypography.iosFootnote,
                  fontWeight: AppTypography.medium,
                ),
              ),
            ),
          ],
          if (newDimensions.isNotEmpty) ...<Widget>[
            SizedBox(width: AppSpacing.intraGroupSm),
            Expanded(
              child: Wrap(
                alignment: WrapAlignment.end,
                spacing: AppSpacing.intraGroupSm,
                runSpacing: AppSpacing.intraGroupXs,
                children: <Widget>[
                  for (final item in newDimensions)
                    CupertinoButton(
                      key: ValueKey<String>(
                        'my-intersections-dimension-${item.dimension}',
                      ),
                      padding: EdgeInsets.zero,
                      minimumSize: Size.zero,
                      onPressed: () => onDimensionTap(item.dimension),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: <Widget>[
                          Container(
                            width: AppSpacing.intraGroupXs,
                            height: AppSpacing.intraGroupXs,
                            decoration: BoxDecoration(
                              color: AppColors.iosDestructive(context),
                              shape: BoxShape.circle,
                            ),
                          ),
                          SizedBox(width: AppSpacing.intraGroupXs),
                          Text(
                            '${item.label} ${item.newCount}'
                            '${DiscoveryFeedText.intersectionNewBadgeSuffix}',
                            style: TextStyle(
                              color: AppColors.iosSecondaryLabel(context),
                              fontSize: AppTypography.iosCaption1,
                            ),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}
