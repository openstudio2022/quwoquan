import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/components/more_actions_popup/configs/media_post_config.dart';

/// 更多操作弹窗组件
class MoreActionPopup extends StatelessWidget {
  final dynamic config;

  const MoreActionPopup({super.key, required this.config});

  /// 显示更多操作弹窗
  static Future<void> show({
    required BuildContext context,
    required dynamic config,
    bool showDragHandle = true,
    bool isScrollControlled = true,
  }) async {
    if (config is MediaPostMoreActionConfig) {
      await showCupertinoModalPopup(
        context: context,
        barrierColor: Colors.transparent,
        builder: (context) => _MediaPostMoreActionSheet(config: config),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(); // Stub
  }
}

/// 滚动行操作项
class _ScrollAction {
  final String id;
  final IconData icon;
  final String label;
  final VoidCallback? onTap;

  const _ScrollAction({
    required this.id,
    required this.icon,
    required this.label,
    this.onTap,
  });
}

/// 底部操作项
class _BottomAction {
  final String id;
  final IconData icon;
  final String label;
  final String? description;
  final VoidCallback? onTap;
  final bool isDestructive;

  const _BottomAction({
    required this.id,
    required this.icon,
    required this.label,
    this.description,
    this.onTap,
    this.isDestructive = false,
  });
}

/// 媒体帖子更多操作底部弹窗
class _MediaPostMoreActionSheet extends ConsumerStatefulWidget {
  final MediaPostMoreActionConfig config;

  const _MediaPostMoreActionSheet({required this.config});

  @override
  ConsumerState<_MediaPostMoreActionSheet> createState() =>
      _MediaPostMoreActionSheetState();
}

class _MediaPostMoreActionSheetState
    extends ConsumerState<_MediaPostMoreActionSheet> {
  List<_ScrollAction> _buildScrollActions(bool isDark) {
    final actions = <_ScrollAction>[
      _ScrollAction(
        id: 'reward',
        icon: CupertinoIcons.gift,
        label: AppStrings.reward,
        onTap: widget.config.onReward,
      ),
      _ScrollAction(
        id: 'save',
        icon: CupertinoIcons.arrow_down_to_line,
        label: AppStrings.save,
        onTap: widget.config.onSave,
      ),
      _ScrollAction(
        id: 'message',
        icon: CupertinoIcons.chat_bubble,
        label: AppStrings.message,
        onTap: widget.config.onMessage,
      ),
      _ScrollAction(
        id: 'copyLink',
        icon: CupertinoIcons.link,
        label: AppStrings.copyLink,
        onTap: widget.config.onCopyLink,
      ),
      _ScrollAction(
        id: 'fontSettings',
        icon: CupertinoIcons.textformat,
        label: AppStrings.fontSettings,
        onTap: widget.config.onFontSettings,
      ),
      _ScrollAction(
        id: 'darkMode',
        icon: isDark ? CupertinoIcons.sun_max : CupertinoIcons.moon,
        label: isDark ? AppStrings.lightMode : AppStrings.darkMode,
        onTap: widget.config.onThemeToggle,
      ),
      _ScrollAction(
        id: 'feedback',
        icon: CupertinoIcons.pencil,
        label: AppStrings.feedback,
        onTap: widget.config.onFeedback,
      ),
    ];
    if (widget.config.showShareAction) {
      actions.insert(
        5,
        _ScrollAction(
          id: 'share',
          icon: CupertinoIcons.share,
          label: UITextConstants.share,
          onTap: widget.config.onShare,
        ),
      );
    }
    if (widget.config.showViewOriginalAction) {
      actions.insert(
        widget.config.showShareAction ? 6 : 5,
        _ScrollAction(
          id: 'viewOriginal',
          icon: CupertinoIcons.photo,
          label: AppStrings.viewOriginal,
          onTap: widget.config.onViewOriginal,
        ),
      );
    }
    return actions;
  }

  List<_BottomAction> _buildBottomActions() {
    return [
      _BottomAction(
        id: 'notInterested',
        icon: CupertinoIcons.eye_slash,
        label: AppStrings.notInterested,
        description: AppStrings.notInterestedDescription,
        onTap: widget.config.onNotInterested,
      ),
      _BottomAction(
        id: 'blockUser',
        icon: CupertinoIcons.person_badge_minus,
        label: AppStrings.blockUser,
        description: AppStrings.blockUserDescription,
        onTap: widget.config.onBlockUser,
      ),
      _BottomAction(
        id: 'blockWords',
        icon: CupertinoIcons.slider_horizontal_3,
        label: AppStrings.blockWords,
        description: AppStrings.blockWordsDescription,
        onTap: widget.config.onBlockWords,
      ),
      _BottomAction(
        id: 'report',
        icon: CupertinoIcons.flag,
        label: AppStrings.report,
        description: AppStrings.reportDescription,
        onTap: widget.config.onReport,
        isDestructive: true,
      ),
    ];
  }

  VoidCallback? _fallbackScrollAction(String actionId) {
    switch (actionId) {
      case 'reward':
        return () => _showToast(AppStrings.rewardFeatureDeveloping);
      case 'save':
        return () => _showToast(AppStrings.saveFeatureDeveloping);
      case 'message':
        return () => _showToast(AppStrings.messageFeatureDeveloping);
      case 'viewOriginal':
        return () => _showToast(AppStrings.viewOriginalFeatureDeveloping);
      case 'fontSettings':
        return () => _showToast(AppStrings.fontSettingsFeatureDeveloping);
      case 'darkMode':
        return () {
          Future<void>.delayed(const Duration(milliseconds: 80), () {
            ref.read(themeProvider.notifier).toggleTheme();
          });
        };
      case 'feedback':
        return () => _showToast(AppStrings.feedbackFeatureDeveloping);
    }
    return null;
  }

  void _showToast(String message) {
    final navigatorContext = Navigator.of(context, rootNavigator: true).context;
    AppToast.show(
      navigatorContext,
      message,
      duration: const Duration(milliseconds: 1600),
    );
  }

  void _handleScrollActionTap(_ScrollAction action) {
    final callback = action.onTap ?? _fallbackScrollAction(action.id);
    Navigator.pop(context);
    callback?.call();
  }

  void _handleBottomActionTap(_BottomAction action) {
    Navigator.pop(context);
    action.onTap?.call();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final scrollActions = _buildScrollActions(isDark);
    final bottomActions = _buildBottomActions();
    final preferenceActions = bottomActions
        .where((action) => !action.isDestructive)
        .toList(growable: false);
    final destructiveActions = bottomActions
        .where((action) => action.isDestructive)
        .toList(growable: false);
    final panelBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.pageBackground,
    );
    final cardBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final iconSurface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceMuted,
    );
    final iconBorder = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    ).withValues(alpha: isDark ? 0.72 : 0.9);
    final divider = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final primaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final destructiveColor = AppColors.iosDestructive(context);

    return AppBottomModalSurface(
      onDismiss: () => Navigator.pop(context),
      backgroundColor: panelBackground,
      panelKey: TestKeys.modalBottomSheetPanel,
      contentPadding: EdgeInsets.only(
        left: AppSpacing.containerXs,
        right: AppSpacing.containerXs,
        bottom: AppSpacing.containerXs,
      ),
      child: SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              height: AppSpacing.modalHeaderHeight,
              child: Center(
                child: Text(
                  AppStrings.moreActionsTitle,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    fontWeight: AppTypography.semiBold,
                    color: primaryText,
                  ),
                ),
              ),
            ),
            if (scrollActions.isNotEmpty) ...[
              _MoreActionQuickSection(
                actions: scrollActions,
                cardBackground: cardBackground,
                iconSurface: iconSurface,
                iconBorder: iconBorder,
                primaryText: primaryText,
                secondaryText: secondaryText,
                onTap: _handleScrollActionTap,
              ),
              SizedBox(height: AppSpacing.interGroupSm),
            ],
            if (preferenceActions.isNotEmpty) ...[
              _MoreActionListSection(
                actions: preferenceActions,
                cardBackground: cardBackground,
                divider: divider,
                primaryText: primaryText,
                secondaryText: secondaryText,
                onTap: _handleBottomActionTap,
              ),
              SizedBox(height: AppSpacing.interGroupSm),
            ],
            if (destructiveActions.isNotEmpty) ...[
              _MoreActionListSection(
                actions: destructiveActions,
                cardBackground: cardBackground,
                divider: divider,
                primaryText: destructiveColor,
                secondaryText: destructiveColor.withValues(alpha: 0.75),
                onTap: _handleBottomActionTap,
              ),
              SizedBox(height: AppSpacing.interGroupSm),
            ],
            _MoreActionCancelSection(
              backgroundColor: cardBackground,
              foregroundColor: secondaryText,
              onTap: () => Navigator.pop(context),
            ),
          ],
        ),
      ),
    );
  }
}

class _MoreActionQuickSection extends StatelessWidget {
  const _MoreActionQuickSection({
    required this.actions,
    required this.cardBackground,
    required this.iconSurface,
    required this.iconBorder,
    required this.primaryText,
    required this.secondaryText,
    required this.onTap,
  });

  final List<_ScrollAction> actions;
  final Color cardBackground;
  final Color iconSurface;
  final Color iconBorder;
  final Color primaryText;
  final Color secondaryText;
  final ValueChanged<_ScrollAction> onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: cardBackground,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      padding: EdgeInsets.symmetric(vertical: AppSpacing.containerSm),
      child: SizedBox(
        height: AppSpacing.oneHundred + AppSpacing.md,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
          itemBuilder: (context, index) {
            final action = actions[index];
            return SizedBox(
              width: AppSpacing.avatarUserLg + AppSpacing.twenty,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => onTap(action),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: AppSpacing.avatarUserLg,
                      height: AppSpacing.avatarUserLg,
                      decoration: BoxDecoration(
                        color: iconSurface,
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: iconBorder,
                          width: AppSpacing.hairline,
                        ),
                      ),
                      child: Icon(
                        action.icon,
                        size: AppSpacing.iconMedium,
                        color: secondaryText,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupSm),
                    Text(
                      action.label,
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: primaryText,
                        fontWeight: AppTypography.medium,
                      ),
                      textAlign: TextAlign.center,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
            );
          },
          separatorBuilder: (context, index) =>
              SizedBox(width: AppSpacing.intraGroupXs),
          itemCount: actions.length,
        ),
      ),
    );
  }
}

class _MoreActionListSection extends StatelessWidget {
  const _MoreActionListSection({
    required this.actions,
    required this.cardBackground,
    required this.divider,
    required this.primaryText,
    required this.secondaryText,
    required this.onTap,
  });

  final List<_BottomAction> actions;
  final Color cardBackground;
  final Color divider;
  final Color primaryText;
  final Color secondaryText;
  final ValueChanged<_BottomAction> onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: cardBackground,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Column(
        children: actions.asMap().entries.map((entry) {
          final index = entry.key;
          final action = entry.value;
          return Column(
            children: [
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: () => onTap(action),
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerMd,
                    vertical: AppSpacing.containerSm,
                  ),
                  child: Row(
                    children: [
                      Icon(
                        action.icon,
                        size: AppSpacing.twenty,
                        color: primaryText,
                      ),
                      SizedBox(width: AppSpacing.containerSm),
                      Expanded(
                        child: Text(
                          action.label,
                          style: TextStyle(
                            fontSize: AppTypography.lg,
                            fontWeight: AppTypography.medium,
                            color: primaryText,
                          ),
                        ),
                      ),
                      if (action.description != null)
                        Flexible(
                          child: Text(
                            action.description!,
                            style: TextStyle(
                              fontSize: AppTypography.base,
                              color: secondaryText,
                            ),
                            textAlign: TextAlign.right,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                    ],
                  ),
                ),
              ),
              if (index < actions.length - 1)
                Container(
                  height: AppSpacing.hairline,
                  margin: EdgeInsets.only(
                    left: AppSpacing.containerMd + AppSpacing.twenty,
                    right: AppSpacing.containerMd,
                  ),
                  color: divider.withValues(alpha: 0.9),
                ),
            ],
          );
        }).toList(),
      ),
    );
  }
}

class _MoreActionCancelSection extends StatelessWidget {
  const _MoreActionCancelSection({
    required this.backgroundColor,
    required this.foregroundColor,
    required this.onTap,
  });

  final Color backgroundColor;
  final Color foregroundColor;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.containerSm),
        onPressed: onTap,
        child: Text(
          UITextConstants.cancel,
          style: TextStyle(
            fontSize: AppTypography.lg,
            fontWeight: AppTypography.medium,
            color: foregroundColor,
          ),
        ),
      ),
    );
  }
}
