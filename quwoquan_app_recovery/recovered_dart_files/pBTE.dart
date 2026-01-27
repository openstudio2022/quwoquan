import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/features/chat/pages/chat_page.dart';
import 'package:quwoquan_app/features/create/pages/create_page.dart';
import 'package:quwoquan_app/features/home/pages/home_page.dart';
import 'package:quwoquan_app/features/profile/pages/my_profile_page.dart';
import 'package:quwoquan_app/features/search/pages/search_page.dart';

/// 页面索引常量
class PageIndices {
  static const int home = 0;
  static const int search = 1;
  static const int create = 2;
  static const int chat = 3;
  static const int profile = 4;
}

/// 主布局组件，包含固定的底部导航栏
class MainLayout extends ConsumerStatefulWidget {
  final String initialRoute;
  final Map<String, dynamic>? routeParams;

  const MainLayout({
    super.key,
    this.initialRoute = '/',
    this.routeParams,
  });

  @override
  ConsumerState<MainLayout> createState() => _MainLayoutState();
}

class _MainLayoutState extends ConsumerState<MainLayout> {
  int _currentIndex = 0;
  late PageController _pageController;

  final List<Map<String, dynamic>> _navItems = [
    {
      'icon': Icons.home,
      'label': UITextConstants.home,
      'route': '/',
    },
    {
      'icon': Icons.search,
      'label': UITextConstants.search,
      'route': '/search',
    },
    {
      'icon': Icons.add_circle,
      'label': UITextConstants.create,
      'route': '/create',
    },
    {
      'icon': Icons.chat_bubble_outline, // 使用单个聊天气泡图标
      'label': UITextConstants.chat,
      'route': '/chat',
    },
    {
      'icon': Icons.person,
      'label': UITextConstants.profile,
      'route': '/my-profile',
    },
  ];

  @override
  void initState() {
    super.initState();
    _pageController = PageController();
    _setInitialIndex();
  }

  void _setInitialIndex() {
    switch (widget.initialRoute) {
      case '/':
        _currentIndex = 0;
        break;
      case '/search':
        _currentIndex = 1;
        break;
      case '/create':
        _currentIndex = 2;
        break;
      case '/chat':
        _currentIndex = 3;
        break;
      case '/my-profile':
        _currentIndex = 4;
        break;
      default:
        _currentIndex = 0;
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  void _onNavItemTap(int index) {
    if (index == _currentIndex) return;

    setState(() {
      _currentIndex = index;
    });

    _pageController.animateToPage(
      index,
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeInOut,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer(
      builder: (context, ref, child) {
        final isDark = ref.watch(effectiveIsDarkProvider);

        // 设置状态栏样式，确保在所有页面中都能正确显示
        SystemChrome.setSystemUIOverlayStyle(
          SystemUiOverlayStyle(
            statusBarColor: Colors.transparent,
            statusBarIconBrightness: isDark ? Brightness.light : Brightness.dark,
            statusBarBrightness: isDark ? Brightness.dark : Brightness.light,
            systemNavigationBarColor: Colors.transparent,
            systemNavigationBarIconBrightness: Brightness.dark,
          ),
        );

        // 🔑 关键：让每个页面独立处理状态栏侵入
        return Scaffold(
          backgroundColor: Colors.transparent,
          extendBodyBehindAppBar: true, // 允许内容侵入状态栏
          body: Stack(
            children: [
              // 页面内容
              PageView(
                controller: _pageController,
                physics: const NeverScrollableScrollPhysics(), // 禁用主布局的PageView滑动
                onPageChanged: (index) {
                  setState(() {
                    _currentIndex = index;
                  });
                },
                children: const [
                  // 首页
                  HomePage(initialTab: 'following'),
                  // 搜索页
                  SearchPage(initialQuery: '', sourcePage: 'users'),
                  // 创建页
                  CreatePage(initialTab: 'moments'),
                  // 聊天页
                  ChatPage(initialTab: 'messages'),
                  // 我的页面
                  MyProfilePage(),
                ],
              ),
              // 底部导航栏（悬浮在所有页面上方）
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: _buildBottomNavigationBar(isDark),
              ),
            ],
          ),
        );
      },
    );
  }

  /// 构建底部导航栏
  Widget _buildBottomNavigationBar(bool isDark) {
    return Container(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        border: Border(
          top: BorderSide(
            color: AppColorsFunctional.getColor(isDark, ColorType.borderPrimary),
            width: context.safeGetIntraGroupSpacing(SpacingSize.xs) / 4,
          ),
        ),
      ),
      child: SafeArea(
        child: SizedBox(
          height: AppSpacing.bottomNavHeight,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: _navItems.asMap().entries.map((entry) {
              final index = entry.key;
              final item = entry.value;
              final isSelected = index == _currentIndex;

              return GestureDetector(
                onTap: () => _onNavItemTap(index),
                child: Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
                    vertical: context.safeGetContainerSpacing(SpacingSize.sm),
                  ),
                  child: Icon(
                    item['icon'] as IconData,
                    size: AppSpacing.iconLarge, // 使用语义图标尺寸
                    color: isSelected
                        ? AppColors.primaryColor
                        : AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                  ),
                ),
              );
            }).toList(),
          ),
        ),
      ),
    );
  }
}
