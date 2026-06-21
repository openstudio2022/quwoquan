import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/user/providers/author_impact_provider.dart';
import 'package:quwoquan_app/ui/user/providers/my_intersection_inbox_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/intersection_statement_card.dart';
import 'package:quwoquan_app/ui/user/widgets/my_intersection_impact_timeline.dart';
import 'package:quwoquan_app/ui/user/widgets/my_intersection_inbox_timeline.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_secondary_tab_bar.dart';
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
  late _IntersectionDetailTab _selectedTab;

  /// 二级筛选闭集（与「我的主页」二级页签同款胶囊样式）。
  static const List<ProfileSecondaryTabItem> _filterTabs =
      <ProfileSecondaryTabItem>[
        ProfileSecondaryTabItem(
          id: 'all',
          label: DiscoveryFeedText.intersectionFilterAll,
        ),
        ProfileSecondaryTabItem(
          id: 'person',
          label: DiscoveryFeedText.intersectionFilterPeople,
        ),
        ProfileSecondaryTabItem(
          id: 'circle',
          label: DiscoveryFeedText.intersectionFilterCircles,
        ),
        ProfileSecondaryTabItem(
          id: 'place',
          label: DiscoveryFeedText.intersectionFilterPlaces,
        ),
        ProfileSecondaryTabItem(
          id: 'interest',
          label: DiscoveryFeedText.intersectionFilterInterests,
        ),
      ];

  /// 二级筛选可选值闭集；不在集合内（如 `fact`/`impact`/空）一律归一到 `all`。
  static const Set<String> _filterIds = <String>{
    'all',
    'person',
    'circle',
    'place',
    'interest',
  };

  IntersectionTargetNavigator get _navigator => IntersectionTargetNavigator(
    onTrack: (target, attribution) {
      final id = target.objectId.trim();
      if (id.isEmpty) return;
      ref
          .read(contentBehaviorTrackerProvider)
          .trackClick(
            id,
            referralSource: ReferralSource.myIntersections,
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
    _selectedTab = widget.filter.trim() == 'impact'
        ? _IntersectionDetailTab.impact
        : _IntersectionDetailTab.intersections;
    // 默认「全部」高亮：仅 person/circle/place/interest 是合法二级筛选；
    // fact / impact / 空 等一律归一到 all，避免「无选中」假象。
    final rawFilter = widget.filter.trim();
    _selectedFilter = _filterIds.contains(rawFilter) ? rawFilter : 'all';
    if (_selectedTab == _IntersectionDetailTab.intersections) {
      Future<void>.microtask(_load);
    }
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
    return resolveIntersectionDetailErrorSemantic(
      context,
      error: error,
      title: '${DiscoveryFeedText.myIntersectionsTitle}暂不可用',
    );
  }

  @override
  Widget build(BuildContext context) {
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
        middle: Text(_titleForTab(_selectedTab)),
      ),
      child: _buildBody(context, state),
    );
  }

  String _titleForTab(_IntersectionDetailTab tab) =>
      tab == _IntersectionDetailTab.impact
      ? UITextConstants.profileTabImpact
      : UITextConstants.profileTabIntersection;

  void _selectDetailTab(_IntersectionDetailTab tab) {
    if (tab == _selectedTab) return;
    setState(() => _selectedTab = tab);
    final state = ref.read(myIntersectionListProvider);
    if (tab == _IntersectionDetailTab.intersections &&
        state.items.isEmpty &&
        !state.isLoading) {
      _load();
    }
  }

  Widget _buildBody(BuildContext context, MyIntersectionListState state) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final items = _visibleItems(state.items);
    final impactState = ref.watch(
      authorImpactProvider(ref.watch(currentUserIdProvider)),
    );
    return ListView(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.sm,
        AppSpacing.md,
        AppSpacing.xl,
      ),
      children: <Widget>[
        // 一级 tab（交集 / 影响力）：移入 body 顶部，与「我的主页」内容区一级 tab 同款
        // 蓝色下划线 + 选中加粗（CenteredScrollableTabBar），导航栏标题随之切换。
        _IntersectionDetailTabs(
          selected: _selectedTab,
          onSelected: _selectDetailTab,
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        if (_selectedTab == _IntersectionDetailTab.impact)
          ImpactTimeline(state: impactState)
        else
          ..._buildIntersectionTimelineChildren(state, items, isDark),
      ],
    );
  }

  List<Widget> _buildIntersectionTimelineChildren(
    MyIntersectionListState state,
    List<IntersectionReason> items,
    bool isDark,
  ) {
    if (state.isLoading && state.items.isEmpty) {
      return const <Widget>[Center(child: CupertinoActivityIndicator())];
    }
    if (state.rawError != null) {
      return <Widget>[
        AppPageErrorState(
          semantic: _resolvePageErrorSemantic(state.rawError!),
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              await _load();
            }
          },
        ),
      ];
    }
    return <Widget>[
      // 二级筛选（全部/人/圈子/地点/兴趣）：accent 胶囊，与「我的主页」二级页签同款。
      ProfileSecondaryTabBar(
        tabs: _filterTabs,
        selectedId: _selectedFilter,
        isDark: isDark,
        onSelected: (value) {
          if (_selectedFilter == value) return;
          setState(() => _selectedFilter = value);
          _load();
        },
      ),
      SizedBox(height: AppSpacing.intraGroupSm),
      if (items.isEmpty)
        const IntersectionTimelineEmptyState()
      else
        IntersectionBucketTimeline(rows: _intersectionRows(items)),
    ];
  }

  /// 交集行 → 时间桶条目（复用共享 [IntersectionStatementRow]：四槽 + 行动 pill + 生命周期弱标）。
  List<IntersectionTimelineEntry> _intersectionRows(
    List<IntersectionReason> items,
  ) {
    return <IntersectionTimelineEntry>[
      for (final reason in items)
        IntersectionTimelineEntry(
          bucket: resolveIntersectionTimeBucket(
            reason.timeBucket,
            reason.freshAt,
          ),
          child: IntersectionTimelineCard(
            child: IntersectionStatementRow(item: _intersectionItem(reason)),
          ),
        ),
    ];
  }

  IntersectionStatementItem _intersectionItem(IntersectionReason reason) {
    final hasAction = reason.actionHints.any(
      (hint) => hint.label.trim().isNotEmpty,
    );
    return IntersectionStatementItem(
      primaryText: reason.primaryText,
      subtitleText: '',
      spans: reason.primarySpans,
      iconKey: reason.iconKey,
      sourceRef: _sourceRefFor(reason),
      dimension: reason.dimension,
      actionHints: reason.actionHints,
      lifecycleState: reason.lifecycleState,
      showAuxiliaryLine: hasAction,
      onTap: () => _openReason(reason),
      onSpanTap: (span) => _onSpanTap(reason, span),
      onActionHintTap: (hint) => _onActionHint(reason, hint),
    );
  }

  void _onActionHint(IntersectionReason reason, IntersectionActionHint hint) {
    if (hint.target != null && hint.target!.objectId.trim().isNotEmpty) {
      _navigator.open(
        context,
        hint.target,
        attribution: _attributionFor(reason),
      );
      return;
    }
    _openReason(reason);
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
        return item.objectKind == 'person' || item.dimension == 'relationship';
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
    final objectType = item.objectKind.trim();
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

  // objectKind → 端路由逻辑名：codegen intersectionRouteIdForObjectKind 单一真相源
  // （registry.objectKinds.routeId）；旧 relationKind 对象类型桥接已删除（§23 去桥接）。
  String _routeIdFor(IntersectionReason reason) =>
      intersectionRouteIdForObjectKind(reason.objectKind.trim());
}

String _sourceRefFor(IntersectionReason reason) {
  final source = reason.source.trim();
  if (source.isNotEmpty) return source;
  if (reason.intersectionPoints.isEmpty) return '';
  return reason.intersectionPoints.first.sourceRef.trim();
}

enum _IntersectionDetailTab { intersections, impact }

class _IntersectionDetailTabs extends StatelessWidget {
  const _IntersectionDetailTabs({
    required this.selected,
    required this.onSelected,
  });

  final _IntersectionDetailTab selected;
  final ValueChanged<_IntersectionDetailTab> onSelected;

  @override
  Widget build(BuildContext context) {
    final tabs = <TabItem>[
      TabItem(
        id: _IntersectionDetailTab.intersections.id,
        label: UITextConstants.profileTabIntersection,
      ),
      TabItem(
        id: _IntersectionDetailTab.impact.id,
        label: UITextConstants.profileTabImpact,
      ),
    ];
    return SizedBox(
      height: AppSpacing.buttonHeightMd,
      child: CenteredScrollableTabBar(
        tabs: tabs,
        activeTab: selected.id,
        onTabChange: (id) => onSelected(_intersectionDetailTabForId(id)),
        transparentBackground: true,
        selectedLabelColor: AppColors.iosAccent(context),
      ),
    );
  }
}

extension _IntersectionDetailTabMetadata on _IntersectionDetailTab {
  String get id => switch (this) {
    _IntersectionDetailTab.intersections => 'intersections',
    _IntersectionDetailTab.impact => 'impact',
  };
}

_IntersectionDetailTab _intersectionDetailTabForId(String id) {
  return id == _IntersectionDetailTab.impact.id
      ? _IntersectionDetailTab.impact
      : _IntersectionDetailTab.intersections;
}
