// ignore_for_file: unnecessary_underscores

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/assistant_avatar.dart';
import 'package:quwoquan_app/components/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/tab_navigation.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/features/assistant/context/assistant_open_context.dart';
import 'package:quwoquan_app/features/assistant/widgets/assistant_half_sheet.dart';

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

  String _selectedDimension = 'all';
  String _selectedSubCategory = UITextConstants.circleSubAll;
  final Map<String, String> _subCategoryByDimension = {};
  late PageController _primaryPageController;

  @override
  bool get wantKeepAlive => true;

  void _recordCirclesVisit(String dimensionId) {
    ref.read(visitRecorderServiceProvider).recordVisit(
          VisitTarget.page('circles_$dimensionId'),
        );
  }

  /// 打开小趣半弹窗（搜索、频道管理等统一由此入口）
  void _openAssistantHalfSheet() {
    final target = VisitTarget.page('circles_$_selectedDimension');
    final service = ref.read(visitRecorderServiceProvider);
    final ctx = AssistantOpenContext(
      source: AssistantSource.circles,
      dimension: _selectedDimension,
      visitTarget: target,
      experienceLevel: service.getExperience(target),
    );
    AssistantHalfSheet.show(context, ctx);
  }

  @override
  void initState() {
    super.initState();
    _primaryPageController = PageController(
      initialPage: _primaryTabIds.indexOf(_selectedDimension).clamp(0, _primaryTabIds.length - 1),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _recordCirclesVisit(_selectedDimension);
    });
  }

  @override
  void dispose() {
    _primaryPageController.dispose();
    super.dispose();
  }

  /// 与 DiscoveryView myCategories 一致：关注 + CATEGORY_CONFIG
  List<Map<String, String>> get _categories {
    final config = ref.read(appContentRepositoryProvider).circlesCategoryConfig;
    final list = <Map<String, String>>[
      {'id': 'following', 'label': '关注'},
    ];
    for (final e in config.entries) {
      list.add({'id': e.key, 'label': e.value['label'] as String});
    }
    return list;
  }

  List<Map<String, dynamic>> _filteredCirclesFor(String dimensionId) {
    final circles = ref.read(appContentRepositoryProvider).circlesMockCircles;
    if (dimensionId == 'all') return circles;
    return circles.where((c) => c['categoryId'] == dimensionId).toList();
  }

  List<Map<String, dynamic>> get _filteredCircles => _filteredCirclesFor(_selectedDimension);

  List<Map<String, dynamic>> _filteredActivitiesFor(String dimensionId) {
    final activities = ref.read(appContentRepositoryProvider).circlesMockActivities;
    if (dimensionId == 'all') return activities;
    final label = ref.read(appContentRepositoryProvider).circlesCategoryConfig[dimensionId]?['label'] as String? ?? '';
    return activities.where((a) => (a['circleName'] as String).contains(label)).toList();
  }

  List<Map<String, dynamic>> get _filteredActivities => _filteredActivitiesFor(_selectedDimension);

  List<String> get _currentSubCategories {
    final config = ref.read(appContentRepositoryProvider).circlesCategoryConfig[_selectedDimension];
    if (config == null) return [];
    final sub = config['subCategories'] as List<dynamic>? ?? [];
    return sub
        .map((e) => e.toString())
        .where((s) => s != '综合' && s != UITextConstants.circleSubAll)
        .toList();
  }

  List<Map<String, dynamic>> _discoveryPostsFor(String dimensionId, String subCategory) {
    final circles = _filteredCirclesFor(dimensionId);
    final poolCircles = circles.isEmpty
        ? ref.read(appContentRepositoryProvider).circlesMockCircles
        : circles;
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
      final type = i % 3 == 0 ? 'video' : i % 3 == 1 ? 'article' : 'image';
      return {
        'id': 'dp-$i-${circle['id']}',
        'image': urls[i % 5],
        'title': '[${circle['subCategory'] ?? '精选'}] ${circle['name']} 的内容分享 #${i + 1}',
        'user': {'name': 'User_$i', 'avatar': 'https://api.dicebear.com/7.x/avataaars/png?seed=$i'},
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

  List<String> get _primaryTabIds =>
      _categories.map((category) => category['id']!).toList(growable: false);

  List<String> _getSubCategoriesFor(String dimensionId) {
    final config = ref.read(appContentRepositoryProvider).circlesCategoryConfig[dimensionId];
    if (config == null) return [];
    final sub = config['subCategories'] as List<dynamic>? ?? [];
    return sub
        .map((e) => e.toString())
        .where((s) => s != '综合' && s != UITextConstants.circleSubAll)
        .toList();
  }

  List<String> get _secondaryTabIds =>
      [UITextConstants.circleSubAll, ..._currentSubCategories];

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
      _selectedSubCategory = _subCategoryByDimension[nextId] ?? UITextConstants.circleSubAll;
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
    final ids = [UITextConstants.circleSubAll, ..._getSubCategoriesFor(dimensionId)];
    if (ids.length <= 1) return;
    final current = _subCategoryByDimension[dimensionId] ?? UITextConstants.circleSubAll;
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
    return coverHeight + AppSpacing.intraGroupXs + AppTypography.sm + AppSpacing.sm;
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final isDark = ref.watch(isDarkProvider);
    final bgPrimary = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fgPrimary = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

    return Scaffold(
      backgroundColor: bgPrimary,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            _buildHeader(context, isDark, fgPrimary, fgSecondary),
            Expanded(
              child: PageView(
                  controller: _primaryPageController,
                  // 禁用 PageView 自带的滑动切换，一级 Tab 切换完全由
                  // 各区域的 GestureDetector 通过 animateToPage 程序驱动
                  physics: const NeverScrollableScrollPhysics(),
                  onPageChanged: (index) {
                    final id = _primaryTabIds[index];
                    if (id != _selectedDimension) {
                      setState(() {
                        _selectedDimension = id;
                        _selectedSubCategory = _subCategoryByDimension[id] ?? UITextConstants.circleSubAll;
                        _recordCirclesVisit(id);
                      });
                    }
                  },
                  children: _primaryTabIds.map((id) {
                    if (id == 'following') {
                      // 关注页无二级 Tab，整页水平拖拽切换一级 Tab
                      return GestureDetector(
                        behavior: HitTestBehavior.translucent,
                        onHorizontalDragEnd: _onPrimaryDragEnd,
                        child: _buildFollowingPlaceholder(fgSecondary),
                      );
                    }
                    return _buildDimensionContent(
                      context, id, isDark, fgPrimary, fgSecondary, borderColor,
                    );
                  }).toList(),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context, bool isDark, Color fgPrimary, Color fgSecondary) {
    final tabs = _categories
        .map((entry) => TabItem(id: entry['id']!, label: entry['label']!))
        .toList(growable: false);

    return Container(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        border: Border(
          bottom: BorderSide(
            color: AppColorsFunctional.getColor(isDark, ColorType.borderPrimary),
            width: 1,
          ),
        ),
      ),
      child: CenteredScrollableTabBar(
        tabs: tabs,
        activeTab: _selectedDimension,
        anchorTabId: 'all',
        isDark: isDark,
        onTabChange: (id) {
          setState(() {
            _selectedDimension = id;
            _selectedSubCategory = _subCategoryByDimension[id] ?? UITextConstants.circleSubAll;
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
          IconButton(
            tooltip: UITextConstants.assistantEntryFind,
            icon: AssistantAvatar(radius: AppSpacing.iconMedium / 2),
            onPressed: _openAssistantHalfSheet,
            style: IconButton.styleFrom(
              minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFollowingPlaceholder(Color fgSecondary) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.people_outline,
            size: AppSpacing.largeButtonSize + AppSpacing.sm,
            color: fgSecondary,
          ),
          SizedBox(height: AppSpacing.interGroupMd),
          Text(
            UITextConstants.circlesFollowingEmpty,
            style: TextStyle(fontSize: AppTypography.lg, color: fgSecondary),
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
    final subCategory = _subCategoryByDimension[dimensionId] ?? UITextConstants.circleSubAll;
    final subCats = _getSubCategoriesFor(dimensionId);
    final circles = _filteredCirclesFor(dimensionId);
    final activities = _filteredActivitiesFor(dimensionId);
    final posts = _discoveryPostsFor(dimensionId, subCategory);

    return CustomScrollView(
      slivers: [
        // 推荐区：二级 Tab 之上区域，水平拖拽切换一级 Tab
        SliverToBoxAdapter(
          child: GestureDetector(
            behavior: HitTestBehavior.translucent,
            onHorizontalDragEnd: _onPrimaryDragEnd,
            child: _buildRecommendedSection(
              context, isDark, fgPrimary, fgSecondary,
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
              child: _buildActivities(context, isDark, fgSecondary, activitiesParam: activities),
            ),
          ),
        if (subCats.isNotEmpty)
          SliverPersistentHeader(
            floating: true,
            delegate: _SubCategoryBarDelegate(
              child: _buildSubCategoryBarContent(
                context, isDark, fgPrimary, fgSecondary, borderColor,
                subCategoriesParam: subCats,
                selectedSubParam: subCategory,
                onSubHorizontalDragEnd: (details) {
                  final velocity = details.primaryVelocity ?? 0;
                  if (velocity.abs() < 220) return;
                  _switchSecondaryByDeltaFor(dimensionId, velocity < 0 ? 1 : -1);
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
          context, isDark, fgPrimary, fgSecondary,
          postsParam: posts,
          onGridHorizontalDragEnd: subCats.isEmpty
              ? _onPrimaryDragEnd // 无二级 Tab 时，瀑布流水平拖拽切换一级 Tab
              : (details) {
                  final velocity = details.primaryVelocity ?? 0;
                  if (velocity.abs() < 220) return;
                  _switchSecondaryByDeltaFor(dimensionId, velocity < 0 ? 1 : -1);
                },
        ),
        SliverToBoxAdapter(
          child: Padding(
            padding: EdgeInsets.only(
              top: AppSpacing.interGroupXl,
              bottom: MediaQuery.of(context).padding.bottom + AppSpacing.bottomNavHeight,
            ),
            child: Center(
              child: Text(
                UITextConstants.discoveryEndHint,
                style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary),
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
    return Container(
      color: isDark ? Colors.white.withValues(alpha: 0.03) : Colors.black.withValues(alpha: 0.02),
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
                  fontSize: AppTypography.lg,
                  fontWeight: AppTypography.extraBold,
                  color: fgSecondary,
                ),
              ),
              TextButton(
                onPressed: () {},
                child: Text(
                  UITextConstants.seeMore,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: AppColors.primaryColor,
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
                    child: GestureDetector(
                      onTap: () {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text(UITextConstants.createCircle), behavior: SnackBarBehavior.floating),
                        );
                      },
                      child: Container(
                        width: _circleCardWidth(context),
                        decoration: BoxDecoration(
                          color: AppColors.primaryColor.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                        ),
                        child: Icon(
                          Icons.add,
                          color: AppColors.primaryColor,
                          size: AppSpacing.iconLarge,
                        ),
                      ),
                    ),
                  );
                }
                final c = circles[i];
                return Padding(
                  padding: EdgeInsets.only(right: AppSpacing.sm),
                  child: GestureDetector(
                    onTap: () => context.push('/circle/${c['id']}'),
                    child: Column(
                      children: [
                        SizedBox(
                          width: _circleCardWidth(context),
                          child: AspectRatio(
                            aspectRatio: _circleCoverAspectRatio,
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(
                                AppSpacing.borderRadius,
                              ),
                              child: Image.network(
                                c['avatar'] as String,
                                fit: BoxFit.cover,
                                errorBuilder: (context, error, stackTrace) =>
                                    Container(
                                      color: fgSecondary.withValues(alpha: 0.2),
                                      child: Icon(
                                        Icons.group,
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
                              fontSize: AppTypography.sm,
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

  Widget _buildActivities(BuildContext context, bool isDark, Color fgSecondary, {List<Map<String, dynamic>>? activitiesParam}) {
    final activities = activitiesParam ?? _filteredActivities;
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.feedContentHorizontal(context),
        vertical: AppSpacing.sm,
      ),
      child: Column(
        children: activities.map((a) {
          return Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.sm),
            child: Material(
              color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.03),
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
              child: InkWell(
                onTap: () {},
                borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
                child: Padding(
                  padding: EdgeInsets.all(AppSpacing.sm),
                  child: Row(
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
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
                              style: TextStyle(
                                fontSize: AppTypography.base,
                                fontWeight: AppTypography.semiBold,
                              ),
                            ),
                            Text(
                              a['circleName'] as String,
                              style: TextStyle(
                                fontSize: AppTypography.sm,
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
    final chipFontSize = AppTypography.responsive(
      context,
      compact: AppTypography.sm,
      regular: AppTypography.base,
      expanded: AppTypography.base,
    );
    final bgBar = isDark
        ? Colors.white.withValues(alpha: 0.04)
        : Colors.black.withValues(alpha: 0.03);

    return Container(
      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      height: AppSpacing.subTabNavigationHeight,
      child: Container(
        color: bgBar,
        child: GestureDetector(
          behavior: HitTestBehavior.translucent,
          onHorizontalDragEnd: onSubHorizontalDragEnd ?? _onSecondaryDragEnd,
          child: ListView.builder(
            scrollDirection: Axis.horizontal,
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.feedContentHorizontal(context),
              vertical: AppSpacing.intraGroupSm,
            ),
            itemCount: subs.length,
            itemBuilder: (context, index) {
              final s = subs[index];
              final selected = selectedSub == s;
              return Padding(
                padding: EdgeInsets.only(right: AppSpacing.intraGroupSm),
                child: Material(
                  color: Colors.transparent,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
                    onTap: () {
                      if (onSubTap != null) {
                        onSubTap(s);
                      } else {
                        setState(() => _selectedSubCategory = s);
                      }
                    },
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      alignment: Alignment.center,
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.intraGroupMd + AppSpacing.xs,
                        vertical: AppSpacing.intraGroupXs,
                      ),
                      decoration: BoxDecoration(
                        color: selected
                            ? (isDark ? Colors.white.withValues(alpha: 0.15) : AppColors.primaryColor.withValues(alpha: 0.12))
                            : Colors.transparent,
                        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
                        border: Border.all(
                          color: selected
                              ? (isDark ? Colors.white.withValues(alpha: 0.2) : AppColors.primaryColor.withValues(alpha: 0.25))
                              : fgSecondary.withValues(alpha: 0.2),
                          width: 0.5,
                        ),
                      ),
                      child: Text(
                        s,
                        style: TextStyle(
                          fontSize: chipFontSize,
                          fontWeight: selected ? AppTypography.semiBold : AppTypography.medium,
                          color: selected
                              ? (isDark ? Colors.white : AppColors.primaryColor)
                              : fgSecondary,
                        ),
                      ),
                    ),
                  ),
                ),
              );
            },
          ),
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
        mainAxisSpacing: AppSpacing.interGroupSm,
        crossAxisSpacing: AppSpacing.interGroupSm,
        childCount: posts.length,
        itemBuilder: (context, i) {
          final p = posts[i];
          return _DiscoveryPostCard(
            post: p,
            isDark: isDark,
            onTap: () => context.push('/article/${p['id']}'),
            onHorizontalDragEnd: onGridHorizontalDragEnd,
          );
        },
      ),
    );
  }
}

/// 简化版宫格卡片：媒体 + 标题 + 作者头像/名字 + 右侧爱心
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

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final user = post['user'] as Map<String, dynamic>? ?? {};
    final gridMetaFontSize = AppTypography.responsive(
      context,
      compact: AppTypography.sm,
      regular: AppTypography.base,
      expanded: AppTypography.base,
    );

    return Material(
      color: Colors.transparent,
      child: GestureDetector(
        behavior: HitTestBehavior.translucent,
        onHorizontalDragEnd: onHorizontalDragEnd,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
            // 媒体图片（按模拟宽高比，最大 9:16）
            AspectRatio(
              aspectRatio: _imageAspectRatio,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    Image.network(
                      post['image'] as String,
                      fit: BoxFit.cover,
                      errorBuilder: (context, error, stackTrace) =>
                          Container(color: fgSecondary.withValues(alpha: 0.15)),
                    ),
                    if (post['type'] == 'video')
                      Positioned(
                        top: AppSpacing.intraGroupSm,
                        right: AppSpacing.intraGroupSm,
                        child: Icon(
                          Icons.play_circle_fill,
                          color: Colors.white,
                          size: AppSpacing.iconLarge - AppSpacing.xs,
                        ),
                      ),
                  ],
                ),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            // 标题（最多2行，正常色）
            Text(
              post['title'] as String,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: gridMetaFontSize,
                color: fgPrimary,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            // 底部行：左侧三动作，右侧转发（宫格保持更紧凑字号）。
            Row(
              children: [
                _buildUserAvatar(
                  user['avatar'] as String?,
                  fgSecondary,
                  radius: AppSpacing.intraGroupMd,
                ),
                SizedBox(width: AppSpacing.intraGroupXs),
                Expanded(
                  child: Text(
                    user['name'] as String? ?? '',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: gridMetaFontSize,
                      color: fgSecondary,
                    ),
                  ),
                ),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      CupertinoIcons.heart,
                      size: gridMetaFontSize,
                      color: fgSecondary,
                    ),
                    Text(
                      ' ${post['likes'] ?? 0}',
                      style: TextStyle(
                        fontSize: gridMetaFontSize,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ),
              ],
            ),
            ],
          ),
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
  Widget build(BuildContext context, double shrinkOffset, bool overlapsContent) {
    return child;
  }

  @override
  bool shouldRebuild(covariant _SubCategoryBarDelegate oldDelegate) => true;
}

/// 用户头像：网络图加载失败时显示占位，避免 Invalid image data 异常。供圈子页与宫格卡片共用。
Widget _buildUserAvatar(String? avatarUrl, Color fgSecondary, {required double radius}) {
  final size = radius * 2;
  if (avatarUrl == null || avatarUrl.trim().isEmpty) {
    return CircleAvatar(
      radius: radius,
      backgroundColor: fgSecondary.withValues(alpha: 0.15),
      child: Icon(Icons.person, size: AppSpacing.iconSmall, color: fgSecondary),
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
          child: Icon(Icons.person, size: AppSpacing.iconSmall, color: fgSecondary),
        ),
      ),
    ),
  );
}
