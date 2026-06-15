import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_section.dart';
import 'package:quwoquan_app/components/object_page/object_page_shell.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_action_bar.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_circles_tab.dart';
import 'package:quwoquan_app/ui/user/providers/author_impact_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/author_impact_card.dart';
import 'package:quwoquan_app/ui/user/widgets/my_intersection_inbox_card.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_header.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_works_tab.dart';

part 'profile_shell_builders.dart';

/// 用户主页壳层（V3 统一对象页骨架 ObjectPageShell + full 吸顶模式）。
/// 几何/滚动/吸顶由 ObjectPageShell 收口；本壳提供用户主页业务插槽与二级页签。
/// 先前「共鸣/我的交集」假数据卡片与独立页链路已彻底移除（V5/S3）；
/// 统一交集卡 ObjectIntersectionCard 在 profile detail intersectionReasons 真实下发后接入（V5/S5）。
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
  static const double _profileCardRadius = AppSpacing.radiusTwentyFour;
  static const double _profileSurfaceBridge = _profileCardRadius;
  final GlobalKey _worksSecondaryTabKey = GlobalKey();
  final GlobalKey _interactionSecondaryTabKey = GlobalKey();

  late String _activeTabId;

  @override
  void initState() {
    super.initState();
    _activeTabId = UserProfileUIConfig.defaultTabId;
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
    final state = ref.read(profileNotifierProvider(widget.userId));
    if (_trySwitchVisibleSecondaryTab(direction, notifier, state)) {
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
    ProfileState state,
  ) {
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

  /// 二级页签是否在可视区（保守口径：viewport 顶部恒减去一级吸顶页签高度）。
  /// 几何已统一到 ObjectPageShell，本判断仅依赖二级页签 renderObject 实际位置。
  bool _isSecondaryTabVisible(GlobalKey key) {
    final renderObject = key.currentContext?.findRenderObject();
    if (renderObject is! RenderBox ||
        !renderObject.attached ||
        !renderObject.hasSize) {
      return false;
    }
    final top = renderObject.localToGlobal(Offset.zero).dy;
    final bottom = top + renderObject.size.height;
    final viewportTop = _toolbarExtent(context) + _primaryTabBarHeight(context);
    final viewportBottom =
        MediaQuery.sizeOf(context).height -
        MediaQuery.viewPaddingOf(context).bottom;
    return bottom > viewportTop + 1 && top < viewportBottom - 1;
  }

  CreationSubTab _creationSubTabForId(String id) => creationSubTabFromId(id);

  InteractionSubTab _interactionSubTabForId(String id) =>
      interactionSubTabFromId(id);

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
    final minHeight = AppSpacing.appChromeTopBarHeight(context);
    return adaptiveHeight > minHeight ? adaptiveHeight : minHeight;
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
    return AppSpacing.appChromeTopSafeInset(
          MediaQuery.viewPaddingOf(context).top,
          context,
        ) +
        _compactToolbarHeight(context);
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

  String? _firstNonEmptyString(Iterable<String?> values) {
    for (final value in values) {
      final trimmed = value?.trim();
      if (trimmed != null && trimmed.isNotEmpty) {
        return trimmed;
      }
    }
    return null;
  }

  BorderSide _profileSeparatorSide(Color border, {double alpha = 0.16}) {
    return BorderSide(
      color: border.withValues(alpha: alpha),
      width: AppSpacing.hairline,
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final state = ref.watch(profileNotifierProvider(widget.userId));
    final notifier = ref.read(profileNotifierProvider(widget.userId).notifier);
    ref.listen<AuthSessionState>(authSessionControllerProvider, (
      AuthSessionState? previous,
      AuthSessionState next,
    ) {
      final justLoggedIn =
          next.isAuthenticated &&
          (previous == null || !previous.isAuthenticated);
      if (justLoggedIn) {
        maybeResumeFollowContinuation(notifier);
        maybeResumeDirectMessageContinuation(context, notifier);
      }
    });
    final userData = ref.watch(userDataProvider);
    final bg = SettingsSemanticConstants.conversationSheetPanelBackground(
      isDark,
    );
    final backgroundBridge =
        SettingsSemanticConstants.conversationSheetPanelBackground(isDark);
    final profileSurface =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final fg = AppColors.iosLabel(context);
    final border = SettingsSemanticConstants.conversationSheetDividerColor(
      isDark,
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
    final backgroundUrl = _firstNonEmptyString([
      widget.initialBackgroundUrl,
      if (isMine) userData?.backgroundImage,
      profile?.backgroundUrl,
      ...state.creations.map((post) => post.authorBackgroundUrl),
    ]);
    final bottomPadding = isMine ? AppSpacing.bottomNavHeight : 0.0;

    return AppScaffold(
      backgroundColor: bg,
      body: ObjectPageShell(
        keyPrefix: 'profile-shell',
        pinMode: ObjectPagePinMode.full,
        cardRadius: _profileCardRadius,
        toolbarContentHeight: _compactToolbarHeight(context),
        collapseCurve: _curveForName(
          UserProfileUIConfig.scrollMotion.collapseCurve,
        ),
        enablePinnedTabOverlay:
            UserProfileUIConfig.scrollMotion.primaryTabStickyBelowToolbar,
        identityPinExtent:
            ProfileHeader.avatarOuterDiameter - ProfileHeader.avatarOverlapPx,
        summaryTrackerKey: const ValueKey<String>('profile-shell-summary-card'),
        onSwipe: _handleTabSwipeDragEnd,
        backgroundBuilder: (c, pull) => _buildBackgroundLayer(
          c,
          backgroundUrl: backgroundUrl,
          backgroundColor: backgroundBridge,
        ),
        summaryBuilder: (c) => _buildSummarySection(
          c,
          isDark: isDark,
          avatarUrl: avatarUrl,
          displayName: displayName,
          bio: bio,
          state: state,
          notifier: notifier,
        ),
        toolbarBuilder: (c, identity, bgOpacity) => _buildToolbarOverlay(
          c,
          isDark: isDark,
          fg: fg,
          border: border,
          displayName: displayName,
          avatarUrl: avatarUrl,
          opacity: identity,
          backgroundOpacity: bgOpacity,
        ),
        tabBarBuilder: (c, pinned, opacity) => _buildPrimaryTabBarSurface(
          bg: profileSurface,
          border: border,
          pinned: pinned,
          opacity: opacity,
        ),
        tabBodyBuilder: (c) => Padding(
          padding: EdgeInsets.only(bottom: bottomPadding),
          child: _buildInlineTabContent(c, isDark),
        ),
      ),
    );
  }
}

enum _ProfileMoreAction { share, block, report }

/// 用户举报原因（与 content/report 后端 reason code 对齐）。
enum _ProfileReportReason {
  spam('spam', UITextConstants.profileReportReasonSpam),
  misinformation(
    'misinformation',
    UITextConstants.profileReportReasonMisinformation,
  ),
  harassment('harassment', UITextConstants.profileReportReasonHarassment),
  pornography('pornography', UITextConstants.profileReportReasonPornography),
  other('other', UITextConstants.profileReportReasonOther);

  const _ProfileReportReason(this.code, this.label);

  final String code;
  final String label;
}
