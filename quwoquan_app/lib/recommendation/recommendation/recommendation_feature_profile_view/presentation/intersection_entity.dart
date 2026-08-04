import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

/// 交集统一原子 [IntersectionEntity] 的展示密度。
///
/// - [spotlight]：首页/频道横滑卡，强调「对象 + 一条云侧证据」。
/// - [objectSummary]：对象页摘要行，强调「我和这个对象为什么有关」。
/// - [inboxList]：我的交集列表行，强调「新增/推荐状态 + 可回看」。
enum IntersectionEntityDensity { spotlight, objectSummary, inboxList }

/// 交集统一原子：人/地点事物/圈子/组织共用同一视觉语言。
///
/// 只读消费 [IntersectionReason]：真实头像（[IntersectionReason.avatarUrl]）+
/// 名字（[IntersectionReason.displayName]）+ 云侧证据短句（[IntersectionReason.primaryText]
/// 或 [IntersectionReason.connectionSummary]）+ 维度短标签；概率（affinity）交集额外标注「推荐」，
/// 不伪装事实、不显示大行动按钮。
/// 导航由父层经 [onTap] 提供，本原子不直接路由 / 埋点。
class IntersectionEntity extends StatelessWidget {
  const IntersectionEntity({
    super.key,
    required this.reason,
    required this.isDark,
    this.density = IntersectionEntityDensity.inboxList,
    this.onTap,
  });

  final IntersectionReason reason;
  final bool isDark;
  final IntersectionEntityDensity density;
  final VoidCallback? onTap;

  bool get _isAffinity => reason.intersectionClass == 'affinity';

  String get _name {
    final name = reason.displayName.trim();
    if (name.isNotEmpty) return name;
    // 兜底：对象页事实理由可能仅带 primaryText（结论句），用作名字占位。
    return reason.primaryText.trim();
  }

  String get _evidenceText {
    final text = reason.primaryText.trim();
    if (text.isNotEmpty && text != _name) return text;
    final summary = reason.connectionSummary.trim();
    if (summary.isNotEmpty && summary != _name) return summary;
    return '';
  }

  String get _classLabel {
    if (_isAffinity) {
      final pointLabel = reason.pointClassLabel.trim();
      if (pointLabel.isNotEmpty) return pointLabel;
      final confidence = reason.confidenceLabel.trim();
      return confidence.isNotEmpty
          ? confidence
          : DiscoveryFeedText.intersectionAffinityLabel;
    }
    return '';
  }

  String get _freshLabel {
    final fresh = DateTime.tryParse(reason.freshAt);
    if (fresh == null) return '';
    final age = DateTime.now().toUtc().difference(fresh.toUtc());
    if (age.isNegative || age.inHours < 24) return '新';
    if (age.inDays < 7) return '本周';
    return '';
  }

  /// §21.3 生命周期弱标（真相源 = 服务端 lifecycleState）：new/strengthened/reactivated
  /// 才出标；stable/weakened/未知返回空。缺省时由 [_freshLabel] 时间派生回退（向后兼容）。
  String get _lifecycleLabel {
    const visible = <String>{'new', 'strengthened', 'reactivated'};
    final state = reason.lifecycleState.trim();
    if (!visible.contains(state)) return '';
    return DiscoveryFeedText.intersectionLifecycleLabel(state);
  }

  @override
  Widget build(BuildContext context) {
    switch (density) {
      case IntersectionEntityDensity.spotlight:
        return _buildSpotlight(context);
      case IntersectionEntityDensity.objectSummary:
        return _buildObjectSummary(context);
      case IntersectionEntityDensity.inboxList:
        return _buildInboxList(context);
    }
  }

  Widget _buildInboxList(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupSm),
        child: Row(
          children: <Widget>[
            _Avatar(
              avatarUrl: reason.avatarUrl,
              objectKind: reason.objectKind,
              size: AppSpacing.avatarUserMd,
              isDark: isDark,
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  _TitleLine(name: _name, trailing: _statusLabels()),
                  if (_evidenceText.isNotEmpty) ...<Widget>[
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      _evidenceText,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                  ],
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Wrap(
                    spacing: AppSpacing.intraGroupXs,
                    runSpacing: AppSpacing.intraGroupXs,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: _chips(context),
                  ),
                ],
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconSmall,
              color: AppColors.iosTertiaryLabel(context),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSpotlight(BuildContext context) {
    final surface = AppColors.iosProfileSurface(context);
    final border = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.24 : 0.1);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        width: AppSpacing.twoHundredTwenty,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupSm,
        ),
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
          border: Border.all(color: border, width: AppSpacing.hairline),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Row(
              children: <Widget>[
                _Avatar(
                  avatarUrl: reason.avatarUrl,
                  objectKind: reason.objectKind,
                  size: AppSpacing.avatarUserXs,
                  isDark: isDark,
                ),
                SizedBox(width: AppSpacing.intraGroupSm),
                Expanded(
                  child: Text(
                    _name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      fontWeight: AppTypography.semiBold,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                ),
              ],
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            if (_evidenceText.isNotEmpty) ...<Widget>[
              Text(
                _evidenceText,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosCaption1,
                  height: AppSpacing.textLineHeightCompact,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupSm),
            ],
            Wrap(
              spacing: AppSpacing.intraGroupXs,
              runSpacing: AppSpacing.intraGroupXs,
              children: _chips(context),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildObjectSummary(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupSm),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            _Avatar(
              avatarUrl: reason.avatarUrl,
              objectKind: reason.objectKind,
              size: AppSpacing.avatarUserSm,
              isDark: isDark,
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  _TitleLine(name: _name, trailing: _statusLabels()),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    _evidenceText.isNotEmpty ? _evidenceText : _name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosCaption1,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Wrap(
                    spacing: AppSpacing.intraGroupXs,
                    runSpacing: AppSpacing.intraGroupXs,
                    children: _chips(context),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _chips(BuildContext context) {
    final chips = <Widget>[
      if (_dimensionLabel.isNotEmpty)
        _Chip(label: _dimensionLabel, tone: _ChipTone.dimension),
    ];
    final pointChip = _pointCountChipLabel();
    if (pointChip.isNotEmpty) {
      chips.add(_Chip(label: pointChip, tone: _ChipTone.quiet));
      if (_isAffinity) {
        chips.add(_Chip(label: _classLabel, tone: _ChipTone.affinity));
      }
      return chips;
    }
    if (_isAffinity) {
      chips.add(_Chip(label: _classLabel, tone: _ChipTone.affinity));
    }
    return chips;
  }

  /// 维度弱标只认云侧 `dimensionPointSummary[].label`（注册表 `dimensionLabels` 渲染）。
  /// 端侧不再持第二份维度文案表；云侧未下发时不渲染该 chip。
  String get _dimensionLabel {
    final dimension = reason.dimension.trim();
    if (dimension.isEmpty) return '';
    for (final tally in reason.dimensionPointSummary) {
      if (tally.dimension.trim() == dimension) {
        return tally.label.trim();
      }
    }
    return '';
  }

  String _pointCountChipLabel() {
    final total = reason.totalPointCount;
    if (total <= 0) return '';
    if (reason.recommendedPointCount > 0 && reason.factPointCount == 0) {
      return DiscoveryFeedText.intersectionRecommendedPointCountChip(total);
    }
    return DiscoveryFeedText.intersectionPointCountChip(total);
  }

  List<String> _statusLabels() {
    final labels = <String>[];
    // 生命周期弱标优先（服务端真相源）；缺省回退时间派生 freshness。
    final lifecycle = _lifecycleLabel;
    if (lifecycle.isNotEmpty) {
      labels.add(lifecycle);
    } else {
      final fresh = _freshLabel;
      if (fresh.isNotEmpty) labels.add(fresh);
    }
    if (_isAffinity) labels.add(_classLabel);
    return labels;
  }
}

class _TitleLine extends StatelessWidget {
  const _TitleLine({required this.name, required this.trailing});

  final String name;
  final List<String> trailing;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        Expanded(
          child: Text(
            name,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              fontWeight: AppTypography.semiBold,
              color: AppColors.iosLabel(context),
            ),
          ),
        ),
        for (final label in trailing.take(2)) ...<Widget>[
          SizedBox(width: AppSpacing.intraGroupXs),
          _StatusBadge(label: label),
        ],
      ],
    );
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final isNew = label == '新';
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.intraGroupXs,
        vertical: AppSpacing.two,
      ),
      decoration: BoxDecoration(
        color: isNew
            ? AppColors.error.withValues(alpha: 0.12)
            : AppColors.iosSeparator(context).withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          fontWeight: AppTypography.medium,
          color: isNew ? AppColors.error : AppColors.iosSecondaryLabel(context),
        ),
      ),
    );
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({
    required this.avatarUrl,
    required this.objectKind,
    required this.size,
    required this.isDark,
  });

  final String avatarUrl;
  final String objectKind;
  final double size;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    // objectKind 一等字段为真相源（codegen UnifiedObjectKind）。未知 kind 不得回落成
    // person：圆形头像 + 人像图标会把一个地点/器材说成是个人。未知一律走中性对象形状。
    final kind = UnifiedObjectKind.fromWire(objectKind);
    final accent = AppColors.iosAccent(context);
    final radius = kind == UnifiedObjectKind.person
        ? BorderRadius.circular(size)
        : BorderRadius.circular(AppSpacing.radiusTen);
    final url = avatarUrl.trim();
    final fallback = Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: accent.withValues(alpha: isDark ? 0.22 : 0.1),
        borderRadius: radius,
      ),
      child: Icon(_iconFor(kind), size: AppSpacing.eighteen, color: accent),
    );
    if (url.isEmpty) return fallback;
    return ClipRRect(
      borderRadius: radius,
      child: AppCachedNetworkImage(
        imageUrl: url,
        width: size,
        height: size,
        fit: BoxFit.cover,
        errorWidget: fallback,
      ),
    );
  }

  IconData _iconFor(UnifiedObjectKind? kind) {
    switch (kind) {
      // 云侧登记了新 objectKind 而端侧尚未 codegen：给中性对象图标，不冒充任何已知类型。
      case null:
        return CupertinoIcons.square_stack_3d_up;
      case UnifiedObjectKind.person:
        return CupertinoIcons.person_crop_circle_fill;
      case UnifiedObjectKind.place:
        return CupertinoIcons.location_solid;
      case UnifiedObjectKind.circle:
        return CupertinoIcons.person_3_fill;
      case UnifiedObjectKind.school:
        return CupertinoIcons.book_fill;
      case UnifiedObjectKind.enterprise:
        return CupertinoIcons.building_2_fill;
      // §22.2 旅行摄影 objectKind（结构就位，本轮无数据流入；保持图标语义可辨识）。
      case UnifiedObjectKind.route:
        return CupertinoIcons.map_pin_ellipse;
      case UnifiedObjectKind.photoSpot:
        return CupertinoIcons.camera_fill;
      case UnifiedObjectKind.gear:
        return CupertinoIcons.bag_fill;
      case UnifiedObjectKind.content:
        return CupertinoIcons.doc_text_fill;
      // trip / meetup 已由领域模型收敛为唯一 Gathering 对象。
      case UnifiedObjectKind.gathering:
        return CupertinoIcons.person_2_fill;
    }
  }
}

enum _ChipTone { dimension, quiet, affinity }

class _Chip extends StatelessWidget {
  const _Chip({required this.label, required this.tone});

  final String label;
  final _ChipTone tone;

  @override
  Widget build(BuildContext context) {
    final Color fg;
    final Color bg;
    switch (tone) {
      case _ChipTone.dimension:
        fg = AppColors.iosAccent(context);
        bg = AppColors.iosAccent(context).withValues(alpha: 0.1);
      case _ChipTone.affinity:
        fg = AppColors.iosSecondaryLabel(context);
        bg = AppColors.iosSeparator(context).withValues(alpha: 0.16);
      case _ChipTone.quiet:
        fg = AppColors.iosSecondaryLabel(context);
        bg = AppColors.iosSystemBackground(context).withValues(alpha: 0.0);
    }
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.intraGroupSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.iosCaption1,
          fontWeight: AppTypography.medium,
          color: fg,
        ),
      ),
    );
  }
}
