import 'dart:math';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_action_bar.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_circles_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_header.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_resonance_card.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_stats_row.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_works_tab.dart';

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

class _ProfileShellState extends ConsumerState<ProfileShell> {
  late final ScrollController _scrollController;
  final GlobalKey _summarySectionKey = GlobalKey();
  final GlobalKey _primaryTabKey = GlobalKey();
  final GlobalKey _worksSecondaryTabKey = GlobalKey();
  final GlobalKey _interactionSecondaryTabKey = GlobalKey();

  late String _activeTabId;
  double _pullOffset = 0;
  double _rawPullOffset = 0;
  double _scrollOffset = 0;
  double _summarySectionHeight = 0;

  @override
  void initState() {
    super.initState();
    _activeTabId = UserProfileUIConfig.defaultTabId;
    _scrollController = ScrollController()..addListener(_onScrollChanged);
  }

  @override
  void dispose() {
    _scrollController
      ..removeListener(_onScrollChanged)
      ..dispose();
    super.dispose();
  }

  void _onScrollChanged() {
    if (!_scrollController.hasClients) return;
    final nextOffset = max(0.0, _scrollController.offset);
    if ((nextOffset - _scrollOffset).abs() < 0.5) return;
    setState(() => _scrollOffset = nextOffset);
  }

  void _showGreetDialog(BuildContext context) {
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

  void _onPrimaryTabChange(String tabId) {
    if (tabId == _activeTabId) return;
    setState(() => _activeTabId = tabId);
  }

  void _handleTabSwipeDragEnd(DragEndDetails details) {
    final direction = TabSwipeSwitchRegion.directionFromDragEnd(details);
    if (direction == null) {
      return;
    }
    _handleTabSwipe(direction);
  }

  void _handleTabSwipe(TabSwipeDirection direction) {
    final notifier = ref.read(profileNotifierProvider(widget.userId));
    if (_trySwitchVisibleSecondaryTab(direction, notifier)) {
      return;
    }
    final tabIds = UserProfileUIConfig.profileTabs
        .map((tab) => tab.id)
        .toList(growable: false);
    final currentIndex = tabIds.indexOf(_activeTabId);
    if (currentIndex < 0) {
      return;
    }
    final nextIndex = currentIndex + direction.delta;
    if (nextIndex < 0 || nextIndex >= tabIds.length) {
      return;
    }
    _onPrimaryTabChange(tabIds[nextIndex]);
  }

  bool _trySwitchVisibleSecondaryTab(
    TabSwipeDirection direction,
    ProfileNotifier notifier,
  ) {
    final state = notifier.state;
    if (_activeTabId == 'circles') {
      return false;
    }
    if (_activeTabId == 'interaction') {
      if (!_isSecondaryTabVisible(_interactionSecondaryTabKey)) {
        return false;
      }
      final filters = UserProfileUIConfig.interactionSubTabs;
      final currentIndex = filters.indexWhere(
        (filter) =>
            _interactionSubTabForId(filter.id) == state.interactionSubTab,
      );
      final nextIndex = currentIndex + direction.delta;
      if (nextIndex < 0 || nextIndex >= filters.length) {
        return false;
      }
      notifier.setInteractionSubTab(
        _interactionSubTabForId(filters[nextIndex].id),
      );
      return true;
    }
    if (!_isSecondaryTabVisible(_worksSecondaryTabKey)) {
      return false;
    }
    final filters = UserProfileUIConfig.creationSubTabs;
    final currentIndex = filters.indexWhere(
      (filter) => _creationSubTabForId(filter.id) == state.activeSubTab,
    );
    final nextIndex = currentIndex + direction.delta;
    if (nextIndex < 0 || nextIndex >= filters.length) {
      return false;
    }
    notifier.setSubTab(_creationSubTabForId(filters[nextIndex].id));
    return true;
  }

  bool _isSecondaryTabVisible(GlobalKey key) {
    final renderObject = key.currentContext?.findRenderObject();
    if (renderObject is! RenderBox ||
        !renderObject.attached ||
        !renderObject.hasSize) {
      return false;
    }
    final top = renderObject.localToGlobal(Offset.zero).dy;
    final bottom = top + renderObject.size.height;
    final pinnedPrimaryInset = _primaryTabPinnedProgress(context) > 0.01
        ? AppSpacing.tabNavigationHeight
        : 0.0;
    final viewportTop = _toolbarExtent(context) + pinnedPrimaryInset;
    final viewportBottom =
        MediaQuery.sizeOf(context).height -
        MediaQuery.viewPaddingOf(context).bottom;
    return bottom > viewportTop + 1 && top < viewportBottom - 1;
  }

  CreationSubTab _creationSubTabForId(String id) {
    switch (id) {
      case 'micro':
        return CreationSubTab.micro;
      case 'image':
        return CreationSubTab.image;
      case 'video':
        return CreationSubTab.video;
      case 'article':
        return CreationSubTab.article;
      default:
        return CreationSubTab.all;
    }
  }

  InteractionSubTab _interactionSubTabForId(String id) {
    switch (id) {
      case 'comments':
        return InteractionSubTab.comments;
      case 'shares':
        return InteractionSubTab.shares;
      case 'likes':
      default:
        return InteractionSubTab.likes;
    }
  }

  double _springDampedOffset(double raw, double maxPull) {
    if (raw <= 0 || maxPull <= 0) return 0;
    final damping = maxPull / 1.2;
    return (maxPull * (1 - exp(-raw / damping))).clamp(0.0, maxPull);
  }

  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification.metrics.axis != Axis.vertical) {
      return false;
    }
    if (notification is ScrollUpdateNotification ||
        notification is OverscrollNotification ||
        notification is ScrollEndNotification) {
      final pixels = notification.metrics.pixels;
      if (pixels < 0) {
        final maxPull =
            _maxStretchBackgroundHeight(context) -
            _baseBackgroundHeight(context);
        final nextRaw = -pixels;
        final nextPull = _springDampedOffset(nextRaw, maxPull);
        if ((nextRaw - _rawPullOffset).abs() < 0.5 &&
            (nextPull - _pullOffset).abs() < 0.5) {
          return false;
        }
        setState(() {
          _rawPullOffset = nextRaw;
          _pullOffset = nextPull;
        });
      } else if (_rawPullOffset != 0 || _pullOffset != 0) {
        setState(() {
          _pullOffset = 0;
          _rawPullOffset = 0;
        });
      }
    }
    return false;
  }

  double _baseBackgroundHeight(BuildContext context) {
    return MediaQuery.sizeOf(context).height *
        UserProfileUIConfig.headerLayout.baseHeightRatio;
  }

  double _maxStretchBackgroundHeight(BuildContext context) {
    return MediaQuery.sizeOf(context).height *
        UserProfileUIConfig.headerLayout.maxStretchHeightRatio;
  }

  double _currentBackgroundHeight(BuildContext context) {
    final base = _baseBackgroundHeight(context);
    final maxStretch = _maxStretchBackgroundHeight(context);
    return (base + _pullOffset).clamp(base, maxStretch);
  }

  double _backgroundSpacerHeight(BuildContext context) {
    return max(0.0, _currentBackgroundHeight(context) - _rawPullOffset);
  }

  double _summaryTopAtRest(BuildContext context) {
    return _baseBackgroundHeight(context);
  }

  double _toolbarExtent(BuildContext context) {
    return MediaQuery.paddingOf(context).top + kToolbarHeight;
  }

  double _pinTransitionDistance() {
    return max(
      AppSpacing.buttonHeight,
      ProfileHeader.avatarOuterDiameter * 0.55,
    );
  }

  double _primaryTabTopAtRest(BuildContext context) {
    return _summaryTopAtRest(context) + _summarySectionHeight;
  }

  double _identityPinnedProgress(BuildContext context) {
    final avatarBottom =
        _baseBackgroundHeight(context) +
        ProfileHeader.avatarOuterDiameter -
        ProfileHeader.avatarOverlapPx;
    final threshold = max(0.0, avatarBottom - _toolbarExtent(context));
    final raw = ((_scrollOffset - threshold) / _pinTransitionDistance()).clamp(
      0.0,
      1.0,
    );
    return _curveTransform(raw, UserProfileUIConfig.scrollMotion.collapseCurve);
  }

  double _primaryTabPinnedProgress(BuildContext context) {
    final threshold = max(
      0.0,
      _primaryTabTopAtRest(context) - _toolbarExtent(context),
    );
    final raw = ((_scrollOffset - threshold) / _pinTransitionDistance()).clamp(
      0.0,
      1.0,
    );
    return _curveTransform(raw, UserProfileUIConfig.scrollMotion.collapseCurve);
  }

  @override
  Widget build(BuildContext context) {
    _scheduleSectionMeasurement();
    final isDark = ref.watch(isDarkProvider);
    final notifier = ref.watch(profileNotifierProvider(widget.userId));
    final state = notifier.state;
    final userData = ref.watch(userDataProvider);
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final bgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    final profile = state.profile;
    final isMine = widget.mode == ProfileMode.mine;
    final avatarUrl =
        widget.initialAvatarUrl ??
        (isMine ? (userData?.avatar ?? userData?.avatarUrl) : null) ??
        profile?.avatarUrl;
    final displayName =
        widget.initialDisplayName ??
        (isMine ? userData?.displayName : null) ??
        profile?.displayName ??
        widget.userId;
    final bio = (profile?.bio.isNotEmpty ?? false)
        ? profile?.bio
        : userData?.bio;
    final backgroundUrl =
        widget.initialBackgroundUrl ??
        (isMine ? userData?.backgroundImage : null) ??
        ((profile?.backgroundUrl.isNotEmpty ?? false)
            ? profile?.backgroundUrl
            : null);
    final identityPinnedProgress = _identityPinnedProgress(context);
    final primaryPinnedProgress = _primaryTabPinnedProgress(context);
    final toolbarBackgroundOpacity = max(
      identityPinnedProgress,
      primaryPinnedProgress * 0.82,
    );
    final statusIconsDark = toolbarBackgroundOpacity > 0.12;
    final bottomPadding = isMine
        ? AppSpacing.bottomNavHeight + MediaQuery.viewPaddingOf(context).bottom
        : MediaQuery.viewPaddingOf(context).bottom + AppSpacing.interGroupLg;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: statusIconsDark
            ? (isDark ? Brightness.light : Brightness.dark)
            : Brightness.light,
        statusBarBrightness: statusIconsDark
            ? (isDark ? Brightness.dark : Brightness.light)
            : Brightness.dark,
      ),
      child: AppScaffold(
        backgroundColor: bg,
        body: Stack(
          children: [
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: SizedBox(
                key: const ValueKey<String>('profile-shell-background-layer'),
                height: _currentBackgroundHeight(context),
                child: _buildBackgroundLayer(
                  context,
                  backgroundUrl: backgroundUrl,
                  backgroundColor: bgSecondary,
                ),
              ),
            ),
            TabSwipeSwitchRegion(
              onSwipe: _handleTabSwipe,
              child: NotificationListener<ScrollNotification>(
                onNotification: _handleScrollNotification,
                child: CustomScrollView(
                  controller: _scrollController,
                  physics: const BouncingScrollPhysics(
                    parent: AlwaysScrollableScrollPhysics(),
                  ),
                  slivers: [
                    SliverToBoxAdapter(
                      child: SizedBox(height: _backgroundSpacerHeight(context)),
                    ),
                    SliverToBoxAdapter(
                      child: _buildSummarySection(
                        context,
                        isDark: isDark,
                        bg: bg,
                        border: border,
                        avatarUrl: avatarUrl,
                        displayName: displayName,
                        bio: bio,
                        state: state,
                        notifier: notifier,
                      ),
                    ),
                    SliverToBoxAdapter(
                      child: _buildPrimaryTabBarSurface(
                        isDark: isDark,
                        bg: bg,
                        border: border,
                        pinned: false,
                      ),
                    ),
                    SliverToBoxAdapter(
                      child: DecoratedBox(
                        decoration: BoxDecoration(color: bg),
                        child: Padding(
                          padding: EdgeInsets.only(bottom: bottomPadding),
                          child: ConstrainedBox(
                            constraints: BoxConstraints(
                              minHeight: max(
                                0.0,
                                MediaQuery.sizeOf(context).height -
                                    _toolbarExtent(context) -
                                    AppSpacing.bottomNavHeight,
                              ),
                            ),
                            child: _buildInlineTabContent(context, isDark),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            _buildToolbarOverlay(
              context,
              isDark: isDark,
              fg: fg,
              bg: bg,
              border: border,
              displayName: displayName,
              avatarUrl: avatarUrl,
              opacity: identityPinnedProgress,
              backgroundOpacity: toolbarBackgroundOpacity,
            ),
            if (UserProfileUIConfig.scrollMotion.primaryTabStickyBelowToolbar)
              Positioned(
                top: _toolbarExtent(context),
                left: 0,
                right: 0,
                child: Offstage(
                  offstage: primaryPinnedProgress <= 0.01,
                  child: IgnorePointer(
                    ignoring: primaryPinnedProgress <= 0,
                    child: Opacity(
                      opacity: primaryPinnedProgress,
                      child: _buildPrimaryTabBarSurface(
                        isDark: isDark,
                        bg: bg,
                        border: border,
                        pinned: true,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  void _scheduleSectionMeasurement() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final summaryHeight =
          _summarySectionKey.currentContext?.size?.height ?? 0;
      if ((summaryHeight - _summarySectionHeight).abs() < 0.5) {
        return;
      }
      setState(() {
        _summarySectionHeight = summaryHeight;
      });
    });
  }

  Widget _buildSummarySection(
    BuildContext context, {
    required bool isDark,
    required Color bg,
    required Color border,
    required String? avatarUrl,
    required String displayName,
    required String? bio,
    required ProfileState state,
    required ProfileNotifier notifier,
  }) {
    final shadowColor = isDark
        ? Colors.black.withValues(alpha: 0.18)
        : Colors.black.withValues(alpha: 0.08);
    return ColoredBox(
      key: _summarySectionKey,
      color: bg,
      child: Padding(
        padding: EdgeInsets.only(bottom: AppSpacing.sm),
        child: Container(
          key: const ValueKey<String>('profile-shell-summary-card'),
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.vertical(
              top: Radius.circular(
                AppSpacing.largeBorderRadius + AppSpacing.sm,
              ),
              bottom: Radius.circular(AppSpacing.largeBorderRadius),
            ),
            border: Border.all(color: border.withValues(alpha: 0.04)),
            boxShadow: [
              BoxShadow(
                color: shadowColor,
                blurRadius: AppSpacing.lg,
                offset: Offset(0, AppSpacing.xs),
              ),
            ],
          ),
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            0,
            AppSpacing.containerMd,
            AppSpacing.containerMd,
          ),
          child: Column(
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
                profile: state.profile,
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
                onManagePersonas: () =>
                    context.push(AppRoutePaths.profilePersonas),
                onFollow: notifier.toggleFollow,
                onMessage: () =>
                    context.push(AppRoutePaths.chatDetail(id: widget.userId)),
                onGreet: () => _showGreetDialog(context),
                onVoiceCall: () => _startCall(context, 'voice'),
                onVideoCall: () => _startCall(context, 'video'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildBackgroundLayer(
    BuildContext context, {
    required String? backgroundUrl,
    required Color backgroundColor,
  }) {
    return Stack(
      fit: StackFit.expand,
      children: [
        if (backgroundUrl != null && backgroundUrl.isNotEmpty)
          Image.network(
            backgroundUrl,
            fit: BoxFit.cover,
            errorBuilder: (context, error, stackTrace) =>
                ColoredBox(color: backgroundColor),
          )
        else
          ColoredBox(color: backgroundColor.withValues(alpha: 0.75)),
        Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                Colors.black.withValues(alpha: 0.08),
                Colors.black.withValues(alpha: 0.04),
                backgroundColor.withValues(alpha: 0.12),
              ],
              stops: const [0.0, 0.56, 1.0],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildToolbarOverlay(
    BuildContext context, {
    required bool isDark,
    required Color fg,
    required Color bg,
    required Color border,
    required String displayName,
    required String? avatarUrl,
    required double opacity,
    required double backgroundOpacity,
  }) {
    final topPadding = MediaQuery.paddingOf(context).top;
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Container(
        padding: EdgeInsets.only(top: topPadding),
        decoration: BoxDecoration(
          color: bg.withValues(alpha: backgroundOpacity.clamp(0.0, 1.0)),
          border: backgroundOpacity > 0.02
              ? Border(bottom: BorderSide(color: border.withValues(alpha: 0.6)))
              : null,
        ),
        child: SizedBox(
          height: kToolbarHeight,
          child: Row(
            children: [
              if (widget.mode == ProfileMode.other)
                IconButton(
                  icon: const Icon(CupertinoIcons.back),
                  color: backgroundOpacity > 0.12 ? fg : Colors.white,
                  onPressed: widget.onBack ?? () => context.pop(),
                )
              else
                SizedBox(width: AppSpacing.minInteractiveSize),
              Expanded(
                child: Opacity(
                  opacity: opacity,
                  child: Row(
                    key: const ValueKey<String>(
                      'profile-shell-compact-identity',
                    ),
                    mainAxisAlignment: MainAxisAlignment.center,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      CircleAvatar(
                        radius: AppSpacing.intraGroupLg,
                        backgroundImage:
                            avatarUrl != null && avatarUrl.isNotEmpty
                            ? NetworkImage(avatarUrl)
                            : null,
                        child: avatarUrl == null || avatarUrl.isEmpty
                            ? Icon(Icons.person, size: AppSpacing.iconSmall)
                            : null,
                      ),
                      SizedBox(width: AppSpacing.sm),
                      Flexible(
                        child: Text(
                          displayName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.lg,
                            fontWeight: AppTypography.semiBold,
                            color: fg,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              if (widget.mode == ProfileMode.mine)
                IconButton(
                  icon: const Icon(Icons.settings_outlined),
                  color: backgroundOpacity > 0.12 ? fg : Colors.white,
                  onPressed: () => context.push(AppRoutePaths.settings),
                )
              else
                IconButton(
                  icon: const Icon(Icons.more_horiz),
                  color: backgroundOpacity > 0.12 ? fg : Colors.white,
                  onPressed: () => _showMoreOptions(context, isDark),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPrimaryTabBarSurface({
    required bool isDark,
    required Color bg,
    required Color border,
    required bool pinned,
  }) {
    final tabs = UserProfileUIConfig.profileTabs
        .map(
          (tab) => TabItem(
            id: tab.id,
            label: UITextConstants.contentLabelForKey(tab.labelKey),
          ),
        )
        .toList(growable: false);
    return Container(
      key: pinned
          ? const ValueKey<String>('profile-shell-primary-tabs-pinned')
          : const ValueKey<String>('profile-shell-primary-tabs-inline'),
      decoration: BoxDecoration(
        color: bg,
        border: Border(
          top: BorderSide(color: border.withValues(alpha: pinned ? 0.7 : 0.45)),
          bottom: BorderSide(color: border.withValues(alpha: 0.7)),
        ),
        boxShadow: pinned
            ? [
                BoxShadow(
                  color: Colors.black.withValues(alpha: isDark ? 0.16 : 0.06),
                  blurRadius: AppSpacing.md,
                  offset: Offset(0, AppSpacing.intraGroupXs / 2),
                ),
              ]
            : null,
      ),
      child: SizedBox(
        key: pinned ? null : _primaryTabKey,
        height: AppSpacing.tabNavigationHeight,
        child: CenteredScrollableTabBar(
          tabs: tabs,
          activeTab: _activeTabId,
          onTabChange: _onPrimaryTabChange,
          onHorizontalDragEnd: _handleTabSwipeDragEnd,
          isDark: isDark,
          transparentBackground: true,
        ),
      ),
    );
  }

  Widget _buildInlineTabContent(BuildContext context, bool isDark) {
    final content = switch (_activeTabId) {
      'circles' => ProfileCirclesTab(
        mode: widget.mode,
        userId: widget.userId,
        isDark: isDark,
        inlineScroll: true,
      ),
      'interaction' => ProfileInteractionTab(
        mode: widget.mode,
        userId: widget.userId,
        isDark: isDark,
        inlineScroll: true,
        secondaryTabBarKey: _interactionSecondaryTabKey,
        onSecondaryHorizontalDragEnd: _handleTabSwipeDragEnd,
      ),
      _ => ProfileWorksTab(
        mode: widget.mode,
        userId: widget.userId,
        isDark: isDark,
        inlineScroll: true,
        secondaryTabBarKey: _worksSecondaryTabKey,
        onSecondaryHorizontalDragEnd: _handleTabSwipeDragEnd,
      ),
    };
    return KeyedSubtree(
      key: ValueKey<String>('profile-tab-body-$_activeTabId'),
      child: content,
    );
  }

  Curve _curveForName(String raw) {
    switch (raw) {
      case 'easeOutBack':
        return Curves.easeOutBack;
      case 'easeOutCubic':
        return Curves.easeOutCubic;
      case 'easeOutQuart':
        return Curves.easeOutQuart;
      default:
        return Curves.easeOut;
    }
  }

  double _curveTransform(double value, String raw) {
    return _curveForName(raw).transform(value.clamp(0.0, 1.0));
  }

  void _showMoreOptions(BuildContext context, bool isDark) {
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );

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
                borderRadius: BorderRadius.circular(
                  AppSpacing.smallBorderRadius,
                ),
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
