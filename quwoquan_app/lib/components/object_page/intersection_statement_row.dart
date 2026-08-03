import 'package:flutter/cupertino.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/components/object_page/intersection_icon_resolver.dart';
import 'package:quwoquan_app/components/object_page/intersection_lifecycle_badge.dart';
import 'package:quwoquan_app/components/object_page/intersection_object_cover.dart';
import 'package:quwoquan_app/components/object_page/intersection_propagation_view.dart';
import 'package:quwoquan_app/components/object_page/intersection_visual_cluster.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 一条交集结论行的数据模型与单行渲染（统一交互子契约 · A–E 横切复用）。
///
/// 从 `intersection_statement_card.dart` 抽出（R03 体量收敛）：单行模型 / 渲染 / 行动 pill
/// 集中在此，section 卡容器（`IntersectionStatementCard`）只负责标题、展开、footer。
/// 时间线（`my_intersection_inbox_timeline.dart`）与打动（`my_intersection_impact_timeline.dart`）
/// 直接复用 [IntersectionStatementRow]，避免维护第二套单行渲染。
///
/// 该积木为对象页/圈子页/用户页共享展示组件，归属 components/object_page（跨 UI 模块可复用）。

enum IntersectionStatementHighlight { blue, gray }

/// 一条交集结论行（canonical 交互子契约 · A–E 横切复用）。
///
/// [primaryText] 为单通道真相源（云侧 primaryText / briefText），[spans] 为同一句话的
/// 结构化富文本切分（云侧产出，端不拼装，G2）；端侧降级链 spans → primaryText → 隐藏。
/// [visuals] 为对象级样本视觉（sampleVisuals），经 [IntersectionVisualCluster] 渲染。
///
/// 四槽具象化（§21.5.1，全部可选、向后兼容）：
/// - 槽①类型图标：[iconKey]/[sourceRef]/[dimension] 任一可解析时渲染 leading 类型图标；
/// - 槽②句内头像：由 [spans] 内 `visual` 字段驱动（[InteractiveIntersectionText] 内联）；
/// - 槽③对象封面：[objectVisual] 非空时渲染 trailing 封面（替代 chevron）；
/// - 槽④生命周期弱标：[lifecycleState]（+ [strengthDelta]）驱动弱标/红点。
///
/// [propagationPath] 非空时（我打动的人 / 圈子打动的人），主句下方渲染传播视图（替代 subtitle 行）。
class IntersectionStatementItem {
  const IntersectionStatementItem({
    required this.primaryText,
    required this.subtitleText,
    this.highlight = IntersectionStatementHighlight.gray,
    this.onTap,
    this.spans = const <IntersectionTextSpan>[],
    this.visuals = const <IntersectionVisual>[],
    this.onSpanTap,
    this.onVisualTap,
    this.iconKey = '',
    this.sourceRef = '',
    this.dimension = '',
    this.tone = '',
    this.typeIconUrl = '',
    this.objectVisual,
    this.actionHints = const <IntersectionActionHint>[],
    this.onActionHintTap,
    this.lifecycleState = '',
    this.strengthDelta = 0,
    this.dotOnlyForNew = false,
    this.propagationPath,
    this.onPropagationTap,
    this.showAuxiliaryLine = true,
  });

  final String primaryText;
  final String subtitleText;
  final IntersectionStatementHighlight highlight;

  /// 整行点击（名字/数字片段未命中时的兜底进入，优先级低于片段点击）。
  final VoidCallback? onTap;

  /// 同一句话的结构化富文本切分（云侧产出）；为空时整行降级渲染 [primaryText]。
  final List<IntersectionTextSpan> spans;

  /// 对象级样本视觉（最多 3 个 + 计数）。
  final List<IntersectionVisual> visuals;

  /// 命中可点击片段（role=object 进对象页 / role=count 进维度或明细）。
  final void Function(IntersectionTextSpan span)? onSpanTap;

  /// 命中样本视觉（进对象页）。
  final void Function(IntersectionVisual visual)? onVisualTap;

  /// 槽① 类型图标语义键（云侧 iconKey）；缺省时回退 [sourceRef]/[dimension]。
  final String iconKey;

  /// 槽① 类型图标回退用标准 kind（sourceRef）。
  final String sourceRef;

  /// 槽① 类型图标末级回退用维度（5 维闭集）。
  final String dimension;

  /// 槽① 云侧指派的色板 token 名（`IntersectionReason.tone`）；空则按 iconKey 查本地表。
  final String tone;

  /// 槽① 云侧下发的远程图标资源（alpha 蒙版图）；空/失败退回本地 glyph。
  final String typeIconUrl;

  /// 槽③ 对象封面（结论句所指对象的封面/缩略图）；非空时走四槽布局。
  final IntersectionVisual? objectVisual;

  /// 云侧下发的下一步行动建议。
  final List<IntersectionActionHint> actionHints;

  /// 命中行动建议。
  final void Function(IntersectionActionHint hint)? onActionHintTap;

  /// 槽④ 生命周期状态（new/strengthened/stable/weakened/reactivated）。
  final String lifecycleState;

  /// 槽④ strengthened 态增量（叠加 +N）。
  final int strengthDelta;

  /// 紧凑面下 new 仅渲染红点。
  final bool dotOnlyForNew;

  /// 传播视图（我打动的人 / 圈子打动的人）；非空时主句下方渲染。
  final IntersectionPropagationPath? propagationPath;

  /// 命中传播结论句。
  final VoidCallback? onPropagationTap;

  /// 是否显示主句下方辅助层；主页高保行只展示一行主文案时关闭。
  final bool showAuxiliaryLine;

  bool get _hasTypeIcon =>
      iconKey.trim().isNotEmpty ||
      sourceRef.trim().isNotEmpty ||
      dimension.trim().isNotEmpty ||
      typeIconUrl.trim().isNotEmpty;

  bool get _hasObjectCover => objectVisual != null;

  bool get _hasPropagation =>
      propagationPath != null && propagationPath!.summaryText.trim().isNotEmpty;

  /// 句内是否已携带头像（槽②）——此时 leading 视觉簇冗余。
  bool get _hasInlineSpanVisuals => spans.any(
    (s) => s.visual != null && s.visual!.imageUrl.trim().isNotEmpty,
  );

  /// 头像已由槽②/槽③/传播节点承载时，抑制 leading 视觉簇，避免重复。
  bool get _suppressLeadingCluster =>
      _hasPropagation || _hasObjectCover || _hasInlineSpanVisuals;
}

class IntersectionStatementRow extends StatelessWidget {
  const IntersectionStatementRow({super.key, required this.item});

  final IntersectionStatementItem item;

  @override
  Widget build(BuildContext context) {
    final primaryColor = item.highlight == IntersectionStatementHighlight.blue
        ? AppColors.iosAccent(context)
        : AppColors.iosLabel(context);
    final metaSurface = AppColors.iosSecondaryFill(context).withValues(
      alpha: CupertinoTheme.of(context).brightness == Brightness.dark
          ? 0.20
          : 0.28,
    );
    final subtitle = item.subtitleText.trim().isNotEmpty
        ? item.subtitleText.trim()
        : ObjectHomepageText.profileStatementFallbackSubtitle;
    final hasSpans = item.spans.isNotEmpty;
    // 头像已由槽②（句内头像）/槽③（对象封面）/传播节点承载时不再渲染 leading 视觉簇，
    // 避免重复；否则继续渲染 leading 簇服务通用消费者。
    final hasVisuals = item.visuals.isNotEmpty && !item._suppressLeadingCluster;
    final primaryActionHint = item.actionHints
        .where(isDisplayableIntersectionActionHint)
        .fold<IntersectionActionHint?>(
          null,
          (best, hint) =>
              best == null ||
                  (hint.isPrimary && !best.isPrimary) ||
                  hint.priority < best.priority
              ? hint
              : best,
        );
    final Widget primaryLineContent = hasSpans
        ? InteractiveIntersectionText(
            spans: item.spans,
            fallbackText: item.primaryText.trim(),
            onSpanTap: item.onSpanTap,
            baseStyle: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              height: AppSpacing.textLineHeightFootnote,
              fontWeight: AppTypography.regular,
              color: AppColors.iosLabel(context),
              letterSpacing: -0.08,
            ),
            accentFontWeight: AppTypography.regular,
          )
        : Text(
            item.primaryText.trim(),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              height: AppSpacing.textLineHeightFootnote,
              fontWeight: AppTypography.regular,
              color: primaryColor,
              letterSpacing: -0.08,
            ),
          );
    final Widget primaryLine = primaryLineContent;
    // 槽④ 生命周期弱标（new/strengthened/reactivated 才渲染；其余零尺寸）。
    const lifecycleVisibleStates = <String>{
      'new',
      'strengthened',
      'reactivated',
    };
    final lifecycleVisible = lifecycleVisibleStates.contains(
      item.lifecycleState.trim(),
    );
    final lifecycleBadge = IntersectionLifecycleBadge(
      lifecycleState: item.lifecycleState,
      strengthDelta: item.strengthDelta,
      dotOnlyForNew: item.dotOnlyForNew,
    );
    // 主句下方辅助行：传播视图（我打动的人/圈子打动的人）优先，否则维度副句胶囊。
    final Widget auxiliaryLine = item._hasPropagation
        ? IntersectionPropagationView(
            path: item.propagationPath!,
            onSummaryTap: item.onPropagationTap ?? item.onTap,
            onNodeTap: item.onVisualTap,
          )
        : primaryActionHint != null
        ? _ActionHintPill(
            hint: primaryActionHint,
            onTap: item.onActionHintTap == null
                ? null
                : () => item.onActionHintTap!(primaryActionHint),
          )
        : Align(
            alignment: Alignment.centerLeft,
            child: Container(
              constraints: BoxConstraints(
                maxWidth: MediaQuery.sizeOf(context).width * 0.68,
              ),
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerXs,
                vertical: AppSpacing.intraGroupXs / 2,
              ),
              decoration: BoxDecoration(
                color: metaSurface,
                borderRadius: BorderRadius.circular(
                  AppSpacing.smallBorderRadius,
                ),
              ),
              child: Text(
                subtitle,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosCaption2,
                  height: AppSpacing.textLineHeightCaption,
                  color: AppColors.iosTertiaryLabel(context),
                  letterSpacing: -0.02,
                ),
              ),
            ),
          );
    final content = ConstrainedBox(
      constraints: BoxConstraints(minHeight: AppSpacing.minInteractiveSize + 8),
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.containerSm),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: <Widget>[
            // 槽① 类型图标（四槽布局 leading）。
            if (item._hasTypeIcon) ...<Widget>[
              IntersectionTypeIcon(
                iconKey: item.iconKey,
                sourceRef: item.sourceRef,
                dimension: item.dimension,
                tone: item.tone,
                assetUrl: item.typeIconUrl,
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
            ],
            // 旧布局 leading 视觉簇（无类型图标时保留，向后兼容）。
            if (hasVisuals) ...<Widget>[
              IntersectionVisualCluster(
                visuals: item.visuals,
                size: AppSpacing.avatarUserSm,
                onVisualTap: item.onVisualTap,
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
            ],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  primaryLine,
                  if (item.showAuxiliaryLine) ...<Widget>[
                    SizedBox(height: AppSpacing.intraGroupXs),
                    auxiliaryLine,
                  ],
                ],
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            // 槽③ 对象封面（+ 槽④ overlay）替代 chevron；否则弱标独立 + chevron。
            if (item._hasObjectCover)
              IntersectionObjectCover(
                visual: item.objectVisual!,
                lifecycleBadge: lifecycleBadge,
                onTap: item.onTap,
              )
            else if (lifecycleVisible)
              lifecycleBadge,
          ],
        ),
      ),
    );
    if (item.onTap == null) {
      return content;
    }
    return Semantics(
      button: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: item.onTap,
        child: content,
      ),
    );
  }
}

/// 判定 actionHint 是否应渲染成可执行 pill。
///
/// 与 `IntersectionTargetNavigator.openActionHint` 分发口径保持单一真相源：
/// - `assistant`：展示（打开小艺）；
/// - `navigate`：有真实可导航 target 才展示（关注 / 加入 / 进入讨论 / 看共同来源等）。
///   `login` 等 requiredGates 由承接页承接续接（§15），不在本层隐藏，否则已登录用户
///   也会失去行动入口；
/// - `gathering`：结伴同行类有真实承接（进发起群聊页，见
///   `IntersectionTargetNavigator._openGathering`），有对象上下文（target 非空）时
///   展示成可点「发起结伴」pill，兑现「共同想去→约伴」北极星闭环（C0）；target 空则不展示，
///   避免无对象上下文的空发起；
/// - `message`：打招呼 / 私信有真实承接（对方主页的破冰状态机，见
///   `IntersectionTargetNavigator._openMessage`），target 是真实 person 时展示；
///   非 person target 不展示，避免「打招呼」退化成对象下钻；
/// - 未登记 dispatch：fail-closed，不渲染。
bool isDisplayableIntersectionActionHint(IntersectionActionHint hint) {
  if (hint.label.trim().isEmpty) {
    return false;
  }
  switch (hint.dispatch.trim()) {
    case 'assistant':
      return true;
    case 'navigate':
    case 'gathering':
      return hint.target?.objectId.trim().isNotEmpty ?? false;
    case 'message':
      final target = hint.target;
      if (target == null || target.objectId.trim().isEmpty) {
        return false;
      }
      return target.objectKind.trim() == 'person' ||
          target.objectType.trim() == 'user' ||
          target.routeId.trim() == 'userProfile';
    default:
      return false;
  }
}

class _ActionHintPill extends StatelessWidget {
  const _ActionHintPill({required this.hint, this.onTap});

  final IntersectionActionHint hint;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final label = hint.label.trim();
    final child = Container(
      constraints: BoxConstraints(
        maxWidth: MediaQuery.sizeOf(context).width * 0.68,
      ),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerXs,
        vertical: AppSpacing.intraGroupXs / 2,
      ),
      decoration: BoxDecoration(
        color: IntersectionIconResolver.toneColor(context).withValues(
          alpha: CupertinoTheme.of(context).brightness == Brightness.dark
              ? 0.20
              : 0.14,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
      ),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          height: AppSpacing.textLineHeightCaption,
          color: AppColors.iosSecondaryLabel(context),
          letterSpacing: -0.02,
        ),
      ),
    );
    if (onTap == null) {
      return Align(alignment: Alignment.centerLeft, child: child);
    }
    return Align(
      alignment: Alignment.centerLeft,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.square(AppSpacing.minInteractiveSize),
        onPressed: onTap,
        child: child,
      ),
    );
  }
}
