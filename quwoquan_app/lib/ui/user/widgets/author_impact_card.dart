import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/user/widgets/author_impact_evidence.dart';
import 'package:quwoquan_app/components/object_page/intersection_statement_card.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';

/// 打动摘要模块（他人主页 / 我的主页双视角，可解释）。
///
/// 统一交互子契约落地（Phase 0 §20.7）：逐条只读 [AuthorImpactSummary]：
/// - 结论句走 [AuthorImpactItem.primarySpans] + 统一渲染器（[IntersectionStatementRow]），
///   端不本地拼装文案（G2），spans 缺省回落 [AuthorImpactItem.primaryText]；
/// - 样本视觉走 [AuthorImpactItem.sampleVisuals] + [IntersectionVisualCluster]；
/// - 名字 / 对象片段经 [IntersectionTargetNavigator] 进对应主页；
/// - 数字片段 / 整行进「打动明细」iOS 底部 sheet，展示来源摘要 + 云侧样本视觉；
///   完整名单（[AuthorImpactItem.evidenceSnapshotId] / 分页）未就绪时只展示样本、不编造全量。
/// other 模式无数据不占位，mine 模式空态展示鼓励发布文案。
class AuthorImpactCard extends ConsumerWidget {
  const AuthorImpactCard({
    super.key,
    required this.summary,
    required this.isDark,
    required this.isMine,
    this.maxItems = 3,
  });

  static const Key cardKey = ValueKey<String>('author-impact-card');
  static const Key emptyKey = ValueKey<String>('author-impact-empty');

  final AuthorImpactSummary summary;
  final bool isDark;

  /// true = 我的主页；false = 他人主页。
  final bool isMine;
  final int maxItems;

  bool get _isEmpty =>
      summary.total <= 0 ||
      summary.items.every((item) => item.primaryText.trim().isEmpty);

  /// 打动明细分页拉取闭包：经 Provider 注入仓库，按 (subAccountId, impactId) 取真实分页。
  /// 延迟到 sheet 打开时才 `ref.read`，构建期不触达 Provider。
  AuthorImpactEvidenceFetcher _evidenceFetcher(
    WidgetRef ref,
    AuthorImpactItem item,
  ) {
    return ({String cursor = ''}) => ref
        .read(userProfileRepositoryProvider)
        .listAuthorImpactEvidence(
          subAccountId: summary.authorId,
          impactId: item.impactId,
          evidenceSnapshotId: item.evidenceSnapshotId,
          cursor: cursor,
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
                // 作者打动卡展示在用户主页（自/他人）→ 来源为作者主页面，非推荐流。
                referralSource: ReferralSource.authorProfile,
                intersectionDimension: attribution.dimension,
                intersectionSourceRef: attribution.sourceRef,
                intersectionTagRefs: attribution.tagRefs,
                intersectionEvidenceId: attribution.evidenceId,
              );
        },
      );

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final visible = summary.items
        .where((item) => item.primaryText.trim().isNotEmpty)
        .take(maxItems)
        .toList(growable: false);
    final navigator = _navigator(ref);

    return IntersectionStatementCard(
      key: AuthorImpactCard.cardKey,
      topDivider: true,
      title: isMine
          ? UITextConstants.profileImpactTitleMine
          : UITextConstants.profileImpactTitleOther,
      footerActionLabel: isMine ? DiscoveryFeedText.intersectionViewAll : null,
      onFooterAction: isMine
          ? () => context.push(AppRoutePaths.myIntersections(filter: 'impact'))
          : null,
      items: _isEmpty
          ? const <IntersectionStatementItem>[]
          : <IntersectionStatementItem>[
              for (final item in visible)
                IntersectionStatementItem(
                  primaryText: item.primaryText.trim(),
                  subtitleText: '',
                  highlight: IntersectionStatementHighlight.gray,
                  spans: item.primarySpans,
                  visuals: const <IntersectionVisual>[],
                  // 四槽：① 类型图标（iconKey 回退 helpType/dimension）+ ④ 传播视图。
                  iconKey: item.iconKey,
                  sourceRef: item.source,
                  dimension: item.intersectionDimension,
                  actionHints: item.actionHints,
                  showAuxiliaryLine: false,
                  onActionHintTap: (hint) =>
                      AuthorImpactEvidence.onActionHintTap(
                        context,
                        navigator: navigator,
                        item: item,
                        hint: hint,
                        isMine: isMine,
                        fetchEvidence: _evidenceFetcher(ref, item),
                      ),
                  onSpanTap: (span) => AuthorImpactEvidence.onSpanTap(
                    context,
                    navigator: navigator,
                    item: item,
                    span: span,
                    isMine: isMine,
                    fetchEvidence: _evidenceFetcher(ref, item),
                  ),
                  onVisualTap: (visual) => navigator.open(
                    context,
                    visual.target,
                    attribution: AuthorImpactEvidence.attributionFor(item),
                  ),
                  onPropagationTap: () => AuthorImpactEvidence.showEvidence(
                    context,
                    navigator: navigator,
                    item: item,
                    isMine: isMine,
                    fetchEvidence: _evidenceFetcher(ref, item),
                  ),
                  onTap: () => AuthorImpactEvidence.showEvidence(
                    context,
                    navigator: navigator,
                    item: item,
                    isMine: isMine,
                    fetchEvidence: _evidenceFetcher(ref, item),
                  ),
                ),
            ],
      emptyChild: Text(
        key: AuthorImpactCard.emptyKey,
        isMine
            ? UITextConstants.profileImpactEmptyMine
            : UITextConstants.profileImpactEmptyOther,
        style: TextStyle(
          fontSize: AppTypography.iosCaption1,
          height: AppSpacing.textLineHeightBody,
          color: fgSecondary,
        ),
      ),
    );
  }
}
