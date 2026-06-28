import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_card.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_card_skeleton.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/constants/plaza_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';

/// 对象页交集区块（V4 · 商用完整态 · 三主页统一）。
///
/// 设计与产品（设计师 + 产品经理视角）：
/// - 统一 async 三态：loading → 骨架；data → 交集卡或空态行动引导（常驻行动区）；error → 收起（不报错噪声，交集是增强位）。
/// - 旅程无断点（§7.3）：命中 [intersectionHighlightIntentProvider] 且对象匹配时，透传 highlightKind 自动展开高亮，并消费意图（一次性）。
/// - 三主页（用户/圈子/实体）共用本组件，杜绝各页各态。
class ObjectIntersectionSection extends ConsumerWidget {
  const ObjectIntersectionSection({
    super.key,
    required this.query,
    required this.title,
    required this.isDark,
    this.bottomPadding = 0,
    this.onReasonTap,
  });

  static const Key sectionKey = ValueKey<String>('object-intersection-section');

  final ObjectIntersectionQuery query;
  final String title;
  final bool isDark;
  final double bottomPadding;
  final void Function(IntersectionReason reason)? onReasonTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!query.isResolvable) {
      return const SizedBox.shrink();
    }
    final async = ref.watch(objectSharedReasonsProvider(query));

    final Widget body = async.when(
      loading: () => ObjectIntersectionCardSkeleton(isDark: isDark),
      // error 时收起：交集是增强位，不以错误噪声打断对象页主体验。
      error: (_, _) => const SizedBox.shrink(),
      data: (reasons) => _buildCard(context, ref, reasons),
    );
    if (body is SizedBox) return body;
    return Padding(
      key: sectionKey,
      padding: EdgeInsets.only(bottom: bottomPadding),
      child: body,
    );
  }

  Widget _buildCard(
    BuildContext context,
    WidgetRef ref,
    List<IntersectionReason> reasons,
  ) {
    final intent = ref.watch(intersectionHighlightIntentProvider);
    final highlightKind = (intent != null && intent.objectId == query.objectBId)
        ? intent.kind
        : null;
    // 一次性消费：命中后首帧展开高亮，随即清空意图（再进同页不重复强展开）。
    if (highlightKind != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final current = ref.read(intersectionHighlightIntentProvider);
        if (current != null && current.objectId == query.objectBId) {
          ref.read(intersectionHighlightIntentProvider.notifier).clear();
        }
      });
    }
    final card = ObjectIntersectionCard.fromReasons(
      title: title,
      reasons: reasons,
      isDark: isDark,
      inlineExpandCount: ref
          .watch(intersectionDisplayConfigProvider)
          .inlineExpandCount,
      moreLabel: DiscoveryFeedText.intersectionMoreLabel,
      highlightKind: highlightKind,
      onMoreTap: () => context.push(
        AppRoutePaths.objectIntersections(
          objectId: query.objectBId,
          objectType: query.objectBType,
          title: title,
        ),
      ),
      onReasonTap: (reason) {
        // 统一交集证据组点击归因（R20 漏斗 · 三主页一致）：
        // 触发维度 + 路径制 tagRefs 回流推荐管线（B3）。仓库内部失败入队。
        _reportReasonTap(ref, reason);
        final external = onReasonTap;
        if (external != null) {
          // 调用方自定义处理（如实体页开助手）：尊重其语义，不叠加默认下钻，避免双跳转。
          external(reason);
          return;
        }
        // 未传外部处理（用户 / 圈子主页「为什么推荐X」）→ 统一 navigator 下钻到该交集
        // 涉及对象，整行对象级可达（消除「整行仅 track 不可下钻」断点 · §20.7 统一交互子契约）。
        _openReasonTarget(context, reason);
      },
      onSpanTap: (reason, span) {
        _reportReasonTap(ref, reason);
        if (_openSpanTarget(context, reason, span)) {
          return;
        }
        onReasonTap?.call(reason);
      },
      onVisualTap: (reason, visual) {
        _reportReasonTap(ref, reason);
        if (_openVisualTarget(context, reason, visual)) {
          return;
        }
        onReasonTap?.call(reason);
      },
      onActionHintTap: (reason, hint) {
        _reportReasonTap(ref, reason);
        if (_openActionHintTarget(context, reason, hint)) {
          return;
        }
        final external = onReasonTap;
        if (external != null) {
          external(reason);
          return;
        }
        _openReasonTarget(context, reason);
      },
    );
    return card ?? _buildEmptyActionZone(context);
  }

  /// 无交集事实时仍保留行动区占位，引导用户成为第一个留下交集的人（同频原型 · 常驻行动区）。
  Widget _buildEmptyActionZone(BuildContext context) {
    return Container(
      key: const ValueKey<String>('object-intersection-empty-action-zone'),
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
      ),
      child: Row(
        children: <Widget>[
          Icon(
            CupertinoIcons.sparkles,
            size: AppSpacing.iconSmall,
            color: AppColors.iosAccent(context),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(
            child: Text(
              PlazaTextConstants.objectActionZoneEmptyHint,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _openReasonTarget(BuildContext context, IntersectionReason reason) {
    // 统一导航器：reason 归一 target → codegen 路由下钻；
    // actionTargetId 缺省 / 不可路由时 open 返回 false 静默不跳（优雅降级）。
    const IntersectionTargetNavigator().open(
      context,
      IntersectionTargetNavigator.targetForReason(reason),
      sourceRef: reason.source,
      attribution: _attributionFor(reason),
    );
  }

  bool _openSpanTarget(
    BuildContext context,
    IntersectionReason reason,
    IntersectionTextSpan span,
  ) {
    return const IntersectionTargetNavigator().open(
      context,
      span.target,
      sourceRef: reason.source,
      attribution: _attributionFor(reason),
    );
  }

  bool _openVisualTarget(
    BuildContext context,
    IntersectionReason reason,
    IntersectionVisual visual,
  ) {
    return const IntersectionTargetNavigator().open(
      context,
      visual.target,
      sourceRef: reason.source,
      attribution: _attributionFor(reason),
    );
  }

  bool _openActionHintTarget(
    BuildContext context,
    IntersectionReason reason,
    IntersectionActionHint hint,
  ) {
    return const IntersectionTargetNavigator().open(
      context,
      hint.target,
      sourceRef: reason.source,
      attribution: _attributionFor(reason),
    );
  }

  IntersectionNavAttribution _attributionFor(IntersectionReason reason) {
    return IntersectionNavAttribution(
      intersectionId: reason.intersectionId,
      dimension: reason.dimension,
      intersectionClass: reason.intersectionClass,
      sourceRef: reason.source,
      tagRefs: reason.tagRefs,
    );
  }

  void _reportReasonTap(WidgetRef ref, IntersectionReason reason) {
    // 统一通道（N7）：经 ContentBehaviorTracker.trackTagClick 上报，保留 tag_click
    // 语义与推荐 HotPath 1.8 权重（禁降级为 click），补齐统一交互子契约归因字段
    // （intersectionId/sourceRef/class），tagRefs 回流推荐管线（B3）不丢。
    ref
        .read(contentBehaviorTrackerProvider)
        .trackTagClick(
          query.objectBId,
          contentType: query.objectBType,
          authorId: query.objectBType == 'user' ? query.objectBId : null,
          referralSource: referralSourceForObjectType(query.objectBType),
          tags: reason.tagRefs,
          intersectionId: reason.intersectionId,
          intersectionDimension: reason.dimension,
          intersectionSourceRef: reason.source,
          intersectionTagRefs: reason.tagRefs,
          intersectionClass: reason.intersectionClass,
        );
  }
}
