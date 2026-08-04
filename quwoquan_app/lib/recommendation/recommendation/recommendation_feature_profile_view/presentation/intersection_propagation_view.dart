import 'package:flutter/cupertino.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/intersection_icon_resolver.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/intersection_visual_cluster.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';

/// 传播视图件（canonical 交集设计 · 我打动的人 / 圈子打动的人 横切复用）。
///
/// 只读消费云侧 [IntersectionPropagationPath]，把「沿边的下游影响」表达为一行：
/// 路径类型图标（按 `pathKind`）+ 云侧结论句 `summaryText`（如「8人通过你建立了新连接」）
/// + 路径节点视觉簇（`nodes`，最多 3 + N）+ 可选「再传播 N」二跳计数弱标。
///
/// 红线（§21.4）：**只展示可证绝对计数 + 路径节点视觉**；禁百分比 / 漏斗 / 增长率；
/// 结论句唯一来源云侧 `summaryText`，端不拼装（G2）；`reach/conversion` 等运营指标不在 DTO。
class IntersectionPropagationView extends StatelessWidget {
  const IntersectionPropagationView({
    super.key,
    required this.path,
    this.onSummaryTap,
    this.onNodeTap,
  });

  final IntersectionPropagationPath path;

  /// 命中结论句（带 summaryTarget 时进对象/明细）。
  final VoidCallback? onSummaryTap;

  /// 命中路径节点视觉（进对象页）。
  final void Function(IntersectionVisual visual)? onNodeTap;

  /// pathKind → 类型图标语义键（§21.4 三类路径）。
  String get _iconKey {
    switch (path.pathKind.trim()) {
      case 'personToCircle':
        return 'circle';
      case 'personToContentToPerson':
        return 'share';
      case 'personToPerson':
      default:
        return 'connect';
    }
  }

  @override
  Widget build(BuildContext context) {
    final summary = path.summaryText.trim();
    if (summary.isEmpty) {
      return const SizedBox.shrink();
    }
    final hasNodes = path.nodes.isNotEmpty;
    final showSpread = path.secondarySpreadCount > 0;

    final summaryStyle = TextStyle(
      fontSize: AppTypography.iosFootnote,
      height: AppSpacing.textLineHeightFootnote,
      fontWeight: AppTypography.regular,
      color: AppColors.iosSecondaryLabel(context),
      letterSpacing: -0.04,
    );
    final Widget summaryWidget = Text(
      summary,
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
      style: summaryStyle,
    );
    final summaryLine = onSummaryTap == null
        ? summaryWidget
        : GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: onSummaryTap,
            child: summaryWidget,
          );

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: <Widget>[
        IntersectionTypeIcon(iconKey: _iconKey, size: AppSpacing.avatarUserXs),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(child: summaryLine),
        if (showSpread) ...<Widget>[
          SizedBox(width: AppSpacing.intraGroupSm),
          _SecondarySpreadChip(count: path.secondarySpreadCount),
        ],
        if (hasNodes) ...<Widget>[
          SizedBox(width: AppSpacing.intraGroupSm),
          IntersectionVisualCluster(
            visuals: path.nodes,
            size: AppSpacing.avatarUserXs,
            onVisualTap: onNodeTap,
          ),
        ],
      ],
    );
  }
}

/// 二跳扩散计数弱标「再传播 N」（仅可证绝对计数）。
class _SecondarySpreadChip extends StatelessWidget {
  const _SecondarySpreadChip({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerXs,
        vertical: AppSpacing.intraGroupXs / 2,
      ),
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
      ),
      child: Text(
        '${DiscoveryFeedText.intersectionPropagationSecondarySpreadPrefix} $count',
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          fontWeight: AppTypography.medium,
          color: AppColors.iosSecondaryLabel(context),
          letterSpacing: -0.02,
        ),
      ),
    );
  }
}
