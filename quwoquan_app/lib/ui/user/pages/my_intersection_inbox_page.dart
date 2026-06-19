import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/components/object_page/intersection_icon_resolver.dart';
import 'package:quwoquan_app/components/object_page/intersection_object_kind.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/user/providers/my_intersection_inbox_provider.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';

/// 「我的交集」详情页：筛选 + 时间桶 timeline。
///
/// 数据顺序由云侧保证：先全局去重，再按 strength/timeBucket/anchor/count/type 排序。
/// 端侧只做防御性分组与展示，不拼装任何事实结论句。
class MyIntersectionInboxPage extends ConsumerStatefulWidget {
  const MyIntersectionInboxPage({
    super.key,
    this.dimension = '',
    this.sourceRef = '',
    this.filter = '',
    this.timeBucket = '',
    this.intersectionId = '',
  });

  factory MyIntersectionInboxPage.fromQuery(Map<String, String> query) {
    return MyIntersectionInboxPage(
      dimension: query['dimension'] ?? '',
      sourceRef: query['sourceRef'] ?? '',
      filter: query['filter'] ?? '',
      timeBucket: query['timeBucket'] ?? '',
      intersectionId: query['intersectionId'] ?? '',
    );
  }

  final String dimension;
  final String sourceRef;
  final String filter;
  final String timeBucket;
  final String intersectionId;

  @override
  ConsumerState<MyIntersectionInboxPage> createState() =>
      _MyIntersectionInboxPageState();
}

class _MyIntersectionInboxPageState
    extends ConsumerState<MyIntersectionInboxPage> {
  late String _selectedFilter;

  static const List<_IntersectionFilter> _filters = <_IntersectionFilter>[
    _IntersectionFilter('all', DiscoveryFeedText.intersectionFilterAll),
    _IntersectionFilter('person', DiscoveryFeedText.intersectionFilterPeople),
    _IntersectionFilter('circle', DiscoveryFeedText.intersectionFilterCircles),
    _IntersectionFilter('place', DiscoveryFeedText.intersectionFilterPlaces),
    _IntersectionFilter(
      'interest',
      DiscoveryFeedText.intersectionFilterInterests,
    ),
  ];

  IntersectionTargetNavigator get _navigator => IntersectionTargetNavigator(
    onTrack: (target, attribution) {
      final id = target.objectId.trim();
      if (id.isEmpty) return;
      ref
          .read(contentBehaviorTrackerProvider)
          .trackClick(
            id,
            referralSource: ReferralSource.organicFeed,
            intersectionId: attribution.intersectionId,
            intersectionDimension: attribution.dimension,
            intersectionClass: attribution.intersectionClass,
            intersectionSourceRef: attribution.sourceRef,
            intersectionTagRefs: attribution.tagRefs,
            intersectionEvidenceId: attribution.evidenceId,
          );
    },
  );

  @override
  void initState() {
    super.initState();
    _selectedFilter = widget.filter.trim().isEmpty
        ? 'all'
        : widget.filter.trim();
    Future<void>.microtask(_load);
  }

  Future<void> _load() {
    return ref
        .read(myIntersectionListProvider.notifier)
        .loadAndMarkVisited(
          dimension: widget.dimension,
          filter: _selectedFilter == 'all' ? 'fact' : _selectedFilter,
          sourceRef: widget.sourceRef,
          timeBucket: widget.timeBucket,
        );
  }

  UiErrorSemantic _resolvePageErrorSemantic(Object error) {
    final resolved = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
    return UiErrorSemantic(
      category: resolved.category,
      scope: resolved.scope,
      title: '${DiscoveryFeedText.myIntersectionsTitle}暂不可用',
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

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColors.iosSystemBackground(context);
    final state = ref.watch(myIntersectionListProvider);
    return AppScaffold(
      backgroundColor: bg,
      navigationBar: AppNavigationBar(
        backgroundColor: bg,
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => context.pop(),
        ),
        middle: Text(
          DiscoveryFeedText.myIntersectionsTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      child: _buildBody(context, state),
    );
  }

  Widget _buildBody(BuildContext context, MyIntersectionListState state) {
    if (state.isLoading && state.items.isEmpty) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (state.rawError != null) {
      return AppPageErrorState(
        semantic: _resolvePageErrorSemantic(state.rawError!),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _load();
          }
        },
      );
    }
    final items = _visibleItems(state.items);
    return ListView(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.sm,
        AppSpacing.md,
        AppSpacing.xl,
      ),
      children: <Widget>[
        _FilterPills(
          filters: _filters,
          selected: _selectedFilter,
          onSelected: (value) {
            if (_selectedFilter == value) return;
            setState(() => _selectedFilter = value);
            _load();
          },
        ),
        SizedBox(height: AppSpacing.containerMd),
        if (items.isEmpty)
          _EmptyTimelineState()
        else
          _BucketTimeline(
            items: items,
            onRowTap: _openReason,
            onSpanTap: _onSpanTap,
          ),
      ],
    );
  }

  List<IntersectionReason> _visibleItems(List<IntersectionReason> raw) {
    final factItems = raw.where((item) => item.intersectionClass == 'fact');
    final filtered = factItems
        .where((item) {
          if (widget.intersectionId.trim().isNotEmpty &&
              item.intersectionId != widget.intersectionId.trim()) {
            return false;
          }
          if (_selectedFilter == 'all') return true;
          return _matchesFilter(item, _selectedFilter);
        })
        .toList(growable: false);
    return _dedupe(filtered);
  }

  bool _matchesFilter(IntersectionReason item, String filter) {
    switch (filter) {
      case 'person':
        return item.objectKind == 'person' ||
            item.relationKind == 'person' ||
            item.dimension == 'relationship';
      case 'circle':
        return item.objectKind == 'circle';
      case 'place':
        return item.objectKind == 'place' || item.dimension == 'location';
      case 'interest':
        return item.dimension == 'interest' || item.objectKind == 'tag';
      default:
        return true;
    }
  }

  List<IntersectionReason> _dedupe(List<IntersectionReason> items) {
    final seen = <String>{};
    final result = <IntersectionReason>[];
    for (final item in items) {
      final key = _dedupeKeyFor(item);
      if (seen.add(key)) {
        result.add(item);
      }
    }
    return result;
  }

  String _dedupeKeyFor(IntersectionReason item) {
    final explicit = item.dedupeKey.trim();
    if (explicit.isNotEmpty) return explicit;
    final objectId = item.actionTargetId.trim().isNotEmpty
        ? item.actionTargetId.trim()
        : item.relationObjectId.trim().isNotEmpty
        ? item.relationObjectId.trim()
        : item.intersectionId.trim();
    final objectType = item.objectKind.trim().isNotEmpty
        ? item.objectKind.trim()
        : item.relationKind.trim();
    return '$objectId:$objectType';
  }

  void _onSpanTap(IntersectionReason reason, IntersectionTextSpan span) {
    if (span.role == 'count') {
      context.push(
        AppRoutePaths.myIntersections(
          filter: 'fact',
          sourceRef: _sourceRefFor(reason),
          intersectionId: reason.intersectionId,
        ),
      );
      return;
    }
    _navigator.open(context, span.target, attribution: _attributionFor(reason));
  }

  void _openReason(IntersectionReason reason) {
    final target = IntersectionTarget(
      objectId: reason.actionTargetId,
      objectKind: reason.objectKind,
      routeId: _routeIdFor(reason),
    );
    final opened = _navigator.open(
      context,
      target,
      attribution: _attributionFor(reason),
    );
    if (!opened) {
      context.push(
        AppRoutePaths.myIntersections(
          filter: 'fact',
          intersectionId: reason.intersectionId,
        ),
      );
    }
  }

  IntersectionNavAttribution _attributionFor(IntersectionReason reason) {
    return IntersectionNavAttribution(
      intersectionId: reason.intersectionId,
      dimension: reason.dimension,
      intersectionClass: reason.intersectionClass,
      sourceRef: _sourceRefFor(reason),
      tagRefs: reason.tagRefs,
      evidenceId: reason.pointSummarySnapshotId,
    );
  }

  String _routeIdFor(IntersectionReason reason) {
    switch (UnifiedObjectKind.resolve(
      objectKind: reason.objectKind,
      relationKind: reason.relationKind,
    )) {
      case UnifiedObjectKind.person:
        return 'userProfile';
      case UnifiedObjectKind.circle:
        return 'circleDetail';
      case UnifiedObjectKind.place:
      case UnifiedObjectKind.school:
      case UnifiedObjectKind.enterprise:
        return 'homepageDetail';
    }
  }
}

String _sourceRefFor(IntersectionReason reason) {
  final source = reason.source.trim();
  if (source.isNotEmpty) return source;
  if (reason.intersectionPoints.isEmpty) return '';
  return reason.intersectionPoints.first.sourceRef.trim();
}

String _timeBucketFor(IntersectionReason reason) {
  final explicit = reason.timeBucket.trim();
  if (explicit.isNotEmpty) return explicit;
  final freshAt = DateTime.tryParse(reason.freshAt);
  if (freshAt == null) return 'lastMonth';
  final diff = DateTime.now().toUtc().difference(freshAt.toUtc());
  if (diff.inHours < 24) return 'today';
  if (diff.inHours < 48) return 'yesterday';
  if (diff.inDays < 7) return 'last7Days';
  if (diff.inDays < 31) return 'thisMonth';
  return 'lastMonth';
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
      return DiscoveryFeedText.intersectionTimeBucketLastMonth;
  }
}

class _IntersectionFilter {
  const _IntersectionFilter(this.value, this.label);

  final String value;
  final String label;
}

class _FilterPills extends StatelessWidget {
  const _FilterPills({
    required this.filters,
    required this.selected,
    required this.onSelected,
  });

  final List<_IntersectionFilter> filters;
  final String selected;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: <Widget>[
          for (final filter in filters) ...<Widget>[
            _FilterPill(
              filter: filter,
              selected: filter.value == selected,
              onTap: () => onSelected(filter.value),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
          ],
        ],
      ),
    );
  }
}

class _FilterPill extends StatelessWidget {
  const _FilterPill({
    required this.filter,
    required this.selected,
    required this.onTap,
  });

  final _IntersectionFilter filter;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        height: AppSpacing.buttonHeightSm,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: selected
              ? AppColors.iosProfileSurface(context)
              : AppColors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.buttonHeightSm / 2),
          boxShadow: selected
              ? <BoxShadow>[
                  BoxShadow(
                    color: AppColors.black.withValues(alpha: 0.05),
                    blurRadius: AppSpacing.sm,
                    offset: const Offset(0, 2),
                  ),
                ]
              : null,
        ),
        child: Text(
          filter.label,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color: selected ? accent : AppColors.iosSecondaryLabel(context),
          ),
        ),
      ),
    );
  }
}

class _BucketTimeline extends StatelessWidget {
  const _BucketTimeline({
    required this.items,
    required this.onRowTap,
    required this.onSpanTap,
  });

  final List<IntersectionReason> items;
  final ValueChanged<IntersectionReason> onRowTap;
  final void Function(IntersectionReason reason, IntersectionTextSpan span)
  onSpanTap;

  static const List<String> _bucketOrder = <String>[
    'today',
    'yesterday',
    'last7Days',
    'thisMonth',
    'lastMonth',
  ];

  @override
  Widget build(BuildContext context) {
    final byBucket = <String, List<IntersectionReason>>{};
    for (final item in items) {
      byBucket.putIfAbsent(_timeBucketFor(item), () => <IntersectionReason>[]);
      byBucket[_timeBucketFor(item)]!.add(item);
    }
    final buckets = _bucketOrder
        .where((bucket) => byBucket[bucket]?.isNotEmpty ?? false)
        .toList(growable: false);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        for (var bucketIndex = 0; bucketIndex < buckets.length; bucketIndex++)
          _BucketSection(
            bucket: buckets[bucketIndex],
            items: byBucket[buckets[bucketIndex]]!,
            showLineTail: bucketIndex < buckets.length - 1,
            onRowTap: onRowTap,
            onSpanTap: onSpanTap,
          ),
      ],
    );
  }
}

class _BucketSection extends StatelessWidget {
  const _BucketSection({
    required this.bucket,
    required this.items,
    required this.showLineTail,
    required this.onRowTap,
    required this.onSpanTap,
  });

  final String bucket;
  final List<IntersectionReason> items;
  final bool showLineTail;
  final ValueChanged<IntersectionReason> onRowTap;
  final void Function(IntersectionReason reason, IntersectionTextSpan span)
  onSpanTap;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
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
                  color: accent,
                  shape: BoxShape.circle,
                ),
              ),
              if (showLineTail)
                Container(
                  width: AppSpacing.hairline,
                  height:
                      (AppSpacing.minInteractiveSize + AppSpacing.sm) *
                      items.length,
                  color: accent.withValues(alpha: 0.18),
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
                    fontWeight: AppTypography.medium,
                    color: AppColors.iosLabel(context),
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
                for (final item in items) ...<Widget>[
                  _TimelineIntersectionRow(
                    reason: item,
                    onTap: () => onRowTap(item),
                    onSpanTap: (span) => onSpanTap(item, span),
                  ),
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

class _TimelineIntersectionRow extends StatelessWidget {
  const _TimelineIntersectionRow({
    required this.reason,
    required this.onTap,
    required this.onSpanTap,
  });

  final IntersectionReason reason;
  final VoidCallback onTap;
  final void Function(IntersectionTextSpan span) onSpanTap;

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
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.square(AppSpacing.minInteractiveSize),
        onPressed: onTap,
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.containerXs,
          ),
          child: Row(
            children: <Widget>[
              IntersectionTypeIcon(
                iconKey: reason.iconKey,
                sourceRef: _sourceRefFor(reason),
                dimension: reason.dimension,
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Expanded(
                child: InteractiveIntersectionText(
                  spans: reason.primarySpans,
                  fallbackText: reason.primaryText,
                  onSpanTap: onSpanTap,
                  onFallbackTap: onTap,
                  baseStyle: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    height: AppSpacing.textLineHeightFootnote,
                    color: AppColors.iosLabel(context),
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconXSmall,
                color: AppColors.iosQuaternaryLabel(context),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _EmptyTimelineState extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.xl),
      child: Center(
        child: Text(
          DiscoveryFeedText.myIntersectionsEmpty,
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
