import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show referralSourceForObjectType;
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_tracker_port.dart';
import 'package:quwoquan_app/runtime/di/navigation/intersection_target_navigator.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/object_intersection_card.dart';
import 'package:quwoquan_app/runtime/di/object_intersection_provider.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/object_intersection_query.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/app_list_page_semantics.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';

class ObjectIntersectionListPage extends ConsumerWidget {
  const ObjectIntersectionListPage({
    super.key,
    required this.objectId,
    required this.objectType,
    required this.currentUserId,
    required this.contentBehaviorTracker,
    this.title = '',
  });

  final String objectId;
  final String objectType;
  final String currentUserId;
  final ContentBehaviorTrackerPort contentBehaviorTracker;
  final String title;

  String get _title {
    final trimmed = title.trim();
    return trimmed.isEmpty
        ? ObjectHomepageText.objectIntersectionsTitle
        : trimmed;
  }

  Future<UiRecoveryOutcome> _retry(
    WidgetRef ref,
    ObjectIntersectionQuery query,
    UiErrorAction action,
  ) async {
    if (action.type != UiErrorActionType.retry &&
        action.type != UiErrorActionType.resubmit) {
      return UiRecoveryOutcome.cancelled;
    }
    try {
      final _ = await ref.refresh(objectSharedReasonsProvider(query).future);
      return UiRecoveryOutcome.recovered;
    } catch (_) {
      return UiRecoveryOutcome.stillBlocked;
    }
  }

  void _openObject(BuildContext context, IntersectionReason reason) {
    final target = IntersectionTargetNavigator.targetForReason(reason);
    IntersectionTargetNavigator(
      onTrack: (hit, attribution) {
        contentBehaviorTracker.trackClick(
          hit.objectId,
          referralSource: referralSourceForObjectType(objectType),
          intersectionId: attribution.intersectionId,
          intersectionDimension: attribution.dimension,
          intersectionClass: attribution.intersectionClass,
          intersectionTagRefs: attribution.tagRefs,
        );
      },
    ).open(
      context,
      target,
      attribution: IntersectionNavAttribution(
        intersectionId: reason.intersectionId,
        dimension: reason.dimension,
        intersectionClass: reason.intersectionClass,
        sourceRef: reason.source,
        tagRefs: reason.tagRefs,
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final query = ObjectIntersectionQuery(
      objectAId: currentUserId,
      objectAType: 'user',
      objectBId: objectId,
      objectBType: objectType,
      limit: 50,
    );
    final asyncReasons = query.isResolvable
        ? ref.watch(objectSharedReasonsProvider(query))
        : const AsyncValue<List<IntersectionReason>>.data(
            <IntersectionReason>[],
          );
    return AppListPageScaffold(
      isDark: isDark,
      kind: AppListPageKind.singleList,
      title: _title,
      onBack: () => context.pop(),
      trailing: query.isResolvable
          ? CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: () {
                ref.invalidate(objectSharedReasonsProvider(query));
              },
              child: Text(SearchText.refresh),
            )
          : null,
      body: asyncReasons.when(
        loading: () => AppRequestFeedback.section(),
        error: (error, _) {
          final resolved = ensureRetryUiErrorSemantic(
            runtimeErrorSemantic(
              context,
              error: error,
              category: UiErrorCategory.pageLoad,
              scope: UiErrorScope.page,
            ),
          );
          return AppPageErrorState(
            semantic: resolved,
            onRecovery: (action) => _retry(ref, query, action),
          );
        },
        data: (reasons) {
          final card = ObjectIntersectionCard.fromReasons(
            title: _title,
            reasons: reasons,
            isDark: isDark,
            inlineExpandCount: 50,
            onReasonTap: (reason) => _openObject(context, reason),
            onInlineExpand: (firstReason) {
              // 全量列表页超过 50 条时的就地展开归因（intersection_expand，B6）。
              contentBehaviorTracker.trackIntersectionExpand(
                contentId: objectId,
                intersectionId: firstReason.intersectionId,
                intersectionDimension: firstReason.dimension,
                intersectionClass: firstReason.intersectionClass,
                intersectionSourceRef: firstReason.source,
                referralSource: referralSourceForObjectType(objectType),
              );
            },
          );
          if (card == null) {
            return Center(
              child: Padding(
                padding: EdgeInsets.all(AppSpacing.lg),
                child: AppListSurface(
                  padding: EdgeInsets.all(AppSpacing.containerMd),
                  child: Text(
                    ObjectHomepageText.objectIntersectionsEmpty,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  ),
                ),
              ),
            );
          }
          return ListView(
            padding: EdgeInsets.fromLTRB(
              SettingsSemanticConstants.insetFormListHorizontalPadding,
              AppSpacing.containerSm,
              SettingsSemanticConstants.insetFormListHorizontalPadding,
              AppSpacing.containerLg,
            ),
            children: <Widget>[card],
          );
        },
      ),
    );
  }
}
