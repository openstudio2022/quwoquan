import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/components/object_page/intersection_entity.dart';
import 'package:quwoquan_app/components/object_page/intersection_object_kind.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/user/providers/my_intersection_inbox_provider.dart';

/// 「我的交集」分维度列表页（自上次查看新增在前）。
///
/// 打开即推进已读水位并清零红点（由 [MyIntersectionListNotifier.loadAndMarkVisited]）。
/// 路由：/profile/intersections?dimension=identity|location|content|relationship|interest
class MyIntersectionInboxPage extends ConsumerStatefulWidget {
  const MyIntersectionInboxPage({super.key, this.dimension = ''});

  final String dimension;

  @override
  ConsumerState<MyIntersectionInboxPage> createState() =>
      _MyIntersectionInboxPageState();
}

class _MyIntersectionInboxPageState
    extends ConsumerState<MyIntersectionInboxPage> {
  UiErrorSemantic _resolvePageErrorSemantic(Object error) {
    final resolved = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
    return UiErrorSemantic(
      category: resolved.category,
      scope: resolved.scope,
      title: '我的交集暂不可用',
      message: resolved.message,
      secondaryMessage: resolved.secondaryMessage,
      primaryAction:
          resolved.primaryAction ??
          const UiErrorAction(
            type: UiErrorActionType.retry,
            label: UITextConstants.tryAgain,
          ),
      secondaryAction: resolved.secondaryAction,
      dismissible: resolved.dismissible,
      sourceCode: resolved.sourceCode,
      failureKind: resolved.failureKind,
      recoveryAction: resolved.recoveryAction,
      presentation: resolved.presentation,
      tone: resolved.tone,
    );
  }

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(
      () => ref
          .read(myIntersectionListProvider.notifier)
          .loadAndMarkVisited(dimension: widget.dimension),
    );
  }

  String get _title {
    if (widget.dimension.isEmpty) {
      return UITextConstants.myIntersectionsTitle;
    }
    return UITextConstants.intersectionDimensionShortLabel(widget.dimension);
  }

  void _openObject(IntersectionReason reason) {
    final id = reason.actionTargetId.trim();
    if (id.isEmpty) return;
    final kind = UnifiedObjectKind.fromRelationKind(reason.relationKind);
    switch (kind) {
      case UnifiedObjectKind.person:
        context.push(AppRoutePaths.userProfile(username: id));
      case UnifiedObjectKind.circle:
        context.push(AppRoutePaths.circleDetail(id: id));
      case UnifiedObjectKind.place:
      case UnifiedObjectKind.org:
        context.push(AppRoutePaths.homepageDetail(id: id));
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColors.iosSystemBackground(context);
    final state = ref.watch(myIntersectionListProvider);
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
      child: _buildBody(context, state, isDark),
    );
  }

  Widget _buildBody(
    BuildContext context,
    MyIntersectionListState state,
    bool isDark,
  ) {
    if (state.isLoading && state.items.isEmpty) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (state.rawError != null) {
      return AppPageErrorState(
        semantic: _resolvePageErrorSemantic(state.rawError!),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await ref
                .read(myIntersectionListProvider.notifier)
                .loadAndMarkVisited(dimension: widget.dimension);
          }
        },
      );
    }
    if (state.items.isEmpty) {
      return Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.lg),
          child: Text(
            UITextConstants.myIntersectionsEmpty,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
        ),
      );
    }
    if (widget.dimension.isNotEmpty) {
      return ListView.separated(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        itemCount: state.items.length,
        separatorBuilder: (_, _) => _divider(context),
        itemBuilder: (_, index) => IntersectionEntity(
          reason: state.items[index],
          isDark: isDark,
          density: IntersectionEntityDensity.inboxList,
          onTap: () => _openObject(state.items[index]),
        ),
      );
    }
    return _buildGrouped(context, state.items, isDark);
  }

  Widget _buildGrouped(
    BuildContext context,
    List<IntersectionReason> items,
    bool isDark,
  ) {
    final byDimension = <String, List<IntersectionReason>>{};
    for (final reason in items) {
      byDimension.putIfAbsent(reason.dimension, () => <IntersectionReason>[]);
      byDimension[reason.dimension]!.add(reason);
    }
    final sections = byDimension.entries.toList(growable: false);
    return ListView.builder(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      itemCount: sections.length,
      itemBuilder: (_, sectionIndex) {
        final entry = sections[sectionIndex];
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Padding(
              padding: EdgeInsets.only(
                top: AppSpacing.sm,
                bottom: AppSpacing.intraGroupSm,
              ),
              child: Text(
                UITextConstants.intersectionDimensionShortLabel(entry.key),
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
            ),
            for (final reason in entry.value) ...<Widget>[
              IntersectionEntity(
                reason: reason,
                isDark: isDark,
                density: IntersectionEntityDensity.inboxList,
                onTap: () => _openObject(reason),
              ),
              _divider(context),
            ],
          ],
        );
      },
    );
  }

  Widget _divider(BuildContext context) => Container(
    height: AppSpacing.hairline,
    color: AppColors.iosSeparator(context).withValues(alpha: 0.12),
  );
}
