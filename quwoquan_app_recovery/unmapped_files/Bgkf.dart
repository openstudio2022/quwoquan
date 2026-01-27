import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/shared/components/post_list_section.dart';
import 'package:quwoquan_app/shared/components/tab_navigation.dart';
import 'package:quwoquan_app/shared/components/image_sub_tab_navigation.dart';

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
    with TickerProviderStateMixin {
  TabController? _tabController;
  String _activeTab = 'following';
  String _activeImageSubCategory = 'all'; // 图片二级分类，持久化状态

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
  }

  @override
  void dispose() {
    _tabController?.dispose();
    super.dispose();
  }


  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(effectiveIsDarkProvider);

    // 管理视频tab强制深色模式
    ref.listen(videoForceDarkProvider, (previous, next) {
      // 当视频tab强制深色模式状态改变时，触发重建
    });

    return Scaffold(
      backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      body: Column(
        children: [
          // 状态栏占位区域 - 确保内容不被状态栏遮挡
          SizedBox(height: MediaQuery.of(context).padding.top),
          
          // Tab导航 - 与状态栏背景色一致
          TabNavigationWidget(
            activeTab: _activeTab,
            onTabChange: (tab) {
              setState(() {
                _activeTab = tab;
                
                // 管理视频tab强制深色模式
                if (tab == 'video') {
                  ref.read(videoForceDarkProvider.notifier).setForceDark(true);
                } else {
                  ref.read(videoForceDarkProvider.notifier).setForceDark(false);
                }
              });
            },
          ),

          // 图片tab的二级导航
          if (_activeTab == 'images')
            ImageSubTabNavigation(
              activeCategory: _activeImageSubCategory,
              onCategoryChange: (category) {
                setState(() {
                  _activeImageSubCategory = category;
                });
              },
            ),

          // 主内容区域 - 统一使用PostListSection
          Expanded(
            child: PostListSection(
              category: _activeTab,
              subCategory: _activeTab == 'images' ? _activeImageSubCategory : null,
              onPostTap: (post, index) {
                // 处理post点击
                if (post['type'] == 'image') {
                  context
                      .push('/media-viewer/${post['username']}/$index');
                } else if (post['type'] == 'video') {
                  context.push('/video-viewer/$index');
                }
              },
              onUserTap: (username) {
                context.go('/user/$username');
              },
            ),
          ),
        ],
      ),
    );
  }
}
