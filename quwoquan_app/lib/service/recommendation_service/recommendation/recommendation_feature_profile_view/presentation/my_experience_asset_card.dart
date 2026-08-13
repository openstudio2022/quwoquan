import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart';
import 'package:quwoquan_app/runtime/di/my_intersection_inbox_provider.dart';
import 'package:quwoquan_app/runtime/di/navigation/intersection_target_navigator.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_actionable_reasons.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_statement_synthesizer.dart'
    show resolvedIntersectionReasonKind;
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/my_intersection_inbox_timeline.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/object_insight_primitives.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 我的主页「共同经历」资产行（REQ-008，仅 mine 模式挂载）。
///
/// 只读经历交集事实（`coExperiencedGathering`，云侧物化器唯一生产者），
/// 主句直出云侧 `primaryText`/`primarySpans`；行尾「再约一次」pill 消费云侧
/// actionHints（飞轮复利环）。无经历交集时整个区块不渲染（诚实空态=不渲染）；
/// 读取失败展示可恢复错误行 + 重试，不伪造「暂无经历」。
class MyExperienceAssetCard extends ConsumerWidget {
  const MyExperienceAssetCard({super.key, required this.isDark});

  static const Key cardKey = ValueKey<String>('my-experience-asset-card');
  static const Key retryKey = ValueKey<String>('my-experience-asset-retry');

  final bool isDark;

  static const int _maxPreviewRows = 3;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(myExperienceIntersectionsProvider);
    return state.when(
      // 加载中不渲染（资产行是次级模块，不在首屏放骨架占位、不阻塞滚动）。
      loading: () => const SizedBox.shrink(),
      error: (_, _) => _buildErrorRow(context, ref),
      data: (items) => _buildCard(context, ref, items),
    );
  }

  Widget _buildErrorRow(BuildContext context, WidgetRef ref) {
    return ProfileInsightSectionCard(
      key: MyExperienceAssetCard.cardKey,
      title: DiscoveryFeedText.myExperienceTitle,
      topPadding: true,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupSm,
        ),
        child: Row(
          children: <Widget>[
            Expanded(
              child: Text(
                DiscoveryFeedText.myExperienceLoadFailed,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
            ),
            CupertinoButton(
              key: MyExperienceAssetCard.retryKey,
              padding: EdgeInsets.zero,
              minimumSize: Size.zero,
              onPressed: () =>
                  ref.invalidate(myExperienceIntersectionsProvider),
              child: Text(
                SearchText.reload,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosAccent(context),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 资产行可渲染判定：数据源已按 `sourceRef=coExperiencedGathering` 单 kind
  /// 收窄（无混排、无宿主上下文），不套用为多 kind 混排设计的展示合同闸
  /// （`displayReadyIntersectionReason` 会因缺宿主对象淘汰 host_implicit 形态）；
  /// 只守事实类别与 G2 不变量（join(spans.text)==primaryText），主句直出不改写。
  static bool _renderableExperience(IntersectionReason reason) {
    if (reason.intersectionClass != 'fact') {
      return false;
    }
    final primary = reason.primaryText.trim();
    if (primary.isEmpty) {
      return false;
    }
    final spans = reason.primarySpans;
    if (spans.isNotEmpty &&
        spans.map((span) => span.text).join() != primary) {
      return false;
    }
    return true;
  }

  Widget _buildCard(
    BuildContext context,
    WidgetRef ref,
    List<IntersectionReason> items,
  ) {
    final visible = items
        .where(_renderableExperience)
        .take(_maxPreviewRows)
        .toList(growable: false);
    if (visible.isEmpty) {
      // 无经历交集：整个区块不渲染（不放鼓励文案硬广，不占首屏空间）。
      return const SizedBox.shrink();
    }
    return ProfileInsightSectionCard(
      key: MyExperienceAssetCard.cardKey,
      title: DiscoveryFeedText.myExperienceTitle,
      actionLabel: DiscoveryFeedText.intersectionViewAll,
      onAction: () => _openFullList(context),
      topPadding: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          for (var index = 0; index < visible.length; index += 1) ...<Widget>[
            if (index > 0) const ProfileInsightDivider(),
            _buildExperienceRow(context, ref, visible[index]),
          ],
        ],
      ),
    );
  }

  Widget _buildExperienceRow(
    BuildContext context,
    WidgetRef ref,
    IntersectionReason reason,
  ) {
    final primaryHint = primaryIntersectionActionHint(reason);
    return IntersectionCompactTimelineRow(
      primaryText: reason.primaryText,
      spans: reason.primarySpans,
      iconKey: reason.iconKey,
      sourceRef: resolvedIntersectionReasonKind(reason),
      dimension: reason.dimension,
      tone: reason.tone,
      typeIconUrl: reason.typeVisual?.imageUrl ?? '',
      lifecycleState: reason.lifecycleState,
      onTap: () => _openGatheringDetail(context, ref, reason),
      onSpanTap: (span) => _onSpanTap(context, ref, reason, span),
      trailing: primaryHint == null
          ? null
          : IntersectionActionablePill(
              label: primaryHint.label,
              onPressed: () =>
                  _openPrimaryHint(context, ref, reason, primaryHint),
            ),
    );
  }

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
                referralSource: ReferralSource.myIntersections,
                intersectionId: attribution.intersectionId,
                intersectionDimension: attribution.dimension,
                intersectionSourceRef: attribution.sourceRef,
                intersectionClass: attribution.intersectionClass,
                intersectionTagRefs: attribution.tagRefs,
                intersectionEvidenceId: attribution.evidenceId,
              );
        },
      );

  IntersectionNavAttribution _attributionFor(IntersectionReason reason) {
    return IntersectionNavAttribution(
      intersectionId: reason.intersectionId,
      dimension: reason.dimension,
      intersectionClass: reason.intersectionClass,
      sourceRef: resolvedIntersectionReasonKind(reason),
      tagRefs: reason.tagRefs,
      evidenceId: reason.pointSummarySnapshotId,
    );
  }

  /// 整行点击 = 回看行动详情（`actionTargetId` 即最近一次共同行动）。
  void _openGatheringDetail(
    BuildContext context,
    WidgetRef ref,
    IntersectionReason reason,
  ) {
    final target = IntersectionTarget(
      objectType: 'gathering',
      objectId: reason.actionTargetId,
      objectKind: 'gathering',
      routeId: IntersectionTargetNavigator.routeIdForObjectKindWire(
        'gathering',
      ),
    );
    final opened = _navigator(ref).open(
      context,
      target,
      attribution: _attributionFor(reason),
    );
    if (!opened) {
      _openFullList(context);
    }
  }

  /// 行尾主行动（如「再约一次」）：经统一 actionHint 分发。
  void _openPrimaryHint(
    BuildContext context,
    WidgetRef ref,
    IntersectionReason reason,
    IntersectionActionHint hint,
  ) {
    final result = _navigator(ref).openActionHint(
      context,
      hint,
      sourceRef: resolvedIntersectionReasonKind(reason),
      attribution: _attributionFor(reason),
      evidenceReason: reason,
    );
    if (!result.didOpen) {
      _openGatheringDetail(context, ref, reason);
    }
  }

  void _onSpanTap(
    BuildContext context,
    WidgetRef ref,
    IntersectionReason reason,
    IntersectionTextSpan span,
  ) {
    final target = span.target;
    if (target == null) {
      _openGatheringDetail(context, ref, reason);
      return;
    }
    _navigator(ref).open(context, target, attribution: _attributionFor(reason));
  }

  void _openFullList(BuildContext context) {
    context.push(
      AppRoutePaths.myIntersections(
        filter: 'fact',
        sourceRef: 'coExperiencedGathering',
      ),
    );
  }
}
