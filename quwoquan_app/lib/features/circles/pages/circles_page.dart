import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/data/mock/prototype_mock_data.dart';

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
  String _selectedDimension = 'all';
  String _selectedSubCategory = '综合';
  final ScrollController _scrollController = ScrollController();
  double _lastScrollY = 0;
  bool _subBarVisible = true;

  @override
  bool get wantKeepAlive => true;

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  /// 与 DiscoveryView myCategories 一致：关注 + CATEGORY_CONFIG
  List<Map<String, String>> get _categories {
    final config = PrototypeMockData.circlesCategoryConfig;
    final list = <Map<String, String>>[
      {'id': 'following', 'label': '关注'},
    ];
    for (final e in config.entries) {
      list.add({'id': e.key, 'label': e.value['label'] as String});
    }
    return list;
  }

  List<Map<String, dynamic>> get _filteredCircles {
    final circles = PrototypeMockData.circlesMockCircles;
    if (_selectedDimension == 'all') return circles;
    return circles.where((c) => c['categoryId'] == _selectedDimension).toList();
  }

  List<Map<String, dynamic>> get _filteredActivities {
    final activities = PrototypeMockData.circlesMockActivities;
    if (_selectedDimension == 'all') return activities;
    final label = PrototypeMockData.circlesCategoryConfig[_selectedDimension]?['label'] as String? ?? '';
    return activities.where((a) => (a['circleName'] as String).contains(label)).toList();
  }

  List<String> get _currentSubCategories {
    final config = PrototypeMockData.circlesCategoryConfig[_selectedDimension];
    if (config == null) return [];
    final sub = config['subCategories'] as List<dynamic>? ?? [];
    return sub.map((e) => e.toString()).where((s) => s != '综合').toList();
  }

  List<Map<String, dynamic>> get _discoveryPosts {
    final circles = _filteredCircles.isEmpty ? PrototypeMockData.circlesMockCircles : _filteredCircles;
    final pool = circles;
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
        'user': {'name': 'User_$i', 'avatar': 'https://api.dicebear.com/7.x/avataaars/svg?seed=$i'},
        'likes': 24 + i * 5,
        'comments': 2 + i,
        'circleName': circle['name'],
        'type': type,
      };
    });
  }

  void _onScroll(double y) {
    if (y - _lastScrollY > 5 && y > 100) {
      if (_subBarVisible) setState(() => _subBarVisible = false);
    } else if (_lastScrollY - y > 5) {
      if (!_subBarVisible) setState(() => _subBarVisible = true);
    }
    _lastScrollY = y;
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final isDark = ref.watch(isDarkProvider);
    final bgColor = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fgPrimary = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor = AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

    return Scaffold(
      backgroundColor: bgColor,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            _buildHeader(context, isDark, fgPrimary, fgSecondary),
            Expanded(
              child: _selectedDimension == 'following'
                  ? _buildFollowingPlaceholder(fgSecondary)
                  : NotificationListener<ScrollNotification>(
                      onNotification: (n) {
                        _onScroll(n.metrics.pixels);
                        return false;
                      },
                      child: ListView(
                        controller: _scrollController,
                        children: [
                        _buildRecommendedSection(context, isDark, fgSecondary),
                        if (_filteredActivities.isNotEmpty) _buildActivities(isDark, fgSecondary),
                        if (_currentSubCategories.isNotEmpty) _buildSubCategoryBar(isDark, fgPrimary, fgSecondary, borderColor),
                        _buildDiscoveryGrid(context, isDark, fgSecondary),
                        Padding(
                          padding: const EdgeInsets.only(top: 32, bottom: 16),
                          child: Center(
                            child: Text(
                              UITextConstants.discoveryEndHint,
                              style: TextStyle(fontSize: 12, color: fgSecondary),
                            ),
                          ),
                        ),
                      ],
                    ),
                    ),
            ),
          ],
        ),
      ),
      floatingActionButton: _selectedDimension != 'following'
          ? FloatingActionButton.extended(
              onPressed: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text('${UITextConstants.createCircle}（CreateCircleWizard 待接入）'),
                    behavior: SnackBarBehavior.floating,
                  ),
                );
              },
              backgroundColor: AppColors.primaryColor,
              icon: const Icon(Icons.add, color: Colors.white),
              label: Text(
                UITextConstants.createCircle,
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
              ),
            )
          : null,
    );
  }

  Widget _buildHeader(BuildContext context, bool isDark, Color fgPrimary, Color fgSecondary) {
    return Container(
      padding: EdgeInsets.only(
        left: AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.sm] ?? AppSpacing.containerSm,
        right: AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.sm] ?? AppSpacing.containerSm,
        top: 8,
        bottom: 8,
      ),
      child: Row(
        children: [
          Expanded(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: _categories.map((c) {
                  final selected = _selectedDimension == c['id'];
                  return Padding(
                    padding: EdgeInsets.only(right: AppSpacing.sm),
                    child: GestureDetector(
                      onTap: () {
                        setState(() {
                          _selectedDimension = c['id']!;
                          _selectedSubCategory = '综合';
                        });
                      },
                      child: Container(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.md,
                          vertical: AppSpacing.sm,
                        ),
                        decoration: BoxDecoration(
                          color: selected ? AppColors.primaryColor : Colors.transparent,
                          borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
                        ),
                        child: Text(
                          c['label']!,
                          style: TextStyle(
                            color: selected ? Colors.white : fgSecondary,
                            fontWeight: selected ? FontWeight.w800 : FontWeight.normal,
                            fontSize: 13,
                          ),
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
          ),
          IconButton(
            icon: Icon(Icons.search, color: fgSecondary),
            onPressed: () {},
          ),
          IconButton(
            icon: Icon(Icons.tune, color: fgSecondary),
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('频道管理（ChannelManager 待接入）'), behavior: SnackBarBehavior.floating),
              );
            },
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
          Icon(Icons.people_outline, size: 64, color: fgSecondary),
          SizedBox(height: AppSpacing.md),
          Text('关注 暂无内容', style: TextStyle(fontSize: 16, color: fgSecondary)),
        ],
      ),
    );
  }

  Widget _buildRecommendedSection(BuildContext context, bool isDark, Color fgSecondary) {
    final circles = _filteredCircles;
    return Container(
      color: isDark ? Colors.white.withValues(alpha: 0.03) : Colors.black.withValues(alpha: 0.02),
      padding: EdgeInsets.symmetric(
        vertical: AppSpacing.md,
        horizontal: AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.sm] ?? AppSpacing.containerSm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                '推荐圈子',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: fgSecondary),
              ),
              TextButton(
                onPressed: () {},
                child: Text(UITextConstants.seeMore, style: TextStyle(fontSize: 12, color: AppColors.primaryColor)),
              ),
            ],
          ),
          SizedBox(
            height: 112,
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
                        width: 80,
                        decoration: BoxDecoration(
                          color: AppColors.primaryColor.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Icon(Icons.add, color: AppColors.primaryColor, size: 32),
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
                        ClipRRect(
                          borderRadius: BorderRadius.circular(12),
                          child: Image.network(
                            c['avatar'] as String,
                            width: 64,
                            height: 64,
                            fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) => Container(
                              width: 64,
                              height: 64,
                              color: fgSecondary.withValues(alpha: 0.2),
                              child: Icon(Icons.group, color: fgSecondary),
                            ),
                          ),
                        ),
                        SizedBox(height: 4),
                        SizedBox(
                          width: 72,
                          child: Text(
                            c['name'] as String,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            textAlign: TextAlign.center,
                            style: TextStyle(fontSize: 11, color: fgSecondary),
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

  Widget _buildActivities(bool isDark, Color fgSecondary) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.semantic[DesignSemanticConstants.container]?[DesignSemanticConstants.md] ?? AppSpacing.containerMd,
        vertical: AppSpacing.sm,
      ),
      child: Column(
        children: _filteredActivities.map((a) {
          return Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.sm),
            child: Material(
              color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.03),
              borderRadius: BorderRadius.circular(12),
              child: InkWell(
                onTap: () {},
                borderRadius: BorderRadius.circular(12),
                child: Padding(
                  padding: EdgeInsets.all(AppSpacing.sm),
                  child: Row(
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: Image.network(
                          a['image'] as String? ?? '',
                          width: 56,
                          height: 56,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => Container(width: 56, height: 56, color: fgSecondary.withValues(alpha: 0.2)),
                        ),
                      ),
                      SizedBox(width: AppSpacing.sm),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(a['title'] as String, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                            Text(a['circleName'] as String, style: TextStyle(fontSize: 11, color: fgSecondary)),
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

  Widget _buildSubCategoryBar(bool isDark, Color fgPrimary, Color fgSecondary, Color borderColor) {
    if (!_subBarVisible) return const SizedBox.shrink();
    final subs = ['综合', ..._currentSubCategories];
    return Container(
      color: (isDark ? Colors.white : Colors.black).withValues(alpha: 0.03),
      padding: EdgeInsets.symmetric(vertical: 8),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
        child: Row(
          children: subs.map((s) {
            final selected = _selectedSubCategory == s;
            return Padding(
              padding: EdgeInsets.only(right: AppSpacing.sm),
              child: GestureDetector(
                onTap: () => setState(() => _selectedSubCategory = s),
                child: Container(
                  padding: EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 6),
                  decoration: BoxDecoration(
                    color: selected ? (isDark ? Colors.white.withValues(alpha: 0.1) : Colors.black.withValues(alpha: 0.06)) : null,
                    border: Border.all(color: borderColor.withValues(alpha: 0.5)),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    s,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: selected ? fgPrimary : fgSecondary,
                    ),
                  ),
                ),
              ),
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _buildDiscoveryGrid(BuildContext context, bool isDark, Color fgSecondary) {
    final posts = _discoveryPosts;
    return Padding(
      padding: EdgeInsets.fromLTRB(12, 16, 12, MediaQuery.of(context).padding.bottom + 80),
      child: GridView.builder(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          mainAxisSpacing: 12,
          crossAxisSpacing: 12,
          childAspectRatio: 0.75,
        ),
        itemCount: posts.length,
        itemBuilder: (context, i) {
          final p = posts[i];
          return _DiscoveryPostCard(
            post: p,
            isDark: isDark,
            onTap: () => context.push('/article/${p['id']}'),
          );
        },
      ),
    );
  }
}

class _DiscoveryPostCard extends StatelessWidget {
  final Map<String, dynamic> post;
  final bool isDark;
  final VoidCallback onTap;

  const _DiscoveryPostCard({required this.post, required this.isDark, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    Image.network(
                      post['image'] as String,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => Container(color: fgSecondary.withValues(alpha: 0.2)),
                    ),
                    if (post['type'] == 'video')
                      Positioned(
                        top: 8,
                        right: 8,
                        child: Icon(Icons.play_circle_fill, color: Colors.white, size: 28),
                      ),
                  ],
                ),
              ),
            ),
            SizedBox(height: 6),
            Text(
              post['title'] as String,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 12, color: fgSecondary),
            ),
            Row(
              children: [
                Icon(Icons.favorite_border, size: 12, color: fgSecondary),
                SizedBox(width: 4),
                Text('${post['likes']}', style: TextStyle(fontSize: 11, color: fgSecondary)),
                SizedBox(width: 8),
                Icon(Icons.chat_bubble_outline, size: 12, color: fgSecondary),
                Text('${post['comments']}', style: TextStyle(fontSize: 11, color: fgSecondary)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
