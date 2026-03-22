// ignore_for_file: unnecessary_underscores

import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/post/post_preview_card.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 圈子页
///
/// 1:1 复制自 趣我圈2026/src CirclesFeed.tsx → CirclesChannel → DiscoveryView
/// 兴趣维度 CATEGORY_CONFIG、推荐圈子 RecommendedCirclesSection、活动 ActivityCard、
/// 子分类 SubCategoryBar、瀑布流 DiscoveryPostCard；创建圈子 FAB。
class CirclesPage extends ConsumerStatefulWidget {
  const CirclesPage({super.key});

  @override
  ConsumerState<CirclesPage> createState() => _CirclesPageState();
}

class _CirclesPageState extends ConsumerState<CirclesPage>
    with AutomaticKeepAliveClientMixin {
  static const double _circleCoverAspectRatio = 4 / 3;
  static const String _channelPrefsKey = 'circles.selected_channels.v1';
  static const String _expandedMenuMineId = '__mine__';
  static const String _expandedMenuAllId = '__all__';
  static const Set<String> _defaultUnselectedChannelIds = <String>{
    'car',
    'humanity',
    'sports',
  };
  static const List<String> _fixedCategoryOrder = <String>['following', 'all'];
  static const Set<String> _myCircleIds = <String>{
    'c-photo-owner',
    'c-tech-admin',
    'c1',
    'c2',
    'c3',
    'c-human-1',
  };

  String _selectedDimension = 'all';
  String _selectedSubCategory = UITextConstants.circleSubAll;
  String _selectedExpandedMenuId = _expandedMenuAllId;
  bool _isChannelPanelOpen = false;
  String? _draggingChannelId;
  List<String>? _selectedCategoryIds;
  final Map<String, String> _subCategoryByDimension = {};
  late PageController _primaryPageController;
  bool _routeContextApplied = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_routeContextApplied) return;
    _routeContextApplied = true;

    final params = _routeQueryParameters;
    final dimensionId = params['category'];
    final requestedMode = params['mode'];
    final requestedSub = params['sub'];

    if (dimensionId != null &&
        _allCategories.any((entry) => entry['id'] == dimensionId)) {
      _selectedDimension = dimensionId;
    }

    final menuIds = _expandedMenuItemsFor(
      _selectedDimension,
    ).map((entry) => entry.id).toSet();
    if (requestedMode == 'mine') {
      _selectedExpandedMenuId = _expandedMenuMineId;
    } else if (requestedSub != null && menuIds.contains(requestedSub)) {
      _selectedExpandedMenuId = requestedSub;
    } else {
      _selectedExpandedMenuId = _expandedMenuAllId;
    }

    _selectedSubCategory =
        _subCategoryByDimension[_selectedDimension] ??
        UITextConstants.circleSubAll;
  }

  void _recordCirclesVisit(String dimensionId) {
    ref
        .read(visitRecorderServiceProvider)
        .recordVisit(VisitTarget.page('circles_$dimensionId'));
  }

  @override
  void initState() {
    super.initState();
    _primaryPageController = PageController(
      initialPage: _primaryTabIds
          .indexOf(_selectedDimension)
          .clamp(0, _primaryTabIds.length - 1),
    );
    unawaited(_restoreChannelSelection());
    _recordCirclesVisit(_selectedDimension);
    unawaited(_loadCirclesFromRepo());
  }

  @override
  void dispose() {
    _primaryPageController.dispose();
    super.dispose();
  }

  /// 与 DiscoveryView myCategories 一致：关注 + CATEGORY_CONFIG
  List<Map<String, String>> get _allCategories {
    final config = CircleMockData.categoryConfig;
    final list = <Map<String, String>>[];
    final seen = <String>{};
    void addCategory(String id, String label) {
      if (!seen.add(id)) return;
      list.add({'id': id, 'label': label});
    }

    // 固定频道始终放在最前，并且不允许在后续配置中重复注入。
    addCategory('following', '关注');
    addCategory('all', (config['all']?['label'] as String?) ?? '推荐');

    for (final entry in config.entries) {
      final id = entry.key;
      if (_fixedCategoryOrder.contains(id)) {
        continue;
      }
      addCategory(id, entry.value['label'] as String);
    }
    return list;
  }

  Map<String, String> get _categoryLabelMap {
    return {for (final item in _allCategories) item['id']!: item['label']!};
  }

  List<String> get _fixedCategoryIds {
    final allIds = _allCategories.map((entry) => entry['id']!).toSet();
    return _fixedCategoryOrder.where(allIds.contains).toList(growable: false);
  }

  List<String> get _manageableAllCategoryIds {
    final fixedSet = _fixedCategoryIds.toSet();
    return _allCategories
        .map((entry) => entry['id']!)
        .where((id) => !fixedSet.contains(id))
        .toList(growable: false);
  }

  List<String> get _defaultSelectedCategoryIds {
    return _manageableAllCategoryIds
        .where((id) => !_defaultUnselectedChannelIds.contains(id))
        .toList(growable: false);
  }

  List<String> _normalizedSelectedCategoryIds(List<String>? source) {
    final allIds = _manageableAllCategoryIds;
    final allIdSet = allIds.toSet();
    final selected = <String>[];
    for (final id in source ?? _defaultSelectedCategoryIds) {
      if (allIdSet.contains(id) && !selected.contains(id)) {
        selected.add(id);
      }
    }
    if (selected.isEmpty) {
      selected.addAll(_defaultSelectedCategoryIds);
    }
    // 配置新增频道时默认归入未选，避免打断既有排序。
    if (source == null) {
      return selected;
    }
    return selected;
  }

  Future<void> _restoreChannelSelection() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getStringList(_channelPrefsKey);
    final normalized = _normalizedSelectedCategoryIds(stored);
    if (!mounted) return;
    setState(() {
      _selectedCategoryIds = normalized;
      if (!_primaryTabIds.contains(_selectedDimension)) {
        _selectedDimension = _primaryTabIds.first;
        _selectedSubCategory =
            _subCategoryByDimension[_selectedDimension] ??
            UITextConstants.circleSubAll;
      }
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _syncPrimaryPageWithActiveTab(animate: false);
    });
  }

  Future<void> _persistChannelSelection() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_channelPrefsKey, _manageableSelectedCategoryIds);
  }

  void _syncPrimaryPageWithActiveTab({required bool animate}) {
    final index = _primaryTabIds.indexOf(_selectedDimension);
    if (index < 0 || !_primaryPageController.hasClients) return;
    final current =
        (_primaryPageController.page ??
                _primaryPageController.initialPage.toDouble())
            .round();
    if (current == index) return;
    if (animate) {
      _primaryPageController.animateToPage(
        index,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOut,
      );
    } else {
      _primaryPageController.jumpToPage(index);
    }
  }

  void _applySelectedCategoryIds(
    List<String> nextIds, {
    required bool persist,
    bool closePanel = false,
  }) {
    final normalized = _normalizedSelectedCategoryIds(nextIds);
    setState(() {
      _selectedCategoryIds = normalized;
      if (!_primaryTabIds.contains(_selectedDimension)) {
        _selectedDimension = _primaryTabIds.first;
        _selectedSubCategory =
            _subCategoryByDimension[_selectedDimension] ??
            UITextConstants.circleSubAll;
      }
      if (closePanel) {
        _isChannelPanelOpen = false;
      }
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _syncPrimaryPageWithActiveTab(animate: false);
    });
    if (persist) {
      unawaited(_persistChannelSelection());
    }
  }

  void _moveToUnselected(String id) {
    final selected = List<String>.from(_manageableSelectedCategoryIds);
    if (!selected.contains(id) || selected.length <= 1) return;
    selected.remove(id);
    _applySelectedCategoryIds(selected, persist: true);
  }

  void _moveToSelected(String id) {
    final selected = List<String>.from(_manageableSelectedCategoryIds);
    if (selected.contains(id)) return;
    selected.add(id);
    _applySelectedCategoryIds(selected, persist: true);
  }

  void _reorderSelectedBefore(String sourceId, String targetId) {
    if (sourceId == targetId) return;
    final selected = List<String>.from(_manageableSelectedCategoryIds);
    final sourceIndex = selected.indexOf(sourceId);
    final targetIndex = selected.indexOf(targetId);
    if (sourceIndex < 0 || targetIndex < 0) return;
    final removed = selected.removeAt(sourceIndex);
    final nextIndex = sourceIndex < targetIndex ? targetIndex - 1 : targetIndex;
    selected.insert(nextIndex, removed);
    _applySelectedCategoryIds(selected, persist: true);
  }

  void _toggleChannelPanel() {
    setState(() {
      _isChannelPanelOpen = !_isChannelPanelOpen;
    });
  }

  List<Map<String, dynamic>> _repoCircles = [];
  bool _circlesLoaded = false;

  Future<void> _loadCirclesFromRepo() async {
    try {
      final repo = ref.read(circleRepositoryProvider);
      final data = await repo.listCircles();
      if (mounted) {
        setState(() {
          _repoCircles = data;
          _circlesLoaded = true;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _repoCircles = CircleMockData.circles;
          _circlesLoaded = true;
        });
      }
    }
  }

  List<Map<String, dynamic>> _filteredCirclesFor(String dimensionId) {
    final circles = _circlesLoaded ? _repoCircles : CircleMockData.circles;
    if (dimensionId == 'all') return circles;
    return circles.where((c) => c['categoryId'] == dimensionId).toList();
  }

  List<Map<String, dynamic>> get _filteredCircles =>
      _filteredCirclesFor(_selectedDimension);

  List<Map<String, dynamic>> _filteredActivitiesFor(String dimensionId) {
    final activities = CircleMockData.activities;
    if (dimensionId == 'all') return activities;
    final label =
        CircleMockData.categoryConfig[dimensionId]?['label'] as String? ?? '';
    return activities
        .where((a) => (a['circleName'] as String).contains(label))
        .toList();
  }

  List<Map<String, dynamic>> get _filteredActivities =>
      _filteredActivitiesFor(_selectedDimension);

  List<String> get _currentSubCategories {
    final config = CircleMockData.categoryConfig[_selectedDimension];
    if (config == null) return [];
    final sub = config['subCategories'] as List<dynamic>? ?? [];
    return sub
        .map((e) => e.toString())
        .where((s) => s != '综合' && s != UITextConstants.circleSubAll)
        .toList();
  }

  List<Map<String, dynamic>> _discoveryPostsFor(
    String dimensionId,
    String subCategory,
  ) {
    final circles = _filteredCirclesFor(dimensionId);
    final poolCircles = circles.isEmpty ? CircleMockData.circles : circles;
    final filtered = subCategory == UITextConstants.circleSubAll
        ? poolCircles
        : poolCircles.where((c) => c['subCategory'] == subCategory).toList();
    final pool = filtered.isEmpty ? poolCircles : filtered;
    final urls = [
      'https://images.unsplash.com/photo-1617634667039-8e4cb277ab46?w=800&fit=crop',
      'https://images.unsplash.com/photo-1551024601-bec78aea704b?w=800&fit=crop',
      'https://images.unsplash.com/photo-1519662978799-2f05096d3636?w=800&fit=crop',
      'https://images.unsplash.com/photo-1528543606781-2f6e6857f318?w=800&fit=crop',
      'https://images.unsplash.com/photo-1735820474275-dd0ff4f28d71?w=800&fit=crop',
    ];
    return List.generate(20, (i) {
      final circle = pool[i % pool.length];
      final type = i % 3 == 0
          ? 'video'
          : i % 3 == 1
          ? 'article'
          : 'image';
      return {
        'id': 'dp-$i-${circle['id']}',
        'image': urls[i % 5],
        'title':
            '[${circle['subCategory'] ?? '精选'}] ${circle['name']} 的内容分享 #${i + 1}',
        'user': {
          'name': 'User_$i',
          'avatar': 'https://api.dicebear.com/7.x/avataaars/png?seed=$i',
        },
        'likes': 24 + i * 5,
        'comments': 2 + i,
        'shares': 1 + (i ~/ 2),
        'bookmarks': 3 + (i % 5),
        'circleName': circle['name'],
        'type': type,
      };
    });
  }

  List<Map<String, dynamic>> get _discoveryPosts =>
      _discoveryPostsFor(_selectedDimension, _selectedSubCategory);

  List<String> get _manageableSelectedCategoryIds =>
      (_selectedCategoryIds ?? _defaultSelectedCategoryIds).toList(
        growable: false,
      );

  List<String> get _primaryTabIds => <String>[
    ..._fixedCategoryIds,
    ..._manageableSelectedCategoryIds,
  ];

  List<Map<String, String>> get _selectedCategories {
    final labelMap = _categoryLabelMap;
    return _primaryTabIds
        .map((id) => <String, String>{'id': id, 'label': labelMap[id] ?? id})
        .toList(growable: false);
  }

  List<String> get _unselectedCategoryIds {
    final selectedSet = _manageableSelectedCategoryIds.toSet();
    return _manageableAllCategoryIds
        .where((id) => !selectedSet.contains(id))
        .toList(growable: false);
  }

  List<String> _getSubCategoriesFor(String dimensionId) {
    final config = CircleMockData.categoryConfig[dimensionId];
    if (config == null) return [];
    final sub = config['subCategories'] as List<dynamic>? ?? [];
    return sub
        .map((e) => e.toString())
        .where((s) => s != '综合' && s != UITextConstants.circleSubAll)
        .toList();
  }

  List<String> get _secondaryTabIds => [
    UITextConstants.circleSubAll,
    ..._currentSubCategories,
  ];

  void _switchPrimaryByDelta(int delta) {
    final ids = _primaryTabIds;
    final currentIndex = ids.indexOf(_selectedDimension);
    if (currentIndex < 0) return;
    final nextIndex = currentIndex + delta;
    if (nextIndex < 0 || nextIndex >= ids.length) {
      HapticFeedback.selectionClick();
      return;
    }
    final nextId = ids[nextIndex];
    setState(() {
      _selectedDimension = nextId;
      _selectedSubCategory =
          _subCategoryByDimension[nextId] ?? UITextConstants.circleSubAll;
      _recordCirclesVisit(nextId);
    });
    if (_primaryPageController.hasClients) {
      _primaryPageController.animateToPage(
        nextIndex,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeInOut,
      );
    }
  }

  void _switchSecondaryByDelta(int delta) {
    final ids = _secondaryTabIds;
    final currentIndex = ids.indexOf(_selectedSubCategory);
    if (currentIndex < 0) return;
    final nextIndex = currentIndex + delta;
    if (nextIndex < 0 || nextIndex >= ids.length) {
      HapticFeedback.selectionClick();
      return;
    }
    setState(() {
      _selectedSubCategory = ids[nextIndex];
      _subCategoryByDimension[_selectedDimension] = ids[nextIndex];
    });
  }

  void _switchSecondaryByDeltaFor(String dimensionId, int delta) {
    final ids = [
      UITextConstants.circleSubAll,
      ..._getSubCategoriesFor(dimensionId),
    ];
    if (ids.length <= 1) return;
    final current =
        _subCategoryByDimension[dimensionId] ?? UITextConstants.circleSubAll;
    final currentIndex = ids.indexOf(current);
    if (currentIndex < 0) return;
    final nextIndex = currentIndex + delta;
    if (nextIndex < 0 || nextIndex >= ids.length) {
      HapticFeedback.selectionClick();
      return;
    }
    final next = ids[nextIndex];
    setState(() {
      _subCategoryByDimension[dimensionId] = next;
      if (dimensionId == _selectedDimension) {
        _selectedSubCategory = next;
      }
    });
  }

  void _onPrimaryDragEnd(DragEndDetails details) {
    final velocity = details.primaryVelocity ?? 0;
    if (velocity.abs() < 220) return;
    _switchPrimaryByDelta(velocity < 0 ? 1 : -1);
  }

  void _onSecondaryDragEnd(DragEndDetails details) {
    final velocity = details.primaryVelocity ?? 0;
    if (velocity.abs() < 220) return;
    _switchSecondaryByDelta(velocity < 0 ? 1 : -1);
  }

  Map<String, String> get _routeQueryParameters {
    try {
      return GoRouterState.of(context).uri.queryParameters;
    } catch (_) {
      return const <String, String>{};
    }
  }

  void _handleExpandedPageBack() {
    final router = GoRouter.maybeOf(context);
    if (router != null && router.canPop()) {
      context.pop();
      return;
    }
    Navigator.of(context).maybePop();
  }

  double _measureSingleLineTextHeight(BuildContext context, TextStyle style) {
    final painter = TextPainter(
      text: TextSpan(text: 'Hg', style: style),
      textDirection: Directionality.of(context),
      textScaler: MediaQuery.textScalerOf(context),
      maxLines: 1,
    )..layout();
    return painter.height;
  }

  double _circleCardWidth(BuildContext context) {
    return AppSpacing.responsiveValue(
      context,
      compact: AppSpacing.bottomNavHeight * 1.5,
      regular: AppSpacing.bottomNavHeight * 1.65,
      expanded: AppSpacing.bottomNavHeight * 1.85,
    );
  }

  double _circleCardRailHeight(BuildContext context) {
    final cardWidth = _circleCardWidth(context);
    final coverHeight = cardWidth / _circleCoverAspectRatio;
    final labelHeight = _measureSingleLineTextHeight(
      context,
      const TextStyle(
        fontSize: AppTypography.iosFootnote,
        fontWeight: AppTypography.medium,
      ),
    );
    return coverHeight + AppSpacing.intraGroupXs + labelHeight + AppSpacing.sm;
  }

  double _channelPanelTileHeight(BuildContext context) {
    final labelHeight = _measureSingleLineTextHeight(
      context,
      const TextStyle(
        fontSize: AppTypography.base,
        fontWeight: AppTypography.medium,
      ),
    );
    final adaptiveHeight = labelHeight + (AppSpacing.containerSm * 2);
    return adaptiveHeight > AppSpacing.bottomNavHeight
        ? adaptiveHeight
        : AppSpacing.bottomNavHeight;
  }

  List<_ExpandedCircleMenuItem> _expandedMenuItemsFor(String dimensionId) {
    final subCategories = _getSubCategoriesFor(
      dimensionId,
    ).where((item) => item != '热门').toList(growable: false);
    final items = <_ExpandedCircleMenuItem>[
      _ExpandedCircleMenuItem(
        id: _expandedMenuMineId,
        label: UITextConstants.homeCirclesMy,
      ),
      _ExpandedCircleMenuItem(
        id: _expandedMenuAllId,
        label: UITextConstants.circleSubAll,
      ),
      ...subCategories.map(
        (item) => _ExpandedCircleMenuItem(id: item, label: item),
      ),
    ];
    final seen = <String>{};
    return items.where((item) => seen.add(item.id)).toList(growable: false);
  }

  List<Map<String, dynamic>> _expandedCirclesForSelectedMenu() {
    final source = List<Map<String, dynamic>>.from(
      _filteredCirclesFor(_selectedDimension),
    );
    source.sort((a, b) {
      final right = (b['memberCount'] as num?)?.toInt() ?? 0;
      final left = (a['memberCount'] as num?)?.toInt() ?? 0;
      return right.compareTo(left);
    });

    if (_selectedExpandedMenuId == _expandedMenuMineId) {
      return source
          .where((item) => _myCircleIds.contains(item['id']?.toString() ?? ''))
          .toList(growable: false);
    }
    if (_selectedExpandedMenuId == _expandedMenuAllId) {
      return source;
    }
    return source
        .where(
          (item) => item['subCategory']?.toString() == _selectedExpandedMenuId,
        )
        .toList(growable: false);
  }

  String _expandedPageTitle() {
    final label = _categoryLabelMap[_selectedDimension] ?? '圈子';
    return _selectedDimension == 'all' ? '圈子' : '$label圈子';
  }

  String _expandedSectionTitle() {
    if (_selectedExpandedMenuId == _expandedMenuMineId) {
      return '我的圈子';
    }
    if (_selectedExpandedMenuId == _expandedMenuAllId) {
      return _expandedPageTitle();
    }
    return '$_selectedExpandedMenuId 圈子';
  }

  bool _isMyCircle(Map<String, dynamic> circle) {
    return _myCircleIds.contains(circle['id']?.toString() ?? '');
  }

  String _formatCircleMetric(num? rawCount, {required String suffix}) {
    final count = rawCount?.toInt() ?? 0;
    if (count >= 10000) {
      final scaled = count / 10000;
      final value = scaled >= 100 || scaled == scaled.roundToDouble()
          ? scaled.toStringAsFixed(0)
          : scaled.toStringAsFixed(1);
      return '$value万$suffix';
    }
    return '$count$suffix';
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final isDark = ref.watch(isDarkProvider);
    final bgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.pageBackground,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    final surfaceColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final menuBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final accentBlue = CupertinoColors.activeBlue.resolveFrom(context);
    final menuItems = _expandedMenuItemsFor(_selectedDimension);
    final circles = _expandedCirclesForSelectedMenu();

    return AppScaffold(
      backgroundColor: bgPrimary,
      child: SafeArea(
        bottom: false,
        child: Column(
          children: [
            Container(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerSm,
                AppSpacing.intraGroupSm,
                AppSpacing.containerSm,
                AppSpacing.containerSm,
              ),
              decoration: BoxDecoration(
                color: surfaceColor,
                border: Border(
                  bottom: BorderSide(
                    color: borderColor.withValues(alpha: 0.18),
                    width: AppSpacing.hairline,
                  ),
                ),
              ),
              child: Row(
                children: [
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    minimumSize: Size.zero,
                    onPressed: _handleExpandedPageBack,
                    child: Icon(
                      CupertinoIcons.back,
                      color: fgPrimary,
                      size: AppSpacing.iconMedium,
                    ),
                  ),
                  Expanded(
                    child: Center(
                      child: Text(
                        _expandedPageTitle(),
                        style: TextStyle(
                          fontSize: AppTypography.iosTitle3,
                          fontWeight: AppTypography.semiBold,
                          color: fgPrimary,
                        ),
                      ),
                    ),
                  ),
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    minimumSize: Size.zero,
                    onPressed: () => GlobalSearchLauncher.open(
                      context,
                      launchContext: SearchLaunchContext(
                        entrySurfaceId: AppRoutePaths.circles,
                        initialScope: SearchScope.circles,
                      ),
                    ),
                    child: Icon(
                      CupertinoIcons.search,
                      color: fgPrimary,
                      size: AppSpacing.iconMedium,
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: Row(
                children: [
                  Container(
                    width: AppSpacing.largeButtonSize * 2,
                    color: menuBackground,
                    child: ListView.separated(
                      padding: EdgeInsets.fromLTRB(
                        AppSpacing.intraGroupXs,
                        AppSpacing.containerMd,
                        AppSpacing.intraGroupXs,
                        AppSpacing.containerMd,
                      ),
                      itemCount: menuItems.length,
                      separatorBuilder: (_, __) =>
                          SizedBox(height: AppSpacing.intraGroupSm),
                      itemBuilder: (context, index) {
                        final item = menuItems[index];
                        final selected = item.id == _selectedExpandedMenuId;
                        return CupertinoButton(
                          padding: EdgeInsets.zero,
                          minimumSize: Size.zero,
                          onPressed: () {
                            setState(() {
                              _selectedExpandedMenuId = item.id;
                              if (item.id == _expandedMenuAllId) {
                                _selectedSubCategory =
                                    UITextConstants.circleSubAll;
                              } else if (item.id != _expandedMenuMineId) {
                                _selectedSubCategory = item.label;
                                _subCategoryByDimension[_selectedDimension] =
                                    item.label;
                              }
                            });
                          },
                          child: AnimatedContainer(
                            duration: const Duration(milliseconds: 180),
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.intraGroupSm,
                              vertical: AppSpacing.containerSm,
                            ),
                            decoration: BoxDecoration(
                              color: selected
                                  ? surfaceColor
                                  : Colors.transparent,
                              borderRadius: BorderRadius.circular(
                                AppSpacing.largeBorderRadius,
                              ),
                              border: selected
                                  ? Border.all(
                                      color: accentBlue.withValues(alpha: 0.18),
                                    )
                                  : null,
                            ),
                            child: Row(
                              children: [
                                AnimatedContainer(
                                  duration: const Duration(milliseconds: 180),
                                  width: AppSpacing.three,
                                  height: AppSpacing.largeButtonSize,
                                  decoration: BoxDecoration(
                                    color: selected
                                        ? accentBlue
                                        : Colors.transparent,
                                    borderRadius: BorderRadius.circular(
                                      AppSpacing.circularBorderRadius,
                                    ),
                                  ),
                                ),
                                SizedBox(width: AppSpacing.sm),
                                Expanded(
                                  child: Text(
                                    item.label,
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: AppTypography.smPlus,
                                      fontWeight: selected
                                          ? AppTypography.semiBold
                                          : AppTypography.medium,
                                      color: selected ? accentBlue : fgPrimary,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                  VerticalDivider(
                    width: AppSpacing.hairline,
                    thickness: AppSpacing.hairline,
                    color: borderColor.withValues(alpha: 0.16),
                  ),
                  Expanded(
                    child: circles.isEmpty
                        ? Center(
                            child: Text(
                              '${_expandedSectionTitle()} ${UITextConstants.noData}',
                              style: TextStyle(
                                fontSize: AppTypography.base,
                                color: fgSecondary,
                              ),
                            ),
                          )
                        : ListView.separated(
                            padding: EdgeInsets.fromLTRB(
                              AppSpacing.containerMd,
                              AppSpacing.containerMd,
                              AppSpacing.containerMd,
                              AppSpacing.containerLg +
                                  MediaQuery.viewPaddingOf(context).bottom,
                            ),
                            itemCount: circles.length,
                            separatorBuilder: (_, __) => Divider(
                              height: AppSpacing.containerMd,
                              color: borderColor.withValues(alpha: 0.14),
                            ),
                            itemBuilder: (context, index) {
                              final circle = circles[index];
                              final joined = _isMyCircle(circle);
                              final coverUrl =
                                  (circle['coverUrl'] ??
                                          circle['cover'] ??
                                          circle['avatar'] ??
                                          '')
                                      .toString();
                              final name = (circle['name'] ?? '圈子').toString();
                              final members = _formatCircleMetric(
                                circle['memberCount'] as num?,
                                suffix: '人',
                              );
                              final posts = _formatCircleMetric(
                                circle['postCount'] as num?,
                                suffix: '件作品',
                              );
                              return CupertinoButton(
                                padding: EdgeInsets.zero,
                                minimumSize: Size.zero,
                                onPressed: () => context.push(
                                  AppRoutePaths.circleDetail(
                                    id: circle['id']?.toString() ?? '',
                                  ),
                                ),
                                child: Row(
                                  children: [
                                    ClipRRect(
                                      borderRadius: BorderRadius.circular(
                                        AppSpacing.contentPreviewCornerRadius,
                                      ),
                                      child: SizedBox(
                                        width: AppSpacing.bottomNavHeight + 8,
                                        height: AppSpacing.bottomNavHeight + 8,
                                        child: coverUrl.isNotEmpty
                                            ? Image.network(
                                                coverUrl,
                                                fit: BoxFit.cover,
                                                errorBuilder: (_, _, _) =>
                                                    ColoredBox(
                                                      color: fgSecondary
                                                          .withValues(
                                                            alpha: 0.12,
                                                          ),
                                                      child: Icon(
                                                        CupertinoIcons
                                                            .person_3_fill,
                                                        color: fgSecondary,
                                                      ),
                                                    ),
                                              )
                                            : ColoredBox(
                                                color: fgSecondary.withValues(
                                                  alpha: 0.12,
                                                ),
                                                child: Icon(
                                                  CupertinoIcons.person_3_fill,
                                                  color: fgSecondary,
                                                ),
                                              ),
                                      ),
                                    ),
                                    SizedBox(width: AppSpacing.containerSm),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            name,
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                            style: TextStyle(
                                              fontSize:
                                                  AppTypography.iosSubheadline,
                                              fontWeight:
                                                  AppTypography.semiBold,
                                              color: fgPrimary,
                                            ),
                                          ),
                                          SizedBox(
                                            height: AppSpacing.intraGroupXs,
                                          ),
                                          Text(
                                            '$members · $posts',
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                            style: TextStyle(
                                              fontSize:
                                                  AppTypography.iosFootnote,
                                              color: fgSecondary,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                    SizedBox(width: AppSpacing.sm),
                                    Container(
                                      padding: EdgeInsets.symmetric(
                                        horizontal: AppSpacing.containerSm,
                                        vertical: AppSpacing.intraGroupSm,
                                      ),
                                      decoration: BoxDecoration(
                                        color: joined
                                            ? accentBlue.withValues(alpha: 0.12)
                                            : accentBlue,
                                        borderRadius: BorderRadius.circular(
                                          AppSpacing.circularBorderRadius,
                                        ),
                                      ),
                                      child: Text(
                                        joined ? '已加入' : '加入',
                                        style: TextStyle(
                                          fontSize: AppTypography.sm,
                                          fontWeight: AppTypography.semiBold,
                                          color: joined
                                              ? accentBlue
                                              : Colors.white,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              );
                            },
                          ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context, bool isDark, Color fgSecondary) {
    final tabs = _selectedCategories
        .map((entry) => TabItem(id: entry['id']!, label: entry['label']!))
        .toList(growable: false);

    return Container(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.backgroundPrimary,
        ),
        border: Border(
          bottom: BorderSide(
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.borderPrimary,
            ),
            width: AppSpacing.intraGroupXs / 2,
          ),
        ),
      ),
      child: CenteredScrollableTabBar(
        tabs: tabs,
        activeTab: _selectedDimension,
        isDark: isDark,
        onTabChange: (id) {
          setState(() {
            _selectedDimension = id;
            _selectedSubCategory =
                _subCategoryByDimension[id] ?? UITextConstants.circleSubAll;
            _recordCirclesVisit(id);
          });
          final index = _primaryTabIds.indexOf(id);
          if (index >= 0 && _primaryPageController.hasClients) {
            _primaryPageController.animateToPage(
              index,
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeInOut,
            );
          }
        },
        // Tab 栏区域：手指滑动只滚动 Tab 栏，不切换 Tab
        trailingActions: [
          Padding(
            padding: EdgeInsets.only(
              right: AppSpacing.topBarTrailingButtonInset(context),
            ),
            child: SizedBox(
              width: AppSpacing.minInteractiveSize,
              height: AppSpacing.minInteractiveSize,
              child: CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: _toggleChannelPanel,
                child: Icon(
                  CupertinoIcons.line_horizontal_3_decrease,
                  size: AppSpacing.iconMedium,
                  color: fgSecondary,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildChannelPanel(
    BuildContext context,
    bool isDark, {
    double bottomInset = 0,
  }) {
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final unselectedIds = _unselectedCategoryIds;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: _toggleChannelPanel,
      child: ColoredBox(
        color: bg,
        child: SingleChildScrollView(
          physics: const BouncingScrollPhysics(
            parent: AlwaysScrollableScrollPhysics(),
          ),
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () {},
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.feedContentHorizontal(context),
                AppSpacing.containerMd,
                AppSpacing.feedContentHorizontal(context),
                AppSpacing.containerMd + bottomInset,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        UITextConstants.circleMyChannels,
                        style: TextStyle(
                          fontSize: AppTypography.lg,
                          fontWeight: AppTypography.semiBold,
                          color: fgPrimary,
                        ),
                      ),
                      SizedBox(width: AppSpacing.intraGroupSm),
                      Text(
                        UITextConstants.circleDragToSort,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: fgSecondary,
                        ),
                      ),
                      const Spacer(),
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: _toggleChannelPanel,
                        child: Text(
                          UITextConstants.done,
                          style: TextStyle(
                            fontSize: AppTypography.base,
                            fontWeight: AppTypography.medium,
                            color: AppColors.primaryColor,
                          ),
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: AppSpacing.interGroupSm),
                  _buildChannelGrid(
                    context: context,
                    channelIds: _manageableSelectedCategoryIds,
                    canRemove: true,
                    onTapIcon: _moveToUnselected,
                  ),
                  SizedBox(height: AppSpacing.interGroupLg),
                  Row(
                    children: [
                      Text(
                        UITextConstants.circleAllChannels,
                        style: TextStyle(
                          fontSize: AppTypography.lg,
                          fontWeight: AppTypography.semiBold,
                          color: fgPrimary,
                        ),
                      ),
                      SizedBox(width: AppSpacing.intraGroupSm),
                      Text(
                        UITextConstants.circleTapToAdd,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: fgSecondary,
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: AppSpacing.interGroupSm),
                  _buildChannelGrid(
                    context: context,
                    channelIds: unselectedIds,
                    canRemove: false,
                    onTapIcon: _moveToSelected,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildChannelGrid({
    required BuildContext context,
    required List<String> channelIds,
    required bool canRemove,
    required ValueChanged<String> onTapIcon,
  }) {
    final labelMap = _categoryLabelMap;
    final spacing = AppSpacing.intraGroupSm;
    final panelTileHeight = _channelPanelTileHeight(context);
    return LayoutBuilder(
      builder: (context, constraints) {
        final totalSpacing = spacing * 3;
        final tileWidth = (constraints.maxWidth - totalSpacing) / 4;
        return Wrap(
          spacing: spacing,
          runSpacing: spacing,
          children: channelIds
              .map((id) {
                final label = labelMap[id] ?? id;
                final tile = _ChannelTile(
                  width: tileWidth,
                  height: panelTileHeight,
                  label: label,
                  canRemove: canRemove,
                  isDragging: _draggingChannelId == id,
                  onIconTap: () => onTapIcon(id),
                );
                if (!canRemove) return tile;
                return SizedBox(
                  width: tileWidth,
                  height: panelTileHeight,
                  child: DragTarget<String>(
                    onWillAcceptWithDetails: (details) => details.data != id,
                    onAcceptWithDetails: (details) {
                      _reorderSelectedBefore(details.data, id);
                    },
                    builder: (context, _, __) {
                      return LongPressDraggable<String>(
                        data: id,
                        onDragStarted: () {
                          setState(() => _draggingChannelId = id);
                        },
                        onDragEnd: (_) {
                          if (mounted) {
                            setState(() => _draggingChannelId = null);
                          }
                        },
                        feedback: Material(
                          color: Colors.transparent,
                          child: _ChannelTile(
                            width: tileWidth,
                            height: panelTileHeight,
                            label: label,
                            canRemove: true,
                            isDragging: false,
                            onIconTap: () {},
                          ),
                        ),
                        childWhenDragging: Opacity(opacity: 0.2, child: tile),
                        child: tile,
                      );
                    },
                  ),
                );
              })
              .toList(growable: false),
        );
      },
    );
  }

  Widget _buildFollowingPlaceholder(Color fgSecondary) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            CupertinoIcons.person_2,
            size: AppSpacing.largeButtonSize + AppSpacing.sm,
            color: fgSecondary,
          ),
          SizedBox(height: AppSpacing.interGroupMd),
          Text(
            UITextConstants.circlesFollowingEmpty,
            style: TextStyle(
              fontSize: AppTypography.iosTitle3,
              color: fgSecondary,
            ),
          ),
        ],
      ),
    );
  }

  /// 构建指定维度（如全部、美食、旅行）的完整内容：推荐区 + 活动 + 二级分类条 + 瀑布流
  Widget _buildDimensionContent(
    BuildContext context,
    String dimensionId,
    bool isDark,
    Color fgPrimary,
    Color fgSecondary,
    Color borderColor,
  ) {
    final subCategory =
        _subCategoryByDimension[dimensionId] ?? UITextConstants.circleSubAll;
    final subCats = _getSubCategoriesFor(dimensionId);
    final circles = _filteredCirclesFor(dimensionId);
    final activities = _filteredActivitiesFor(dimensionId);
    final posts = _discoveryPostsFor(dimensionId, subCategory);

    return CustomScrollView(
      physics: const BouncingScrollPhysics(
        parent: AlwaysScrollableScrollPhysics(),
      ),
      slivers: [
        // 推荐区：二级 Tab 之上区域，水平拖拽切换一级 Tab
        SliverToBoxAdapter(
          child: GestureDetector(
            behavior: HitTestBehavior.translucent,
            onHorizontalDragEnd: _onPrimaryDragEnd,
            child: _buildRecommendedSection(
              context,
              isDark,
              fgPrimary,
              fgSecondary,
              circlesParam: circles,
            ),
          ),
        ),
        // 活动区：二级 Tab 之上区域，水平拖拽切换一级 Tab
        if (activities.isNotEmpty)
          SliverToBoxAdapter(
            child: GestureDetector(
              behavior: HitTestBehavior.translucent,
              onHorizontalDragEnd: _onPrimaryDragEnd,
              child: _buildActivities(
                context,
                isDark,
                fgSecondary,
                activitiesParam: activities,
              ),
            ),
          ),
        if (subCats.isNotEmpty)
          SliverPersistentHeader(
            floating: true,
            delegate: _SubCategoryBarDelegate(
              child: _buildSubCategoryBarContent(
                context,
                isDark,
                fgPrimary,
                fgSecondary,
                borderColor,
                subCategoriesParam: subCats,
                selectedSubParam: subCategory,
                onSubHorizontalDragEnd: (details) {
                  final velocity = details.primaryVelocity ?? 0;
                  if (velocity.abs() < 220) return;
                  _switchSecondaryByDeltaFor(
                    dimensionId,
                    velocity < 0 ? 1 : -1,
                  );
                },
                onSubTap: (s) {
                  setState(() {
                    _subCategoryByDimension[dimensionId] = s;
                    if (dimensionId == _selectedDimension) {
                      _selectedSubCategory = s;
                    }
                  });
                },
              ),
              extent: AppSpacing.subTabNavigationHeight,
            ),
          ),
        _buildDiscoveryMasonryGrid(
          context,
          isDark,
          fgPrimary,
          fgSecondary,
          postsParam: posts,
          onGridHorizontalDragEnd: subCats.isEmpty
              ? _onPrimaryDragEnd // 无二级 Tab 时，瀑布流水平拖拽切换一级 Tab
              : (details) {
                  final velocity = details.primaryVelocity ?? 0;
                  if (velocity.abs() < 220) return;
                  _switchSecondaryByDeltaFor(
                    dimensionId,
                    velocity < 0 ? 1 : -1,
                  );
                },
        ),
        SliverToBoxAdapter(
          child: Padding(
            padding: EdgeInsets.only(
              top: AppSpacing.interGroupXl,
              bottom:
                  MediaQuery.of(context).padding.bottom +
                  AppSpacing.bottomNavHeight,
            ),
            child: Center(
              child: Text(
                UITextConstants.discoveryEndHint,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: fgSecondary,
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildRecommendedSection(
    BuildContext context,
    bool isDark,
    Color fgPrimary,
    Color fgSecondary, {
    List<Map<String, dynamic>>? circlesParam,
  }) {
    final circles = circlesParam ?? _filteredCircles;
    final sectionBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceMuted,
    );
    return Container(
      color: sectionBg,
      padding: EdgeInsets.symmetric(
        vertical: AppSpacing.md,
        horizontal: AppSpacing.feedContentHorizontal(context),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                UITextConstants.circlesRecommendedTitle,
                style: TextStyle(
                  fontSize: AppTypography.iosTitle3,
                  fontWeight: AppTypography.bold,
                  color: fgPrimary,
                ),
              ),
              CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                onPressed: () {},
                child: Text(
                  UITextConstants.seeMore,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    fontWeight: AppTypography.semiBold,
                    color: AppColors.iosAccent(context),
                  ),
                ),
              ),
            ],
          ),
          SizedBox(
            height: _circleCardRailHeight(context),
            child: ListView.builder(
              scrollDirection: Axis.horizontal,
              itemCount: circles.length + 1,
              itemBuilder: (context, i) {
                if (i == circles.length) {
                  return Padding(
                    padding: EdgeInsets.only(left: AppSpacing.sm),
                    child: CupertinoButton(
                      padding: EdgeInsets.zero,
                      minimumSize: Size.zero,
                      onPressed: () {
                        AppToast.show(context, UITextConstants.createCircle);
                      },
                      child: Container(
                        width: _circleCardWidth(context),
                        decoration: BoxDecoration(
                          color: AppColorsFunctional.getColor(
                            isDark,
                            ColorType.selectionBackground,
                          ),
                          borderRadius: BorderRadius.circular(
                            AppSpacing.largeBorderRadius,
                          ),
                          border: Border.all(
                            color: AppColorsFunctional.getColor(
                              isDark,
                              ColorType.selectionBorder,
                            ),
                          ),
                        ),
                        child: Icon(
                          CupertinoIcons.add,
                          color: AppColors.iosAccent(context),
                          size: AppSpacing.iconLarge,
                        ),
                      ),
                    ),
                  );
                }
                final c = circles[i];
                return Padding(
                  padding: EdgeInsets.only(right: AppSpacing.sm),
                  child: CupertinoButton(
                    padding: EdgeInsets.zero,
                    minimumSize: Size.zero,
                    onPressed: () => context.push(
                      AppRoutePaths.circleDetail(id: '${c['id']}'),
                    ),
                    child: Column(
                      children: [
                        SizedBox(
                          width: _circleCardWidth(context),
                          child: AspectRatio(
                            aspectRatio: _circleCoverAspectRatio,
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(
                                AppSpacing.contentPreviewCornerRadius,
                              ),
                              child: Image.network(
                                c['avatar'] as String,
                                fit: BoxFit.cover,
                                errorBuilder: (context, error, stackTrace) =>
                                    Container(
                                      color: fgSecondary.withValues(alpha: 0.2),
                                      child: Icon(
                                        CupertinoIcons.person_3_fill,
                                        color: fgSecondary,
                                        size: AppSpacing.iconMedium,
                                      ),
                                    ),
                              ),
                            ),
                          ),
                        ),
                        SizedBox(height: AppSpacing.intraGroupXs),
                        SizedBox(
                          width: _circleCardWidth(context),
                          child: Text(
                            c['name'] as String,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: AppTypography.iosFootnote,
                              fontWeight: AppTypography.medium,
                              color: fgPrimary,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActivities(
    BuildContext context,
    bool isDark,
    Color fgSecondary, {
    List<Map<String, dynamic>>? activitiesParam,
  }) {
    final activities = activitiesParam ?? _filteredActivities;
    final cardBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final dividerColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.feedContentHorizontal(context),
        vertical: AppSpacing.sm,
      ),
      child: Column(
        children: activities.map((a) {
          return Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.sm),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: cardBg,
                borderRadius: BorderRadius.circular(
                  AppSpacing.largeBorderRadius,
                ),
                border: Border.all(color: dividerColor),
              ),
              child: CupertinoButton(
                padding: EdgeInsets.all(AppSpacing.sm),
                minimumSize: Size.zero,
                onPressed: () {},
                child: Row(
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(
                        AppSpacing.contentPreviewCornerRadius,
                      ),
                      child: Image.network(
                        a['image'] as String? ?? '',
                        width: AppSpacing.bottomNavHeight,
                        height: AppSpacing.bottomNavHeight,
                        fit: BoxFit.cover,
                        errorBuilder: (context, error, stackTrace) => Container(
                          width: AppSpacing.bottomNavHeight,
                          height: AppSpacing.bottomNavHeight,
                          color: fgSecondary.withValues(alpha: 0.2),
                        ),
                      ),
                    ),
                    SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            a['title'] as String,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.iosSubheadline,
                              fontWeight: AppTypography.semiBold,
                            ),
                          ),
                          Text(
                            a['circleName'] as String,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.iosFootnote,
                              color: fgSecondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  /// 二级分类条内容 — 胶囊样式 + 浅色背景工具栏
  Widget _buildSubCategoryBarContent(
    BuildContext context,
    bool isDark,
    Color fgPrimary,
    Color fgSecondary,
    Color borderColor, {
    List<String>? subCategoriesParam,
    String? selectedSubParam,
    void Function(String)? onSubTap,
    GestureDragEndCallback? onSubHorizontalDragEnd,
  }) {
    final subCats = subCategoriesParam ?? _currentSubCategories;
    final subs = [UITextConstants.circleSubAll, ...subCats];
    final selectedSub = selectedSubParam ?? _selectedSubCategory;
    final activeIndex = subs.indexOf(selectedSub);

    return Container(
      color: AppColorsFunctional.getColor(isDark, ColorType.pageBackground),
      child: GestureDetector(
        behavior: HitTestBehavior.translucent,
        onHorizontalDragEnd: onSubHorizontalDragEnd ?? _onSecondaryDragEnd,
        child: SecondaryCapsuleTabBar(
          isDark: isDark,
          tabs: subs,
          activeIndex: activeIndex < 0 ? 0 : activeIndex,
          onTap: (index) {
            final sub = subs[index];
            if (onSubTap != null) {
              onSubTap(sub);
            } else {
              setState(() => _selectedSubCategory = sub);
            }
          },
          fontSize: AppTypography.smPlus,
        ),
      ),
    );
  }

  /// 瀑布流宫格（Sliver 版本）
  Widget _buildDiscoveryMasonryGrid(
    BuildContext context,
    bool isDark,
    Color fgPrimary,
    Color fgSecondary, {
    List<Map<String, dynamic>>? postsParam,
    GestureDragEndCallback? onGridHorizontalDragEnd,
  }) {
    final posts = postsParam ?? _discoveryPosts;
    final horizontal = AppSpacing.feedContentHorizontal(context);
    return SliverPadding(
      padding: EdgeInsets.fromLTRB(
        horizontal,
        AppSpacing.containerMd,
        horizontal,
        0,
      ),
      sliver: SliverMasonryGrid.count(
        crossAxisCount: 2,
        mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
        crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
        childCount: posts.length,
        itemBuilder: (context, i) {
          final p = posts[i];
          return _DiscoveryPostCard(
            post: p,
            isDark: isDark,
            onTap: () =>
                context.push(AppRoutePaths.articleDetail(id: '${p['id']}')),
            onHorizontalDragEnd: onGridHorizontalDragEnd,
          );
        },
      ),
    );
  }
}

class _ExpandedCircleMenuItem {
  const _ExpandedCircleMenuItem({required this.id, required this.label});

  final String id;
  final String label;
}

/// 圈子瀑布流卡片：复用组件库中的 Post 预览卡片，
/// 底部插槽保留为「作者头像 + 作者名 + 点赞」。
class _DiscoveryPostCard extends StatelessWidget {
  final Map<String, dynamic> post;
  final bool isDark;
  final VoidCallback onTap;
  final GestureDragEndCallback? onHorizontalDragEnd;

  const _DiscoveryPostCard({
    required this.post,
    required this.isDark,
    required this.onTap,
    this.onHorizontalDragEnd,
  });

  /// 计算图片显示宽高比（随机模拟），最大不超过 9:16
  double get _imageAspectRatio {
    // 用 post id 的 hashCode 做伪随机
    final hash = post['id'].hashCode;
    final ratios = [1.0, 4 / 3, 3 / 4, 1 / 1, 9 / 16];
    final ratio = ratios[hash.abs() % ratios.length];
    // 最小 9/16 = 0.5625（最高竖图）
    return ratio.clamp(9.0 / 16.0, 16.0 / 9.0);
  }

  String get _coverUrl {
    final primary =
        (post['image'] ?? post['coverUrl'] ?? post['thumbnailUrl'] ?? '')
            .toString()
            .trim();
    if (primary.isNotEmpty) {
      return primary;
    }
    final imageUrls = post['imageUrls'];
    if (imageUrls is List && imageUrls.isNotEmpty) {
      return imageUrls.first.toString();
    }
    return '';
  }

  String get _bodyText {
    final candidates = <Object?>[
      post['body'],
      post['description'],
      post['content'],
      post['caption'],
    ];
    for (final candidate in candidates) {
      final text = candidate?.toString().trim() ?? '';
      if (text.isNotEmpty) {
        return text;
      }
    }
    return '';
  }

  String get _headlineText {
    final title = (post['title'] ?? '').toString().trim();
    final body = _bodyText;
    if (title.isNotEmpty) {
      return title;
    }
    if (body.isNotEmpty) {
      return body;
    }
    return '帖子';
  }

  String get _supportingText {
    final title = (post['title'] ?? '').toString().trim();
    final body = _bodyText;
    if (title.isEmpty || body.isEmpty || title == body) {
      return '';
    }
    return body;
  }

  String get _authorName {
    final user = post['user'] as Map<String, dynamic>? ?? {};
    final authorName =
        (user['name'] ??
                post['authorNickname'] ??
                post['displayName'] ??
                post['username'] ??
                post['authorId'] ??
                '')
            .toString();
    return authorName.isEmpty ? UITextConstants.unknownUser : authorName;
  }

  String? get _authorAvatarUrl {
    final user = post['user'] as Map<String, dynamic>? ?? {};
    final avatarUrl =
        (user['avatar'] ?? post['authorAvatarUrl'] ?? post['avatarUrl'] ?? '')
            .toString()
            .trim();
    return avatarUrl.isEmpty ? null : avatarUrl;
  }

  int get _likeCount {
    return (post['likes'] as num?)?.toInt() ??
        (post['likeCount'] as num?)?.toInt() ??
        0;
  }

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final gridMetaFontSize = AppTypography.responsive(
      context,
      compact: AppTypography.sm,
      regular: AppTypography.base,
      expanded: AppTypography.base,
    );

    return PostPreviewCard(
      isDark: isDark,
      title: _headlineText,
      supportingText: _supportingText,
      coverUrl: _coverUrl,
      mediaAspectRatio: _imageAspectRatio,
      showVideoBadge: post['type'] == 'video',
      onTap: onTap,
      onHorizontalDragEnd: onHorizontalDragEnd,
      footer: Row(
        children: [
          _buildUserAvatar(
            _authorAvatarUrl,
            fgSecondary,
            radius: AppSpacing.intraGroupMd,
          ),
          SizedBox(width: AppSpacing.intraGroupXs),
          Expanded(
            child: Text(
              _authorName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: fgSecondary,
              ),
            ),
          ),
          PostCardMetric(
            icon: CupertinoIcons.heart,
            iconSize: gridMetaFontSize,
            label: '$_likeCount',
            color: fgSecondary,
            textStyle: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

class _ChannelTile extends StatelessWidget {
  const _ChannelTile({
    required this.width,
    required this.height,
    required this.label,
    required this.canRemove,
    required this.isDragging,
    required this.onIconTap,
  });

  final double width;
  final double height;
  final String label;
  final bool canRemove;
  final bool isDragging;
  final VoidCallback onIconTap;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = canRemove
        ? AppColorsFunctional.getColor(isDark, ColorType.surfaceElevated)
        : AppColorsFunctional.getColor(isDark, ColorType.pageBackground);
    final borderColor = canRemove
        ? Colors.transparent
        : AppColorsFunctional.getColor(
            isDark,
            ColorType.separatorSubtle,
          ).withValues(alpha: 0.5);
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final iconBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundTertiary,
    );

    return SizedBox(
      width: width,
      height: height,
      child: Opacity(
        opacity: isDragging ? 0.45 : 1,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Container(
              width: width,
              height: height,
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              decoration: BoxDecoration(
                color: bg,
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                border: Border.all(color: borderColor),
              ),
              child: Center(
                child: Text(
                  canRemove ? label : '+ $label',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    color: fg,
                    fontWeight: AppTypography.medium,
                  ),
                ),
              ),
            ),
            if (canRemove)
              Positioned(
                top: -AppSpacing.intraGroupXs,
                right: -AppSpacing.intraGroupXs,
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: onIconTap,
                  child: Container(
                    width: AppSpacing.minInteractiveSize / 2,
                    height: AppSpacing.minInteractiveSize / 2,
                    decoration: BoxDecoration(
                      color: iconBg,
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      CupertinoIcons.xmark,
                      size: AppSpacing.iconSmall,
                      color: AppColorsFunctional.getColor(
                        isDark,
                        ColorType.foregroundSecondary,
                      ),
                    ),
                  ),
                ),
              )
            else
              Positioned.fill(
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                  onPressed: onIconTap,
                  child: const SizedBox.expand(),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// 浮动二级分类条的 delegate
class _SubCategoryBarDelegate extends SliverPersistentHeaderDelegate {
  final Widget child;
  final double extent;

  _SubCategoryBarDelegate({required this.child, required this.extent});

  @override
  double get maxExtent => extent;

  @override
  double get minExtent => extent;

  @override
  Widget build(
    BuildContext context,
    double shrinkOffset,
    bool overlapsContent,
  ) {
    return child;
  }

  @override
  bool shouldRebuild(covariant _SubCategoryBarDelegate oldDelegate) => true;
}

/// 用户头像：网络图加载失败时显示占位，避免 Invalid image data 异常。供圈子页与宫格卡片共用。
Widget _buildUserAvatar(
  String? avatarUrl,
  Color fgSecondary, {
  required double radius,
}) {
  final size = radius * 2;
  if (avatarUrl == null || avatarUrl.trim().isEmpty) {
    return CircleAvatar(
      radius: radius,
      backgroundColor: fgSecondary.withValues(alpha: 0.15),
      child: Icon(
        CupertinoIcons.person_fill,
        size: AppSpacing.iconSmall,
        color: fgSecondary,
      ),
    );
  }
  return SizedBox(
    width: size,
    height: size,
    child: ClipOval(
      child: Image.network(
        avatarUrl,
        fit: BoxFit.cover,
        width: size,
        height: size,
        errorBuilder: (_, __, ___) => Container(
          color: fgSecondary.withValues(alpha: 0.15),
          child: Icon(
            CupertinoIcons.person_fill,
            size: AppSpacing.iconSmall,
            color: fgSecondary,
          ),
        ),
      ),
    ),
  );
}
