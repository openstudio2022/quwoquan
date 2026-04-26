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
import 'package:quwoquan_app/ui/user/widgets/profile_ios_components.dart';
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
  static const double _profileCardRadius = AppSpacing.radiusTwenty;
  static const double _profileSurfaceBridge = _profileCardRadius;
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
    final notifier = ref.read(profileNotifierProvider(widget.userId).notifier);
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
        ? _primaryTabBarHeight(context)
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
        max(
          UserProfileUIConfig.headerLayout.baseHeightRatio,
          AppSpacing.profileHeaderBaseHeightRatio,
        );
  }

  double _maxStretchBackgroundHeight(BuildContext context) {
    return MediaQuery.sizeOf(context).height *
        max(
          UserProfileUIConfig.headerLayout.maxStretchHeightRatio,
          AppSpacing.profileHeaderMaxStretchHeightRatio,
        );
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

  double _summaryTrackerTop(BuildContext context) {
    return _backgroundSpacerHeight(context) - _scrollOffset + _rawPullOffset;
  }

  Widget _buildConstrainedContent(Widget child) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isWide = constraints.maxWidth > AppSpacing.feedMaxContentWidth;
        final maxWidth = isWide
            ? constraints.maxWidth - AppSpacing.containerLg * 2
            : AppSpacing.feedMaxContentWidth;
        return Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: maxWidth),
            child: child,
          ),
        );
      },
    );
  }

  BorderSide _profileSeparatorSide(Color border, {double alpha = 0.16}) {
    return BorderSide(
      color: border.withValues(alpha: alpha),
      width: AppSpacing.hairline,
    );
  }

  Widget _buildPrimaryTabContentSurface(
    BuildContext context, {
    required Color bg,
    required Color border,
    required bool isDark,
    required double bottomPadding,
    required double inlinePrimaryTabOpacity,
  }) {
    final sectionBorder = border.withValues(alpha: isDark ? 0.22 : 0.08);
    final sectionShadow = isDark
        ? AppColors.black.withValues(alpha: 0.12)
        : AppColors.black.withValues(alpha: 0.03);
    return Container(
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.only(
          bottomLeft: Radius.circular(_profileCardRadius),
          bottomRight: Radius.circular(_profileCardRadius),
        ),
        border: Border.all(color: sectionBorder, width: AppSpacing.hairline),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: sectionShadow,
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(height: _profileSurfaceBridge),
          _buildPrimaryTabBarSurface(
            bg: bg,
            border: border,
            pinned: false,
            opacity: inlinePrimaryTabOpacity,
          ),
          Padding(
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
        ],
      ),
    );
  }

  double _measureSingleLineTextHeight(BuildContext context, TextStyle style) {
    final painter = TextPainter(
      text: TextSpan(text: 'Hg', style: style),
      textDirection: Directionality.of(context),
      textScaler: MediaQuery.textScalerOf(context),
      maxLines: 1,
    )..layout();
    return painter.height;
  }

  double _compactToolbarHeight(BuildContext context) {
    final titleHeight = _measureSingleLineTextHeight(
      context,
      const TextStyle(
        fontSize: AppTypography.iosNavTitle,
        fontWeight: AppTypography.semiBold,
      ),
    );
    final adaptiveHeight = titleHeight + (AppSpacing.intraGroupSm * 2);
    return adaptiveHeight > kToolbarHeight ? adaptiveHeight : kToolbarHeight;
  }

  double _primaryTabBarHeight(BuildContext context) {
    final labelHeight = _measureSingleLineTextHeight(
      context,
      TextStyle(
        fontSize: AppTypography.primaryTabLabelResponsive(context),
        fontWeight: AppTypography.primaryTabSelectedWeight,
      ),
    );
    final adaptiveHeight =
        labelHeight + (AppSpacing.intraGroupSm * 2) + AppSpacing.intraGroupXs;
    return adaptiveHeight > AppSpacing.tabNavigationHeight
        ? adaptiveHeight
        : AppSpacing.tabNavigationHeight;
  }

  double _toolbarExtent(BuildContext context) {
    return MediaQuery.paddingOf(context).top + _compactToolbarHeight(context);
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
    final personaManagementEnabled = ref.watch(
      personaManagementFeatureFlagProvider,
    );
    final state = ref.watch(profileNotifierProvider(widget.userId));
    final notifier = ref.read(profileNotifierProvider(widget.userId).notifier);
    final userData = ref.watch(userDataProvider);
    final bg = AppColors.iosPageBackground(context);
    final backgroundBridge = AppColors.iosPageBackground(context);
    final profileSurface = AppColors.iosProfileSurface(context);
    final fg = AppColors.iosLabel(context);
    final border = AppColors.iosSeparator(context);
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
    final inlinePrimaryTabOpacity = (1 - (primaryPinnedProgress * 6)).clamp(
      0.0,
      1.0,
    );
    final statusIconsDark = toolbarBackgroundOpacity > 0.12;
    final bottomPadding = isMine
        ? AppSpacing.bottomNavHeight + MediaQuery.viewPaddingOf(context).bottom
        : MediaQuery.viewPaddingOf(context).bottom + AppSpacing.interGroupLg;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle(
        statusBarColor: AppColors.transparent,
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
                  backgroundColor: backgroundBridge,
                ),
              ),
            ),
            TabSwipeSwitchRegion(
              onSwipe: _handleTabSwipe,
              child: NotificationListener<ScrollNotification>(
                onNotification: _handleScrollNotification,
                child: CustomScrollView(
                  controller: _scrollController,
                  cacheExtent: MediaQuery.sizeOf(context).height * 4,
                  physics: const BouncingScrollPhysics(
                    parent: AlwaysScrollableScrollPhysics(),
                  ),
                  slivers: [
                    SliverToBoxAdapter(
                      child: SizedBox(height: _backgroundSpacerHeight(context)),
                    ),
                    SliverToBoxAdapter(
                      child: _buildConstrainedContent(
                        _buildSummarySection(
                          context,
                          isDark: isDark,
                          personaManagementEnabled: personaManagementEnabled,
                          avatarUrl: avatarUrl,
                          displayName: displayName,
                          bio: bio,
                          state: state,
                          notifier: notifier,
                        ),
                      ),
                    ),
                    SliverToBoxAdapter(
                      child: _buildConstrainedContent(
                        Transform.translate(
                          offset: const Offset(0, -_profileSurfaceBridge),
                          child: _buildPrimaryTabContentSurface(
                            context,
                            bg: profileSurface,
                            border: border,
                            isDark: isDark,
                            bottomPadding: bottomPadding,
                            inlinePrimaryTabOpacity: inlinePrimaryTabOpacity,
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
              fg: fg,
              border: border,
              displayName: displayName,
              avatarUrl: avatarUrl,
              opacity: identityPinnedProgress,
              backgroundOpacity: toolbarBackgroundOpacity,
            ),
            Positioned(
              top: _summaryTrackerTop(context),
              left: 0,
              right: 0,
              child: IgnorePointer(
                child: _buildConstrainedContent(
                  SizedBox(
                    key: const ValueKey<String>('profile-shell-summary-card'),
                    height: AppSpacing.one,
                  ),
                ),
              ),
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
                      child: _buildConstrainedContent(
                        _buildPrimaryTabBarSurface(
                          bg: profileSurface,
                          border: border,
                          pinned: true,
                        ),
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
    required bool personaManagementEnabled,
    required String? avatarUrl,
    required String displayName,
    required String? bio,
    required ProfileState state,
    required ProfileNotifier notifier,
  }) {
    final summarySurface = AppColors.iosProfileSurface(context);
    final summaryBorder = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.24 : 0.08);
    final displayCapability = state.displayCapability;
    final summaryShadow = isDark
        ? AppColors.black.withValues(alpha: 0.18)
        : AppColors.black.withValues(alpha: 0.05);
    return Container(
      key: _summarySectionKey,
      child: Container(
        decoration: BoxDecoration(
          color: summarySurface,
          borderRadius: BorderRadius.circular(_profileCardRadius),
          border: Border.all(color: summaryBorder, width: AppSpacing.hairline),
          boxShadow: <BoxShadow>[
            BoxShadow(
              color: summaryShadow,
              blurRadius: AppSpacing.twenty,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Padding(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.feedContentHorizontal(context),
            0,
            AppSpacing.feedContentHorizontal(context),
            AppSpacing.containerLg,
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
              if (widget.mode == ProfileMode.other &&
                  displayCapability == null) ...[
                SizedBox(height: AppSpacing.xl + AppSpacing.md),
              ] else ...[
                ProfileActionBar(
                  mode: widget.mode,
                  isDark: isDark,
                  capability: displayCapability,
                  onEditProfile: () => context.push(AppRoutePaths.profileEdit),
                  onManagePersonas: personaManagementEnabled
                      ? () => context.push(AppRoutePaths.profilePersonas)
                      : null,
                  onFollow: notifier.toggleFollow,
                  onMessage: () =>
                      context.push(AppRoutePaths.chatDetail(id: widget.userId)),
                  onGreet: () => _showGreetDialog(context),
                  onVoiceCall: () => _startCall(context, 'voice'),
                  onVideoCall: () => _startCall(context, 'video'),
                ),
              ],
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
      clipBehavior: Clip.none,
      children: [
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          bottom: -_profileSurfaceBridge,
          child: backgroundUrl != null && backgroundUrl.isNotEmpty
              ? Image.network(
                  backgroundUrl,
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) =>
                      ColoredBox(color: backgroundColor),
                )
              : ColoredBox(color: backgroundColor.withValues(alpha: 0.75)),
        ),
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          bottom: -_profileSurfaceBridge,
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  AppColors.black.withValues(alpha: 0.08),
                  AppColors.black.withValues(alpha: 0.04),
                  backgroundColor.withValues(alpha: 0.12),
                ],
                stops: const [0.0, 0.56, 1.0],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildToolbarOverlay(
    BuildContext context, {
    required Color fg,
    required Color border,
    required String displayName,
    required String? avatarUrl,
    required double opacity,
    required double backgroundOpacity,
  }) {
    final topPadding = MediaQuery.paddingOf(context).top;
    final sideSlotWidth =
        AppSpacing.minInteractiveSize + AppSpacing.containerXs;
    final resolvedOpacity = backgroundOpacity.clamp(0.0, 1.0);
    final compactForeground = resolvedOpacity > 0.12
        ? fg
        : CupertinoColors.white;
    final toolbarChrome = Color.lerp(
      AppColors.transparent,
      AppColors.iosSystemBackground(context),
      resolvedOpacity,
    )!;
    final tintFill = resolvedOpacity > 0.14
        ? AppColors.iosSecondaryFill(context)
        : AppColors.black.withValues(alpha: 0.24);
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Container(
        padding: EdgeInsets.only(top: topPadding),
        decoration: BoxDecoration(
          color: toolbarChrome,
          border: resolvedOpacity > 0.02
              ? Border(bottom: _profileSeparatorSide(border))
              : null,
        ),
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              maxWidth: AppSpacing.feedMaxContentWidth,
            ),
            child: SizedBox(
              height: _compactToolbarHeight(context),
              child: Row(
                children: [
                  SizedBox(
                    width: sideSlotWidth,
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: widget.mode == ProfileMode.other
                          ? ProfileIosIconButton(
                              icon: CupertinoIcons.back,
                              onPressed: widget.onBack ?? () => context.pop(),
                              backgroundColor: tintFill,
                              foregroundColor: compactForeground,
                            )
                          : const SizedBox.shrink(),
                    ),
                  ),
                  Expanded(
                    child: Opacity(
                      opacity: opacity,
                      child: LayoutBuilder(
                        builder: (context, constraints) {
                          return Center(
                            child: ConstrainedBox(
                              constraints: BoxConstraints(
                                maxWidth: constraints.maxWidth,
                              ),
                              child: Row(
                                key: const ValueKey<String>(
                                  'profile-shell-compact-identity',
                                ),
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  CircleAvatar(
                                    radius: AppSpacing.avatarUserSm / 2,
                                    backgroundColor: tintFill,
                                    backgroundImage:
                                        avatarUrl != null &&
                                            avatarUrl.isNotEmpty
                                        ? NetworkImage(avatarUrl)
                                        : null,
                                    child:
                                        avatarUrl == null || avatarUrl.isEmpty
                                        ? Icon(
                                            CupertinoIcons
                                                .person_crop_circle_fill,
                                            size: AppSpacing.iconMedium,
                                            color: compactForeground,
                                          )
                                        : null,
                                  ),
                                  SizedBox(width: AppSpacing.containerSm),
                                  Flexible(
                                    child: Text(
                                      displayName,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      textAlign: TextAlign.center,
                                      style: TextStyle(
                                        fontSize: AppTypography.iosNavTitle,
                                        fontWeight: AppTypography.medium,
                                        color: compactForeground,
                                        letterSpacing: -0.24,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ),
                  SizedBox(
                    width: sideSlotWidth,
                    child: Align(
                      alignment: Alignment.centerRight,
                      child: widget.mode == ProfileMode.mine
                          ? ProfileIosIconButton(
                              icon: CupertinoIcons.settings,
                              onPressed: () =>
                                  context.push(AppRoutePaths.settings),
                              backgroundColor: tintFill,
                              foregroundColor: compactForeground,
                            )
                          : ProfileIosIconButton(
                              icon: CupertinoIcons.ellipsis,
                              onPressed: () => _showMoreOptions(context),
                              backgroundColor: tintFill,
                              foregroundColor: compactForeground,
                            ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildPrimaryTabBarSurface({
    required Color bg,
    required Color border,
    required bool pinned,
    double opacity = 1.0,
  }) {
    final tabs = UserProfileUIConfig.profileTabs
        .map(
          (tab) => TabItem(
            id: tab.id,
            label: UITextConstants.contentLabelForKey(tab.labelKey),
          ),
        )
        .toList(growable: false);
    final surface = Container(
      key: pinned
          ? const ValueKey<String>('profile-shell-primary-tabs-pinned')
          : const ValueKey<String>('profile-shell-primary-tabs-inline'),
      clipBehavior: pinned ? Clip.none : Clip.antiAlias,
      decoration: BoxDecoration(
        color: bg,
        border: Border(bottom: _profileSeparatorSide(border, alpha: 0.1)),
      ),
      child: SizedBox(
        key: pinned ? null : _primaryTabKey,
        height: _primaryTabBarHeight(context),
        child: CenteredScrollableTabBar(
          tabs: tabs,
          activeTab: _activeTabId,
          onTabChange: _onPrimaryTabChange,
          onHorizontalDragEnd: _handleTabSwipeDragEnd,
          transparentBackground: true,
        ),
      ),
    );
    if (pinned) {
      return surface;
    }
    return IgnorePointer(
      ignoring: opacity <= 0.02,
      child: Opacity(opacity: opacity, child: surface),
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

  Future<void> _showMoreOptions(BuildContext context) async {
    final action = await showAppActionSheet<_ProfileMoreAction>(
      context,
      title: '更多操作',
      sections: const [
        AppActionSheetSection<_ProfileMoreAction>(
          items: [
            AppActionSheetItem<_ProfileMoreAction>(
              value: _ProfileMoreAction.share,
              label: '分享',
              icon: CupertinoIcons.share,
            ),
          ],
        ),
        AppActionSheetSection<_ProfileMoreAction>(
          items: [
            AppActionSheetItem<_ProfileMoreAction>(
              value: _ProfileMoreAction.block,
              label: '拉黑',
              icon: CupertinoIcons.person_crop_circle_badge_xmark,
            ),
            AppActionSheetItem<_ProfileMoreAction>(
              value: _ProfileMoreAction.report,
              label: '举报',
              icon: CupertinoIcons.flag,
              isDestructive: true,
            ),
          ],
        ),
      ],
    );
    if (!context.mounted || action == null) return;
    switch (action) {
      case _ProfileMoreAction.share:
        AppToast.show(context, '分享能力待接入');
      case _ProfileMoreAction.block:
        AppToast.show(context, '拉黑能力待接入');
      case _ProfileMoreAction.report:
        AppToast.show(context, '举报能力待接入');
    }
  }
}

enum _ProfileMoreAction { share, block, report }
