import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/post_list_section.dart';
import 'package:quwoquan_app/components/tab_navigation.dart';
import 'package:quwoquan_app/components/bottom_navigation.dart';

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
  String _activeTab = 'following';
  String _activeImageSubCategory = 'all'; // 图片二级分类，持久化状态
  int _currentBottomNavIndex = 0; // 底部导航栏当前索引
  
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
              setState(() {
                _activeTab = tab;
              });
              
              // 管理视频tab强制深色模式
              if (tab == 'video') {
                ref.read(videoForceDarkProvider.notifier).setForceDark(true);
              } else {
                ref.read(videoForceDarkProvider.notifier).setForceDark(false);
              }
            },
          ),

          // 图片tab的二级导航已移到PostListSection中，跟随列表滚动

          // 主内容区域 - 统一使用PostListSection
          Expanded(
            child: PostListSection(
              category: _activeTab,
              subCategory: _activeTab == 'images' ? _activeImageSubCategory : null,
              isDark: isDark, // 传递当前主题状态
              onPostTap: (post, index) {
                // 处理post点击
                if (post['type'] == 'image') {
                  context.push('/media-viewer/${_activeTab}/$index');
                } else if (post['type'] == 'video') {
                  context.push('/video-viewer/$index');
                }
              },
              onUserTap: (username) {
                context.push('/user/$username');
              },
              onImageSubCategoryChange: (category) {
                setState(() {
                  _activeImageSubCategory = category;
                });
              },
            ),
          ),
        ],
      ),
      bottomNavigationBar: BottomNavigationWidget(
        currentIndex: _currentBottomNavIndex,
        onTap: (index) {
          setState(() {
            _currentBottomNavIndex = index;
          });
          
          // 根据索引导航到不同页面
          switch (index) {
            case 0: // 首页
              context.go('/');
              break;
            case 1: // 搜索
              // TODO: 实现搜索页面
              break;
            case 2: // 创建
              // TODO: 实现创建页面
              break;
            case 3: // 聊天
              // TODO: 实现聊天页面
              break;
            case 4: // 我的
              context.go('/my-profile');
              break;
          }
        },
      ),
    );
  }
}
