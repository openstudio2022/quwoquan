import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/components/object_page/intersection_icon_resolver.dart';
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

/// 时间桶归一（交集 / 影响力共用）：服务端 [timeBucket] 优先；缺省按 [freshAt] 推导。
/// 详情页只展示 today/yesterday/last7Days/thisMonth/lastMonth 五个互斥桶。
String resolveIntersectionTimeBucket(String timeBucket, String freshAt) {
  final explicit = timeBucket.trim();
  if (explicit.isNotEmpty) return explicit;
  final fresh = DateTime.tryParse(freshAt);
  if (fresh == null) return 'lastMonth';
  final now = DateTime.now().toUtc();
  final today = DateTime.utc(now.year, now.month, now.day);
  final yesterday = today.subtract(const Duration(days: 1));
  final freshDay = fresh.toUtc();
  final day = DateTime.utc(freshDay.year, freshDay.month, freshDay.day);
  if (day == today) return 'today';
  if (day == yesterday) return 'yesterday';
  if (!day.isBefore(today.subtract(const Duration(days: 7)))) {
    return 'last7Days';
  }
  if (day.year == today.year && day.month == today.month) {
    return 'thisMonth';
  }
  final lastMonth = DateTime.utc(today.year, today.month - 1);
  if (day.year == lastMonth.year && day.month == lastMonth.month) {
    return 'lastMonth';
  }
  return 'outOfRange';
}

List<String> _timelineBucketOrder() {
  return const <String>[
    'today',
    'yesterday',
    'last7Days',
    'thisMonth',
    'lastMonth',
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
      return '';
  }
}

String _bucketCountLabel(int count) =>
    DiscoveryFeedText.intersectionTimelineBucketCount(count);

/// 时间桶条目：bucket key + 已构建好的行 widget（交集/影响力共用）。
class IntersectionTimelineEntry {
  const IntersectionTimelineEntry({required this.bucket, required this.child});

  final String bucket;
  final Widget child;
}

/// 交集 / 影响力详情页专用紧凑行：类型图标 + 单句 primaryText + chevron。
class IntersectionCompactTimelineRow extends StatelessWidget {
  const IntersectionCompactTimelineRow({
    super.key,
    required this.primaryText,
    this.spans = const <IntersectionTextSpan>[],
    this.iconKey = '',
    this.sourceRef = '',
    this.dimension = '',
    this.onTap,
    this.onSpanTap,
  });

  final String primaryText;
  final List<IntersectionTextSpan> spans;
  final String iconKey;
  final String sourceRef;
  final String dimension;
  final VoidCallback? onTap;
  final void Function(IntersectionTextSpan span)? onSpanTap;

  @override
  Widget build(BuildContext context) {
    final row = ConstrainedBox(
      constraints: BoxConstraints(
        minHeight: AppSpacing.minInteractiveSize + AppSpacing.twenty,
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
        child: Row(
          children: <Widget>[
            _CompactTimelineTypeIcon(
              iconKey: iconKey,
              sourceRef: sourceRef,
              dimension: dimension,
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Expanded(
              child: InteractiveIntersectionText(
                spans: spans,
                fallbackText: primaryText.trim(),
                onSpanTap: onSpanTap,
                onFallbackTap: onTap,
                baseStyle: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  height: AppSpacing.textLineHeightFootnote,
                  fontWeight: AppTypography.regular,
                  color: AppColors.iosLabel(context),
                ),
                accentFontWeight: AppTypography.regular,
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.eighteen,
              color: AppColors.iosTertiaryLabel(context),
            ),
          ],
        ),
      ),
    );
    if (onTap == null) return row;
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.square(AppSpacing.minInteractiveSize),
      onPressed: onTap,
      child: row,
    );
  }
}

class _CompactTimelineTypeIcon extends StatelessWidget {
  const _CompactTimelineTypeIcon({
    required this.iconKey,
    required this.sourceRef,
    required this.dimension,
  });

  final String iconKey;
  final String sourceRef;
  final String dimension;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    return Container(
      width: AppSpacing.forty,
      height: AppSpacing.forty,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: accent.withValues(alpha: 0.10),
        shape: BoxShape.circle,
        border: Border.all(
          color: accent.withValues(alpha: 0.12),
          width: AppSpacing.hairline,
        ),
      ),
      child: Icon(
        IntersectionIconResolver.resolve(
          iconKey: iconKey,
          sourceRef: sourceRef,
          dimension: dimension,
        ),
        size: AppSpacing.twenty,
        color: accent,
      ),
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

class IntersectionTimelineRecentLimitNote extends StatelessWidget {
  const IntersectionTimelineRecentLimitNote({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        top: AppSpacing.sm,
        bottom: AppSpacing.containerMd,
      ),
      child: Center(
        child: Text(
          '- ${DiscoveryFeedText.intersectionTimelineRecentLimitNote} -',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color: AppColors.iosTertiaryLabel(context),
            height: AppSpacing.textLineHeightFootnote,
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
    final buckets = _timelineBucketOrder()
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
                  '${_bucketLabel(bucket)} ${_bucketCountLabel(children.length)}',
                  style: TextStyle(
                    fontSize: AppTypography.iosBody,
                    fontWeight: AppTypography.semiBold,
                    color: AppColors.iosLabel(context),
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
                _BucketGroupCard(children: children),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _BucketGroupCard extends StatelessWidget {
  const _BucketGroupCard({required this.children});

  final List<Widget> children;

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
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.04),
            blurRadius: AppSpacing.sm,
            offset: Offset(AppSpacing.zero, AppSpacing.two),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: <Widget>[
          for (var index = 0; index < children.length; index++) ...<Widget>[
            children[index],
            if (index < children.length - 1)
              Padding(
                padding: EdgeInsets.only(
                  left: AppSpacing.forty + AppSpacing.lg,
                ),
                child: Container(
                  height: AppSpacing.hairline,
                  color: AppColors.iosSeparator(
                    context,
                  ).withValues(alpha: 0.30),
                ),
              ),
          ],
        ],
      ),
    );
  }
}
