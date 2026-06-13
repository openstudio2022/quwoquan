import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/components/object_page/intersection_object_kind.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

/// 首页 / 频道交集推荐模块（V6 · 高保横滑头像卡）。
///
/// 设计（专业设计师视角：精致 / 美观 / 事实清晰 / 简洁）：
/// - iPhone 宽度展示 3~3.5 张卡，留出半张暗示横滑；
/// - 头像/对象图标是视觉主角，头像下仅三行：名称、主交集、副交集；
/// - 文案、计数、实例来自云侧证据组，端不本地拼装事实（G2）。
class IntersectionSpotlightModule extends StatefulWidget {
  const IntersectionSpotlightModule({
    super.key,
    required this.reasons,
    required this.isDark,
    this.title,
    this.onReasonTap,
    this.windowSize = 6,
  });

  static const Key moduleKey = ValueKey<String>('home-intersection-spotlight');
  static const Key shuffleKey = ValueKey<String>(
    'home-intersection-spotlight-shuffle',
  );
  static const Key primaryTextKey = ValueKey<String>(
    'home-intersection-spotlight-primary-text',
  );
  static const Key secondaryTextKey = ValueKey<String>(
    'home-intersection-spotlight-secondary-text',
  );

  /// 体验规格：单屏可见 3~3.5 张卡（半露暗示横滑）。
  static const double visibleCardsPerViewport = 3.35;

  final List<IntersectionReason> reasons;
  final bool isDark;
  final String? title;
  final void Function(IntersectionReason reason)? onReasonTap;

  /// 单屏展示窗大小；reasons 为云侧候选窗（maxCandidateWindow），端内轮转。
  final int windowSize;

  @override
  State<IntersectionSpotlightModule> createState() =>
      _IntersectionSpotlightModuleState();
}

class _IntersectionSpotlightModuleState
    extends State<IntersectionSpotlightModule> {
  int _offset = 0;
  // 用于「换一批」时强制重建卡列表，触发 stagger 入场。
  int _batchSeed = 0;

  // 主交集结论句由云侧产出（G2 端不本地拼装）；缺 primaryText 的对象不进展示窗。
  List<IntersectionReason> get _candidates => widget.reasons
      .where((reason) => reason.actionTargetId.trim().isNotEmpty)
      .where((reason) => reason.primaryText.trim().isNotEmpty)
      .toList(growable: false);

  void _shuffle() {
    final candidates = _candidates;
    if (candidates.length <= widget.windowSize) return;
    setState(() {
      _offset = (_offset + widget.windowSize) % candidates.length;
      _batchSeed++;
    });
  }

  @override
  Widget build(BuildContext context) {
    final candidates = _candidates;
    if (candidates.isEmpty) return const SizedBox.shrink();

    // 候选窗内轮转出本屏展示窗（环形取 windowSize 条）。
    final window = <IntersectionReason>[];
    final take = candidates.length < widget.windowSize
        ? candidates.length
        : widget.windowSize;
    for (var i = 0; i < take; i++) {
      window.add(candidates[(_offset + i) % candidates.length]);
    }
    final canShuffle = candidates.length > widget.windowSize;

    return Padding(
      key: IntersectionSpotlightModule.moduleKey,
      padding: EdgeInsets.fromLTRB(
        AppSpacing.feedContentHorizontal(context),
        AppSpacing.intraGroupSm,
        AppSpacing.feedContentHorizontal(context),
        AppSpacing.intraGroupSm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          _buildHeader(context, canShuffle: canShuffle),
          SizedBox(height: AppSpacing.intraGroupSm),
          SizedBox(
            height: _RelationCoverCard.cardHeight,
            child: LayoutBuilder(
              builder: (context, constraints) {
                final gap = AppSpacing.containerSm;
                final visibleCards =
                    IntersectionSpotlightModule.visibleCardsPerViewport;
                final cardWidth =
                    (constraints.maxWidth - gap * visibleCards.floor()) /
                    visibleCards;
                return ListView.separated(
                  scrollDirection: Axis.horizontal,
                  physics: const BouncingScrollPhysics(),
                  padding: EdgeInsets.zero,
                  itemCount: window.length,
                  separatorBuilder: (_, _) => SizedBox(width: gap),
                  itemBuilder: (context, i) => _StaggeredEntrance(
                    key: ValueKey<String>(
                      'spotlight-$_batchSeed-${window[i].intersectionId}-$i',
                    ),
                    index: i,
                    child: _RelationCoverCard(
                      reason: window[i],
                      isDark: widget.isDark,
                      width: cardWidth,
                      onTap: widget.onReasonTap == null
                          ? null
                          : () => widget.onReasonTap!(window[i]),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHeader(BuildContext context, {required bool canShuffle}) {
    final heading = widget.title ?? UITextConstants.homeTodayIntersection;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: <Widget>[
        Expanded(
          child: Text(
            heading,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              fontWeight: AppTypography.medium,
              color: AppColors.iosLabel(context),
              letterSpacing: -0.08,
            ),
          ),
        ),
        if (canShuffle)
          GestureDetector(
            key: IntersectionSpotlightModule.shuffleKey,
            behavior: HitTestBehavior.opaque,
            onTap: _shuffle,
            child: Padding(
              padding: EdgeInsets.only(left: AppSpacing.intraGroupSm),
              child: Text(
                UITextConstants.intersectionShuffle,
                style: TextStyle(
                  fontSize: AppTypography.iosCaption1,
                  color: AppColors.iosSecondaryLabel(context),
                  letterSpacing: -0.04,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// §7.5 stagger 入场：按 index 递延 fade + 轻微上移，强调「保鲜/换一批」。
class _StaggeredEntrance extends StatefulWidget {
  const _StaggeredEntrance({
    super.key,
    required this.index,
    required this.child,
  });

  final int index;
  final Widget child;

  @override
  State<_StaggeredEntrance> createState() => _StaggeredEntranceState();
}

class _StaggeredEntranceState extends State<_StaggeredEntrance>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 320),
  );
  late final Animation<double> _anim = CurvedAnimation(
    parent: _controller,
    curve: Curves.easeOutCubic,
  );
  Timer? _delayTimer;

  @override
  void initState() {
    super.initState();
    final delayMs = 40 * widget.index;
    if (delayMs == 0) {
      _controller.forward();
    } else {
      _delayTimer = Timer(Duration(milliseconds: delayMs), () {
        if (mounted) _controller.forward();
      });
    }
  }

  @override
  void dispose() {
    _delayTimer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _anim,
      child: AnimatedBuilder(
        animation: _anim,
        builder: (context, child) => Transform.translate(
          offset: Offset(0, (1 - _anim.value) * AppSpacing.intraGroupSm),
          child: child,
        ),
        child: widget.child,
      ),
    );
  }
}

/// 高保横滑头像卡：头像/真实对象图标 + 三行文字，主交集蓝、副交集灰。
class _RelationCoverCard extends StatelessWidget {
  const _RelationCoverCard({
    required this.reason,
    required this.isDark,
    required this.width,
    this.onTap,
  });

  static const double cardHeight = 142.0;

  final IntersectionReason reason;
  final bool isDark;
  final double width;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final kind = UnifiedObjectKind.resolve(
      objectKind: reason.objectKind,
      relationKind: reason.relationKind,
    );
    final surface = AppColors.feedCardSurface(context);
    final border = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.18 : 0.08);

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        width: width,
        height: cardHeight,
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
          border: Border.all(color: border, width: AppSpacing.hairline),
          boxShadow: isDark
              ? null
              : <BoxShadow>[
                  BoxShadow(
                    color: AppColors.black.withValues(alpha: 0.035),
                    blurRadius: AppSpacing.xs,
                    offset: const Offset(0, AppSpacing.two),
                  ),
                ],
        ),
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerSm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: <Widget>[
              _buildAvatarMark(
                context,
                kind,
                reason.intersectionClass == 'affinity',
              ),
              SizedBox(height: AppSpacing.containerSm),
              Expanded(child: Center(child: _buildInfo(context))),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAvatarMark(
    BuildContext context,
    UnifiedObjectKind kind,
    bool recommended,
  ) {
    final url = reason.avatarUrl.trim();
    return SizedBox(
      width: AppSpacing.avatarUserLg,
      height: AppSpacing.avatarUserLg,
      child: Stack(
        clipBehavior: Clip.none,
        children: <Widget>[
          Positioned.fill(child: _avatarSurface(context, kind, url)),
          Positioned(
            right: -AppSpacing.two,
            bottom: -AppSpacing.two,
            child: _ObjectTypeBadge(kind: kind),
          ),
          if (recommended)
            Positioned(
              top: -AppSpacing.two,
              right: -AppSpacing.two,
              child: _FreshDot(isDark: isDark),
            ),
        ],
      ),
    );
  }

  Widget _avatarSurface(
    BuildContext context,
    UnifiedObjectKind kind,
    String url,
  ) {
    final fill = AppColors.iosSecondaryFill(context);
    final borderRadius = BorderRadius.circular(
      kind == UnifiedObjectKind.person
          ? AppSpacing.radiusTwentyEight
          : AppSpacing.radiusTen,
    );
    final fallbackIcon = _fallbackIcon(kind);
    return ClipRRect(
      borderRadius: borderRadius,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: fill,
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: <Color>[
              AppColors.iosAccent(context).withValues(alpha: 0.16),
              fill,
            ],
          ),
          border: Border.all(
            color: AppColors.iosSystemBackground(context),
            width: AppSpacing.one,
          ),
        ),
        child: url.isEmpty
            ? Center(
                child: Icon(
                  fallbackIcon,
                  size: AppSpacing.iconLarge,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              )
            : AppCachedNetworkImage(
                imageUrl: url,
                fit: BoxFit.cover,
                errorWidget: ColoredBox(
                  color: fill,
                  child: Center(
                    child: Icon(
                      fallbackIcon,
                      size: AppSpacing.iconLarge,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  ),
                ),
              ),
      ),
    );
  }

  IconData _fallbackIcon(UnifiedObjectKind kind) {
    switch (kind) {
      case UnifiedObjectKind.person:
        return CupertinoIcons.person_crop_circle_fill;
      case UnifiedObjectKind.circle:
        return CupertinoIcons.person_2_fill;
      case UnifiedObjectKind.school:
        return CupertinoIcons.building_2_fill;
      case UnifiedObjectKind.place:
        return CupertinoIcons.location_solid;
      case UnifiedObjectKind.enterprise:
        return CupertinoIcons.briefcase_fill;
    }
  }

  Widget _buildInfo(BuildContext context) {
    final name = reason.displayName.trim();
    // 主交集结论句（蓝）与副交集辅助说明（灰）均为云侧产出，端只读直出（G2）。
    final primaryText = reason.primaryText.trim();
    final secondaryText = reason.secondaryText.trim();
    return FittedBox(
      fit: BoxFit.scaleDown,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: width - (AppSpacing.containerSm * 2),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              name.isEmpty ? reason.label.trim() : name,
              maxLines: 1,
              textAlign: TextAlign.center,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
                height: AppTypography.lineHeightTight,
              ),
            ),
            if (primaryText.isNotEmpty)
              Padding(
                padding: EdgeInsets.only(top: AppSpacing.intraGroupXs),
                child: Text(
                  key: IntersectionSpotlightModule.primaryTextKey,
                  primaryText,
                  maxLines: 1,
                  textAlign: TextAlign.center,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: AppColors.iosAccent(context),
                    height: AppTypography.lineHeightTight,
                    letterSpacing: -0.04,
                  ),
                ),
              ),
            if (secondaryText.isNotEmpty)
              Padding(
                padding: EdgeInsets.only(top: AppSpacing.intraGroupXs),
                child: Text(
                  key: IntersectionSpotlightModule.secondaryTextKey,
                  secondaryText,
                  maxLines: 1,
                  textAlign: TextAlign.center,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption2,
                    color: AppColors.iosSecondaryLabel(context),
                    height: AppTypography.lineHeightTight,
                    letterSpacing: -0.02,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// 统一品牌蓝对象角标：文字「人/圈/校/地/企」表达对象类型（规格：蓝=连接，不按类型分色）。
class _ObjectTypeBadge extends StatelessWidget {
  const _ObjectTypeBadge({required this.kind});

  final UnifiedObjectKind kind;

  @override
  Widget build(BuildContext context) {
    final label = UITextConstants.intersectionObjectKindBadgeLabel(kind.name);
    if (label.isEmpty) return const SizedBox.shrink();
    return Semantics(
      container: true,
      label: label,
      child: Container(
        width: AppSpacing.buttonHeightXs,
        height: AppSpacing.buttonHeightXs,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: AppColors.primaryColor,
          shape: BoxShape.circle,
          border: Border.all(
            color: AppColors.iosSystemBackground(context),
            width: AppSpacing.one,
          ),
        ),
        child: Icon(
          _badgeIcon,
          size: AppSpacing.fourteen,
          color: AppColors.white,
        ),
      ),
    );
  }

  IconData get _badgeIcon {
    switch (kind) {
      case UnifiedObjectKind.person:
        return CupertinoIcons.person_fill;
      case UnifiedObjectKind.circle:
        return CupertinoIcons.person_2_fill;
      case UnifiedObjectKind.school:
        return CupertinoIcons.building_2_fill;
      case UnifiedObjectKind.place:
        return CupertinoIcons.location_solid;
      case UnifiedObjectKind.enterprise:
        return CupertinoIcons.briefcase_fill;
    }
  }
}

/// 推荐/新鲜小蓝点：只表达新鲜状态，不额外制造事实文案。
class _FreshDot extends StatelessWidget {
  const _FreshDot({required this.isDark});
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: isDark ? AppColors.iosAccentDark : AppColors.primaryColor,
        shape: BoxShape.circle,
        border: Border.all(
          color: AppColors.iosSystemBackground(context),
          width: AppSpacing.one,
        ),
      ),
      child: const SizedBox(width: AppSpacing.sm, height: AppSpacing.sm),
    );
  }
}
