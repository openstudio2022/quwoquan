import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart';
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/runtime/di/navigation/intersection_target_navigator.dart';
import 'package:quwoquan_app/runtime/di/author_impact_provider.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/author_impact_evidence.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/my_intersection_inbox_timeline.dart';

/// 「打动」时间线：与交集 tab 同款最近时间桶脚手架（[IntersectionBucketTimeline]），
/// 逐条复用详情页紧凑行，只展示云侧下发的 primaryText。
/// 名字/对象片段进对应主页，数字片段/整行进影响明细 sheet（[AuthorImpactEvidence]）。
///
/// 从 `my_intersection_inbox_page.dart` 抽出（R03 文件体量收敛）：打动 tab 的时间线渲染、
/// impact item 装配与 evidence 接线集中在此，页面只负责 tab 切换与状态注入。
class ImpactTimeline extends ConsumerWidget {
  const ImpactTimeline({super.key, required this.state, this.filter = 'all'});

  final AsyncValue<AuthorImpactSummary> state;
  final String filter;

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
      loading: () => AppRequestFeedback.section(),
      error: (error, _) {
        return AppPageErrorState(
          semantic: resolveIntersectionDetailErrorSemantic(
            context,
            error: error,
            title: ContentText.profileImpactUnavailableTitle,
          ),
          onRecovery: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              ref.invalidate(
                authorImpactProvider((
                  personaId: ref.read(currentUserIdProvider),
                  surface: AppUiSurfaces.myIntersections,
                )),
              );
              return UiRecoveryOutcome.superseded;
            }
            return UiRecoveryOutcome.cancelled;
          },
        );
      },
      data: (summary) {
        final items = summary.items
            .where(
              (item) =>
                  item.primaryText.trim().isNotEmpty &&
                  _matchesImpactFilter(item, filter),
            )
            .toList(growable: false);
        if (items.isEmpty) {
          return Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpacing.xl),
            child: Center(
              child: Text(
                ContentText.profileImpactEmptyMine,
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
        return Column(
          children: <Widget>[
            IntersectionBucketTimeline(
              rows: <IntersectionTimelineEntry>[
                for (final item in items)
                  IntersectionTimelineEntry(
                    bucket: resolveIntersectionTimeBucket(
                      item.timeBucket,
                      item.freshAt,
                    ),
                    child: IntersectionCompactTimelineRow(
                      primaryText: item.primaryText.trim(),
                      spans: item.primarySpans,
                      iconKey: item.iconKey,
                      sourceRef: item.source,
                      dimension: item.intersectionDimension,
                      onTap: () => _openImpactEvidence(
                        context,
                        ref,
                        navigator,
                        item,
                        summary.authorId,
                      ),
                      onSpanTap: (span) => _onImpactSpanTap(
                        context,
                        ref,
                        navigator,
                        item,
                        summary.authorId,
                        span,
                      ),
                    ),
                  ),
              ],
            ),
            const IntersectionTimelineRecentLimitNote(),
          ],
        );
      },
    );
  }

  bool _matchesImpactFilter(AuthorImpactItem item, String filter) {
    final dimension = item.intersectionDimension.toLowerCase();
    final countObjectKind = item.countObjectKind.toLowerCase();
    final source = item.source.toLowerCase();
    final action = item.action.toLowerCase();
    final helpType = item.helpType.toLowerCase();
    switch (filter.trim()) {
      case 'records':
        return dimension == 'content' ||
            countObjectKind == 'content' ||
            countObjectKind == 'post' ||
            source.contains('content') ||
            source.contains('record');
      case 'discussion':
        return action.contains('comment') ||
            action.contains('reply') ||
            helpType.contains('discussion') ||
            source.contains('discussion');
      case 'homepage':
        return countObjectKind == 'homepage' ||
            countObjectKind == 'profile' ||
            source.contains('homepage') ||
            source.contains('profile');
      default:
        return true;
    }
  }

  AuthorImpactEvidenceFetcher _evidenceFetcher(
    WidgetRef ref,
    AuthorImpactItem item,
    String personaId,
  ) {
    return ({String cursor = ''}) => ref
        .read(authorImpactQueryProvider(AppUiSurfaces.myIntersections))
        .listAuthorImpactEvidence(
          personaId: personaId,
          impactId: item.impactId,
          evidenceSnapshotId: item.evidenceSnapshotId,
          cursor: cursor,
        );
  }

  void _openImpactEvidence(
    BuildContext context,
    WidgetRef ref,
    IntersectionTargetNavigator navigator,
    AuthorImpactItem item,
    String personaId,
  ) {
    AuthorImpactEvidence.showEvidence(
      context,
      navigator: navigator,
      item: item,
      isMine: true,
      fetchEvidence: _evidenceFetcher(ref, item, personaId),
    );
  }

  void _onImpactSpanTap(
    BuildContext context,
    WidgetRef ref,
    IntersectionTargetNavigator navigator,
    AuthorImpactItem item,
    String personaId,
    IntersectionTextSpan span,
  ) {
    AuthorImpactEvidence.onSpanTap(
      context,
      navigator: navigator,
      item: item,
      span: span,
      isMine: true,
      fetchEvidence: _evidenceFetcher(ref, item, personaId),
    );
  }
}
