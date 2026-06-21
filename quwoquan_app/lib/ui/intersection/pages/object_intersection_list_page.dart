import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show referralSourceForObjectType;
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_card.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

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
    return trimmed.isEmpty ? UITextConstants.objectIntersectionsTitle : trimmed;
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
    final bg = AppColors.iosSystemBackground(context);
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
    return AppScaffold(
      backgroundColor: bg,
      navigationBar: AppNavigationBar(
        backgroundColor: bg,
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => context.pop(),
        ),
        middle: Text(
          _title,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      child: asyncReasons.when(
        loading: () => const Center(child: CupertinoActivityIndicator()),
        error: (error, _) {
          final resolved = runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
          );
          return AppPageErrorState(
            semantic: UiErrorSemantic(
              category: resolved.category,
              scope: resolved.scope,
              title: UITextConstants.objectIntersectionsUnavailableTitle,
              message: resolved.message,
              secondaryMessage: resolved.secondaryMessage,
              primaryAction: resolved.primaryAction,
              secondaryAction: resolved.secondaryAction,
              dismissible: resolved.dismissible,
              sourceCode: resolved.sourceCode,
              failureKind: resolved.failureKind,
              recoveryAction: resolved.recoveryAction,
              presentation: resolved.presentation,
              tone: resolved.tone,
            ),
          );
        },
        data: (reasons) {
          final card = ObjectIntersectionCard.fromReasons(
            title: _title,
            reasons: reasons,
            isDark: isDark,
            inlineExpandCount: 50,
            onReasonTap: (reason) => _openObject(context, ref, reason),
          );
          if (card == null) {
            return Center(
              child: Padding(
                padding: EdgeInsets.all(AppSpacing.lg),
                child: Text(
                  UITextConstants.objectIntersectionsEmpty,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    color: AppColors.iosSecondaryLabel(context),
                  ),
                ),
              ),
            );
          }
          return ListView(
            padding: EdgeInsets.all(AppSpacing.containerMd),
            children: <Widget>[card],
          );
        },
      ),
    );
  }
}
