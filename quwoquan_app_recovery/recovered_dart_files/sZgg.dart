import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/shared/components/post_list_section.dart';
import 'package:quwoquan_app/shared/components/tab_navigation.dart';

class HomePage extends ConsumerStatefulWidget {
  final String initialTab;

  const HomePage({
    super.key,
    this.initialTab = 'following',
  });

  @override
  ConsumerState<HomePage> createState() => _HomePageState();
}

class _HomePageState extends ConsumerState<HomePage>
    with TickerProviderStateMixin, AutomaticKeepAliveClientMixin {
  TabController? _tabController;
  PageController? _pageController; // 改为可空类型
  String _activeTab = 'following';
  // 移除未使用的_activeImageSubCategory字段，状态通过_tabSubCategories管理
  
  // 为每个tab维护独立的状态
  final Map<String, String> _tabSubCategories = {
    'images': 'all',
    'video': 'all',
    'articles': 'all',
    'moments': 'all',
  };
  
  @override
  bool get wantKeepAlive => true; // 保持页面状态

  final List<String> _tabs = [
    'following',
    'recommended',
    'images',
    'video',
    'articles',
    'moments',
  ];

  @override
  void initState() {
    super.initState();
    _activeTab = widget.initialTab;
    _tabController = TabController(
      length: _tabs.length,
      vsync: this,
      initialIndex: _tabs.indexOf(_activeTab),
    );
    _pageController = PageController(initialPage: _tabs.indexOf(_activeTab));
    
    // 设置初始的视频tab强制深色模式状态
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_activeTab == 'video') {
        ref.read(videoForceDarkProvider.notifier).setForceDark(true);
      } else {
        ref.read(videoForceDarkProvider.notifier).setForceDark(false);
      }
    });
  }

  @override
  void dispose() {
    _tabController?.dispose();
    _pageController?.dispose();
    super.dispose();
  }


  @override
  Widget build(BuildContext context) {
    super.build(context); // 必须调用，用于AutomaticKeepAliveClientMixin
    final isDark = ref.watch(effectiveIsDarkProvider);

    return Scaffold(
      backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      body: Column(
        children: [
          // 状态栏占位区域 - 确保内容不被状态栏遮挡
          SizedBox(height: MediaQuery.of(context).padding.top),
          
          // Tab导航 - 与状态栏背景色一致
          TabNavigationWidget(
            activeTab: _activeTab,
            isDark: isDark, // 传递当前主题状态
            onTabChange: (tab) {
              final tabIndex = _tabs.indexOf(tab);
              if (tabIndex != -1 && _pageController != null) {
                _pageController!.animateToPage(
                  tabIndex,
                  duration: const Duration(milliseconds: 300),
                  curve: Curves.easeInOut,
                );
              }
            },
          ),

          // 图片tab的二级导航已移到PostListSection中，跟随列表滚动

          // 主内容区域 - 使用PageView保持每个tab的状态
          Expanded(
            child: _pageController != null ? PageView.builder(
              controller: _pageController!,
              onPageChanged: (index) {
                setState(() {
                  _activeTab = _tabs[index];
                  // 状态通过_tabSubCategories管理，无需额外处理
                });
                
                // 管理视频tab强制深色模式
                if (_activeTab == 'video') {
                  ref.read(videoForceDarkProvider.notifier).setForceDark(true);
                } else {
                  ref.read(videoForceDarkProvider.notifier).setForceDark(false);
                }
              },
              itemCount: _tabs.length,
              itemBuilder: (context, index) {
                final tab = _tabs[index];
                return PostListSection(
                  category: tab,
                  subCategory: tab == 'images' ? (_tabSubCategories[tab] ?? 'all') : null,
                  isDark: isDark,
                  onPostTap: (post, postIndex) {
                    // 处理post点击
                    if (post['type'] == 'image') {
                      context.push('/media-viewer/${post['username']}/$postIndex');
                    } else if (post['type'] == 'video') {
                      context.push('/video-viewer/$postIndex');
                    }
                  },
                  onUserTap: (username) {
                    context.go('/user/$username');
                  },
                  onImageSubCategoryChange: (category) {
                    setState(() {
                      // 保存当前tab的二级分类状态
                      _tabSubCategories[tab] = category;
                    });
                  },
                );
              },
            ) : const SizedBox.shrink(), // 如果PageController未初始化，显示空白
          ),
        ],
      ),
    );
  }
}
