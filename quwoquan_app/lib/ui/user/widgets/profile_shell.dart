import 'dart:math';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_header.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_stats_row.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_action_bar.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_resonance_card.dart';
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
  late PageController _pageController;
  late AnimationController _pullBackController;
  int _activeTabIndex = 0;
  double _pullOffset = 0;
  double _rawPullOffset = 0;
  bool _isPulling = false;
  bool _isHeaderCollapsed = false;

  @override
  void initState() {
    super.initState();
    _pageController = PageController(initialPage: 0);
    _pullBackController = AnimationController(
      duration: const Duration(milliseconds: 250),
      vsync: this,
    );
  }

  @override
  void dispose() {
    _pageController.dispose();
    _pullBackController.dispose();
    super.dispose();
  }

  // — 关系动作 —

  void _showGreetDialog(BuildContext context) {
    // TODO(D2): 打招呼对话框（自定义内容 + GreetingRepository.sendGreeting）
    // 当前阶段使用 Snackbar 占位，待 greeting_repository 后端就绪后替换
    AppToast.show(context, '打招呼功能即将上线');
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
        final expandedHeight = max(420.0, screenHeight * 0.25 + kToolbarHeight);
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
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );

    final avatarUrl = widget.initialAvatarUrl ?? userData?.avatar;
    final displayName =
        widget.initialDisplayName ?? userData?.displayName ?? widget.userId;
    final bio = userData?.bio;
    final backgroundUrl =
        widget.initialBackgroundUrl ?? userData?.backgroundImage;

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
      child: AppScaffold(
        backgroundColor: bg,
        child: NotificationListener<ScrollNotification>(
          onNotification: _handleScrollNotification,
          child: NestedScrollView(
            headerSliverBuilder: (context, innerBoxIsScrolled) {
              if (innerBoxIsScrolled != _isHeaderCollapsed) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  if (mounted)
                    setState(() => _isHeaderCollapsed = innerBoxIsScrolled);
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
                      ? CupertinoButton(
                          padding: EdgeInsets.zero,
                          child: const Icon(CupertinoIcons.back),
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
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        child: const Icon(CupertinoIcons.settings),
                        onPressed: () => context.push(AppRoutePaths.settings),
                      )
                    else
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        child: const Icon(CupertinoIcons.ellipsis),
                        onPressed: () => _showMoreOptions(context, isDark),
                      ),
                  ],
                  flexibleSpace: FlexibleSpaceBar(
                    background: Stack(
                      fit: StackFit.expand,
                      children: [
                        if (backgroundUrl != null && backgroundUrl.isNotEmpty)
                          Transform.scale(
                            scale:
                                1 +
                                (_pullOffset /
                                    (MediaQuery.of(context).size.height * 0.25 +
                                        1) /
                                    2),
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
                                  onTap: () => context.push(
                                    AppRoutePaths.profileResonance,
                                  ),
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
                                  onEditProfile: () =>
                                      context.push(AppRoutePaths.profileEdit),
                                  onManagePersonas: () => context.push(
                                    AppRoutePaths.profilePersonas,
                                  ),
                                  onFollow: notifier.toggleFollow,
                                  onMessage: () => context.push(
                                    AppRoutePaths.chatDetail(id: widget.userId),
                                  ),
                                  onGreet: () => _showGreetDialog(context),
                                  onVoiceCall: () =>
                                      _startCall(context, 'voice'),
                                  onVideoCall: () =>
                                      _startCall(context, 'video'),
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
                      padding: EdgeInsets.symmetric(vertical: 8),
                      child: Center(
                        child: CupertinoSlidingSegmentedControl<int>(
                          groupValue: _activeTabIndex,
                          children: const {
                            0: Padding(padding: EdgeInsets.symmetric(horizontal: 20), child: Text('创作')),
                            1: Padding(padding: EdgeInsets.symmetric(horizontal: 20), child: Text('圈子')),
                            2: Padding(padding: EdgeInsets.symmetric(horizontal: 20), child: Text('互动')),
                          },
                          onValueChanged: (index) {
                            if (index != null) {
                              _onTabTap(index);
                              _pageController.animateToPage(
                                index,
                                duration: const Duration(milliseconds: 300),
                                curve: Curves.easeInOut,
                              );
                            }
                          },
                        ),
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
    final tabView = PageView(
      controller: _pageController,
      physics: const BouncingScrollPhysics(),
      onPageChanged: (index) => setState(() => _activeTabIndex = index),
      children: [
        ProfileWorksTab(
          mode: widget.mode,
          userId: widget.userId,
          isDark: isDark,
        ),
        ProfileCirclesTab(
          mode: widget.mode,
          userId: widget.userId,
          isDark: isDark,
        ),
        ProfileInteractionTab(
          mode: widget.mode,
          userId: widget.userId,
          isDark: isDark,
        ),
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
    showCupertinoModalPopup<void>(
      context: context,
      builder: (context) => CupertinoActionSheet(
        actions: [
          CupertinoActionSheetAction(
            onPressed: () => Navigator.pop(context),
            child: const Text('拉黑'),
          ),
          CupertinoActionSheetAction(
            onPressed: () => Navigator.pop(context),
            child: const Text('举报'),
          ),
          CupertinoActionSheetAction(
            onPressed: () => Navigator.pop(context),
            child: const Text('分享'),
          ),
        ],
        cancelButton: CupertinoActionSheetAction(
          isDefaultAction: true,
          onPressed: () => Navigator.pop(context),
          child: const Text('取消'),
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
  Widget build(
    BuildContext context,
    double shrinkOffset,
    bool overlapsContent,
  ) {
    return SizedBox.expand(child: child);
  }

  @override
  bool shouldRebuild(_TabBarDelegate oldDelegate) {
    return height != oldDelegate.height;
  }
}
