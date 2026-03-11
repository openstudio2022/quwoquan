import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_header.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_stats_row.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_action_bar.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_resonance_card.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_moments_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_works_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_circles_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';

class ProfileShell extends ConsumerStatefulWidget {
  const ProfileShell({
    super.key,
    required this.mode,
    required this.userId,
    this.initialAvatarUrl,
    this.initialDisplayName,
    this.initialBackgroundUrl,
    this.onBack,
  });

  final ProfileMode mode;
  final String userId;
  final String? initialAvatarUrl;
  final String? initialDisplayName;
  final String? initialBackgroundUrl;
  final VoidCallback? onBack;

  @override
  ConsumerState<ProfileShell> createState() => _ProfileShellState();
}

class _ProfileShellState extends ConsumerState<ProfileShell>
    with TickerProviderStateMixin {
  late TabController _mainTabController;
  late AnimationController _pullBackController;
  int _activeTabIndex = 0;
  double _pullOffset = 0;
  double _rawPullOffset = 0;
  bool _isPulling = false;
  bool _isHeaderCollapsed = false;

  static const _tabLabels = ['微趣', '作品', '圈子', '互动'];

  @override
  void initState() {
    super.initState();
    _mainTabController = TabController(length: 4, vsync: this);
    _mainTabController.addListener(_onTabChanged);
    _pullBackController = AnimationController(
      duration: const Duration(milliseconds: 250),
      vsync: this,
    );
  }

  @override
  void dispose() {
    _mainTabController.removeListener(_onTabChanged);
    _mainTabController.dispose();
    _pullBackController.dispose();
    super.dispose();
  }

  // — 关系动作 —

  void _showGreetDialog(BuildContext context) {
    // TODO(D2): 打招呼对话框（自定义内容 + GreetingRepository.sendGreeting）
    // 当前阶段使用 Snackbar 占位，待 greeting_repository 后端就绪后替换
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('打招呼功能即将上线')),
    );
  }

  Future<void> _startCall(BuildContext context, String callType) async {
    final router = GoRouter.of(context);
    final notifier = ref.read(callSessionProvider.notifier);
    final callId = await notifier.initiateCall(
      callTypeStr: callType,
      targetUserIds: [widget.userId],
      conversationId: widget.userId,
    );
    if (!mounted) return;
    if (callId != null) {
      router.push(AppRoutePaths.rtcOutgoing(callId: callId));
    }
  }

  // — Tab management —

  void _onTabChanged() {
    if (_mainTabController.indexIsChanging) return;
    final newIndex = _mainTabController.index;
    if (newIndex != _activeTabIndex) {
      setState(() => _activeTabIndex = newIndex);
    }
  }

  void _onTabTap(int index) {
    setState(() => _activeTabIndex = index);
  }

  // — Spring-damped pull-to-stretch (KD11) —

  double _springDampedOffset(double raw, double maxPull) {
    if (raw <= 0 || maxPull <= 0) return 0;
    final damping = maxPull / 1.2;
    return (maxPull * (1 - exp(-raw / damping))).clamp(0.0, maxPull);
  }

  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification is ScrollUpdateNotification) {
      final pixels = notification.metrics.pixels;
      if (pixels < 0) {
        final screenHeight = MediaQuery.of(context).size.height;
        final expandedHeight =
            max(420.0, screenHeight * 0.25 + kToolbarHeight);
        final maxPull = min(screenHeight * 0.25, expandedHeight);
        setState(() {
          _rawPullOffset = -pixels;
          _pullOffset = _springDampedOffset(_rawPullOffset, maxPull);
          _isPulling = true;
        });
      } else if (_isPulling) {
        _isPulling = false;
        _animatePullBack();
      } else if (_pullOffset != 0) {
        setState(() {
          _pullOffset = 0;
          _rawPullOffset = 0;
        });
      }
    }
    return false;
  }

  void _animatePullBack() {
    if (_pullOffset <= 0) return;
    final startOffset = _pullOffset;
    void listener() {
      if (!mounted) return;
      setState(() {
        _pullOffset = startOffset * (1 - _pullBackController.value);
        if (_pullBackController.isCompleted) {
          _pullOffset = 0;
          _rawPullOffset = 0;
        }
      });
    }

    _pullBackController
      ..reset()
      ..addListener(listener);
    _pullBackController.forward().then((_) {
      _pullBackController.removeListener(listener);
    });
  }

  // — Build —

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final notifier = ref.watch(profileNotifierProvider(widget.userId));
    final state = notifier.state;
    final userData = ref.watch(userDataProvider);
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final primary = AppColors.primaryColor;

    final avatarUrl = widget.initialAvatarUrl ?? userData?.avatar;
    final displayName = widget.initialDisplayName ?? userData?.displayName ?? widget.userId;
    final bio = userData?.bio;
    final backgroundUrl = widget.initialBackgroundUrl ?? userData?.backgroundImage;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: _isHeaderCollapsed
            ? (isDark ? Brightness.light : Brightness.dark)
            : Brightness.light,
        statusBarBrightness: _isHeaderCollapsed
            ? (isDark ? Brightness.dark : Brightness.light)
            : Brightness.dark,
      ),
      child: Scaffold(
        backgroundColor: bg,
        body: NotificationListener<ScrollNotification>(
          onNotification: _handleScrollNotification,
          child: NestedScrollView(
            headerSliverBuilder: (context, innerBoxIsScrolled) {
              if (innerBoxIsScrolled != _isHeaderCollapsed) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  if (mounted) setState(() => _isHeaderCollapsed = innerBoxIsScrolled);
                });
              }

              return [
                SliverAppBar(
                  expandedHeight: max(
                    420.0,
                    MediaQuery.sizeOf(context).height * 0.25 + kToolbarHeight,
                  ),
                  pinned: true,
                  backgroundColor: bg,
                  foregroundColor: fg,
                  leading: widget.mode == ProfileMode.other
                      ? IconButton(
                          icon: const Icon(Icons.arrow_back),
                          onPressed: widget.onBack ?? () => context.pop(),
                        )
                      : null,
                  automaticallyImplyLeading: false,
                  title: AnimatedOpacity(
                    opacity: innerBoxIsScrolled ? 1.0 : 0.0,
                    duration: const Duration(milliseconds: 200),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (avatarUrl != null && avatarUrl.isNotEmpty)
                          CircleAvatar(
                            radius: AppSpacing.intraGroupLg,
                            backgroundImage: NetworkImage(avatarUrl),
                            onBackgroundImageError: (e, s) {},
                          ),
                        SizedBox(width: AppSpacing.sm),
                        Text(
                          displayName,
                          style: TextStyle(
                            fontSize: AppTypography.lg,
                            fontWeight: AppTypography.semiBold,
                            color: fg,
                          ),
                        ),
                      ],
                    ),
                  ),
                  actions: [
                    if (widget.mode == ProfileMode.mine)
                      IconButton(
                        icon: const Icon(Icons.settings_outlined),
                        onPressed: () => context.push(AppRoutePaths.settings),
                      )
                    else
                      IconButton(
                        icon: const Icon(Icons.more_horiz),
                        onPressed: () => _showMoreOptions(context, isDark),
                      ),
                  ],
                  flexibleSpace: FlexibleSpaceBar(
                    background: Stack(
                      fit: StackFit.expand,
                      children: [
                        if (backgroundUrl != null && backgroundUrl.isNotEmpty)
                          Transform.scale(
                            scale: 1 + (_pullOffset / (MediaQuery.of(context).size.height * 0.25 + 1) / 2),
                            child: Image.network(
                              backgroundUrl,
                              fit: BoxFit.cover,
                              errorBuilder: (c, e, s) => Container(color: bg),
                            ),
                          ),
                        Container(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              begin: Alignment.topCenter,
                              end: Alignment.bottomCenter,
                              colors: [
                                Colors.transparent,
                                bg.withValues(alpha: 0.4),
                                bg.withValues(alpha: 0.85),
                                bg,
                              ],
                              stops: const [0.0, 0.35, 0.6, 0.75],
                            ),
                          ),
                        ),
                        SafeArea(
                          bottom: false,
                          child: Padding(
                            padding: EdgeInsets.only(
                              top: kToolbarHeight,
                              left: AppSpacing.containerMd,
                              right: AppSpacing.containerMd,
                              bottom: AppSpacing.sm,
                            ),
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.end,
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                ProfileHeader(
                                  isDark: isDark,
                                  avatarUrl: avatarUrl,
                                  displayName: displayName,
                                  bio: bio,
                                ),
                                SizedBox(height: AppSpacing.md),
                                ProfileResonanceCard(
                                  mode: widget.mode,
                                  isDark: isDark,
                                  resonanceCount: 128,
                                  onTap: () => context.push(AppRoutePaths.profileResonance),
                                ),
                                SizedBox(height: AppSpacing.sm),
                                ProfileStatsRow(
                                  isDark: isDark,
                                  stats: state.stats,
                                  onStatTap: (type) => context.push(
                                    '${AppRoutePaths.profileStats(type: type)}&userId=${Uri.encodeComponent(widget.userId)}',
                                  ),
                                ),
                                SizedBox(height: AppSpacing.sm),
                                ProfileActionBar(
                                  mode: widget.mode,
                                  isDark: isDark,
                                  isFollowing: state.isFollowing,
                                  capability: state.capability,
                                  onEditProfile: () => context.push(AppRoutePaths.profileEdit),
                                  onManagePersonas: () => context.push(AppRoutePaths.profilePersonas),
                                  onFollow: notifier.toggleFollow,
                                  onMessage: () => context.push(
                                    AppRoutePaths.chatDetail(
                                      id: widget.userId,
                                    ),
                                  ),
                                  onGreet: () => _showGreetDialog(context),
                                  onVoiceCall: () => _startCall(context, 'voice'),
                                  onVideoCall: () => _startCall(context, 'video'),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                SliverPersistentHeader(
                  pinned: true,
                  delegate: _TabBarDelegate(
                    child: Container(
                      color: bg,
                      child: TabBar(
                        controller: _mainTabController,
                        labelColor: fg,
                        unselectedLabelColor: fgSecondary,
                        labelStyle: TextStyle(
                          fontSize: AppTypography.lg,
                          fontWeight: AppTypography.semiBold,
                        ),
                        unselectedLabelStyle: TextStyle(
                          fontSize: AppTypography.lg,
                          fontWeight: AppTypography.normal,
                        ),
                        indicatorColor: primary,
                        indicatorSize: TabBarIndicatorSize.label,
                        tabs: _tabLabels
                            .map((l) => Tab(child: Text(l)))
                            .toList(),
                        onTap: _onTabTap,
                      ),
                    ),
                    height: AppSpacing.tabNavigationHeight,
                  ),
                ),
              ];
            },
            body: _buildTabBody(context, isDark),
          ),
        ),
      ),
    );
  }

  Widget _buildTabBody(BuildContext context, bool isDark) {
    final tabView = TabBarView(
      controller: _mainTabController,
      children: [
        ProfileMomentsTab(mode: widget.mode, userId: widget.userId, isDark: isDark),
        ProfileWorksTab(mode: widget.mode, userId: widget.userId, isDark: isDark),
        ProfileCirclesTab(mode: widget.mode, userId: widget.userId, isDark: isDark),
        ProfileInteractionTab(mode: widget.mode, userId: widget.userId, isDark: isDark),
      ],
    );

    if (widget.mode == ProfileMode.mine) {
      final bottomNavInset =
          AppSpacing.bottomNavHeight + MediaQuery.viewPaddingOf(context).bottom;
      return Padding(
        padding: EdgeInsets.only(bottom: bottomNavInset),
        child: tabView,
      );
    }
    return tabView;
  }

  void _showMoreOptions(BuildContext context, bool isDark) {
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);

    showModalBottomSheet<void>(
      context: context,
      backgroundColor: bg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(AppSpacing.largeBorderRadius),
        ),
      ),
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(height: AppSpacing.sm),
            Container(
              width: AppSpacing.xl,
              height: AppSpacing.intraGroupXs,
              decoration: BoxDecoration(
                color: fg.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
              ),
            ),
            ListTile(
              leading: Icon(Icons.block, color: fg),
              title: Text('拉黑', style: TextStyle(color: fg)),
              onTap: () => Navigator.pop(context),
            ),
            ListTile(
              leading: Icon(Icons.flag_outlined, color: fg),
              title: Text('举报', style: TextStyle(color: fg)),
              onTap: () => Navigator.pop(context),
            ),
            ListTile(
              leading: Icon(Icons.share_outlined, color: fg),
              title: Text('分享', style: TextStyle(color: fg)),
              onTap: () => Navigator.pop(context),
            ),
          ],
        ),
      ),
    );
  }
}

class _TabBarDelegate extends SliverPersistentHeaderDelegate {
  const _TabBarDelegate({required this.child, required this.height});

  final Widget child;
  final double height;

  @override
  double get minExtent => height;

  @override
  double get maxExtent => height;

  @override
  Widget build(BuildContext context, double shrinkOffset, bool overlapsContent) {
    return SizedBox.expand(child: child);
  }

  @override
  bool shouldRebuild(_TabBarDelegate oldDelegate) {
    return height != oldDelegate.height;
  }
}
