import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/shared/components/tab_navigation.dart';
import 'package:quwoquan_app/shared/components/feed_section.dart';
import 'package:quwoquan_app/features/video/pages/video_channel_page.dart';
// import '../analytics/analytics.dart';

class HomePage extends ConsumerStatefulWidget {
  final String initialTab;

  const HomePage({
    super.key,
    this.initialTab = 'following',
  });

  @override
  ConsumerState<HomePage> createState() => _HomePageState();
}

class _HomePageState extends ConsumerState<HomePage> with TickerProviderStateMixin {
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

  /// 构建视频频道内容
  Widget _buildVideoChannel() {
    return const VideoChannelPage();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    
    // 设置状态栏背景色与主题同步
    WidgetsBinding.instance.addPostFrameCallback((_) {
      SystemChrome.setSystemUIOverlayStyle(
        SystemUiOverlayStyle(
          statusBarColor: isDark 
            ? const Color(0xFF000000)  // 直接使用纯黑色
            : AppColors.light.backgroundPrimary,
          statusBarIconBrightness: isDark ? Brightness.light : Brightness.dark,
          systemNavigationBarColor: Colors.transparent,
          systemNavigationBarIconBrightness: Brightness.dark,
        ),
      );
    });
    
    return Scaffold(
      backgroundColor: isDark 
        ? AppColors.dark.backgroundSecondary
        : AppColors.light.backgroundPrimary,
      body: SafeArea(
        child: Column(
          children: [
            // Tab导航 - 恢复SafeArea，不侵入状态栏
            TabNavigationWidget(
              activeTab: _activeTab,
              onTabChange: (tab) {
                setState(() {
                  _activeTab = tab;
                });
              },
            ),
          
          // 主内容区域
          Expanded(
            child: _activeTab == 'video' 
              ? _buildVideoChannel()
              : FeedSection(
                  category: _activeTab,
                  onPostTap: (post, index) {
                    // 处理post点击
                    if (post['type'] == 'image') {
                      // 使用传递的索引作为photoIndex
                      context.push('/media-viewer/${post['username']}/$index');
                    } else if (post['type'] == 'video') {
                      // 处理视频点击
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
      ),
    );
  }

}
