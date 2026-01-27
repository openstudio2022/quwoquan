import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/features/video/pages/video_channel_page.dart';
import 'package:quwoquan_app/shared/components/feed_section.dart';
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

  /// 构建视频频道内容
  Widget _buildVideoChannel() {
    return const VideoChannelPage();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);

    // 设置状态栏为透明，实现侵入式体验
    WidgetsBinding.instance.addPostFrameCallback((_) {
      SystemChrome.setSystemUIOverlayStyle(
        SystemUiOverlayStyle(
          statusBarColor: Colors.transparent, // 透明状态栏，让背景色自然延伸
          statusBarIconBrightness: isDark ? Brightness.light : Brightness.dark,
          systemNavigationBarColor: Colors.transparent,
          systemNavigationBarIconBrightness: Brightness.dark,
        ),
      );
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
                        context
                            .push('/media-viewer/${post['username']}/$index');
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
    );
  }
}
