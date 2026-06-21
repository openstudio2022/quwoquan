import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/user/providers/author_impact_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/author_impact_evidence.dart';
import 'package:quwoquan_app/ui/user/widgets/intersection_statement_card.dart';
import 'package:quwoquan_app/ui/user/widgets/my_intersection_inbox_timeline.dart';

/// 「我的影响力」时间线：与交集 tab 同款 5 年时间桶脚手架（[IntersectionBucketTimeline]），
/// 逐条复用共享 [IntersectionStatementRow]（四槽 + 行动 pill + 生命周期弱标 + 传播视图）。
/// 名字/对象片段进对应主页，数字片段/整行进影响明细 sheet（[AuthorImpactEvidence]）。
///
/// 从 `my_intersection_inbox_page.dart` 抽出（R03 文件体量收敛）：影响力 tab 的时间线渲染、
/// impact item 装配与 evidence 接线集中在此，页面只负责 tab 切换与状态注入。
class ImpactTimeline extends ConsumerWidget {
  const ImpactTimeline({super.key, required this.state});

  final AsyncValue<AuthorImpactSummary> state;

  IntersectionTargetNavigator _navigator(WidgetRef ref) =>
      IntersectionTargetNavigator(
        onTrack: (target, attribution) {
          final id = target.objectId.trim();
          if (id.isEmpty) return;
          ref
              .read(contentBehaviorTrackerProvider)
              .trackClick(
                id,
                referralSource: ReferralSource.myIntersections,
                intersectionDimension: attribution.dimension,
                intersectionSourceRef: attribution.sourceRef,
                intersectionTagRefs: attribution.tagRefs,
                intersectionEvidenceId: attribution.evidenceId,
              );
        },
      );

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return state.when(
      loading: () => const Center(child: CupertinoActivityIndicator()),
      error: (error, _) {
        return AppPageErrorState(
          semantic: resolveIntersectionDetailErrorSemantic(
            context,
            error: error,
            title: '${UITextConstants.profileImpactTitleMine}暂不可用',
          ),
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              ref.invalidate(
                authorImpactProvider(ref.read(currentUserIdProvider)),
              );
            }
          },
        );
      },
      data: (summary) {
        final items = summary.items
            .where((item) => item.primaryText.trim().isNotEmpty)
            .toList(growable: false);
        if (items.isEmpty) {
          return Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpacing.xl),
            child: Center(
              child: Text(
                UITextConstants.profileImpactEmptyMine,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
            ),
          );
        }
        final navigator = _navigator(ref);
        return IntersectionBucketTimeline(
          rows: <IntersectionTimelineEntry>[
            for (final item in items)
              IntersectionTimelineEntry(
                bucket: resolveIntersectionTimeBucket(
                  item.timeBucket,
                  item.freshAt,
                ),
                child: IntersectionTimelineCard(
                  child: IntersectionStatementRow(
                    item: _impactItem(
                      context,
                      ref,
                      navigator,
                      item,
                      summary.authorId,
                    ),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }

  IntersectionStatementItem _impactItem(
    BuildContext context,
    WidgetRef ref,
    IntersectionTargetNavigator navigator,
    AuthorImpactItem item,
    String subAccountId,
  ) {
    final AuthorImpactEvidenceFetcher evidenceFetcher =
        ({String cursor = ''}) => ref
            .read(userProfileRepositoryProvider)
            .listAuthorImpactEvidence(
              subAccountId: subAccountId,
              impactId: item.impactId,
              evidenceSnapshotId: item.evidenceSnapshotId,
              cursor: cursor,
            );
    final hasAction = item.actionHints.any(
      (hint) => hint.label.trim().isNotEmpty,
    );
    final hasPropagation =
        item.propagationPath != null &&
        item.propagationPath!.summaryText.trim().isNotEmpty;
    return IntersectionStatementItem(
      primaryText: item.primaryText.trim(),
      subtitleText: '',
      spans: item.primarySpans,
      iconKey: item.iconKey,
      sourceRef: item.source,
      dimension: item.intersectionDimension,
      actionHints: item.actionHints,
      lifecycleState: item.lifecycleState,
      strengthDelta: item.strengthDelta.round(),
      propagationPath: item.propagationPath,
      showAuxiliaryLine: hasAction || hasPropagation,
      onSpanTap: (span) => AuthorImpactEvidence.onSpanTap(
        context,
        navigator: navigator,
        item: item,
        span: span,
        isMine: true,
        fetchEvidence: evidenceFetcher,
      ),
      onActionHintTap: (hint) => AuthorImpactEvidence.onActionHintTap(
        context,
        navigator: navigator,
        item: item,
        hint: hint,
        isMine: true,
        fetchEvidence: evidenceFetcher,
      ),
      onPropagationTap: () => AuthorImpactEvidence.showEvidence(
        context,
        navigator: navigator,
        item: item,
        isMine: true,
        fetchEvidence: evidenceFetcher,
      ),
      onTap: () => AuthorImpactEvidence.showEvidence(
        context,
        navigator: navigator,
        item: item,
        isMine: true,
        fetchEvidence: evidenceFetcher,
      ),
    );
  }
}
