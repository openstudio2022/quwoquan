import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/components/object_page/intersection_icon_resolver.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';

/// 内容卡交集理由位 / post 作者信任徽标（一行克制摘要）。
///
/// 单列 / 多列 / 沉浸 viewer / 转发卡 / 内容详情页**同一口径**：
/// - 只读消费云侧 [IntersectionReason] 的最强证据组，端不本地拼装事实（G2）；
/// - 取最强证据组短句 + 计数（如「共同关注 4」），不再用「N 个交集点」空数字；
/// - 无来源 / 无可展示证据 → 不展示（[fromReasons] 返回 null，调用方据此不插入）。
///
/// 渲染归一（N5）：
/// - 槽①类型图标走统一 [IntersectionTypeIcon]（iconKey → sourceRef → dimension 降级链），
///   不再在本组件按 `kind` 自造第二套图标 switch（消除与 [IntersectionIconResolver] 的分叉）；
/// - 结论句走统一 [InteractiveIntersectionText]，云侧 `primarySpans` 非空时对象/计数片段
///   可点击经统一 [IntersectionTargetNavigator] 进对象页 / 维度下钻，埋点保 `tag_click`
///   语义（[ContentBehaviorTracker.trackTagClick]，推荐 HotPath 1.8 权重）。`referralSource`
///   由展示面（用户主页 / 圈子 / 实体）透传，精确归因（R23/N10）。
/// - spans 缺省或 target 不完整时 fail-closed，不回退 reason.actionTargetId 自跳转。
class IntersectionReasonChip extends ConsumerWidget {
  const IntersectionReasonChip({
    super.key,
    required this.text,
    required this.isDark,
    this.reason,
    this.weightTier = '',
    this.referralSource,
    this.contextObjectName = '',
    this.contextObjectTarget,
  });

  static const Key chipKey = ValueKey<String>('intersection-reason-chip');
  static const Key iconKey = ValueKey<String>('intersection-reason-chip-icon');
  static const Key textKey = ValueKey<String>('intersection-reason-chip-text');

  final String text;
  final bool isDark;

  /// 最强证据组（导航 target / spans / 图标语义 / 归因的同一真相源），缺省时纯展示降级。
  final IntersectionReason? reason;
  final String weightTier;
  final String contextObjectName;
  final IntersectionTarget? contextObjectTarget;

  /// 展示面来源渠道（用户主页 / 圈子 / 实体）；span 点击埋点按此精确归因（N10）。
  final ReferralSource? referralSource;

  /// 交集理由位口径真相源：云侧主交集结论句 [IntersectionReason.primaryText] 直出。
  /// 无来源 / 无可展示结论句 → null（不展示）。
  /// 所有承载交集理由位的 surface 必须经此函数解析（四口径一致）。
  static String? primaryText(
    List<IntersectionReason>? reasons, {
    String contextObjectName = '',
    IntersectionTarget? contextObjectTarget,
  }) {
    if (reasons == null || reasons.isEmpty) return null;
    final first = displayReadyIntersectionReason(
      reasons.first,
      contextObjectTarget: contextObjectTarget,
    );
    if (first == null) return null;
    final primary = first.primaryText.trim();
    if (primary.isNotEmpty) return primary;
    return null;
  }

  /// 旅程高亮锚（§7.3）：徽标对应的最强证据组 kind；点击跳作者主页时透传，
  /// 对象页据此自动展开并高亮同一证据组，旅程无断点。
  static String? primaryKind(
    List<IntersectionReason>? reasons, {
    IntersectionTarget? contextObjectTarget,
  }) {
    if (reasons == null || reasons.isEmpty) return null;
    final first = displayReadyIntersectionReason(
      reasons.first,
      contextObjectTarget: contextObjectTarget,
    );
    if (first == null) return null;
    final kind = resolvedIntersectionReasonKind(first).trim();
    return kind.isEmpty ? null : kind;
  }

  /// 便捷构造：无来源返回 null，调用方据此「不展示」，保证四口径一致。
  static Widget? fromReasons(
    List<IntersectionReason>? reasons, {
    required bool isDark,
    ReferralSource? referralSource,
    Key? key,
    String contextObjectName = '',
    IntersectionTarget? contextObjectTarget,
  }) {
    final text = primaryText(
      reasons,
      contextObjectName: contextObjectName,
      contextObjectTarget: contextObjectTarget,
    );
    if (text == null) return null;
    final first = reasons?.isNotEmpty == true
        ? displayReadyIntersectionReason(
            reasons!.first,
            contextObjectTarget: contextObjectTarget,
          )
        : null;
    if (first == null) return null;
    return IntersectionReasonChip(
      key: key,
      text: text,
      isDark: isDark,
      reason: first,
      weightTier: first.weightTier,
      referralSource: referralSource,
      contextObjectName: contextObjectName,
      contextObjectTarget: contextObjectTarget,
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final displayReason = reason == null
        ? null
        : displayReadyIntersectionReason(
            reason!,
            contextObjectTarget: contextObjectTarget,
          );
    if (displayReason == null) {
      return const SizedBox.shrink();
    }
    final resolvedTier = _resolveWeightTier(displayReason.weightTier);
    final isLight = resolvedTier == _IntersectionReasonWeightTier.light;
    final accent = AppColors.iosAccent(context);
    final foreground = isLight ? AppColors.iosSecondaryLabel(context) : accent;
    final spans = displayReason.primarySpans;
    final displayText = displayReason.primaryText;
    final fontWeight = isLight ? AppTypography.regular : AppTypography.medium;
    return Row(
      key: chipKey,
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: <Widget>[
        IntersectionTypeIcon(
          key: iconKey,
          iconKey: displayReason.iconKey,
          sourceRef: displayReason.source,
          dimension: displayReason.dimension,
          size: AppSpacing.iconSmall,
        ),
        SizedBox(width: AppSpacing.intraGroupXs),
        Flexible(
          child: InteractiveIntersectionText(
            key: textKey,
            spans: spans,
            fallbackText: displayText,
            maxLines: 1,
            accentFontWeight: fontWeight,
            baseStyle: TextStyle(
              fontSize: AppTypography.feedBodyResponsive(context),
              fontWeight: fontWeight,
              color: foreground,
              letterSpacing: 0,
            ),
            onSpanTap: (span) => _onSpanTap(context, ref, span),
          ),
        ),
      ],
    );
  }

  /// 结论句对象/计数片段点击：经统一导航器进对象页 / 维度下钻，保 `tag_click` 语义归因。
  void _onSpanTap(
    BuildContext context,
    WidgetRef ref,
    IntersectionTextSpan span,
  ) {
    final current = reason == null
        ? null
        : displayReadyIntersectionReason(
            reason!,
            contextObjectTarget: contextObjectTarget,
          );
    if (current == null) {
      return;
    }
    final spanTarget = span.target;
    if (spanTarget == null || spanTarget.objectId.trim().isEmpty) {
      return;
    }
    final target = spanTarget;
    final attribution = IntersectionNavAttribution(
      intersectionId: current.intersectionId,
      dimension: current.dimension,
      intersectionClass: current.intersectionClass,
      sourceRef: current.source,
      tagRefs: current.tagRefs,
      evidenceId: current.pointSummarySnapshotId,
    );
    final navigator = IntersectionTargetNavigator(
      onTrack: (navTarget, attr) => ref
          .read(contentBehaviorTrackerProvider)
          .trackTagClick(
            navTarget.objectId,
            referralSource: referralSource,
            tags: attr.tagRefs,
            intersectionId: attr.intersectionId,
            intersectionDimension: attr.dimension,
            intersectionSourceRef: attr.sourceRef,
            intersectionTagRefs: attr.tagRefs,
            intersectionClass: attr.intersectionClass,
            intersectionEvidenceId: attr.evidenceId,
          ),
    );
    navigator.open(context, target, attribution: attribution);
  }

  static _IntersectionReasonWeightTier _resolveWeightTier(String raw) {
    switch (raw.trim().toLowerCase()) {
      case 'light':
        return _IntersectionReasonWeightTier.light;
      case 'heavy':
      case '':
      default:
        return _IntersectionReasonWeightTier.heavy;
    }
  }
}

enum _IntersectionReasonWeightTier { heavy, light }
