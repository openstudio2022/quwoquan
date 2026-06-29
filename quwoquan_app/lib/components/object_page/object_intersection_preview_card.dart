import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/components/object_page/object_insight_primitives.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';

/// 「我的交集」预览卡（对象/圈子/用户主页共享）。
///
/// 单一真相源 `objectSharedReasonsProvider`（viewer × 对象），与我的主页同壳同语义 token：
/// 单列预览句（蓝色可点击锚点）+ 弱入口「查看全部」；无真实交集时克制空态，不占位、不造假（G2）。
/// 渲染只读 [IntersectionReason.primaryText]/[IntersectionReason.primarySpans]，端不本地拼句。
class ObjectIntersectionPreviewCard extends ConsumerWidget {
  const ObjectIntersectionPreviewCard({
    super.key,
    required this.objectId,
    required this.objectType,
    required this.title,
    required this.emptyText,
    required this.referralSource,
    this.viewAllTitle,
    this.cardKey,
    this.emptyKey,
    this.topPadding = true,
    this.maxPreview = 3,
  });

  /// 目标对象 id（实体 homepageId / 圈子 circleId / 用户 userId）。
  final String objectId;

  /// 目标对象类型（'homepage' | 'circle' | 'user'）。
  final String objectType;

  /// 模块标题（统一「我的交集」语义 token）。
  final String title;

  /// 无交集事实时的克制空态文案。
  final String emptyText;

  /// 交集片段点击归因来源（实体 entityPage / 圈子 circlePost / 用户 authorProfile）。
  final ReferralSource referralSource;

  /// 「查看全部」明细页标题；缺省回退 [title]。
  final String? viewAllTitle;

  final Key? cardKey;
  final Key? emptyKey;
  final bool topPadding;
  final int maxPreview;

  IntersectionTargetNavigator _navigator(WidgetRef ref) =>
      IntersectionTargetNavigator(
        onTrack: (target, attribution) {
          final id = target.objectId.trim();
          if (id.isEmpty) {
            return;
          }
          ref
              .read(contentBehaviorTrackerProvider)
              .trackClick(
                id,
                referralSource: referralSource,
                intersectionId: attribution.intersectionId,
                intersectionDimension: attribution.dimension,
                intersectionClass: attribution.intersectionClass,
                intersectionSourceRef: attribution.sourceRef,
                intersectionTagRefs: attribution.tagRefs,
                intersectionEvidenceId: attribution.evidenceId,
              );
        },
      );

  void _openList(BuildContext context) {
    context.push(
      AppRoutePaths.objectIntersections(
        objectId: objectId,
        objectType: objectType,
        title: viewAllTitle ?? title,
      ),
    );
  }

  void _onSpanTap(
    BuildContext context,
    WidgetRef ref,
    IntersectionReason reason,
    IntersectionTextSpan span,
  ) {
    if (span.role == 'count') {
      _openList(context);
      return;
    }
    final target = span.target;
    if (target == null) {
      return;
    }
    _navigator(ref).open(
      context,
      target,
      sourceRef: profileIntersectionSourceRef(reason),
      attribution: IntersectionNavAttribution(
        intersectionId: reason.intersectionId,
        dimension: reason.dimension,
        intersectionClass: reason.intersectionClass,
        sourceRef: profileIntersectionSourceRef(reason),
        tagRefs: reason.tagRefs,
        evidenceId: reason.pointSummarySnapshotId,
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final viewerId = ref.watch(currentUserIdProvider);
    final query = ObjectIntersectionQuery(
      objectAId: viewerId,
      objectAType: 'user',
      objectBId: objectId,
      objectBType: objectType,
    );
    if (!query.isResolvable) {
      return _buildCard(
        context: context,
        showAction: false,
        child: ProfileIntersectionEmptyState(key: emptyKey, text: emptyText),
      );
    }
    final async = ref.watch(objectSharedReasonsProvider(query));
    return async.when(
      loading: () => _buildCard(
        context: context,
        showAction: false,
        child: const ProfileIntersectionSkeletonList(),
      ),
      error: (_, _) => _buildCard(
        context: context,
        showAction: false,
        child: ProfileIntersectionEmptyState(key: emptyKey, text: emptyText),
      ),
      data: (reasons) {
        final visible = reasons
            .where((item) => item.primaryText.trim().isNotEmpty)
            .take(maxPreview)
            .toList(growable: false);
        return _buildCard(
          context: context,
          showAction: visible.isNotEmpty,
          child: visible.isEmpty
              ? ProfileIntersectionEmptyState(key: emptyKey, text: emptyText)
              : Column(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    for (var index = 0; index < visible.length; index += 1) ...[
                      if (index > 0) const ProfileInsightDivider(),
                      ProfileIntersectionPreviewRow(
                        reason: visible[index],
                        onTap: () => _openList(context),
                        onSpanTap: (span) =>
                            _onSpanTap(context, ref, visible[index], span),
                      ),
                    ],
                  ],
                ),
        );
      },
    );
  }

  Widget _buildCard({
    required BuildContext context,
    required Widget child,
    required bool showAction,
  }) {
    return ProfileInsightSectionCard(
      key: cardKey,
      title: title,
      actionLabel: showAction ? DiscoveryFeedText.intersectionViewAll : null,
      onAction: showAction ? () => _openList(context) : null,
      topPadding: topPadding,
      child: child,
    );
  }
}
