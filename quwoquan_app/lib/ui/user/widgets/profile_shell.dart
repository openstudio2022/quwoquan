import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide InteractionDirection;
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/rtc/call_session/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/components/object_page/object_page_shell.dart';
import 'package:quwoquan_app/components/rtc/rtc_call_entry_presenter.dart';
import 'package:quwoquan_app/components/media/app_media_image.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/links/app_public_content_links.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/cloud/runtime/generated/link_templates.g.dart';
import 'package:share_plus/share_plus.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/content_report_reason_sheet.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/providers/share_interaction_provider.dart';
import 'package:quwoquan_app/ui/user/models/share_interaction_models.dart';
import 'package:quwoquan_app/core/trackers/share_interaction_observability.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_action_bar.dart';
import 'package:quwoquan_app/ui/user/providers/author_impact_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/author_impact_card.dart';
import 'package:quwoquan_app/ui/user/widgets/my_intersection_inbox_card.dart';
import 'package:quwoquan_app/ui/user/widgets/other_profile_intersection_card.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_completeness_card.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_header.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_stats_row.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';
import 'package:quwoquan_app/components/object_page/profile_ios_components.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_slogan_card.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_works_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_footprint_tab.dart';
part 'profile_shell_builders.dart';
part 'profile_shell_builders_parts.dart';
part 'profile_shell_builders_more.dart';

/// 用户主页壳层（统一对象页骨架 ObjectPageShell + full 吸顶模式）。
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
    this.openMessageComposerOnOpen = false,
    this.greetingIntersectionRef,
  });

  final ProfileMode mode;
  final String userId;
  final String? initialAvatarUrl;
  final String? initialDisplayName;
  final String? initialBackgroundUrl;
  final VoidCallback? onBack;

  /// 进入主页后一次性执行「私信 / 打招呼」分流（交集卡 `dispatch: message` 的承接）。
  final bool openMessageComposerOnOpen;
  final GreetingIntersectionRef? greetingIntersectionRef;

  @override
  ConsumerState<ProfileShell> createState() => _ProfileShellState();
}

class _ProfileShellState extends ConsumerState<ProfileShell> {
  static const double _profileCardRadius = AppSpacing.radiusTwentyFour;
  static const double _profileSurfaceBridge = _profileCardRadius;
  final GlobalKey _worksSecondaryTabKey = GlobalKey();
  final GlobalKey _interactionSecondaryTabKey = GlobalKey();
  late final ScrollController _profileScrollController;

  late String _activeTabId;
  late bool _pendingMessageComposerIntent;

  @override
  void initState() {
    super.initState();
    _profileScrollController = ScrollController()
      ..addListener(_saveActiveShareScrollOffset);
    _activeTabId = UserProfileUIConfig.defaultTabId;
    _pendingMessageComposerIntent = widget.openMessageComposerOnOpen;
  }

  /// 交集卡「打招呼 / 私信」落地：等关系能力位就绪后跑一次主页原有分流。
  ///
  /// 能力位未到达前不执行，避免把陌生人误判成可直开会话；游客态由
  /// [_gatedOpenMessage] 自行登记 continuation 并拉起登录。
  void _maybeRunPendingMessageComposerIntent(
    BuildContext context,
    ProfileState state,
    ProfileNotifier notifier,
  ) {
    if (!_pendingMessageComposerIntent) {
      return;
    }
    final authenticated = ref
        .read(authSessionControllerProvider)
        .isAuthenticated;
    if (authenticated && state.capability == null) {
      return;
    }
    _pendingMessageComposerIntent = false;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      unawaited(_gatedOpenMessage(context, notifier));
    });
  }

  @override
  void dispose() {
    _profileScrollController
      ..removeListener(_saveActiveShareScrollOffset)
      ..dispose();
    super.dispose();
  }

  void _leaveProfile(BuildContext context) {
    final onBack = widget.onBack;
    if (onBack != null) {
      onBack();
      return;
    }
    if (context.canPop()) {
      context.pop();
      return;
    }
    context.go(AppRoutePaths.home);
  }

  void _saveActiveShareScrollOffset() {
    if (!_profileScrollController.hasClients || _activeTabId != 'interaction') {
      return;
    }
    final profileState = ref.read(profileNotifierProvider(widget.userId));
    if (profileState.interactionSubTab != InteractionSubTab.shares) return;
    final direction =
        profileState.interactionDirection == InteractionDirection.received
        ? ShareInteractionDirection.received
        : ShareInteractionDirection.initiated;
    ref
        .read(
          shareInteractionProvider(
            ShareInteractionBucketKey(
              personaId: widget.userId,
              direction: direction,
            ),
          ).notifier,
        )
        .saveScrollOffset(_profileScrollController.offset);
  }

  void _selectInteractionDirection(InteractionDirection direction) {
    final profileState = ref.read(profileNotifierProvider(widget.userId));
    if (profileState.interactionDirection == direction) return;
    _saveActiveShareScrollOffset();
    ref
        .read(profileNotifierProvider(widget.userId).notifier)
        .setInteractionDirection(direction);
    if (profileState.interactionSubTab != InteractionSubTab.shares) return;
    final shareDirection = direction == InteractionDirection.received
        ? ShareInteractionDirection.received
        : ShareInteractionDirection.initiated;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_profileScrollController.hasClients) return;
      final targetOffset = ref
          .read(
            shareInteractionProvider(
              ShareInteractionBucketKey(
                personaId: widget.userId,
                direction: shareDirection,
              ),
            ),
          )
          .scrollOffset
          .clamp(
            _profileScrollController.position.minScrollExtent,
            _profileScrollController.position.maxScrollExtent,
          )
          .toDouble();
      _profileScrollController.jumpTo(targetOffset);
    });
  }

  Future<void> _refreshActiveShare() async {
    if (_activeTabId != 'interaction') return;
    final profileState = ref.read(profileNotifierProvider(widget.userId));
    if (profileState.interactionSubTab != InteractionSubTab.shares) return;
    final direction =
        profileState.interactionDirection == InteractionDirection.received
        ? ShareInteractionDirection.received
        : ShareInteractionDirection.initiated;
    ref
        .read(shareInteractionObservabilityProvider)
        .track(
          eventName: ShareInteractionEventNames.refresh,
          personaId: widget.userId,
          direction: direction,
        );
    await ref
        .read(
          shareInteractionProvider(
            ShareInteractionBucketKey(
              personaId: widget.userId,
              direction: direction,
            ),
          ).notifier,
        )
        .refresh();
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
        .where((tab) => tab.visibleInMode(widget.mode.name))
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
    if (_activeTabId == 'interaction') {
      if (!_isSecondaryTabVisible(_interactionSecondaryTabKey)) {
        return false;
      }
      final filters = UserProfileUIConfig.interactionSubTabs
          .where((filter) => filter.visibleInMode(widget.mode.name))
          .toList(growable: false);
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
    if (_activeTabId != 'creations') {
      return false;
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
        fontWeight: AppTypography.regular,
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
    final adaptiveHeight = labelHeight + (AppSpacing.intraGroupSm * 2);
    final minHeight = AppSpacing.buttonHeightSm;
    return adaptiveHeight > minHeight ? adaptiveHeight : minHeight;
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
        maybeResumeDirectCallContinuation(context, notifier);
        if (state.identityFailure != null || state.worksFailure != null) {
          unawaited(notifier.loadProfile());
        }
      }
    });
    _maybeRunPendingMessageComposerIntent(context, state, notifier);
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
    final impactRequest = (
      personaId: widget.userId,
      surface: isMine ? AppUiSurfaces.profileHome : AppUiSurfaces.userProfile,
    );
    final impact = ref.watch(authorImpactProvider(impactRequest));
    final identitySemantic = state.identityFailure == null
        ? null
        : runtimeErrorSemantic(
            context,
            error: state.identityFailure!,
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
          );
    final worksSemantic = state.worksFailure == null
        ? null
        : runtimeErrorSemantic(
            context,
            error: state.worksFailure!,
            category: UiErrorCategory.sectionLoad,
            scope: UiErrorScope.section,
          );
    final impactSemantic = impact.hasError
        ? runtimeErrorSemantic(
            context,
            error: impact.error!,
            category: UiErrorCategory.sectionLoad,
            scope: UiErrorScope.section,
          )
        : null;
    final loadDecision = AppPageLoadArbiter.decide(<AppPageLoadSlice>[
      AppPageLoadSlice(
        id: 'identity',
        isCritical: true,
        hasUsableContent: profile != null,
        phase: state.isIdentityLoading
            ? AppPageLoadPhase.loading
            : state.identityFailure != null
            ? AppPageLoadPhase.failure
            : profile == null
            ? AppPageLoadPhase.empty
            : AppPageLoadPhase.content,
        semantic: identitySemantic,
      ),
      AppPageLoadSlice(
        id: 'works',
        hasUsableContent: state.creations.isNotEmpty,
        phase: state.isWorksLoading
            ? AppPageLoadPhase.loading
            : state.worksFailure != null
            ? AppPageLoadPhase.failure
            : state.creations.isEmpty
            ? AppPageLoadPhase.empty
            : AppPageLoadPhase.content,
        semantic: worksSemantic,
      ),
      AppPageLoadSlice(
        id: 'impact',
        hasUsableContent: impact.hasValue,
        phase: impact.isLoading
            ? AppPageLoadPhase.loading
            : impact.hasError
            ? AppPageLoadPhase.failure
            : AppPageLoadPhase.content,
        semantic: impactSemantic,
      ),
    ]);
    // 头像源在 Shell 层只选择一次，避免主头像与吸顶头像走不同兜底路径。
    final avatarUrl = _firstNonEmptyString([
      widget.initialAvatarUrl,
      if (isMine) userData?.avatarUrl,
      profile?.avatarUrl,
    ]);
    final profileName = profile?.displayName.trim() ?? '';
    final displayName =
        widget.initialDisplayName ??
        (isMine ? userData?.displayName : null) ??
        (profileName.isNotEmpty ? profileName : '');
    final bio = (profile?.bio.isNotEmpty ?? false)
        ? profile?.bio
        : (isMine ? userData?.bio : null);
    final backgroundUrl = _firstNonEmptyString([
      widget.initialBackgroundUrl,
      if (isMine) userData?.backgroundImage,
      profile?.backgroundUrl,
      ...state.creations.map((post) => post.authorBackgroundUrl),
    ]);
    final hasCoverImage = backgroundUrl != null && backgroundUrl.isNotEmpty;
    // 无真实封面（默认渐变封面）时，浅色模式需要深色 toolbar 前景才可见；
    // 有真实封面图则保持白色前景叠加在顶部暗纱上。
    final contentForegroundIsDark = !hasCoverImage && !isDark;
    final bottomPadding = isMine ? AppSpacing.bottomNavHeight : 0.0;

    return AppScaffold(
      backgroundColor: bg,
      body: ObjectPageShell(
        scrollController: _profileScrollController,
        onRefresh: _refreshActiveShare,
        keyPrefix: 'profile-shell',
        pinMode: ObjectPagePinMode.full,
        cardRadius: _profileCardRadius,
        toolbarContentHeight: _compactToolbarHeight(context),
        identityTransitionDistance: AppSpacing.xs,
        collapseCurve: _curveForName(
          UserProfileUIConfig.scrollMotion.collapseCurve,
        ),
        enablePinnedTabOverlay:
            UserProfileUIConfig.scrollMotion.primaryTabStickyBelowToolbar,
        identityPinExtent:
            ProfileHeader.avatarOuterDiameter - ProfileHeader.avatarOverlapPx,
        summaryTrackerKey: const ValueKey<String>('profile-shell-summary-card'),
        onSwipe: _handleTabSwipeDragEnd,
        surfaceBridgeOverride: AppSpacing.zero,
        scrollBackgroundWithContent: true,
        tabSurfaceTopRadius: _profileCardRadius,
        backgroundBuilder: (c, pull) => _buildBackgroundLayer(
          c,
          backgroundUrl: backgroundUrl,
          backgroundColor: backgroundBridge,
          showCoverPrompt: isMine && !hasCoverImage,
          onCoverPrompt: () => context.push(AppRoutePaths.profileEdit),
        ),
        summaryBuilder: (c) =>
            profile == null &&
                (state.isIdentityLoading || state.identityFailure != null)
            ? const SizedBox.shrink()
            : _buildSummarySection(
                c,
                isDark: isDark,
                avatarUrl: avatarUrl,
                displayName: displayName,
                bio: bio,
                state: state,
                notifier: notifier,
                suppressImpactFailure: loadDecision.suppresses('impact'),
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
          contentForegroundIsDark: contentForegroundIsDark,
        ),
        tabBarBuilder: (c, pinned, opacity) => _buildPrimaryTabBarSurface(
          bg: profileSurface,
          pinned: pinned,
          opacity: opacity,
        ),
        tabBodyBuilder: (c) => Padding(
          padding: EdgeInsets.only(bottom: bottomPadding),
          // 首屏聚合失败且无可展示档案时，渲染结构化可见错误态（重试），不让
          // 乐观壳层静默吞掉失败（R17/R20）。已有档案则保留乐观渲染。
          child: state.isIdentityLoading && profile == null
              ? AppRequestFeedback.page(showSlowHint: state.isIdentitySlow)
              : state.identityFailure != null && profile == null
              ? _buildFirstScreenError(c, state)
              : _buildInlineTabContent(
                  c,
                  isDark,
                  loadDecision: loadDecision,
                  impactRequest: impactRequest,
                ),
        ),
      ),
    );
  }
}

enum _ProfileMoreAction { share, block, report }
