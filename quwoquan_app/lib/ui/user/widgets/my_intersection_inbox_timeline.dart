import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 「我的交集」/「我的影响力」详情页共用的展示支撑：时间桶时间线脚手架 + 详情页错误语义归一。
///
/// 从 `my_intersection_inbox_page.dart` 抽出（R03 文件体量收敛 + R25 重复构造收敛）：
/// 页面只保留筛选 / 数据装配 / 导航业务逻辑，时间桶归一、时间线渲染、错误语义构造由本文件承载。
/// 交集 tab 与影响力 tab 复用同一套 5 年时间桶顺序、「空桶隐藏」不变量与错误语义，
/// 避免维护第二套时间线/错误构造实现。

/// 详情页错误语义归一（交集 / 影响力共用）：在 `runtimeErrorSemantic` 结果上仅覆盖标题，
/// 并在缺省主动作时补「重试」，其余字段（恢复动作 / 展示形态 / tone）原样透传。
UiErrorSemantic resolveIntersectionDetailErrorSemantic(
  BuildContext context, {
  required Object error,
  required String title,
}) {
  final resolved = runtimeErrorSemantic(
    context,
    error: error,
    category: UiErrorCategory.pageLoad,
    scope: UiErrorScope.page,
  );
  return UiErrorSemantic(
    category: resolved.category,
    scope: resolved.scope,
    title: title,
    message: resolved.message,
    secondaryMessage: resolved.secondaryMessage,
    primaryAction:
        resolved.primaryAction ??
        const UiErrorAction(
          type: UiErrorActionType.retry,
          label: UITextConstants.tryAgain,
        ),
    secondaryAction: resolved.secondaryAction,
    dismissible: resolved.dismissible,
    sourceCode: resolved.sourceCode,
    failureKind: resolved.failureKind,
    recoveryAction: resolved.recoveryAction,
    presentation: resolved.presentation,
    tone: resolved.tone,
  );
}

/// 时间桶归一（交集 / 影响力共用）：服务端 [timeBucket] 优先；缺省按 [freshAt] 推导，
/// 覆盖 today/yesterday/last7Days/thisMonth/lastMonth + 近若干年的 `year:N`。
String resolveIntersectionTimeBucket(String timeBucket, String freshAt) {
  final explicit = timeBucket.trim();
  if (explicit.isNotEmpty) return explicit;
  final fresh = DateTime.tryParse(freshAt);
  if (fresh == null) return 'lastMonth';
  final diff = DateTime.now().toUtc().difference(fresh.toUtc());
  if (diff.inHours < 24) return 'today';
  if (diff.inHours < 48) return 'yesterday';
  if (diff.inDays < 7) return 'last7Days';
  if (diff.inDays < 31) return 'thisMonth';
  if (diff.inDays < 62) return 'lastMonth';
  return _yearBucket(fresh.year);
}

String _yearBucket(int year) => 'year:$year';

List<String> _timelineBucketOrder() {
  final now = DateTime.now();
  return <String>[
    'today',
    'yesterday',
    'last7Days',
    'thisMonth',
    'lastMonth',
    for (var offset = 0; offset < 10; offset += 1)
      _yearBucket(now.year - offset),
  ];
}

String _bucketLabel(String bucket) {
  switch (bucket) {
    case 'today':
      return DiscoveryFeedText.intersectionTimeBucketToday;
    case 'yesterday':
      return DiscoveryFeedText.intersectionTimeBucketYesterday;
    case 'last7Days':
      return DiscoveryFeedText.intersectionTimeBucketLast7Days;
    case 'thisMonth':
      return DiscoveryFeedText.intersectionTimeBucketThisMonth;
    case 'lastMonth':
      return DiscoveryFeedText.intersectionTimeBucketLastMonth;
    default:
      if (bucket.startsWith('year:')) {
        return '${bucket.substring('year:'.length)} 年';
      }
      return DiscoveryFeedText.intersectionTimeBucketLastMonth;
  }
}

/// 时间桶条目：bucket key + 已构建好的行 widget（交集/影响力共用）。
class IntersectionTimelineEntry {
  const IntersectionTimelineEntry({required this.bucket, required this.child});

  final String bucket;
  final Widget child;
}

/// 时间线卡：统一交集/影响力行的柔和表面 + 细边框容器（内部嵌共享 `IntersectionStatementRow`）。
class IntersectionTimelineCard extends StatelessWidget {
  const IntersectionTimelineCard({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.iosProfileSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(
          color: AppColors.iosSeparator(context).withValues(alpha: 0.10),
          width: AppSpacing.hairline,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      child: child,
    );
  }
}

/// 全部时间桶为空时的占位（仅整页无任何 item 时出现；空时间桶本身不渲染）。
class IntersectionTimelineEmptyState extends StatelessWidget {
  const IntersectionTimelineEmptyState({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.xl),
      child: Center(
        child: Text(
          DiscoveryFeedText.intersectionTimeBucketEmpty,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosSubheadline,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ),
    );
  }
}

/// 通用 5 年时间线：按 bucket 归组，**只渲染有 item 的时间桶**（空桶隐藏）。
class IntersectionBucketTimeline extends StatelessWidget {
  const IntersectionBucketTimeline({super.key, required this.rows});

  final List<IntersectionTimelineEntry> rows;

  @override
  Widget build(BuildContext context) {
    final byBucket = <String, List<Widget>>{};
    for (final row in rows) {
      byBucket.putIfAbsent(row.bucket, () => <Widget>[]).add(row.child);
    }
    final canonicalBuckets = _timelineBucketOrder();
    final extraBuckets =
        byBucket.keys
            .where((bucket) => !canonicalBuckets.contains(bucket))
            .toList(growable: false)
          ..sort((a, b) => b.compareTo(a));
    final buckets = <String>[...canonicalBuckets, ...extraBuckets]
        .where((bucket) => (byBucket[bucket]?.isNotEmpty ?? false))
        .toList(growable: false);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        for (var bucketIndex = 0; bucketIndex < buckets.length; bucketIndex++)
          _BucketSection(
            bucket: buckets[bucketIndex],
            showLineTail: bucketIndex < buckets.length - 1,
            children: byBucket[buckets[bucketIndex]]!,
          ),
      ],
    );
  }
}

class _BucketSection extends StatelessWidget {
  const _BucketSection({
    required this.bucket,
    required this.children,
    required this.showLineTail,
  });

  final String bucket;
  final List<Widget> children;
  final bool showLineTail;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final timelineColor =
        (isDark
                ? AppColors.profileSloganAccentDark
                : AppColors.profileSloganAccentLight)
            .withValues(alpha: isDark ? 0.34 : 0.24);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SizedBox(
          width: AppSpacing.containerMd,
          child: Column(
            children: <Widget>[
              SizedBox(height: AppSpacing.xs),
              Container(
                width: AppSpacing.xs,
                height: AppSpacing.xs,
                decoration: BoxDecoration(
                  color: timelineColor,
                  shape: BoxShape.circle,
                ),
              ),
              if (showLineTail)
                Container(
                  width: AppSpacing.hairline,
                  height:
                      (AppSpacing.minInteractiveSize + AppSpacing.sm) *
                      children.length,
                  color: timelineColor,
                ),
            ],
          ),
        ),
        Expanded(
          child: Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.containerMd),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  _bucketLabel(bucket),
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    fontWeight: AppTypography.regular,
                    color: AppColors.iosLabel(context),
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
                for (final child in children) ...<Widget>[
                  child,
                  SizedBox(height: AppSpacing.intraGroupSm),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}
