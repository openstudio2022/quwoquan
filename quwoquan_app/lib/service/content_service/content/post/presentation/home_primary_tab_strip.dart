import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

class HomePrimaryTabStrip extends StatefulWidget {
  const HomePrimaryTabStrip({
    super.key,
    required this.activeChannelId,
    required this.onChannelChanged,
    required this.isDark,
    this.channels,
  });

  static const String followingChannelId = 'following';
  // 与 ContentUIConfig.homeChannels 的推荐频道 id 对齐（运营/远程覆盖真相源）。
  static const String recommendedChannelId = 'recommend';
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

  static Key channelKey(String channelId) =>
      ValueKey<String>('home-primary-tab-$channelId');

  final String activeChannelId;
  final ValueChanged<String> onChannelChanged;
  final bool isDark;

  /// 首页频道（运营资产，来自 homeChannelsProvider：端默认 + 远程覆盖）。
  /// 为空时回退发布自带默认 [homeChannelIds]（仅离线兜底）。
  final List<HomeChannelConfig>? channels;

  @override
  State<HomePrimaryTabStrip> createState() => _HomePrimaryTabStripState();

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

  static double _slotWidth(BuildContext context, String label) {
    final labelWidth = _measureLabelWidth(context, label);
    final edgeReserve = AppSpacing.primaryTabSlotSidePadding(context);
    return (labelWidth + (edgeReserve * 2)).clamp(
      AppSpacing.minInteractiveSize,
      double.infinity,
    );
  }

  static String _labelForChannel(String channelId) => switch (channelId) {
    followingChannelId => DiscoveryText.homeTabFollowing,
    recommendedChannelId => DiscoveryText.homeTabRecommended,
    circlesChannelId => DiscoveryText.homeTabCircles,
    travelPhotographyChannelId => DiscoveryText.circleScenarioTravelPhotography,
    campusChannelId => DiscoveryText.circleScenarioCampus,
    travelChannelId => DiscoveryText.homeTabTravel,
    photographyChannelId => DiscoveryText.homeTabPhotography,
    techChannelId => DiscoveryText.homeTabTech,
    carFriendsChannelId => DiscoveryText.homeTabCarFriends,
    _ => DiscoveryText.homeTabRecommended,
  };

  void _handleChannelTap(String channelId) {
    if (channelId != activeChannelId) {
      HapticFeedback.selectionClick();
    }
    onChannelChanged(channelId);
  }
}

class _HomePrimaryTabStripState extends State<HomePrimaryTabStrip>
    with SingleTickerProviderStateMixin {
  final ScrollController _scrollController = ScrollController();
  late final AnimationController _selectionAnimation = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 200),
  )..addListener(_advanceSelection);
  double _animationStart = 0;
  double _animationTarget = 0;

  void _advanceSelection() {
    if (!_scrollController.hasClients) return;
    final progress = Curves.easeOutCubic.transform(_selectionAnimation.value);
    _scrollController.jumpTo(
      (_animationStart + (_animationTarget - _animationStart) * progress).clamp(
        0.0,
        _scrollController.position.maxScrollExtent,
      ),
    );
  }

  List<double> _geometry = const [];
  String? _syncedChannel;
  int _layoutGeneration = 0;

  @override
  void dispose() {
    _layoutGeneration++;
    _selectionAnimation.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _syncSelection(List<double> geometry, double target) {
    if (_syncedChannel == widget.activeChannelId &&
        listEquals(_geometry, geometry)) {
      return;
    }
    _geometry = geometry;
    _syncedChannel = widget.activeChannelId;
    final generation = ++_layoutGeneration;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          generation != _layoutGeneration ||
          !_scrollController.hasClients) {
        return;
      }
      final position = _scrollController.position;
      final offset = target.clamp(0.0, position.maxScrollExtent);
      // ScrollPosition.animateTo 会忽略动画中子项的点击；逐帧 jump 保持标签可点击。
      _selectionAnimation.stop();
      if (MediaQuery.disableAnimationsOf(context) ||
          (position.pixels - offset).abs() < 0.1) {
        _scrollController.jumpTo(offset);
      } else {
        _animationStart = position.pixels;
        _animationTarget = offset;
        _selectionAnimation.forward(from: 0);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final channels = widget.channels;
    final ids = channels != null && channels.isNotEmpty
        ? channels.map((channel) => channel.id).toList(growable: false)
        : HomePrimaryTabStrip.homeChannelIds;
    final labels = <String, String>{
      for (final channel in channels ?? const <HomeChannelConfig>[])
        channel.id: UITextConstants.homeChannelLabel(channel.labelKey),
    };
    String labelFor(String id) =>
        labels[id] ?? HomePrimaryTabStrip._labelForChannel(id);
    final widths = [
      for (final id in ids)
        HomePrimaryTabStrip._slotWidth(context, labelFor(id)),
    ];
    final gap = AppSpacing.primaryTabGroupGap(context);
    final starts = <double>[];
    var total = 0.0;
    for (var i = 0; i < ids.length; i++) {
      starts.add(total);
      total += widths[i] + (i == ids.length - 1 ? 0 : gap);
    }
    final hasAnchor =
        ids.length > 1 &&
        ids[0] == HomePrimaryTabStrip.followingChannelId &&
        ids[1] == HomePrimaryTabStrip.recommendedChannelId;
    Widget item(int i) => _HomePrimaryTabStripItem(
      key: HomePrimaryTabStrip.channelKey(ids[i]),
      channelId: ids[i],
      label: labelFor(ids[i]),
      selected: widget.activeChannelId == ids[i],
      slotWidth: widths[i],
      isDark: widget.isDark,
      onTap: () => widget._handleChannelTap(ids[i]),
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        final index = ids.indexOf(widget.activeChannelId);
        final center = index < 0 ? 0.0 : starts[index] + widths[index] / 2;
        final target = total > width && index >= 0 && (!hasAnchor || index > 1)
            ? center - width / 2
            : 0.0;
        _syncSelection([width, gap, ...widths, index.toDouble()], target);
        return SizedBox(
          key: HomePrimaryTabStrip.stripKey,
          height: AppSpacing.primaryTopBarHeight(context),
          child: AnimatedBuilder(
            animation: _scrollController,
            builder: (context, _) {
              final offset = _scrollController.hasClients
                  ? _scrollController.offset
                  : 0.0;
              final anchored = hasAnchor && total > width && offset > 0;
              return Stack(
                clipBehavior: Clip.hardEdge,
                children: [
                  Listener(
                    onPointerDown: (_) => _selectionAnimation.stop(),
                    child: ClipRect(
                      clipper: _HomeTabViewportClipper(
                        anchored ? widths[1] + gap : 0,
                      ),
                      child: SingleChildScrollView(
                        controller: _scrollController,
                        scrollDirection: Axis.horizontal,
                        physics: const ClampingScrollPhysics(),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            for (var i = 0; i < ids.length; i++) ...[
                              if (i > 0) SizedBox(width: gap),
                              if (hasAnchor && i == 1)
                                SizedBox(width: widths[i])
                              else
                                item(i),
                            ],
                          ],
                        ),
                      ),
                    ),
                  ),
                  if (hasAnchor)
                    Positioned(
                      left: anchored ? 0 : starts[1] - offset,
                      top: 0,
                      bottom: 0,
                      child: item(1),
                    ),
                ],
              );
            },
          ),
        );
      },
    );
  }
}

class _HomeTabViewportClipper extends CustomClipper<Rect> {
  const _HomeTabViewportClipper(this.left);

  final double left;

  @override
  Rect getClip(Size size) => Rect.fromLTRB(left, 0, size.width, size.height);

  @override
  bool shouldReclip(_HomeTabViewportClipper oldClipper) =>
      left != oldClipper.left;
}

class _HomePrimaryTabStripItem extends StatelessWidget {
  const _HomePrimaryTabStripItem({
    super.key,
    required this.channelId,
    required this.label,
    required this.selected,
    required this.slotWidth,
    required this.isDark,
    required this.onTap,
  });

  final String channelId;
  final String label;
  final bool selected;
  final double slotWidth;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final selectedColor = isDark
        ? AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary)
        : AppColors.primaryColor;
    final unselectedColor = isDark
        ? AppColorsFunctional.getColor(isDark, ColorType.tabUnselected)
        : AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
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
    final showUnderline = selected;

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
      textScaler: MediaQuery.textScalerOf(context),
    )..layout();
    return painter.width;
  }
}
