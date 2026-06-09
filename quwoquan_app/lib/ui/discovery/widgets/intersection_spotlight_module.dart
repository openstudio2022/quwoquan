import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/components/object_page/evidence_group.dart';
import 'package:quwoquan_app/components/object_page/intersection_object_kind.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

/// 首页 / 频道交集推荐模块（V4 · 等高关系封面卡）。
///
/// 设计（专业设计师视角：精致 / 美观 / 事实清晰 / 简洁）：
/// - 去掉模块头红色数量徽标，改一行安静轻提示「这些人和地方与你有交集」；
/// - 横滑等高对象卡：上半封面（圈子/实体封面图、用户头像+柔光底纹，推荐类右上角标），
///   下半固定高信息区（对象名 + 最强证据组短句 + 计数 + 一个实例）；
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

  List<IntersectionReason> get _candidates => widget.reasons
      .where((reason) => reason.actionTargetId.trim().isNotEmpty)
      .where((reason) => EvidenceGroup.fromReason(reason).isNotEmpty)
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

    final surface = AppColors.iosProfileSurface(context);

    return Padding(
      key: IntersectionSpotlightModule.moduleKey,
      padding: EdgeInsets.fromLTRB(
        AppSpacing.feedContentHorizontal(context),
        AppSpacing.intraGroupSm,
        AppSpacing.feedContentHorizontal(context),
        AppSpacing.intraGroupSm,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(
            AppSpacing.contentPreviewCornerRadius,
          ),
          border: Border.all(
            color: AppColors.iosSeparator(
              context,
            ).withValues(alpha: widget.isDark ? 0.2 : 0.08),
            width: AppSpacing.hairline,
          ),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            vertical: AppSpacing.containerSm,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerMd,
                ),
                child: _buildHeader(context, canShuffle: canShuffle),
              ),
              SizedBox(height: AppSpacing.intraGroupSm),
              SizedBox(
                height: _RelationCoverCard.cardHeight,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  physics: const BouncingScrollPhysics(),
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerMd,
                  ),
                  itemCount: window.length,
                  separatorBuilder: (_, _) =>
                      SizedBox(width: AppSpacing.intraGroupSm),
                  itemBuilder: (context, i) => _StaggeredEntrance(
                    // batchSeed 变化 → key 变化 → 重新播放 stagger 入场。
                    key: ValueKey<String>(
                      'spotlight-$_batchSeed-${window[i].intersectionId}-$i',
                    ),
                    index: i,
                    child: _RelationCoverCard(
                      reason: window[i],
                      isDark: widget.isDark,
                      onTap: widget.onReasonTap == null
                          ? null
                          : () => widget.onReasonTap!(window[i]),
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

  Widget _buildHeader(BuildContext context, {required bool canShuffle}) {
    final heading = widget.title ?? UITextConstants.homeTodayIntersection;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(
                heading,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosLabel(context),
                ),
              ),
              SizedBox(height: AppSpacing.two),
              Text(
                UITextConstants.intersectionSpotlightSubtitle,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
            ],
          ),
        ),
        if (canShuffle)
          GestureDetector(
            key: IntersectionSpotlightModule.shuffleKey,
            behavior: HitTestBehavior.opaque,
            onTap: _shuffle,
            child: Padding(
              padding: EdgeInsets.only(left: AppSpacing.intraGroupSm),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Icon(
                    CupertinoIcons.arrow_2_circlepath,
                    size: AppSpacing.fourteen,
                    color: AppColors.iosAccent(context),
                  ),
                  SizedBox(width: AppSpacing.two),
                  Text(
                    UITextConstants.intersectionShuffle,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      fontWeight: AppTypography.medium,
                      color: AppColors.iosAccent(context),
                    ),
                  ),
                ],
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

/// 等高关系封面卡：上半封面 + 下半固定高信息区，消除一高一低。
class _RelationCoverCard extends StatelessWidget {
  const _RelationCoverCard({
    required this.reason,
    required this.isDark,
    this.onTap,
  });

  static const double cardWidth = 150.0;
  static const double coverHeight = 92.0;
  static const double infoHeight = 78.0;
  static const double cardHeight = coverHeight + infoHeight;

  final IntersectionReason reason;
  final bool isDark;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final groups = EvidenceGroup.fromReason(reason);
    final primary = groups.isNotEmpty ? groups.first : null;
    final kind = UnifiedObjectKind.fromRelationKind(reason.relationKind);
    final surface = AppColors.iosSystemBackground(context);
    final border = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.1);

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        width: cardWidth,
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(
            AppSpacing.contentPreviewCornerRadius,
          ),
          border: Border.all(color: border, width: AppSpacing.hairline),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            _buildCover(context, kind, primary?.isRecommended ?? false),
            Expanded(child: _buildInfo(context, primary)),
          ],
        ),
      ),
    );
  }

  Widget _buildCover(
    BuildContext context,
    UnifiedObjectKind kind,
    bool recommended,
  ) {
    final url = reason.avatarUrl.trim();
    final fill = AppColors.iosFill(context);
    final Widget base = kind == UnifiedObjectKind.person
        ? _personCover(context, url, fill)
        : _objectCover(url, fill);
    return SizedBox(
      height: _RelationCoverCard.coverHeight,
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          base,
          if (recommended)
            Positioned(
              top: AppSpacing.intraGroupXs,
              right: AppSpacing.intraGroupXs,
              child: _RecommendBadge(isDark: isDark),
            ),
        ],
      ),
    );
  }

  /// 用户卡：头像居中 + 柔光底纹。
  Widget _personCover(BuildContext context, String url, Color fill) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[
            AppColors.iosAccent(context).withValues(alpha: 0.16),
            fill,
          ],
        ),
      ),
      child: Center(
        child: Container(
          width: AppSpacing.avatarUserMd,
          height: AppSpacing.avatarUserMd,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
              color: AppColors.iosSystemBackground(context),
              width: AppSpacing.hairline * 2,
            ),
          ),
          child: ClipOval(
            child: url.isEmpty
                ? ColoredBox(
                    color: fill,
                    child: Icon(
                      CupertinoIcons.person_crop_circle_fill,
                      size: AppSpacing.iconMedium,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  )
                : AppCachedNetworkImage(
                    imageUrl: url,
                    fit: BoxFit.cover,
                    errorWidget: ColoredBox(color: fill),
                  ),
          ),
        ),
      ),
    );
  }

  /// 圈子/实体卡：横向封面图铺满。
  Widget _objectCover(String url, Color fill) {
    if (url.isEmpty) {
      return ColoredBox(color: fill);
    }
    return AppCachedNetworkImage(
      imageUrl: url,
      fit: BoxFit.cover,
      errorWidget: ColoredBox(color: fill),
    );
  }

  Widget _buildInfo(BuildContext context, EvidenceGroup? primary) {
    final name = reason.displayName.trim();
    return Padding(
      padding: EdgeInsets.all(AppSpacing.containerSm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.start,
        mainAxisSize: MainAxisSize.max,
        children: <Widget>[
          Text(
            name.isEmpty ? reason.label.trim() : name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              fontWeight: AppTypography.semiBold,
              color: AppColors.iosLabel(context),
              height: AppTypography.lineHeightTight,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          if (primary != null)
            Flexible(
              child: Align(
                alignment: Alignment.topLeft,
                child: Text(
                  primary.count > 0
                      ? '${primary.label} ${primary.count}'
                      : primary.label,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    fontWeight: AppTypography.medium,
                    color: AppColors.iosLabel(context),
                    height: AppTypography.lineHeightCompact,
                  ),
                ),
              ),
            ),
          if (primary != null && primary.sampleText.isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.two),
            Flexible(
              child: Align(
                alignment: Alignment.topLeft,
                child: Text(
                  primary.sampleText,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: AppColors.iosSecondaryLabel(context),
                    height: AppTypography.lineHeightCompact,
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// 推荐类小角标（概率，不伪装事实）。
class _RecommendBadge extends StatelessWidget {
  const _RecommendBadge({required this.isDark});
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.intraGroupXs,
        vertical: AppSpacing.hairline,
      ),
      decoration: BoxDecoration(
        color: AppColors.black.withValues(alpha: 0.42),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
      ),
      child: Text(
        UITextConstants.intersectionAffinityLabel,
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          fontWeight: AppTypography.medium,
          color: AppColors.white,
        ),
      ),
    );
  }
}
