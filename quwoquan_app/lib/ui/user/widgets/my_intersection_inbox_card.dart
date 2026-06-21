import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/components/object_page/intersection_icon_resolver.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/user/providers/my_intersection_inbox_provider.dart';

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
    final sourceRef = span.role == 'count' ? _sourceRefFor(reason) : '';
    _navigator.open(
      context,
      target,
      sourceRef: sourceRef,
      attribution: IntersectionNavAttribution(
        intersectionId: reason.intersectionId,
        dimension: reason.dimension,
        intersectionClass: reason.intersectionClass,
        sourceRef: _sourceRefFor(reason),
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
        .take(3)
        .toList(growable: false);
    return _ProfileInsightSectionCard(
      key: MyIntersectionInboxCard.cardKey,
      title: DiscoveryFeedText.myIntersectionsTitle,
      actionLabel: DiscoveryFeedText.intersectionViewAll,
      onAction: () => _openList(),
      topPadding: true,
      child: state.isLoading && visible.isEmpty
          ? const _MyIntersectionSkeletonList()
          : visible.isEmpty
          ? _MyIntersectionEmptyState()
          : Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                for (var index = 0; index < visible.length; index += 1) ...[
                  if (index > 0) _InsightDivider(),
                  _MyIntersectionPreviewRow(
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

String _sourceRefFor(IntersectionReason reason) {
  final source = reason.source.trim();
  if (source.isNotEmpty) {
    return source;
  }
  if (reason.intersectionPoints.isEmpty) {
    return '';
  }
  return reason.intersectionPoints.first.sourceRef.trim();
}

class _ProfileInsightSectionCard extends StatelessWidget {
  const _ProfileInsightSectionCard({
    super.key,
    required this.title,
    required this.actionLabel,
    required this.child,
    this.onAction,
    this.topPadding = false,
  });

  final String title;
  final String actionLabel;
  final Widget child;
  final VoidCallback? onAction;
  final bool topPadding;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final separator = AppColors.iosSeparator(context);
    final border = separator.withValues(alpha: isDark ? 0.14 : 0.07);
    final shadow = AppColors.black.withValues(alpha: isDark ? 0.10 : 0.018);
    return Padding(
      padding: EdgeInsets.only(top: topPadding ? AppSpacing.interGroupSm : 0),
      child: Container(
        width: double.infinity,
        decoration: BoxDecoration(
          color: AppColors.iosProfileSurface(context),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(color: border, width: AppSpacing.hairline),
          boxShadow: <BoxShadow>[
            BoxShadow(
              color: shadow,
              blurRadius: AppSpacing.fourteen,
              offset: const Offset(0, 5),
            ),
          ],
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerSm,
                AppSpacing.containerXs,
                AppSpacing.intraGroupXs,
                AppSpacing.intraGroupXs,
              ),
              child: Row(
                children: <Widget>[
                  Container(
                    width: AppSpacing.xs / 2,
                    height: AppSpacing.iconSmall,
                    decoration: BoxDecoration(
                      color:
                          (isDark
                                  ? AppColors.profileSloganAccentDark
                                  : AppColors.profileSloganAccentLight)
                              .withValues(alpha: isDark ? 0.80 : 0.56),
                      borderRadius: BorderRadius.circular(AppSpacing.xs / 2),
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupSm),
                  Expanded(
                    child: Text(
                      title,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.regular,
                        color: AppColors.iosLabel(context),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            _InsightDivider(),
            child,
            _InsightDivider(),
            _InsightFooterAction(label: actionLabel, onTap: onAction),
          ],
        ),
      ),
    );
  }
}

class _InsightFooterAction extends StatelessWidget {
  const _InsightFooterAction({required this.label, this.onTap});

  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final surface = isDark
        ? AppColors.iosSecondaryFill(context)
        : AppColors.iosSystemBackground(context);
    final ink = AppColors.iosLabel(context);
    final ornament = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.26 : 0.18);
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
      minimumSize: Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.buttonHeightMd,
      ),
      onPressed: onTap,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          Expanded(child: _InsightFooterLine(color: ornament)),
          SizedBox(width: AppSpacing.intraGroupSm),
          DecoratedBox(
            decoration: BoxDecoration(
              color: surface.withValues(alpha: isDark ? 0.32 : 0.68),
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              border: Border.all(color: ornament, width: AppSpacing.hairline),
            ),
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    label,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      fontWeight: AppTypography.regular,
                      color: ink,
                    ),
                  ),
                ],
              ),
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(child: _InsightFooterLine(color: ornament, reverse: true)),
        ],
      ),
    );
  }
}

class _InsightFooterLine extends StatelessWidget {
  const _InsightFooterLine({required this.color, this.reverse = false});

  final Color color;
  final bool reverse;

  @override
  Widget build(BuildContext context) {
    final dot = Container(
      width: AppSpacing.xs,
      height: AppSpacing.xs,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
    final line = Expanded(
      child: Container(height: AppSpacing.hairline, color: color),
    );
    return Row(
      children: reverse
          ? <Widget>[dot, SizedBox(width: AppSpacing.intraGroupXs), line]
          : <Widget>[line, SizedBox(width: AppSpacing.intraGroupXs), dot],
    );
  }
}

class _MyIntersectionPreviewRow extends StatelessWidget {
  const _MyIntersectionPreviewRow({
    required this.reason,
    required this.onTap,
    required this.onSpanTap,
  });

  final IntersectionReason reason;
  final VoidCallback onTap;
  final void Function(IntersectionTextSpan span) onSpanTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.square(AppSpacing.minInteractiveSize),
      onPressed: onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.containerSm,
        ),
        child: Row(
          children: <Widget>[
            IntersectionTypeIcon(
              iconKey: reason.iconKey,
              sourceRef: _sourceRefFor(reason),
              dimension: reason.dimension,
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Expanded(
              child: InteractiveIntersectionText(
                spans: reason.primarySpans,
                fallbackText: reason.primaryText,
                onSpanTap: onSpanTap,
                onFallbackTap: onTap,
                accentFontWeight: AppTypography.regular,
                baseStyle: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  height: AppSpacing.textLineHeightFootnote,
                  fontWeight: AppTypography.regular,
                  color: AppColors.iosLabel(context),
                  letterSpacing: -0.08,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MyIntersectionEmptyState extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.containerMd,
      ),
      child: Text(
        UITextConstants.profileIntersectionEmptyGuidance,
        style: TextStyle(
          fontSize: AppTypography.iosSubheadline,
          height: AppSpacing.textLineHeightFootnote,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
    );
  }
}

class _MyIntersectionSkeletonList extends StatelessWidget {
  const _MyIntersectionSkeletonList();

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        for (var i = 0; i < 3; i += 1) ...[
          if (i > 0) _InsightDivider(),
          const _MyIntersectionSkeletonRow(),
        ],
      ],
    );
  }
}

class _MyIntersectionSkeletonRow extends StatelessWidget {
  const _MyIntersectionSkeletonRow();

  @override
  Widget build(BuildContext context) {
    final fill = AppColors.iosSecondaryFill(context).withValues(alpha: 0.65);
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.containerSm,
      ),
      child: Row(
        children: <Widget>[
          Container(
            width: AppSpacing.avatarUserSm,
            height: AppSpacing.avatarUserSm,
            decoration: BoxDecoration(color: fill, shape: BoxShape.circle),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(
            child: Container(
              height: AppSpacing.sm,
              decoration: BoxDecoration(
                color: fill,
                borderRadius: BorderRadius.circular(AppSpacing.sm),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _InsightDivider extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(left: AppSpacing.containerSm * 2),
      child: Container(
        height: AppSpacing.hairline,
        color: AppColors.iosSeparator(context).withValues(alpha: 0.12),
      ),
    );
  }
}
