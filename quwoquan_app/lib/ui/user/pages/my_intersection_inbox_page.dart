import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/user/providers/author_impact_provider.dart';
import 'package:quwoquan_app/ui/user/providers/my_intersection_inbox_provider.dart';
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
  late String _selectedIntersectionFilter;
  String _selectedImpactFilter = 'all';
  late _IntersectionDetailTab _selectedTab;

  /// 二级筛选闭集 = 交集五维（`_shared/types.yaml#IntersectionDimension`）+「全部」。
  ///
  /// 筛选轴与模型同一套维度，因此 identity / content 不再因为筛选是 objectKind 与
  /// dimension 的混合匹配而不可达；标签复用 [DiscoveryFeedText.intersectionDimensionShortLabels]，
  /// 与结论句里的维度弱标同一份文案。
  static const List<ProfileSecondaryTabItem> _filterTabs =
      <ProfileSecondaryTabItem>[
        ProfileSecondaryTabItem(
          id: 'all',
          label: DiscoveryFeedText.intersectionFilterAll,
        ),
        ProfileSecondaryTabItem(
          id: 'relationship',
          label: DiscoveryFeedText.intersectionDimensionRelationship,
        ),
        ProfileSecondaryTabItem(
          id: 'location',
          label: DiscoveryFeedText.intersectionDimensionLocation,
        ),
        ProfileSecondaryTabItem(
          id: 'identity',
          label: DiscoveryFeedText.intersectionDimensionIdentity,
        ),
        ProfileSecondaryTabItem(
          id: 'content',
          label: DiscoveryFeedText.intersectionDimensionContent,
        ),
        ProfileSecondaryTabItem(
          id: 'interest',
          label: DiscoveryFeedText.intersectionDimensionInterest,
        ),
      ];

  /// 二级筛选可选值闭集；不在集合内（如 `fact`/`impact`/旧 objectKind 值/空）一律归一到 `all`。
  static const Set<String> _filterIds = <String>{
    'all',
    'relationship',
    'location',
    'identity',
    'content',
    'interest',
  };

  static const List<ProfileSecondaryTabItem> _impactFilterTabs =
      <ProfileSecondaryTabItem>[
        ProfileSecondaryTabItem(
          id: 'all',
          label: DiscoveryFeedText.intersectionFilterAll,
        ),
        ProfileSecondaryTabItem(
          id: 'records',
          label: DiscoveryFeedText.impactFilterRecords,
        ),
        ProfileSecondaryTabItem(
          id: 'discussion',
          label: DiscoveryFeedText.impactFilterDiscussions,
        ),
        ProfileSecondaryTabItem(
          id: 'homepage',
          label: DiscoveryFeedText.impactFilterHomepage,
        ),
      ];

  static const Set<String> _impactFilterIds = <String>{
    'all',
    'records',
    'discussion',
    'homepage',
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
    // 二级筛选高亮的真相源是深链维度：从红点 / 通知 / 交集句下钻带 dimension 进来时，
    // 必须让对应维度胶囊选中，否则列表已按维度收窄却高亮「全部」。
    // filter（fact / impact / 空）不是维度，不参与胶囊选中。
    final rawDimension = widget.dimension.trim();
    _selectedIntersectionFilter = _filterIds.contains(rawDimension)
        ? rawDimension
        : 'all';
    // 打动页签的筛选轴仍是 records/discussion/homepage，走 filter 参数。
    final rawFilter = widget.filter.trim();
    _selectedImpactFilter = _impactFilterIds.contains(rawFilter)
        ? rawFilter
        : 'all';
    if (_selectedTab == _IntersectionDetailTab.intersections) {
      Future<void>.microtask(_load);
    }
  }

  /// 拉取当前筛选下的交集列表。
  ///
  /// 维度筛选走云侧 `dimension` 参数（五维闭集，云侧 `reasonHasDimension` 会同时看
  /// reason 与 point 的维度），`filter` 恒为 `fact`：本页交集页签只展示事实交集，
  /// 概率推荐不混入。此前把胶囊 id（person/circle/place/interest）当作 `filter` 传，
  /// 云侧闭集只认 all/new/fact/affinity，因此那些值被静默忽略、分页拉的是未收窄的全量，
  /// 只靠端上二次过滤，既让 identity/content 不可达，也让翻页页码与筛选结果错位。
  Future<void> _load() {
    final selected = _selectedIntersectionFilter;
    return ref
        .read(myIntersectionListProvider.notifier)
        .loadAndMarkVisited(
          dimension: selected == 'all' ? widget.dimension : selected,
          filter: 'fact',
          sourceRef: widget.sourceRef,
          timeBucket: widget.timeBucket,
        );
  }

  UiErrorSemantic _resolvePageErrorSemantic(Object error) {
    return resolveIntersectionDetailErrorSemantic(
      context,
      error: error,
      title: ObjectHomepageText.objectIntersectionsUnavailableTitle,
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final state = ref.watch(myIntersectionListProvider);
    return AppListPageScaffold(
      isDark: isDark,
      kind: AppListPageKind.multiOptionList,
      middle: _IntersectionNavSwitch(
        selected: _selectedTab,
        onSelected: _selectDetailTab,
      ),
      backgroundColor: AppColors.iosIntersectionTimelineBackground(context),
      onBack: () => context.pop(),
      body: _buildBody(context, state),
    );
  }

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
    final children = _selectedTab == _IntersectionDetailTab.impact
        ? _buildImpactTimelineChildren(
            ref.watch(
              authorImpactProvider((
                personaId: ref.watch(currentUserIdProvider),
                surface: AppUiSurfaces.myIntersections,
              )),
            ),
            isDark,
          )
        : _buildIntersectionTimelineChildren(state, items, isDark);
    return ListView(
      padding: EdgeInsets.fromLTRB(
        SettingsSemanticConstants.insetFormListHorizontalPadding,
        AppSpacing.containerSm,
        SettingsSemanticConstants.insetFormListHorizontalPadding,
        AppSpacing.containerLg,
      ),
      children: children,
    );
  }

  List<Widget> _buildImpactTimelineChildren(
    AsyncValue<AuthorImpactSummary> impactState,
    bool isDark,
  ) {
    return <Widget>[
      ProfileSecondaryTabBar(
        tabs: _impactFilterTabs,
        selectedId: _selectedImpactFilter,
        isDark: isDark,
        onSelected: (value) {
          if (_selectedImpactFilter == value) return;
          setState(() => _selectedImpactFilter = value);
        },
      ),
      SizedBox(height: AppSpacing.intraGroupSm),
      ImpactTimeline(state: impactState, filter: _selectedImpactFilter),
    ];
  }

  List<Widget> _buildIntersectionTimelineChildren(
    MyIntersectionListState state,
    List<IntersectionReason> items,
    bool isDark,
  ) {
    if (state.isLoading && state.items.isEmpty) {
      return <Widget>[AppRequestFeedback.section()];
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
      // 二级筛选（全部 + 交集五维）：accent 胶囊，与「我的主页」二级页签同款。
      ProfileSecondaryTabBar(
        tabs: _filterTabs,
        selectedId: _selectedIntersectionFilter,
        isDark: isDark,
        onSelected: (value) {
          if (_selectedIntersectionFilter == value) return;
          setState(() => _selectedIntersectionFilter = value);
          _load();
        },
      ),
      SizedBox(height: AppSpacing.intraGroupSm),
      if (items.isEmpty)
        const IntersectionTimelineEmptyState()
      else ...<Widget>[
        IntersectionBucketTimeline(rows: _intersectionRows(items)),
        const IntersectionTimelineRecentLimitNote(),
      ],
    ];
  }

  /// 交集行 → 时间桶条目（详情页紧凑行：图标 + 单句 + chevron）。
  List<IntersectionTimelineEntry> _intersectionRows(
    List<IntersectionReason> items,
  ) {
    return <IntersectionTimelineEntry>[
      for (final reason in items)
        if (displayReadyIntersectionReason(reason) case final displayReason?)
          IntersectionTimelineEntry(
            bucket: resolveIntersectionTimeBucket(
              displayReason.timeBucket,
              displayReason.freshAt,
            ),
            child: IntersectionCompactTimelineRow(
              primaryText: displayReason.primaryText,
              spans: displayReason.primarySpans,
              iconKey: displayReason.iconKey,
              sourceRef: _sourceRefFor(displayReason),
              dimension: displayReason.dimension,
              tone: displayReason.tone,
              typeIconUrl: displayReason.typeVisual?.imageUrl ?? '',
              lifecycleState: displayReason.lifecycleState,
              onTap: () => _openReason(displayReason),
              onSpanTap: (span) => _onSpanTap(displayReason, span),
              onNegativeFeedback: () => _onNegativeFeedback(displayReason),
            ),
          ),
    ];
  }

  /// 交集主体冷却主键：与云侧 coolKey()（ActionTargetID，缺省 RelationObjectID）同源，
  /// 保证端上报的 subjectId 命中 Feed 负反馈过滤集（rec:ineg）。
  String _subjectIdFor(IntersectionReason reason) {
    final target = reason.actionTargetId.trim();
    if (target.isNotEmpty) return target;
    return reason.relationObjectId.trim();
  }

  /// 收件箱交集条目负反馈真实入口（F 推荐差异化）：长按 → action sheet「不感兴趣」→
  /// trackIntersectionFeedback（feedbackKind ∈ registry 闭集，端云同源），驱动云侧
  /// rec:ineg 冷却，命中 subject 冷却期内不再推荐。归因键与曝光/点击同源，负反馈可下钻。
  Future<void> _onNegativeFeedback(IntersectionReason reason) async {
    final subjectId = _subjectIdFor(reason);
    if (subjectId.isEmpty) return;
    final selected = await showAppActionSheet<String>(
      context,
      sections: <AppActionSheetSection<String>>[
        AppActionSheetSection<String>(
          items: <AppActionSheetItem<String>>[
            AppActionSheetItem<String>(
              label: ContentText.notInterested,
              value: intersectionFeedbackKindNotInterested,
              icon: CupertinoIcons.hand_thumbsdown,
              isDestructive: true,
            ),
          ],
        ),
      ],
    );
    if (selected == null || !mounted) return;
    ref
        .read(contentBehaviorTrackerProvider)
        .trackIntersectionFeedback(
          subjectId,
          feedbackKind: selected,
          intersectionId: reason.intersectionId,
          intersectionDimension: reason.dimension,
          intersectionClass: reason.intersectionClass,
          intersectionSourceRef: _sourceRefFor(reason),
        );
    if (mounted) {
      AppToast.show(
        context,
        DiscoveryFeedText.feedNegativeFeedbackNotInterested,
      );
    }
  }

  List<IntersectionReason> _visibleItems(List<IntersectionReason> raw) {
    final factItems = raw.where((item) => item.intersectionClass == 'fact');
    final filtered = factItems
        .where((item) {
          if (displayReadyIntersectionReason(item) == null) {
            return false;
          }
          if (widget.intersectionId.trim().isNotEmpty &&
              item.intersectionId != widget.intersectionId.trim()) {
            return false;
          }
          if (_selectedIntersectionFilter == 'all') return true;
          return _matchesFilter(item, _selectedIntersectionFilter);
        })
        .toList(growable: false);
    return filtered;
  }

  /// 端侧维度谓词：与云侧 `reasonHasDimension` 同口径——reason 维度命中，或任一
  /// intersectionPoint 维度命中（point 维度缺省回落 reason 维度）。
  ///
  /// 云侧已按同一谓词收窄，这里只兜住「缓存里还留着上一次筛选结果」的过渡帧，
  /// 不做任何 objectKind 与 dimension 的混合匹配（那会让维度筛选变成对象类型筛选）。
  bool _matchesFilter(IntersectionReason item, String dimension) {
    if (item.dimension == dimension) return true;
    for (final point in item.intersectionPoints) {
      final pointDimension = point.dimension.trim().isEmpty
          ? item.dimension
          : point.dimension;
      if (pointDimension == dimension) return true;
    }
    return false;
  }

  void _onSpanTap(IntersectionReason reason, IntersectionTextSpan span) {
    if (span.role == 'count') {
      context.push(
        AppRoutePaths.myIntersections(
          dimension: reason.dimension,
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
      objectType: reason.objectKind,
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
  final resolved = resolvedIntersectionReasonKind(reason).trim();
  if (resolved.isNotEmpty) {
    return resolved;
  }
  return reason.source.trim();
}

enum _IntersectionDetailTab { intersections, impact }

const Duration _navSwitchIndicatorDuration = Duration(milliseconds: 160);

class _IntersectionNavSwitch extends StatelessWidget {
  const _IntersectionNavSwitch({
    required this.selected,
    required this.onSelected,
  });

  final _IntersectionDetailTab selected;
  final ValueChanged<_IntersectionDetailTab> onSelected;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        _IntersectionNavSwitchItem(
          label: ProfileText.profileTabIntersection,
          selected: selected == _IntersectionDetailTab.intersections,
          onTap: () => onSelected(_IntersectionDetailTab.intersections),
        ),
        SizedBox(width: AppSpacing.lg),
        _IntersectionNavSwitchItem(
          label: ProfileText.profileTabImpact,
          selected: selected == _IntersectionDetailTab.impact,
          onTap: () => onSelected(_IntersectionDetailTab.impact),
        ),
      ],
    );
  }
}

class _IntersectionNavSwitchItem extends StatelessWidget {
  const _IntersectionNavSwitchItem({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected
        ? AppColors.iosAccent(context)
        : AppColors.iosSecondaryLabel(context);
    return Semantics(
      button: true,
      selected: selected,
      child: CupertinoButton(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.xs),
        minimumSize: Size(
          AppSpacing.minInteractiveSize,
          AppSpacing.minInteractiveSize,
        ),
        onPressed: selected ? () {} : onTap,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosNavTitle,
                fontWeight: AppTypography.regular,
                color: color,
              ),
            ),
            SizedBox(height: AppSpacing.xs),
            AnimatedContainer(
              duration: _navSwitchIndicatorDuration,
              width: selected ? AppSpacing.thirtySix : AppSpacing.zero,
              height: AppSpacing.two,
              decoration: BoxDecoration(
                color: AppColors.iosAccent(context),
                borderRadius: BorderRadius.circular(AppSpacing.radiusTwo),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
