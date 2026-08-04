import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/intersection_entity.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/intersection_target_navigator.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/object_insight_primitives.dart'
    show profileIntersectionSourceRef;
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/user/providers/my_intersection_inbox_provider.dart';

/// 首页/频道交集横滑模块（`intersectionModulePolicy == 'spotlightSegment'` 时出现）。
///
/// 数据只来自「我的交集」事实读面（`listMyIntersections(filter: 'fact')`，与收件箱
/// 同一个 provider 与同一份短时缓存），因此首页与收件箱不会出现两套交集事实：
/// 端不再合成句子、不补默认头像、也不把概率交集混进来。
///
/// 空态与失败态一律不占版式（返回零高度）：交集是「有就说、没有就不说」的事实模块，
/// 用占位卡撑住模块会让用户以为自己有交集（§24.10 诚实红线）。
class HomeIntersectionSpotlightRail extends ConsumerStatefulWidget {
  const HomeIntersectionSpotlightRail({
    super.key,
    required this.isDark,
    required this.channelId,
  });

  final bool isDark;
  final String channelId;

  /// 频道标题：真相源是频道 id，不做拼接式文案。
  static String titleFor(String channelId) {
    switch (channelId.trim()) {
      case 'travel':
        return DiscoveryFeedText.intersectionTravelSpotlightTitle;
      case 'campus':
        return DiscoveryFeedText.intersectionCampusSpotlightTitle;
      default:
        return DiscoveryFeedText.intersectionRecommendSpotlightTitle;
    }
  }

  /// 进 spotlight 的事实交集：必须有云侧句子与可跳转对象，否则不展示。
  /// 句子由云侧 hydrate，端只做「可展示性」判断，不补句、不猜对象。
  static List<IntersectionReason> displayable(
    List<IntersectionReason> reasons, {
    int limit = 8,
  }) {
    final out = <IntersectionReason>[];
    for (final reason in reasons) {
      if (reason.intersectionClass == 'affinity') continue;
      if (reason.primaryText.trim().isEmpty &&
          reason.connectionSummary.trim().isEmpty) {
        continue;
      }
      if (reason.displayName.trim().isEmpty) continue;
      out.add(reason);
      if (out.length >= limit) break;
    }
    return out;
  }

  @override
  ConsumerState<HomeIntersectionSpotlightRail> createState() =>
      _HomeIntersectionSpotlightRailState();
}

class _HomeIntersectionSpotlightRailState
    extends ConsumerState<HomeIntersectionSpotlightRail> {
  @override
  void initState() {
    super.initState();
    // 与收件箱共用 provider 的 TTL 去重：窗口内重建不会重复打服务。
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref.read(myIntersectionPreviewProvider.notifier).load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(myIntersectionPreviewProvider);
    final items = HomeIntersectionSpotlightRail.displayable(state.items);
    if (items.isEmpty) {
      // 加载中 / 失败 / 无交集：都不占版式，避免用「即将有交集」的假象占位。
      return const SizedBox.shrink();
    }
    final horizontal = AppSpacing.feedContentHorizontal(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(
        0,
        AppSpacing.intraGroupSm,
        0,
        AppSpacing.interGroupSm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Padding(
            padding: EdgeInsets.symmetric(horizontal: horizontal),
            child: Text(
              HomeIntersectionSpotlightRail.titleFor(widget.channelId),
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
              ),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: EdgeInsets.symmetric(horizontal: horizontal),
            child: Row(
              children: <Widget>[
                for (final reason in items) ...<Widget>[
                  IntersectionEntity(
                    key: ValueKey<String>(
                      'home-intersection-spotlight-${reason.intersectionId}',
                    ),
                    reason: reason,
                    isDark: widget.isDark,
                    density: IntersectionEntityDensity.spotlight,
                    onTap: () => _openObject(reason),
                  ),
                  SizedBox(width: AppSpacing.intraGroupSm),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// 点击落到交集对象本身（人/地点/圈子主页），承接与对象页、收件箱同一个导航器，
  /// 因此路由映射、不可导航降级与点击归因都只有一处实现。
  void _openObject(IntersectionReason reason) {
    final navigator = IntersectionTargetNavigator(
      onTrack: (target, attribution) {
        final id = target.objectId.trim();
        if (id.isEmpty) return;
        ref
            .read(contentBehaviorTrackerProvider)
            .trackClick(
              id,
              referralSource: ReferralSource.myIntersections,
              channelId: widget.channelId,
              intersectionId: attribution.intersectionId,
              intersectionDimension: attribution.dimension,
              intersectionClass: attribution.intersectionClass,
              intersectionSourceRef: attribution.sourceRef,
              intersectionTagRefs: attribution.tagRefs,
              intersectionEvidenceId: attribution.evidenceId,
            );
      },
    );
    navigator.open(
      context,
      IntersectionTargetNavigator.targetForReason(reason),
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
}
