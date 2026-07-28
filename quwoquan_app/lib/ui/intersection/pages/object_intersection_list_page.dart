import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show referralSourceForObjectType;
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_card.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';

class ObjectIntersectionListPage extends ConsumerWidget {
  const ObjectIntersectionListPage({
    super.key,
    required this.objectId,
    required this.objectType,
    this.title = '',
  });

  final String objectId;
  final String objectType;
  final String title;

  String get _title {
    final trimmed = title.trim();
    return trimmed.isEmpty
        ? ObjectHomepageText.objectIntersectionsTitle
        : trimmed;
  }

  void _openObject(
    BuildContext context,
    WidgetRef ref,
    IntersectionReason reason,
  ) {
    final target = IntersectionTargetNavigator.targetForReason(reason);
    IntersectionTargetNavigator(
      onTrack: (hit, attribution) {
        ref
            .read(contentBehaviorTrackerProvider)
            .trackClick(
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
      objectAId: ref.watch(currentUserIdProvider),
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
      body: asyncReasons.when(
        loading: () => AppRequestFeedback.section(),
        error: (error, _) {
          final resolved = runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
          );
          return AppPageErrorState(semantic: resolved);
        },
        data: (reasons) {
          final card = ObjectIntersectionCard.fromReasons(
            title: _title,
            reasons: reasons,
            isDark: isDark,
            inlineExpandCount: 50,
            onReasonTap: (reason) => _openObject(context, ref, reason),
            onInlineExpand: (firstReason) {
              // 全量列表页超过 50 条时的就地展开归因（intersection_expand，B6）。
              ref
                  .read(contentBehaviorTrackerProvider)
                  .trackIntersectionExpand(
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
