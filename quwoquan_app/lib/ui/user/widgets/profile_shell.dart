import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_header.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_stats_row.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_action_bar.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_resonance_card.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_creations_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_circles_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_lifestyle_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/creation_visibility_popup.dart';

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
  bool _showVisibilityPopup = false;
  double _pullOffset = 0;
  double _rawPullOffset = 0;
  bool _isPulling = false;
  bool _isHeaderCollapsed = false;

  final LayerLink _tabBarLayerLink = LayerLink();
  OverlayEntry? _popupEntry;
  Timer? _autoDismissTimer;

  static const _tabLabels = ['创作', '圈子', '互动', '生活'];

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
    _autoDismissTimer?.cancel();
    _autoDismissTimer = null;
    _popupEntry?.remove();
    _popupEntry = null;
    _mainTabController.removeListener(_onTabChanged);
    _mainTabController.dispose();
    _pullBackController.dispose();
    super.dispose();
  }

  // — Tab management —

  void _onTabChanged() {
    if (_mainTabController.indexIsChanging) return;
    final newIndex = _mainTabController.index;
    if (newIndex != _activeTabIndex) {
      setState(() => _activeTabIndex = newIndex);
    }
    if (newIndex != 0) _dismissPopup();
  }

  void _onTabTap(int index) {
    if (index == 0) {
      if (_showVisibilityPopup) {
        _dismissPopup();
      } else {
        _openVisibilityPopup();
      }
    } else {
      _dismissPopup();
      setState(() => _activeTabIndex = index);
    }
  }

  // — Visibility popup —

  void _openVisibilityPopup() {
    if (!mounted) return;
    setState(() => _showVisibilityPopup = true);

    _popupEntry = OverlayEntry(
      builder: (overlayCtx) => Consumer(
        builder: (ctx, ref, _) {
          final notifier = ref.watch(profileNotifierProvider(widget.userId));
          final isDark = ref.watch(isDarkProvider);
          return _VisibilityPopupOverlay(
            link: _tabBarLayerLink,
            mode: widget.mode,
            current: notifier.state.activeVisibility,
            isDark: isDark,
            onSelected: (v) {
              notifier.setVisibility(v);
              _dismissPopup();
            },
            onDismiss: _dismissPopup,
          );
        },
      ),
    );
    Overlay.of(context).insert(_popupEntry!);
    _autoDismissTimer = Timer(const Duration(seconds: 5), () {
      if (mounted) _dismissPopup();
    });
  }

  void _dismissPopup() {
    _autoDismissTimer?.cancel();
    _autoDismissTimer = null;
    _popupEntry?.remove();
    _popupEntry = null;
    if (mounted && _showVisibilityPopup) {
      setState(() => _showVisibilityPopup = false);
    }
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
        final maxPull = screenHeight * 0.25;
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
                  expandedHeight: 420,
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
                        onPressed: () => context.push('/settings'),
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
                                  onTap: () => context.push('/profile/resonance'),
                                ),
                                SizedBox(height: AppSpacing.sm),
                                ProfileStatsRow(
                                  isDark: isDark,
                                  stats: state.stats,
                                  onStatTap: (type) => context.push('/profile/stats?type=$type'),
                                ),
                                SizedBox(height: AppSpacing.sm),
                                ProfileActionBar(
                                  mode: widget.mode,
                                  isDark: isDark,
                                  isFollowing: state.isFollowing,
                                  onEditProfile: () => context.push('/profile/edit'),
                                  onManagePersonas: () => context.push('/profile/personas'),
                                  onFollow: notifier.toggleFollow,
                                  onMessage: () {},
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
                    child: CompositedTransformTarget(
                      link: _tabBarLayerLink,
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
                          tabs: List.generate(_tabLabels.length, (i) {
                            if (i == 0) {
                              return Tab(
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Text(_tabLabels[0]),
                                    SizedBox(width: AppSpacing.intraGroupXs / 2),
                                    Visibility(
                                      visible: _activeTabIndex == 0,
                                      maintainSize: true,
                                      maintainAnimation: true,
                                      maintainState: true,
                                      child: AnimatedRotation(
                                        turns: _showVisibilityPopup ? 0.5 : 0,
                                        duration: const Duration(milliseconds: 200),
                                        child: Icon(
                                          Icons.keyboard_arrow_down,
                                          size: AppTypography.lg,
                                          color: _activeTabIndex == 0
                                              ? fg
                                              : Colors.transparent,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              );
                            }
                            return Tab(child: Text(_tabLabels[i]));
                          }),
                          onTap: _onTabTap,
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
    final tabView = TabBarView(
      controller: _mainTabController,
      children: [
        ProfileCreationsTab(mode: widget.mode, userId: widget.userId, isDark: isDark),
        ProfileCirclesTab(mode: widget.mode, userId: widget.userId, isDark: isDark),
        ProfileInteractionTab(mode: widget.mode, userId: widget.userId, isDark: isDark),
        ProfileLifestyleTab(mode: widget.mode, userId: widget.userId, isDark: isDark),
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

class _VisibilityPopupOverlay extends StatelessWidget {
  const _VisibilityPopupOverlay({
    required this.link,
    required this.mode,
    required this.current,
    required this.isDark,
    required this.onSelected,
    required this.onDismiss,
  });

  final LayerLink link;
  final ProfileMode mode;
  final CreationVisibility current;
  final bool isDark;
  final ValueChanged<CreationVisibility> onSelected;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Positioned.fill(
          child: GestureDetector(
            behavior: HitTestBehavior.translucent,
            onTap: onDismiss,
          ),
        ),
        CompositedTransformFollower(
          link: link,
          showWhenUnlinked: false,
          targetAnchor: Alignment.bottomLeft,
          followerAnchor: Alignment.topLeft,
          child: Material(
            type: MaterialType.transparency,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () {},
              child: Padding(
                padding: EdgeInsets.only(
                  left: AppSpacing.containerMd,
                  top: AppSpacing.xs,
                ),
                child: CreationVisibilityPopup(
                  mode: mode,
                  current: current,
                  isDark: isDark,
                  onSelected: onSelected,
                ),
              ),
            ),
          ),
        ),
      ],
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
