import 'package:flutter/cupertino.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_media_image.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';

/// 发布圈子选择页（design §3.7）
///
/// 已加入 / 推荐圈子分区，Cupertino 语义，底部取消+确认。
/// 无已加入圈子时展示空态「加入圈子，发现同好」+ 发现页 CTA。
class PublishCircleSelectPage extends StatefulWidget {
  const PublishCircleSelectPage({
    super.key,
    required this.joinedCircles,
    required this.initialSelected,
    this.recommendedCircles = const [],
  });

  final List<CreateCircleOption> joinedCircles;
  final Map<String, String> initialSelected;
  final List<CreateCircleOption> recommendedCircles;

  @override
  State<PublishCircleSelectPage> createState() =>
      _PublishCircleSelectPageState();
}

class _PublishCircleSelectPageState extends State<PublishCircleSelectPage> {
  static const double _kCoverSize = AppSpacing.avatarUserLg;

  late Map<String, String> _selected;

  @override
  void initState() {
    super.initState();
    _selected = Map<String, String>.from(widget.initialSelected);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final hasJoined = widget.joinedCircles.isNotEmpty;
    final hasRecommended = widget.recommendedCircles.isNotEmpty;

    return IosSelectionPageScaffold(
      pageKey: TestKeys.publishCircleSelectPage,
      title: l10n.selectCircle,
      onBack: () => Navigator.of(context).pop<Map<String, String>?>(null),
      backgroundColor: AppColors.iosPageBackground(context),
      body: CustomScrollView(
        slivers: <Widget>[
          const SliverToBoxAdapter(
            child: SizedBox(height: AppSpacing.intraGroupXs),
          ),
          if (hasJoined) ...<Widget>[
            SliverToBoxAdapter(
              child: IosSelectionSectionHeader(title: l10n.circleJoinedSection),
            ),
            _buildSection(widget.joinedCircles),
          ],
          if (hasRecommended) ...<Widget>[
            SliverToBoxAdapter(
              child: IosSelectionSectionHeader(
                title: l10n.circleRecommendedSection,
              ),
            ),
            _buildSection(widget.recommendedCircles),
          ],
          if (!hasJoined && !hasRecommended)
            SliverFillRemaining(
              hasScrollBody: false,
              child: _buildEmptyState(context, l10n),
            )
          else
            const SliverToBoxAdapter(
              child: SizedBox(height: AppSpacing.interGroupMd),
            ),
        ],
      ),
      bottomBar: IosSelectionBottomBar(
        cancelButtonKey: TestKeys.publishCircleCancelButton,
        confirmButtonKey: TestKeys.publishCircleConfirmButton,
        onCancel: () => Navigator.of(context).pop<Map<String, String>?>(null),
        onConfirm: () => Navigator.of(context).pop(_selected),
      ),
    );
  }

  Widget _buildSection(List<CreateCircleOption> circles) {
    return SliverToBoxAdapter(
      child: Column(
        children: <Widget>[
          for (var i = 0; i < circles.length; i++) ...<Widget>[
            _buildCircleTile(circles[i]),
            if (i != circles.length - 1) _buildSectionDivider(),
          ],
          const SizedBox(height: AppSpacing.interGroupSm),
        ],
      ),
    );
  }

  Widget _buildCircleTile(CreateCircleOption circle) {
    final checked = _selected.containsKey(circle.id);
    final subtitle = _buildSubtitle(circle);
    return IosSelectionOptionTile(
      key: ValueKey<String>('publish_circle_tile_${circle.id}'),
      backgroundColor: AppColors.iosSystemBackground(context),
      pressedColor: AppColors.iosSecondaryFill(context),
      leading: _buildCircleCover(circle),
      title: Text(
        circle.name,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize: AppTypography.iosSubheadline,
          fontWeight: AppTypography.medium,
          color: AppColors.iosLabel(context),
        ),
      ),
      subtitle: subtitle.isEmpty
          ? null
          : Text(
              subtitle,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
      trailing: _buildSelectionIndicator(checked: checked),
      onTap: () => _toggleSelection(circle),
    );
  }

  String _buildSubtitle(CreateCircleOption circle) {
    final parts = <String>[
      if (circle.memberCount != null)
        '${formatCompactActionCount(circle.memberCount!)} ${UITextConstants.circleMembers}',
      if (circle.postCount != null)
        '${formatCompactActionCount(circle.postCount!)} ${UITextConstants.circleWorksCountSuffix}',
      if ((circle.recommendationReason ?? '').trim().isNotEmpty)
        circle.recommendationReason!.trim(),
    ];
    return parts.join(' · ');
  }

  Widget _buildCircleCover(CreateCircleOption circle) {
    final fallback = ColoredBox(
      color: AppColors.iosSecondaryFill(context),
      child: Center(
        child: Icon(
          CupertinoIcons.person_3_fill,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
    );

    return ClipRRect(
      borderRadius: BorderRadius.circular(
        AppSpacing.contentPreviewCornerRadius,
      ),
      child: SizedBox(
        width: _kCoverSize,
        height: _kCoverSize,
        child: (circle.coverUrl ?? '').trim().isEmpty
            ? fallback
            : CircleMediaImage(
                imageSource: circle.coverUrl!,
                fit: BoxFit.cover,
                placeholder: fallback,
                errorWidget: fallback,
              ),
      ),
    );
  }

  Widget _buildSectionDivider() {
    return IosSelectionInlineDivider(
      indent: AppSpacing.containerMd + _kCoverSize + AppSpacing.containerSm,
      endIndent: AppSpacing.containerMd,
    );
  }

  Widget _buildSelectionIndicator({required bool checked}) {
    return SizedBox(
      width: AppSpacing.minInteractiveSize,
      height: AppSpacing.minInteractiveSize,
      child: Center(
        child: Icon(
          checked
              ? CupertinoIcons.check_mark_circled_solid
              : CupertinoIcons.circle,
          size: AppSpacing.iconMedium,
          color: checked
              ? AppColors.primaryColor
              : CupertinoColors.systemGrey2.resolveFrom(context),
        ),
      ),
    );
  }

  void _toggleSelection(CreateCircleOption circle) {
    setState(() {
      if (_selected.containsKey(circle.id)) {
        _selected.remove(circle.id);
      } else {
        _selected[circle.id] = circle.name;
      }
    });
  }

  Widget _buildEmptyState(BuildContext context, AppLocalizations l10n) {
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: IosSelectionSection(
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.containerLg),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  l10n.noCirclesAvailable,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: AppTypography.iosBody,
                    color: fgSecondary,
                    height: AppTypography.bodyLineHeight,
                  ),
                ),
                SizedBox(height: AppSpacing.interGroupMd),
                SizedBox(
                  width: double.infinity,
                  child: _CircleGhostActionButton(
                    label: l10n.goToDiscovery,
                    onPressed: () => context.go(AppRoutePaths.home),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _CircleGhostActionButton extends StatelessWidget {
  const _CircleGhostActionButton({
    required this.label,
    required this.onPressed,
  });

  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    return SizedBox(
      height: AppSpacing.buttonHeight + AppSpacing.intraGroupSm,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.iosProfileSurface(context),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
          border: Border.all(
            color: accent.withValues(alpha: 0.2),
            width: AppSpacing.hairline,
          ),
        ),
        child: CupertinoButton(
          padding: EdgeInsets.zero,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
          onPressed: onPressed,
          child: Text(
            label,
            style: TextStyle(
              color: accent,
              fontSize: AppTypography.iosButton,
              fontWeight: AppTypography.semiBold,
            ),
          ),
        ),
      ),
    );
  }
}
