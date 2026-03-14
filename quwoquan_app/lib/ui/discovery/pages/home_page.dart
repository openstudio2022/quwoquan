import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/circle/pages/home_circles_hub_page.dart';
import 'package:quwoquan_app/ui/discovery/widgets/moment_social_feed.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';

class HomePage extends ConsumerStatefulWidget {
  const HomePage({super.key});

  @override
  ConsumerState<HomePage> createState() => _HomePageState();
}

class _HomePageState extends ConsumerState<HomePage>
    with AutomaticKeepAliveClientMixin {
  static const String _defaultTab = 'circles'; // Change default to circles to avoid starting in immersive mode without nav
  String _activeTab = _defaultTab;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    // Ensure state consistency on load
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _updateImmersiveState();
    });
  }

  void _handleTabChange(String id) {
    if (_activeTab == id) return;
    setState(() => _activeTab = id);
    _updateImmersiveState();
  }

  void _updateImmersiveState() {
    final isImmersive = _activeTab == 'featured';
    // Use Future.microtask to avoid build conflicts if called during build
    Future.microtask(() {
      if (!mounted) return;
      ref.read(bottomNavHiddenProvider.notifier).setHidden(isImmersive);
      ref.read(videoForceDarkProvider.notifier).setForceDark(isImmersive);
    });
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    
    // 沉浸式模式（精品页）直接返回全屏 Viewer
    if (_activeTab == 'featured') {
      return CupertinoPageScaffold(
        backgroundColor: Colors.black, // Immersive background
        child: WorksImmersiveViewer(
          showWorksToolbar: true,
          onUserTap: _openUserProfile,
          onAssistantTap: _openAssistantHalfSheet,
          // 点击关闭/切换到圈子 (X 按钮 - 暂时保留作为后备)
          onSwitchToMoment: () => _handleTabChange('circles'),
          // 顶部导航回调
          onSwitchToFollowing: () => _handleTabChange('following'),
          onSwitchToCircles: () => _handleTabChange('circles'),
        ),
      );
    }

    // 常规模式
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final tabs = const <TabItem>[
      TabItem(id: 'following', label: UITextConstants.homeTabFollowing),
      TabItem(id: 'featured', label: UITextConstants.homeTabFeatured),
      TabItem(id: 'circles', label: UITextConstants.homeTabCircles),
    ];

    return CupertinoPageScaffold(
      backgroundColor: bg,
      child: SafeArea(
        bottom: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              height: AppSpacing.tabNavigationHeight,
              decoration: BoxDecoration(
                color: bg,
                border: Border(
                  bottom: BorderSide(
                    color: fgSecondary.withValues(alpha: 0.15),
                  ),
                ),
              ),
              child: Stack(
                children: [
                  // Layer 1: Absolutely Centered Tabs
                  Positioned.fill(
                    child: Center(
                      child: CenteredScrollableTabBar(
                        tabs: tabs,
                        activeTab: _activeTab,
                        onTabChange: _handleTabChange,
                        // Remove actions from here to ensure centering
                        leadingActions: const [],
                        trailingActions: const [],
                        // Ensure background is transparent so it doesn't cover actions if expanding
                        transparentBackground: true,
                      ),
                    ),
                  ),
                  // Layer 2: Trailing Actions
                  Positioned(
                    right: AppSpacing.feedContentHorizontal(context),
                    top: 0,
                    bottom: 0,
                    child: const Center(
                      child: GlobalTopActions(
                        initialSearchScope: GlobalSearchScope.content,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(child: _buildBody(isDark)),
          ],
        ),
      ),
    );
  }

  Widget _buildBody(bool isDark) {
    switch (_activeTab) {
      case 'following':
        return MomentSocialFeed(
          isDark: isDark,
          feedTabId: 'following',
          onUserTap: _openUserProfile,
        );
      case 'circles':
        return const HomeCirclesHubPage();
      case 'featured':
        // This case is handled in the main build method now for full screen
        return const SizedBox.shrink(); 
      default:
        return const SizedBox.shrink();
    }
  }

  void _openUserProfile(
    String userId, {
    String? avatarUrl,
    String? displayName,
    String? backgroundUrl,
  }) {
    context.push(
      AppRoutePaths.userProfile(username: userId),
      extra: UserProfileRouteExtra(
        avatar: avatarUrl,
        displayName: displayName,
        backgroundImage: backgroundUrl,
      ),
    );
  }

  void _openAssistantHalfSheet() {
    final target = VisitTarget.page('home_$_activeTab');
    final service = ref.read(visitRecorderServiceProvider);
    final ctx = AssistantOpenContext(
      source: AssistantSource.discovery,
      tab: _activeTab,
      visitTarget: target,
      experienceLevel: service.getExperience(target),
    );
    AssistantHalfSheet.show(context, ctx);
  }
}
