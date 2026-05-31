import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

enum HomePrimaryTabStripStyle { regular, immersive }

class HomePrimaryTabStrip extends StatelessWidget {
  const HomePrimaryTabStrip({
    super.key,
    required this.activeChannelId,
    required this.onChannelChanged,
    required this.isDark,
    this.channels,
    this.style = HomePrimaryTabStripStyle.regular,
    this.featuredIndicatorVisible = false,
    this.featuredExpanded = false,
    this.onHorizontalDragEnd,
    this.immersiveSelectedColor,
    this.immersiveUnselectedColor,
  });

  static const String followingChannelId = 'following';
  // 与 ContentUIConfig.homeChannels 的推荐频道 id 对齐（运营/远程覆盖真相源）。
  static const String recommendedChannelId = 'recommend';
  static const String featuredChannelId = 'featured';
  static const String circlesChannelId = 'circles';
  static const String travelPhotographyChannelId = 'travel_photography';
  static const String campusChannelId = 'campus';
  static const String travelChannelId = 'travel';
  static const String photographyChannelId = 'photography';
  static const String techChannelId = 'tech';
  static const String carChannelId = 'car';
  static const String carFriendsChannelId = carChannelId;
  static const Key stripKey = ValueKey<String>('home-primary-tab-strip');

  static const List<String> homeChannelIds = <String>[
    followingChannelId,
    recommendedChannelId,
    campusChannelId,
    travelChannelId,
    photographyChannelId,
    techChannelId,
    carChannelId,
  ];

  static const List<String> immersiveChannelIds = <String>[
    followingChannelId,
    featuredChannelId,
  ];

  static Key channelKey(String channelId) =>
      ValueKey<String>('home-primary-tab-$channelId');

  final String activeChannelId;
  final ValueChanged<String> onChannelChanged;
  final bool isDark;

  /// 首页频道（运营资产，来自 homeChannelsProvider：端默认 + 远程覆盖）。
  /// 为空时回退发布自带默认 [homeChannelIds]（仅离线兜底）；immersive 风格固定用 [immersiveChannelIds]。
  final List<HomeChannelConfig>? channels;
  final HomePrimaryTabStripStyle style;
  final bool featuredIndicatorVisible;
  final bool featuredExpanded;
  final GestureDragEndCallback? onHorizontalDragEnd;
  final Color? immersiveSelectedColor;
  final Color? immersiveUnselectedColor;

  static double _measureLabelWidth(BuildContext context, String label) {
    final painter = TextPainter(
      text: TextSpan(
        text: label,
        style: TextStyle(
          fontSize: AppTypography.primaryTabLabelResponsive(context),
          fontWeight: AppTypography.primaryTabSelectedWeight,
        ),
      ),
      maxLines: 1,
      textDirection: Directionality.of(context),
      textScaler: MediaQuery.textScalerOf(context),
    )..layout();
    return painter.width;
  }

  static double _slotWidth(
    BuildContext context,
    String label, {
    bool reserveAccessorySlot = false,
  }) {
    final labelWidth = _measureLabelWidth(context, label);
    final edgeReserve = reserveAccessorySlot
        ? AppSpacing.primaryTabAccessoryReserve(context)
        : AppSpacing.primaryTabSlotSidePadding(context);
    return (labelWidth + (edgeReserve * 2)).clamp(
      AppSpacing.minInteractiveSize,
      double.infinity,
    );
  }

  @override
  Widget build(BuildContext context) {
    final gap = AppSpacing.primaryTabGroupGap(context);
    final labelByChannelId = <String, String>{
      for (final channel in channels ?? const <HomeChannelConfig>[])
        channel.id: UITextConstants.homeChannelLabel(channel.labelKey),
    };
    final regularChannelIds = (channels != null && channels!.isNotEmpty)
        ? channels!.map((channel) => channel.id).toList(growable: false)
        : homeChannelIds;
    final channelIds = style == HomePrimaryTabStripStyle.immersive
        ? immersiveChannelIds
        : regularChannelIds;
    String labelFor(String channelId) =>
        labelByChannelId[channelId] ?? _labelForChannel(channelId);
    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      onHorizontalDragEnd: onHorizontalDragEnd,
      child: SingleChildScrollView(
        key: stripKey,
        scrollDirection: Axis.horizontal,
        physics: const BouncingScrollPhysics(),
        child: SizedBox(
          height: AppSpacing.primaryTopBarHeight(context),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (var i = 0; i < channelIds.length; i++) ...[
                if (i > 0) SizedBox(width: gap),
                _HomePrimaryTabStripItem(
                  key: channelKey(channelIds[i]),
                  channelId: channelIds[i],
                  label: labelFor(channelIds[i]),
                  selected: activeChannelId == channelIds[i],
                  slotWidth: _slotWidth(
                    context,
                    labelFor(channelIds[i]),
                    reserveAccessorySlot: channelIds[i] == featuredChannelId,
                  ),
                  isDark: isDark,
                  style: style,
                  reserveIndicatorSlot: channelIds[i] == featuredChannelId,
                  showIndicator:
                      channelIds[i] == featuredChannelId &&
                      featuredIndicatorVisible,
                  indicatorExpanded: featuredExpanded,
                  immersiveSelectedColor: immersiveSelectedColor,
                  immersiveUnselectedColor: immersiveUnselectedColor,
                  onTap: () => _handleChannelTap(channelIds[i]),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  static String _labelForChannel(String channelId) => switch (channelId) {
    followingChannelId => UITextConstants.homeTabFollowing,
    recommendedChannelId => UITextConstants.homeTabRecommended,
    featuredChannelId => UITextConstants.homeTabFeatured,
    circlesChannelId => UITextConstants.homeTabCircles,
    travelPhotographyChannelId =>
      UITextConstants.circleScenarioTravelPhotography,
    campusChannelId => UITextConstants.circleScenarioCampus,
    travelChannelId => UITextConstants.homeTabTravel,
    photographyChannelId => UITextConstants.homeTabPhotography,
    techChannelId => UITextConstants.homeTabTech,
    carFriendsChannelId => UITextConstants.homeTabCarFriends,
    _ => UITextConstants.homeTabRecommended,
  };

  void _handleChannelTap(String channelId) {
    if (channelId != activeChannelId) {
      HapticFeedback.selectionClick();
    }
    onChannelChanged(channelId);
  }
}

class _HomePrimaryTabStripItem extends StatelessWidget {
  const _HomePrimaryTabStripItem({
    super.key,
    required this.channelId,
    required this.label,
    required this.selected,
    required this.slotWidth,
    required this.isDark,
    required this.style,
    required this.onTap,
    this.reserveIndicatorSlot = false,
    this.showIndicator = false,
    this.indicatorExpanded = false,
    this.immersiveSelectedColor,
    this.immersiveUnselectedColor,
  });

  final String channelId;
  final String label;
  final bool selected;
  final double slotWidth;
  final bool isDark;
  final HomePrimaryTabStripStyle style;
  final VoidCallback onTap;
  final bool reserveIndicatorSlot;
  final bool showIndicator;
  final bool indicatorExpanded;
  final Color? immersiveSelectedColor;
  final Color? immersiveUnselectedColor;

  @override
  Widget build(BuildContext context) {
    final selectedColor = switch (style) {
      HomePrimaryTabStripStyle.immersive =>
        immersiveSelectedColor ?? AppColors.worksTitle,
      HomePrimaryTabStripStyle.regular =>
        isDark
            ? AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary)
            : AppColors.primaryColor,
    };
    final unselectedColor = switch (style) {
      HomePrimaryTabStripStyle.immersive =>
        immersiveUnselectedColor ??
            AppColors.worksTitle.withValues(alpha: 0.72),
      HomePrimaryTabStripStyle.regular =>
        isDark
            ? AppColorsFunctional.getColor(isDark, ColorType.tabUnselected)
            : AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundSecondary,
              ),
    };
    final underlineColor = isDark
        ? AppColors.iosAccentDark
        : AppColors.primaryColor;
    final fontSize = AppTypography.primaryTabLabelResponsive(context);
    final selectedWeight = AppTypography.primaryTabSelectedWeight;
    final unselectedWeight = AppTypography.primaryTabUnselectedWeight;
    final textStyle = TextStyle(
      fontSize: fontSize,
      fontWeight: selected ? selectedWeight : unselectedWeight,
      color: selected ? selectedColor : unselectedColor,
    );
    final underlineWidth = _measureLabelWidth(
      context,
      fontSize,
      selectedWeight,
    );
    final indicatorColor = selected
        ? selectedColor
        : unselectedColor.withValues(alpha: 0.88);
    final indicatorReserve = reserveIndicatorSlot
        ? AppSpacing.primaryTabAccessoryReserve(context)
        : 0.0;
    final showUnderline =
        selected &&
        style == HomePrimaryTabStripStyle.regular &&
        channelId != HomePrimaryTabStrip.featuredChannelId;

    return SizedBox(
      width: slotWidth,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.square(AppSpacing.minInteractiveSize),
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        onPressed: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            minWidth: AppSpacing.minInteractiveSize,
            minHeight: AppSpacing.minInteractiveSize,
          ),
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              Align(
                alignment: Alignment.center,
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: textStyle,
                ),
              ),
              if (reserveIndicatorSlot)
                Positioned.fill(
                  child: Align(
                    alignment: Alignment.centerRight,
                    child: SizedBox(
                      width: indicatorReserve,
                      child: AnimatedOpacity(
                        duration: const Duration(milliseconds: 180),
                        opacity: showIndicator ? 1 : 0,
                        child: AnimatedRotation(
                          duration: const Duration(milliseconds: 220),
                          turns: indicatorExpanded ? 0.5 : 0,
                          curve: Curves.easeOutCubic,
                          child: Icon(
                            Icons.keyboard_arrow_down,
                            color: indicatorColor,
                            size: AppSpacing.iconSmall,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: Center(
                  child: SizedBox(
                    width: underlineWidth,
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      height: showUnderline
                          ? AppSpacing.primaryTabUnderlineHeight
                          : 0,
                      decoration: BoxDecoration(
                        color: underlineColor,
                        borderRadius: BorderRadius.circular(
                          AppSpacing.primaryTabUnderlineHeight / 2,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  double _measureLabelWidth(
    BuildContext context,
    double fontSize,
    FontWeight fontWeight,
  ) {
    final painter = TextPainter(
      text: TextSpan(
        text: label,
        style: TextStyle(fontSize: fontSize, fontWeight: fontWeight),
      ),
      maxLines: 1,
      textDirection: Directionality.of(context),
    )..layout();
    return painter.width;
  }
}
