// ignore_for_file: unnecessary_underscores

import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_defaults.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_media_image.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_action_sheet.dart';

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
  static const String _expandedMenuMineId = '__mine__';
  static const String _expandedMenuAllId = 'all';
  static const List<String> _fixedCategoryOrder = <String>['all'];
  static const Set<String> _myCircleIds = <String>{
    'c-photo-owner',
    'c-tech-admin',
    'c1',
    'c2',
    'c3',
    'c-human-1',
  };

  String _selectedDimension = 'all';
  String _selectedExpandedMenuId = _expandedMenuAllId;
  bool _routeContextApplied = false;
  Map<String, CircleCategoryTabConfigDto> _categoryConfig =
      CircleCategoryTabDefaults.remoteStyleFallback;

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

    final menuIds = _expandedMenuItemsFor().map((entry) => entry.id).toSet();
    if (requestedMode == 'mine') {
      _selectedExpandedMenuId = _expandedMenuMineId;
    } else if (dimensionId != null && menuIds.contains(dimensionId)) {
      _selectedDimension = dimensionId;
      _selectedExpandedMenuId = dimensionId;
    } else {
      _selectedExpandedMenuId = _expandedMenuAllId;
      _selectedDimension = _expandedMenuAllId;
    }
    _recordCirclesVisit(_selectedDimension);
  }

  void _recordCirclesVisit(String dimensionId) {
    ref
        .read(visitRecorderServiceProvider)
        .recordVisit(VisitTarget.page('circles_$dimensionId'));
  }

  @override
  void initState() {
    super.initState();
    unawaited(_loadCirclesFromRepo());
  }

  List<Map<String, String>> get _allCategories {
    final config = _categoryConfig;
    final list = <Map<String, String>>[];
    final seen = <String>{};

    void addCategory(String id, String label) {
      if (!seen.add(id)) return;
      list.add({'id': id, 'label': label});
    }

    addCategory('all', config['all']?.label ?? '推荐');
    for (final entry in config.entries) {
      if (_fixedCategoryOrder.contains(entry.key)) continue;
      addCategory(entry.key, entry.value.label.isNotEmpty ? entry.value.label : entry.key);
    }
    return list;
  }

  Map<String, String> get _categoryLabelMap {
    return {for (final item in _allCategories) item['id']!: item['label']!};
  }

  List<CircleDto> _repoCircles = [];
  bool _circlesLoaded = false;

  Future<void> _loadCirclesFromRepo() async {
    try {
      final repo = ref.read(circleRepositoryProvider);
      final data = await repo.listCircles();
      final cfg = await repo.getCircleCategoryConfig();
      if (mounted) {
        setState(() {
          _categoryConfig = Map<String, CircleCategoryTabConfigDto>.from(cfg);
          _repoCircles = List<CircleDto>.from(data);
          _circlesLoaded = true;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _categoryConfig = Map<String, CircleCategoryTabConfigDto>.from(
            CircleCategoryTabDefaults.remoteStyleFallback,
          );
          _repoCircles = [];
          _circlesLoaded = true;
        });
      }
    }
  }

  List<CircleDto> _filteredCirclesFor(String dimensionId) {
    final circles = _circlesLoaded ? _repoCircles : <CircleDto>[];
    if (dimensionId == 'all') return circles;
    return circles.where((c) => c.category == dimensionId).toList();
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
    context.go(AppRoutePaths.home);
  }

  List<_ExpandedCircleMenuItem> _expandedMenuItemsFor() {
    final items = <_ExpandedCircleMenuItem>[
      _ExpandedCircleMenuItem(
        id: _expandedMenuMineId,
        label: UITextConstants.homeCirclesMy,
      ),
      ..._allCategories.map(
        (item) =>
            _ExpandedCircleMenuItem(id: item['id']!, label: item['label']!),
      ),
    ];
    final seen = <String>{};
    return items.where((item) => seen.add(item.id)).toList(growable: false);
  }

  List<CircleDto> _expandedCirclesForSelectedMenu() {
    final source = List<CircleDto>.from(
      _filteredCirclesFor(_expandedMenuAllId),
    );
    source.sort((a, b) {
      return b.memberCount.compareTo(a.memberCount);
    });

    if (_selectedExpandedMenuId == _expandedMenuMineId) {
      return source
          .where((item) => _myCircleIds.contains(item.id))
          .toList(growable: false);
    }
    if (_selectedExpandedMenuId == _expandedMenuAllId) {
      return source;
    }
    return source
        .where((item) => item.category == _selectedExpandedMenuId)
        .toList(growable: false);
  }

  String _expandedPageTitle() {
    return UITextConstants.circlesDirectoryTitle;
  }

  String _expandedSectionTitle() {
    if (_selectedExpandedMenuId == _expandedMenuMineId) {
      return UITextConstants.homeCirclesMyCircles;
    }
    final label = _categoryLabelMap[_selectedExpandedMenuId];
    if (label == null) {
      return _expandedPageTitle();
    }
    return '$label${UITextConstants.homeTabCircles}';
  }

  bool _isMyCircle(CircleDto circle) {
    return _myCircleIds.contains(circle.id);
  }

  String _formatCircleMetric(int rawCount, {required String suffix}) {
    final count = rawCount;
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
    ref.listen<int>(circleDirectoryRefreshProvider, (_, __) {
      unawaited(_loadCirclesFromRepo());
    });
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
    final listSurface = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final menuBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final accentBlue = CupertinoColors.activeBlue.resolveFrom(context);
    final menuItems = _expandedMenuItemsFor();
    final circles = _expandedCirclesForSelectedMenu();
    final menuWidth = AppSpacing.responsiveValue(
      context,
      compact: AppSpacing.largeButtonSize * 2,
      regular: AppSpacing.largeButtonSize * 2.1,
      expanded: AppSpacing.largeButtonSize * 2.3,
    );
    final coverSize = AppSpacing.bottomNavHeight + AppSpacing.containerXs;

    return AppScaffold(
      backgroundColor: bgPrimary,
      child: ColoredBox(
        color: bgPrimary,
        child: SafeArea(
          bottom: false,
          child: Column(
            children: [
              _CirclesDirectoryTopBar(
                title: _expandedPageTitle(),
                onBack: _handleExpandedPageBack,
                trailing: const GlobalTopActions(
                  initialSearchScope: GlobalSearchScope.circles,
                  quickActionPriority: CreateActionSheetPriority.socialPrimary,
                ),
              ),
              Expanded(
                child: Row(
                  children: [
                    ColoredBox(
                      color: menuBackground,
                      child: SizedBox(
                        width: menuWidth,
                        child: ListView.separated(
                          padding: EdgeInsets.fromLTRB(
                            AppSpacing.containerXs,
                            AppSpacing.containerSm,
                            AppSpacing.containerXs,
                            AppSpacing.containerSm,
                          ),
                          itemCount: menuItems.length,
                          separatorBuilder: (_, __) =>
                              SizedBox(height: AppSpacing.intraGroupXs),
                          itemBuilder: (context, index) {
                            final item = menuItems[index];
                            return _CirclesDirectoryMenuItem(
                              label: item.label,
                              selected: item.id == _selectedExpandedMenuId,
                              accentColor: accentBlue,
                              foregroundColor: fgPrimary,
                              onTap: () {
                                if (item.id == _selectedExpandedMenuId) {
                                  return;
                                }
                                setState(() {
                                  _selectedExpandedMenuId = item.id;
                                  if (item.id != _expandedMenuMineId) {
                                    _selectedDimension = item.id;
                                    _recordCirclesVisit(item.id);
                                  }
                                });
                              },
                            );
                          },
                        ),
                      ),
                    ),
                    VerticalDivider(
                      width: AppSpacing.hairline,
                      thickness: AppSpacing.hairline,
                      color: borderColor.withValues(alpha: 0.16),
                    ),
                    Expanded(
                      child: ColoredBox(
                        color: listSurface,
                        child: circles.isEmpty
                            ? Center(
                                child: Padding(
                                  padding: EdgeInsets.symmetric(
                                    horizontal: AppSpacing.containerLg,
                                  ),
                                  child: Text(
                                    '${_expandedSectionTitle()} ${UITextConstants.noData}',
                                    textAlign: TextAlign.center,
                                    style: TextStyle(
                                      fontSize: AppTypography.base,
                                      color: fgSecondary,
                                    ),
                                  ),
                                ),
                              )
                            : ListView.separated(
                                padding: EdgeInsets.fromLTRB(
                                  AppSpacing.feedContentHorizontal(context),
                                  AppSpacing.containerMd,
                                  AppSpacing.feedContentHorizontal(context),
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
                                      (circle.coverUrl ?? '').trim();
                                  final name = circle.name.isNotEmpty
                                      ? circle.name
                                      : UITextConstants.homeTabCircles;
                                  final members = _formatCircleMetric(
                                    circle.memberCount,
                                    suffix: '人',
                                  );
                                  final posts = _formatCircleMetric(
                                    circle.postCount,
                                    suffix: '件作品',
                                  );
                                  return CupertinoButton(
                                    padding: EdgeInsets.zero,
                                    minimumSize: Size.zero,
                                    onPressed: () => context.push(
                                      AppRoutePaths.circleDetail(
                                        id: circle.id,
                                      ),
                                    ),
                                    child: Row(
                                      children: [
                                        ClipRRect(
                                          borderRadius: BorderRadius.circular(
                                            AppSpacing
                                                .contentPreviewCornerRadius,
                                          ),
                                          child: SizedBox(
                                            width: coverSize,
                                            height: coverSize,
                                            child: coverUrl.isNotEmpty
                                                ? CircleMediaImage(
                                                    imageSource: coverUrl,
                                                    fit: BoxFit.cover,
                                                    errorWidget: ColoredBox(
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
                                                  fontSize: AppTypography
                                                      .iosSubheadline,
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
                                                ? accentBlue.withValues(
                                                    alpha: 0.12,
                                                  )
                                                : accentBlue,
                                            borderRadius: BorderRadius.circular(
                                              AppSpacing.circularBorderRadius,
                                            ),
                                          ),
                                          child: Text(
                                            joined
                                                ? UITextConstants.joinedCircle
                                                : UITextConstants.joinCircle,
                                            style: TextStyle(
                                              fontSize: AppTypography.sm,
                                              fontWeight:
                                                  AppTypography.semiBold,
                                              color: joined
                                                  ? accentBlue
                                                  : AppColors.white,
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  );
                                },
                              ),
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
  }

}

class _ExpandedCircleMenuItem {
  const _ExpandedCircleMenuItem({required this.id, required this.label});

  final String id;
  final String label;
}

class _CirclesDirectoryTopBar extends StatelessWidget {
  const _CirclesDirectoryTopBar({
    required this.title,
    required this.onBack,
    required this.trailing,
  });

  final String title;
  final VoidCallback onBack;
  final Widget trailing;

  @override
  Widget build(BuildContext context) {
    final isDark =
        CupertinoTheme.of(context).brightness == Brightness.dark;
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    final titleInset =
        AppSpacing.discoveryHeaderSideAnchorMinWidth +
        AppSpacing.minInteractiveSize;

    return Container(
      height: AppSpacing.tabNavigationHeight,
      decoration: BoxDecoration(
        color: bg,
        border: Border(
          bottom: BorderSide(
            color: borderColor.withValues(alpha: 0.18),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: Stack(
        children: [
          Positioned(
            left: AppSpacing.containerSm,
            top: 0,
            bottom: 0,
            child: CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: const Size(
                AppSpacing.minInteractiveSize,
                AppSpacing.minInteractiveSize,
              ),
              onPressed: onBack,
              child: Icon(
                CupertinoIcons.back,
                size: AppSpacing.iconMedium,
                color: fgPrimary,
              ),
            ),
          ),
          Positioned.fill(
            child: Center(
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: titleInset),
                child: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosTitle3,
                    fontWeight: AppTypography.semiBold,
                    color: fgPrimary,
                  ),
                ),
              ),
            ),
          ),
          Positioned(
            right: AppSpacing.topBarTrailingButtonInset(context),
            top: 0,
            bottom: 0,
            child: Center(child: trailing),
          ),
        ],
      ),
    );
  }
}

class _CirclesDirectoryMenuItem extends StatelessWidget {
  const _CirclesDirectoryMenuItem({
    required this.label,
    required this.selected,
    required this.accentColor,
    required this.foregroundColor,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final Color accentColor;
  final Color foregroundColor;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOutCubic,
        width: double.infinity,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.containerSm,
        ),
        decoration: BoxDecoration(
          color: selected
              ? accentColor.withValues(alpha: 0.1)
              : AppColors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        ),
        child: Text(
          label,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.smPlus,
            fontWeight: selected
                ? AppTypography.semiBold
                : AppTypography.medium,
            color: selected ? accentColor : foregroundColor,
          ),
        ),
      ),
    );
  }
}
