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
    with TickerProviderStateMixin {
  TabController? _tabController;
  String _activeTab = 'following';

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
    final isDark = ref.watch(isDarkProvider);

    // 状态栏样式由 main_layout.dart 统一管理

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
              });
            },
          ),

          // 主内容区域 - 统一使用PostListSection
          Expanded(
            child: PostListSection(
              category: _activeTab,
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
