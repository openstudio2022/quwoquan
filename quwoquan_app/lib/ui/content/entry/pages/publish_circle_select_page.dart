import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';
import 'package:quwoquan_app/l10n/l10n.dart';

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
  late Map<String, String> _selected;

  @override
  void initState() {
    super.initState();
    _selected = Map<String, String>.from(widget.initialSelected);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);
    final blockBg = SettingsSemanticConstants.blockBackground(isDark);
    final dividerClr = SettingsSemanticConstants.dividerColor(isDark);
    final blue = AppColors.primaryColor;

    final hasJoined = widget.joinedCircles.isNotEmpty;
    final hasRecommended = widget.recommendedCircles.isNotEmpty;

    return CupertinoPageScaffold(
      navigationBar: CupertinoNavigationBar(
        middle: Text(
          l10n.selectCircle,
          style: TextStyle(
            fontSize: AppTypography.lg,
            fontWeight: FontWeight.w600,
            color: isDark ? CupertinoColors.white : CupertinoColors.black,
          ),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          child: const Icon(CupertinoIcons.xmark),
          onPressed: () =>
              Navigator.of(context).pop<Map<String, String>?>(null),
        ),
      ),
      child: Material(
        type: MaterialType.transparency,
        child: SafeArea(
          child: Column(
            children: [
              Expanded(
                child: CustomScrollView(
                  slivers: [
                    if (!hasJoined) ...[
                      SliverToBoxAdapter(
                        child: Padding(
                          padding: EdgeInsets.symmetric(
                            horizontal:
                                SettingsSemanticConstants.blockHorizontalPadding,
                            vertical: AppSpacing.interGroupMd,
                          ),
                          child: Text(
                            l10n.noCirclesAvailable,
                            style: TextStyle(
                              fontSize: AppTypography.sm,
                              color: fgSecondary,
                            ),
                          ),
                        ),
                      ),
                    ],
                    if (hasJoined) ...[
                      _sectionHeader(l10n.circleJoinedSection, fgSecondary),
                      SliverToBoxAdapter(
                        child: Container(
                          margin: EdgeInsets.symmetric(
                            horizontal:
                                SettingsSemanticConstants.blockHorizontalPadding,
                            vertical: AppSpacing.sm,
                          ),
                          decoration: BoxDecoration(
                            color: blockBg,
                            borderRadius: BorderRadius.circular(
                              SettingsSemanticConstants.blockBorderRadius,
                            ),
                            border: Border.all(
                              color: SettingsSemanticConstants.blockBorderColor(
                                isDark,
                              ),
                            ),
                          ),
                          child: Column(
                            children: [
                              for (
                                var i = 0;
                                i < widget.joinedCircles.length;
                                i++
                              ) ...[
                                if (i > 0)
                                  Divider(
                                    height: 1,
                                    color: dividerClr,
                                    thickness: SettingsSemanticConstants
                                        .dividerThickness,
                                  ),
                                _buildJoinedTile(
                                  widget.joinedCircles[i],
                                  l10n,
                                  fgPrimary,
                                  fgSecondary,
                                  blue,
                                ),
                              ],
                            ],
                          ),
                        ),
                      ),
                    ],
                    if (hasRecommended) ...[
                      _sectionHeader(
                        l10n.circleRecommendedSection,
                        fgSecondary,
                      ),
                      SliverToBoxAdapter(
                        child: Container(
                          margin: EdgeInsets.symmetric(
                            horizontal:
                                SettingsSemanticConstants.blockHorizontalPadding,
                            vertical: AppSpacing.sm,
                          ),
                          decoration: BoxDecoration(
                            color: blockBg,
                            borderRadius: BorderRadius.circular(
                              SettingsSemanticConstants.blockBorderRadius,
                            ),
                            border: Border.all(
                              color: SettingsSemanticConstants.blockBorderColor(
                                isDark,
                              ),
                            ),
                          ),
                          child: Column(
                            children: [
                              for (
                                var i = 0;
                                i < widget.recommendedCircles.length;
                                i++
                              ) ...[
                                if (i > 0)
                                  Divider(
                                    height: 1,
                                    color: dividerClr,
                                    thickness: SettingsSemanticConstants
                                        .dividerThickness,
                                  ),
                                _buildRecommendedTile(
                                  widget.recommendedCircles[i],
                                  l10n,
                                  fgPrimary,
                                  fgSecondary,
                                ),
                              ],
                            ],
                          ),
                        ),
                      ),
                    ],
                    if (!hasJoined && !hasRecommended)
                      SliverFillRemaining(
                        hasScrollBody: false,
                        child: _buildEmptyState(context, l10n, fgSecondary),
                      ),
                  ],
                ),
              ),
              Container(
                padding: EdgeInsets.symmetric(
                  horizontal: SettingsSemanticConstants.blockHorizontalPadding,
                  vertical: AppSpacing.interGroupMd,
                ),
                decoration: BoxDecoration(
                  color: SettingsSemanticConstants.pageBackground(isDark),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: CupertinoButton(
                        onPressed: () =>
                            Navigator.of(context).pop<Map<String, String>?>(null),
                        child: Text(l10n.cancel),
                      ),
                    ),
                    SizedBox(width: AppSpacing.interGroupMd),
                    Expanded(
                      child: CupertinoButton.filled(
                        onPressed: () => Navigator.of(context).pop(_selected),
                        child: Text(l10n.confirm),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _sectionHeader(String title, Color color) {
    return SliverToBoxAdapter(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          SettingsSemanticConstants.blockHorizontalPadding,
          AppSpacing.interGroupMd,
          SettingsSemanticConstants.blockHorizontalPadding,
          AppSpacing.sm,
        ),
        child: Text(
          title,
          style: TextStyle(
            fontSize: AppTypography.sm,
            fontWeight: AppTypography.semiBold,
            color: color,
          ),
        ),
      ),
    );
  }

  Widget _buildJoinedTile(
    CreateCircleOption circle,
    AppLocalizations l10n,
    Color fgPrimary,
    Color fgSecondary,
    Color blue,
  ) {
    final subtitle = circle.memberCount != null
        ? l10n.circleMemberCountJoined(circle.memberCount!)
        : l10n.circleJoinedLabel;
    return _buildSelectableTile(
      circle: circle,
      subtitle: subtitle,
      fgPrimary: fgPrimary,
      fgSecondary: fgSecondary,
      blue: blue,
    );
  }

  Widget _buildRecommendedTile(
    CreateCircleOption circle,
    AppLocalizations l10n,
    Color fgPrimary,
    Color fgSecondary,
  ) {
    final reason = circle.recommendationReason ?? '';
    final count = circle.memberCount ?? 0;
    final subtitle = reason.isNotEmpty && count > 0
        ? l10n.circleRecommendedSubtitle(reason, count)
        : count > 0
        ? '$count ${l10n.circleMembers}'
        : null;
    return _buildSelectableTile(
      circle: circle,
      subtitle: subtitle,
      fgPrimary: fgPrimary,
      fgSecondary: fgSecondary,
      blue: AppColors.primaryColor,
    );
  }

  Widget _buildSelectableTile({
    required CreateCircleOption circle,
    required String? subtitle,
    required Color fgPrimary,
    required Color fgSecondary,
    required Color blue,
  }) {
    final checked = _selected.containsKey(circle.id);
    return CupertinoListTile(
      leadingSize: AppSpacing.minInteractiveSize,
      leading: CircleAvatar(
        radius: AppSpacing.avatarUserMd / 2,
        backgroundColor: blue.withValues(alpha: 0.16),
        child: Text(
          circle.name.isNotEmpty ? circle.name[0] : '?',
          style: TextStyle(
            color: blue,
            fontSize: AppTypography.sm,
            fontWeight: AppTypography.semiBold,
          ),
        ),
      ),
      title: Text(
        circle.name,
        style: TextStyle(
          fontSize: AppTypography.lg,
          fontWeight: AppTypography.medium,
          color: fgPrimary,
        ),
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: subtitle == null
          ? null
          : Text(
              subtitle,
              style: TextStyle(fontSize: AppTypography.xs, color: fgSecondary),
              overflow: TextOverflow.ellipsis,
            ),
      trailing: _buildSelectionIndicator(
        checked: checked,
        onTap: () => _toggleSelection(circle),
      ),
      onTap: () => _toggleSelection(circle),
    );
  }

  Widget _buildSelectionIndicator({
    required bool checked,
    required VoidCallback onTap,
  }) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: SizedBox(
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
                : CupertinoColors.systemGrey2,
          ),
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

  Widget _buildEmptyState(
    BuildContext context,
    AppLocalizations l10n,
    Color fgSecondary,
  ) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(
          SettingsSemanticConstants.blockHorizontalPadding,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              l10n.noCirclesAvailable,
              style: TextStyle(
                fontSize: AppTypography.lg,
                color: fgSecondary,
                height: 1.4,
              ),
              textAlign: TextAlign.center,
            ),
            SizedBox(height: AppSpacing.interGroupLg),
            CupertinoButton.filled(
              onPressed: () => context.go(AppRoutePaths.home),
              child: Text(l10n.goToDiscovery),
            ),
          ],
        ),
      ),
    );
  }
}
