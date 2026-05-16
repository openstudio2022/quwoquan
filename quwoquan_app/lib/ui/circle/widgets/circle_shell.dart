import 'dart:math';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/page_access_internal_routes.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_edit_settings_page.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_action_bar.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_header.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_stats_row.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_chat.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_creations.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_interaction.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_storage.dart';

class CircleShell extends ConsumerStatefulWidget {
  const CircleShell({super.key, required this.circleId, this.onBack});

  final String circleId;
  final VoidCallback? onBack;

  @override
  ConsumerState<CircleShell> createState() => _CircleShellState();
}

class _CircleShellState extends ConsumerState<CircleShell> {
  static const List<String> _defaultSections = <String>[
    'content',
    'discussion',
    'assets',
  ];
  static const double _cardRadius = AppSpacing.radiusTwenty;
  static const double _surfaceBridge = _cardRadius;

  late final ScrollController _scrollController;
  final GlobalKey _summaryKey = GlobalKey();
  final GlobalKey _primaryTabKey = GlobalKey();

  late String _activeTabId;
  List<_TabSpec> _resolvedTabs = const <_TabSpec>[];
  double _scrollOffset = 0;
  double _rawPullOffset = 0;
  double _pullOffset = 0;
  double _summaryHeight = 0;

  @override
  void initState() {
    super.initState();
    _resolvedTabs = _resolveTabs(null);
    _activeTabId = _resolvedTabs.first.type;
    _scrollController = ScrollController()..addListener(_handleScrollOffset);
  }

  @override
  void dispose() {
    _scrollController
      ..removeListener(_handleScrollOffset)
      ..dispose();
    super.dispose();
  }

  void _handleScrollOffset() {
    if (!_scrollController.hasClients) return;
    final next = max(0.0, _scrollController.offset);
    if ((next - _scrollOffset).abs() < 0.5) return;
    setState(() => _scrollOffset = next);
  }

  List<_TabSpec> _resolveTabs(CircleState? state) {
    final sectionConfig = state?.circleData?.sectionConfig ?? const [];
    final visible =
        sectionConfig
            .where((section) => section.visible)
            .toList(growable: false)
          ..sort((a, b) => a.order.compareTo(b.order));
    final available = visible.isNotEmpty
        ? visible.map((section) => section.sectionType).toSet()
        : <String>{'works', 'interaction', 'chat', 'storage'};
    final tabs = <_TabSpec>[];
    if (available.contains('works')) {
      tabs.add(
        _TabSpec(type: 'content', label: UITextConstants.circleWorksTab),
      );
    }
    if (available.contains('interaction')) {
      tabs.add(
        _TabSpec(
          type: 'discussion',
          label: UITextConstants.circleInteractionTab,
        ),
      );
    }
    if (available.contains('chat') || available.contains('storage')) {
      tabs.add(
        _TabSpec(type: 'assets', label: UITextConstants.circleAssetsTab),
      );
    }
    if (tabs.isNotEmpty) return tabs;
    return _defaultSections
        .map(
          (type) => _TabSpec(
            type: type,
            label: switch (type) {
              'content' => UITextConstants.circleWorksTab,
              'discussion' => UITextConstants.circleInteractionTab,
              'assets' => UITextConstants.circleAssetsTab,
              _ => type,
            },
          ),
        )
        .toList(growable: false);
  }

  void _syncTabs(List<_TabSpec> tabs) {
    _resolvedTabs = tabs;
    if (_resolvedTabs.every((tab) => tab.type != _activeTabId)) {
      _activeTabId = _resolvedTabs.first.type;
    }
  }

  void _changeTab(String tabId) {
    if (tabId == _activeTabId) return;
    setState(() => _activeTabId = tabId);
  }

  void _handleTabSwipe(TabSwipeDirection direction) {
    final ids = _resolvedTabs.map((tab) => tab.type).toList(growable: false);
    final current = ids.indexOf(_activeTabId);
    if (current < 0) return;
    final next = current + direction.delta;
    if (next < 0 || next >= ids.length) return;
    _changeTab(ids[next]);
  }

  void _handleTabSwipeDragEnd(DragEndDetails details) {
    final direction = TabSwipeSwitchRegion.directionFromDragEnd(details);
    if (direction == null) return;
    _handleTabSwipe(direction);
  }

  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification.metrics.axis != Axis.vertical) return false;
    if (notification is ScrollUpdateNotification ||
        notification is OverscrollNotification ||
        notification is ScrollEndNotification) {
      final pixels = notification.metrics.pixels;
      if (pixels < 0) {
        final nextRaw = -pixels;
        final maxPull =
            _maxBackgroundHeight(context) - _baseBackgroundHeight(context);
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
          _rawPullOffset = 0;
          _pullOffset = 0;
        });
      }
    }
    return false;
  }

  double _springDampedOffset(double raw, double maxPull) {
    if (raw <= 0 || maxPull <= 0) return 0;
    final damping = maxPull / 1.2;
    return (maxPull * (1 - exp(-raw / damping))).clamp(0.0, maxPull);
  }

  double _baseBackgroundHeight(BuildContext context) {
    return MediaQuery.sizeOf(context).height *
        AppSpacing.profileHeaderBaseHeightRatio;
  }

  double _maxBackgroundHeight(BuildContext context) {
    return MediaQuery.sizeOf(context).height *
        AppSpacing.profileHeaderMaxStretchHeightRatio;
  }

  double _currentBackgroundHeight(BuildContext context) {
    final base = _baseBackgroundHeight(context);
    final maxStretch = _maxBackgroundHeight(context);
    return (base + _pullOffset).clamp(base, maxStretch);
  }

  double _backgroundSpacerHeight(BuildContext context) {
    return max(0.0, _currentBackgroundHeight(context) - _rawPullOffset);
  }

  double _toolbarHeight(BuildContext context) {
    return MediaQuery.paddingOf(context).top + kToolbarHeight;
  }

  double _pinTransitionDistance() {
    return max(
      AppSpacing.buttonHeight,
      CircleHeader.avatarOuterDiameter * 0.55,
    );
  }

  double _summaryTopAtRest(BuildContext context) {
    return _baseBackgroundHeight(context);
  }

  double _primaryTabTopAtRest(BuildContext context) {
    return _summaryTopAtRest(context) + _summaryHeight;
  }

  double _curve(double value) {
    return Curves.easeOutCubic.transform(value.clamp(0.0, 1.0));
  }

  double _identityPinnedProgress(BuildContext context) {
    final avatarBottom =
        _baseBackgroundHeight(context) +
        CircleHeader.avatarOuterDiameter -
        CircleHeader.avatarIntrusion;
    final threshold = max(0.0, avatarBottom - _toolbarHeight(context));
    return _curve((_scrollOffset - threshold) / _pinTransitionDistance());
  }

  double _primaryTabPinnedProgress(BuildContext context) {
    final threshold = max(
      0.0,
      _primaryTabTopAtRest(context) - _toolbarHeight(context),
    );
    return _curve((_scrollOffset - threshold) / _pinTransitionDistance());
  }

  String _formatCount(dynamic value) {
    if (value == null) return '0';
    if (value is String) {
      final parsed = int.tryParse(value.trim());
      return parsed == null
          ? (value.trim().isEmpty ? '0' : value.trim())
          : formatCompactActionCount(parsed);
    }
    final parsed = value is int ? value : int.tryParse(value.toString()) ?? 0;
    return formatCompactActionCount(parsed);
  }

  String _joinPolicyLabel(String? joinPolicy) {
    return joinPolicy == 'approval'
        ? UITextConstants.circleJoinApproval
        : UITextConstants.joinCircle;
  }

  String _metaLine(CircleState state) {
    final circle = state.circleData;
    final cs = state.circleStats;
    final members = _formatCount(
      cs.members != 0 ? cs.members : circle?.memberCount,
    );
    final posts = _formatCount(cs.posts != 0 ? cs.posts : circle?.postCount);
    return <String>[
      '$members ${UITextConstants.circleMembers}',
      '$posts ${UITextConstants.circlePosts}',
      _joinPolicyLabel(circle?.joinPolicy),
    ].join(' · ');
  }

  bool _isMemberLike(CircleState state) {
    return state.role == CircleRole.owner ||
        state.role == CircleRole.admin ||
        state.role == CircleRole.member ||
        state.joinStatus == 'joined';
  }

  bool _canAccessPrimaryContent(CircleState state) {
    final visibility = state.circleData?.visibility ?? 'public';
    return visibility != 'private' || _isMemberLike(state);
  }

  bool _canAccessMemberSpaces(CircleState state) {
    return _isMemberLike(state);
  }

  List<_CircleMetaChipData> _metaChips(CircleState state) {
    final circle = state.circleData;
    final chips = <_CircleMetaChipData>[
      _CircleMetaChipData(
        label: circle?.visibility == 'private'
            ? UITextConstants.visibilityMembers
            : UITextConstants.visibilityPublic,
        icon: circle?.visibility == 'private'
            ? CupertinoIcons.lock_fill
            : CupertinoIcons.globe,
      ),
      _CircleMetaChipData(
        label: _joinPolicyLabel(circle?.joinPolicy),
        icon: circle?.joinPolicy == 'approval'
            ? CupertinoIcons.time_solid
            : CupertinoIcons.person_add,
      ),
    ];
    if (state.joinStatus == 'pending') {
      chips.add(
        const _CircleMetaChipData(
          label: UITextConstants.joinPending,
          icon: CupertinoIcons.time,
          accent: true,
        ),
      );
    } else if (_isMemberLike(state) && state.role == CircleRole.member) {
      chips.add(
        const _CircleMetaChipData(
          label: UITextConstants.joinedCircle,
          icon: CupertinoIcons.check_mark_circled,
          accent: true,
        ),
      );
    } else if (state.isFollowed) {
      chips.add(
        const _CircleMetaChipData(
          label: UITextConstants.followedCircle,
          icon: CupertinoIcons.check_mark,
          accent: true,
        ),
      );
    }
    return chips;
  }

  String? _badgeLabel(CircleState state) {
    final status = (state.circleData?.status ?? '').trim().toLowerCase();
    if (status == 'official' || status == 'verified') {
      return UITextConstants.circleOfficialBadge;
    }
    return null;
  }

  Future<void> _openEditor(
    BuildContext context, {
    required CircleState state,
    required CircleEditSettingsTab initialTab,
  }) async {
    final circle = state.circleData;
    if (circle == null) {
      AppToast.show(context, UITextConstants.loadFailed);
      return;
    }
    await Navigator.of(context).push(
      CupertinoPageRoute<void>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.circleShellEditSettings,
        ),
        builder: (_) => CircleEditSettingsPage(
          circleId: widget.circleId,
          initialCircle: circle,
          initialTab: initialTab,
        ),
      ),
    );
  }

  void _openChat(BuildContext context, String conversationId) {
    context.push(AppRoutePaths.chatDetail(id: conversationId));
  }

  Future<void> _showMoreOptions(
    BuildContext context, {
    required String circleName,
  }) async {
    final action = await showAppActionSheet<_CircleMoreAction>(
      context,
      title: circleName.isEmpty ? AppConceptConstants.circles : circleName,
      sections: [
        const AppActionSheetSection<_CircleMoreAction>(
          items: [
            AppActionSheetItem<_CircleMoreAction>(
              value: _CircleMoreAction.share,
              label: UITextConstants.share,
              icon: CupertinoIcons.share,
            ),
            AppActionSheetItem<_CircleMoreAction>(
              value: _CircleMoreAction.copyLink,
              label: UITextConstants.copyLink,
              icon: CupertinoIcons.link,
            ),
          ],
        ),
        const AppActionSheetSection<_CircleMoreAction>(
          items: [
            AppActionSheetItem<_CircleMoreAction>(
              value: _CircleMoreAction.report,
              label: UITextConstants.report,
              icon: CupertinoIcons.flag,
              isDestructive: true,
            ),
          ],
        ),
      ],
    );
    if (!context.mounted || action == null) return;
    switch (action) {
      case _CircleMoreAction.share:
        AppToast.show(context, UITextConstants.share);
      case _CircleMoreAction.copyLink:
        await Clipboard.setData(ClipboardData(text: widget.circleId));
        if (context.mounted) {
          AppToast.show(context, UITextConstants.copiedToClipboard);
        }
      case _CircleMoreAction.report:
        AppToast.show(context, UITextConstants.report);
    }
  }

  void _scheduleSummaryMeasure() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final height = _summaryKey.currentContext?.size?.height ?? 0;
      if ((height - _summaryHeight).abs() < 0.5) return;
      setState(() => _summaryHeight = height);
    });
  }

  @override
  Widget build(BuildContext context) {
    _scheduleSummaryMeasure();
    final isDark = ref.watch(isDarkProvider);
    final state = ref.watch(circleStateProvider(widget.circleId));
    final circleCtrl = ref.read(circleStateProvider(widget.circleId).notifier);
    final circle = state.circleData;
    final bg = AppColors.iosPageBackground(context);
    final surface = AppColors.iosProfileSurface(context);
    final border = AppColors.iosSeparator(context);
    final fg = AppColors.iosLabel(context);

    final nextTabs = _resolveTabs(state);
    if (nextTabs.length != _resolvedTabs.length ||
        !_tabsEqual(nextTabs, _resolvedTabs)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          setState(() => _syncTabs(nextTabs));
        }
      });
    }

    final circleName = (circle?.name ?? '').trim().isEmpty
        ? AppConceptConstants.circles
        : circle!.name;
    final coverUrl = circle?.coverUrl;
    final identityPinnedProgress = _identityPinnedProgress(context);
    final primaryTabPinnedProgress = _primaryTabPinnedProgress(context);
    final toolbarOpacity = max(
      identityPinnedProgress,
      primaryTabPinnedProgress * 0.82,
    );
    final inlineTabOpacity = (1 - (primaryTabPinnedProgress * 6)).clamp(
      0.0,
      1.0,
    );
    final bottomPadding =
        MediaQuery.viewPaddingOf(context).bottom + AppSpacing.interGroupLg;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle(
        statusBarColor: AppColors.transparent,
        statusBarIconBrightness: toolbarOpacity > 0.12
            ? (isDark ? Brightness.light : Brightness.dark)
            : Brightness.light,
        statusBarBrightness: toolbarOpacity > 0.12
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
                key: const ValueKey<String>('circle-shell-background-layer'),
                height: _currentBackgroundHeight(context),
                child: _buildBackgroundLayer(bg: bg, coverUrl: coverUrl),
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
                        _buildSummaryCard(
                          context,
                          isDark: isDark,
                          state: state,
                          notifier: circleCtrl,
                          circleName: circleName,
                          coverUrl: coverUrl,
                        ),
                      ),
                    ),
                    SliverToBoxAdapter(
                      child: _buildConstrainedContent(
                        Transform.translate(
                          offset: const Offset(0, -_surfaceBridge),
                          child: _buildTabContentSurface(
                            context,
                            bg: surface,
                            border: border,
                            isDark: isDark,
                            state: state,
                            bottomPadding: bottomPadding,
                            inlineTabOpacity: inlineTabOpacity,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            _buildToolbar(
              context,
              fg: fg,
              border: border,
              circleName: circleName,
              avatarUrl: coverUrl,
              identityOpacity: identityPinnedProgress,
              backgroundOpacity: toolbarOpacity,
            ),
            Positioned(
              top:
                  _backgroundSpacerHeight(context) -
                  _scrollOffset +
                  _rawPullOffset,
              left: 0,
              right: 0,
              child: IgnorePointer(
                child: _buildConstrainedContent(
                  const SizedBox(
                    key: ValueKey<String>('circle-shell-summary-card'),
                    height: AppSpacing.one,
                  ),
                ),
              ),
            ),
            Positioned(
              top: _toolbarHeight(context),
              left: 0,
              right: 0,
              child: Offstage(
                offstage: primaryTabPinnedProgress <= 0.01,
                child: IgnorePointer(
                  ignoring: primaryTabPinnedProgress <= 0,
                  child: Opacity(
                    opacity: primaryTabPinnedProgress,
                    child: _buildConstrainedContent(
                      _buildPrimaryTabBar(
                        context,
                        bg: surface,
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

  Widget _buildConstrainedContent(Widget child) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final maxWidth = AppSpacing.adaptiveFeedMaxContentWidth(
          constraints.maxWidth,
        );
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

  Widget _buildSummaryCard(
    BuildContext context, {
    required bool isDark,
    required CircleState state,
    required CircleStateNotifier notifier,
    required String circleName,
    required String? coverUrl,
  }) {
    final circle = state.circleData;
    final hasConversation = (circle?.conversationId ?? '').trim().isNotEmpty;
    final summarySurface = AppColors.iosProfileSurface(context);
    final summaryBorder = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.24 : 0.08);
    final summaryShadow = isDark
        ? AppColors.black.withValues(alpha: 0.18)
        : AppColors.black.withValues(alpha: 0.05);

    return Container(
      key: _summaryKey,
      decoration: BoxDecoration(
        color: summarySurface,
        borderRadius: BorderRadius.circular(_cardRadius),
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
            CircleHeader(
              isDark: isDark,
              avatarUrl: coverUrl,
              name: circleName,
              description: circle?.description,
              tags: circle?.tags ?? const [],
              badgeLabel: _badgeLabel(state),
              metaLine: _metaLine(state),
              onTagTap: (tag) {
                ref.read(contentEngagementTrackerProvider).trackTagClick(
                  tag,
                  fromContentId: widget.circleId,
                );
              },
            ),
            SizedBox(height: AppSpacing.md),
            Wrap(
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: _metaChips(state)
                  .map(
                    (chip) => _CircleMetaChip(
                      label: chip.label,
                      icon: chip.icon,
                      accent: chip.accent,
                    ),
                  )
                  .toList(growable: false),
            ),
            SizedBox(height: AppSpacing.sm),
            CircleStatsRow(
              isDark: isDark,
              stats: state.circleStats.forDetailRow(circle),
            ),
            SizedBox(height: AppSpacing.sm),
            CircleActionBar(
              isDark: isDark,
              role: state.role,
              joinStatus: state.joinStatus,
              isFollowed: state.isFollowed,
              joinPolicy: circle?.joinPolicy ?? 'open',
              hasConversation: hasConversation,
              onEditCircle: () => _openEditor(
                context,
                state: state,
                initialTab: CircleEditSettingsTab.info,
              ),
              onManageCenter: () => _openEditor(
                context,
                state: state,
                initialTab: CircleEditSettingsTab.settings,
              ),
              onFollow: notifier.toggleFollow,
              onJoinCircle:
                  _isMemberLike(state) || state.joinStatus == 'pending'
                  ? null
                  : notifier.joinCircle,
              onOpenChat: hasConversation
                  ? () => _openChat(context, circle!.conversationId!)
                  : null,
            ),
            if (state.error != null && state.error!.trim().isNotEmpty) ...[
              SizedBox(height: AppSpacing.sm),
              Container(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                  vertical: AppSpacing.containerSm,
                ),
                decoration: BoxDecoration(
                  color: AppColors.error.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius,
                  ),
                ),
                child: Row(
                  children: [
                    Icon(
                      CupertinoIcons.exclamationmark_triangle_fill,
                      size: AppSpacing.iconSmall,
                      color: AppColors.error,
                    ),
                    SizedBox(width: AppSpacing.intraGroupSm),
                    Expanded(
                      child: Text(
                        UITextConstants.loadFailed,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: AppColors.iosSecondaryLabel(context),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildBackgroundLayer({required Color bg, required String? coverUrl}) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          bottom: -_surfaceBridge,
          child: coverUrl != null && coverUrl.isNotEmpty
              ? Image.network(
                  coverUrl,
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) =>
                      ColoredBox(color: bg),
                )
              : ColoredBox(color: bg.withValues(alpha: 0.75)),
        ),
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          bottom: -_surfaceBridge,
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  AppColors.black.withValues(alpha: 0.08),
                  AppColors.black.withValues(alpha: 0.04),
                  bg.withValues(alpha: 0.12),
                ],
                stops: const [0.0, 0.56, 1.0],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildToolbar(
    BuildContext context, {
    required Color fg,
    required Color border,
    required String circleName,
    required String? avatarUrl,
    required double identityOpacity,
    required double backgroundOpacity,
  }) {
    final topPadding = MediaQuery.paddingOf(context).top;
    final slotWidth = AppSpacing.minInteractiveSize + AppSpacing.containerXs;
    final chrome = Color.lerp(
      AppColors.transparent,
      AppColors.iosSystemBackground(context),
      backgroundOpacity.clamp(0.0, 1.0),
    )!;
    final compactForeground = backgroundOpacity > 0.12
        ? fg
        : CupertinoColors.white;
    final tintFill = backgroundOpacity > 0.14
        ? AppColors.iosSecondaryFill(context)
        : AppColors.black.withValues(alpha: 0.24);

    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Container(
        padding: EdgeInsets.only(top: topPadding),
        decoration: BoxDecoration(
          color: chrome,
          border: backgroundOpacity > 0.02
              ? Border(
                  bottom: BorderSide(
                    color: border.withValues(alpha: 0.16),
                    width: AppSpacing.hairline,
                  ),
                )
              : null,
        ),
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = AppSpacing.adaptiveFeedMaxContentWidth(
              constraints.maxWidth,
            );
            return Align(
              alignment: Alignment.topCenter,
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: maxWidth),
                child: SizedBox(
                  height: kToolbarHeight,
                  child: Row(
                    children: [
                      SizedBox(
                        width: slotWidth,
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: _CircleToolbarButton(
                            icon: CupertinoIcons.back,
                            onPressed:
                                widget.onBack ??
                                () {
                                  Navigator.of(context).maybePop();
                                },
                            backgroundColor: tintFill,
                            foregroundColor: compactForeground,
                          ),
                        ),
                      ),
                      Expanded(
                        child: Opacity(
                          opacity: identityOpacity,
                          child: Row(
                            key: const ValueKey<String>(
                              'circle-shell-compact-identity',
                            ),
                            mainAxisAlignment: MainAxisAlignment.center,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              CircleAvatar(
                                radius: AppSpacing.avatarUserSm / 2,
                                backgroundColor: tintFill,
                                backgroundImage:
                                    avatarUrl != null && avatarUrl.isNotEmpty
                                    ? NetworkImage(avatarUrl)
                                    : null,
                                child: avatarUrl == null || avatarUrl.isEmpty
                                    ? Icon(
                                        CupertinoIcons.person_3_fill,
                                        size: AppSpacing.iconMedium,
                                        color: compactForeground,
                                      )
                                    : null,
                              ),
                              SizedBox(width: AppSpacing.containerSm),
                              Flexible(
                                child: Text(
                                  circleName,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
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
                      ),
                      SizedBox(
                        width: slotWidth,
                        child: Align(
                          alignment: Alignment.centerRight,
                          child: _CircleToolbarButton(
                            icon: CupertinoIcons.ellipsis,
                            onPressed: () => _showMoreOptions(
                              context,
                              circleName: circleName,
                            ),
                            backgroundColor: tintFill,
                            foregroundColor: compactForeground,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildTabContentSurface(
    BuildContext context, {
    required Color bg,
    required Color border,
    required bool isDark,
    required CircleState state,
    required double bottomPadding,
    required double inlineTabOpacity,
  }) {
    final shadow = isDark
        ? AppColors.black.withValues(alpha: 0.12)
        : AppColors.black.withValues(alpha: 0.03);
    return Container(
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.only(
          bottomLeft: Radius.circular(_cardRadius),
          bottomRight: Radius.circular(_cardRadius),
        ),
        border: Border.all(
          color: border.withValues(alpha: isDark ? 0.22 : 0.08),
          width: AppSpacing.hairline,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: shadow,
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(height: _surfaceBridge),
          _buildPrimaryTabBar(
            context,
            bg: bg,
            border: border,
            pinned: false,
            opacity: inlineTabOpacity,
          ),
          Padding(
            padding: EdgeInsets.only(bottom: bottomPadding),
            child: ConstrainedBox(
              constraints: BoxConstraints(
                minHeight: max(
                  0.0,
                  MediaQuery.sizeOf(context).height -
                      _toolbarHeight(context) -
                      MediaQuery.viewPaddingOf(context).bottom,
                ),
              ),
              child: _buildInlineTabBody(context, isDark: isDark, state: state),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPrimaryTabBar(
    BuildContext context, {
    required Color bg,
    required Color border,
    required bool pinned,
    double opacity = 1.0,
  }) {
    final tabs = _resolvedTabs
        .map((tab) => TabItem(id: tab.type, label: tab.label))
        .toList(growable: false);
    final surface = Container(
      key: pinned
          ? const ValueKey<String>('circle-shell-primary-tabs-pinned')
          : const ValueKey<String>('circle-shell-primary-tabs-inline'),
      decoration: BoxDecoration(
        color: bg,
        border: Border(
          bottom: BorderSide(
            color: border.withValues(alpha: 0.1),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: SizedBox(
        key: pinned ? null : _primaryTabKey,
        height: AppSpacing.tabNavigationHeight,
        child: CenteredScrollableTabBar(
          tabs: tabs,
          activeTab: _activeTabId,
          onTabChange: _changeTab,
          onHorizontalDragEnd: _handleTabSwipeDragEnd,
          transparentBackground: true,
        ),
      ),
    );
    if (pinned) return surface;
    return IgnorePointer(
      ignoring: opacity <= 0.02,
      child: Opacity(opacity: opacity, child: surface),
    );
  }

  Widget _buildInlineTabBody(
    BuildContext context, {
    required bool isDark,
    required CircleState state,
  }) {
    final circle = state.circleData;
    final contentLocked = !_canAccessPrimaryContent(state);
    final memberLocked = !_canAccessMemberSpaces(state);

    final child = switch (_activeTabId) {
      'content' =>
        contentLocked
            ? _buildGateCard(
                context,
                title: UITextConstants.visibilityPrivate,
                description: UITextConstants.circleVisibilityMembersDescription,
                keySuffix: 'content',
              )
            : SectionCreations(
                circleId: widget.circleId,
                isDark: isDark,
                role: state.role,
                inlineScroll: true,
              ),
      'discussion' =>
        contentLocked
            ? _buildGateCard(
                context,
                title: UITextConstants.visibilityPrivate,
                description: UITextConstants.circleVisibilityMembersDescription,
                keySuffix: 'discussion',
              )
            : Padding(
                padding: EdgeInsets.fromLTRB(
                  AppSpacing.containerMd,
                  AppSpacing.containerSm,
                  AppSpacing.containerMd,
                  0,
                ),
                child: _SectionSurface(
                  isDark: isDark,
                  child: SectionInteraction(
                    circleId: widget.circleId,
                    isDark: isDark,
                  ),
                ),
              ),
      'assets' =>
        memberLocked
            ? _buildGateCard(
                context,
                title: UITextConstants.visibilityMembers,
                description: circle?.joinPolicy == 'approval'
                    ? UITextConstants.circleJoinApprovalDescription
                    : UITextConstants.circleJoinOpenDescription,
                keySuffix: 'assets',
              )
            : Padding(
                padding: EdgeInsets.fromLTRB(
                  AppSpacing.containerMd,
                  AppSpacing.containerSm,
                  AppSpacing.containerMd,
                  0,
                ),
                child: Column(
                  children: [
                    _SectionSurface(
                      isDark: isDark,
                      child: SectionChat(
                        circleId: widget.circleId,
                        conversationId: circle?.conversationId,
                        isDark: isDark,
                      ),
                    ),
                    SizedBox(height: AppSpacing.md),
                    _SectionSurface(
                      isDark: isDark,
                      child: SectionStorage(
                        circleId: widget.circleId,
                        isDark: isDark,
                        storageUsedBytes: circle?.storageUsedBytes ?? 0,
                        storageQuotaBytes:
                            circle?.storageQuotaBytes ?? 1073741824,
                      ),
                    ),
                  ],
                ),
              ),
      _ => const SizedBox.shrink(),
    };

    return KeyedSubtree(
      key: ValueKey<String>('circle-tab-body-$_activeTabId'),
      child: child,
    );
  }

  Widget _buildGateCard(
    BuildContext context, {
    required String title,
    required String description,
    required String keySuffix,
  }) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerSm,
        AppSpacing.containerMd,
        0,
      ),
      child: _SectionSurface(
        isDark: CupertinoTheme.of(context).brightness == Brightness.dark,
        child: Container(
          key: ValueKey<String>('circle-shell-gate-$keySuffix'),
          padding: EdgeInsets.all(AppSpacing.containerLg),
          child: Column(
            children: [
              Container(
                width: AppSpacing.buttonHeight + AppSpacing.xs,
                height: AppSpacing.buttonHeight + AppSpacing.xs,
                decoration: BoxDecoration(
                  color: AppColors.primaryColor.withValues(alpha: 0.1),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  CupertinoIcons.lock_shield_fill,
                  color: AppColors.primaryColor,
                  size: AppSpacing.iconMedium,
                ),
              ),
              SizedBox(height: AppSpacing.sm),
              Text(
                title,
                style: TextStyle(
                  fontSize: AppTypography.base,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosLabel(context),
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                description,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: AppColors.iosSecondaryLabel(context),
                  height: AppTypography.bodyLineHeight,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  bool _tabsEqual(List<_TabSpec> a, List<_TabSpec> b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i].type != b[i].type || a[i].label != b[i].label) {
        return false;
      }
    }
    return true;
  }
}

enum _CircleMoreAction { share, copyLink, report }

class _CircleToolbarButton extends StatelessWidget {
  const _CircleToolbarButton({
    required this.icon,
    required this.onPressed,
    required this.backgroundColor,
    required this.foregroundColor,
  });

  final IconData icon;
  final VoidCallback? onPressed;
  final Color backgroundColor;
  final Color foregroundColor;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      onPressed: onPressed,
      child: Container(
        width: AppSpacing.minInteractiveSize,
        height: AppSpacing.minInteractiveSize,
        decoration: BoxDecoration(
          color: backgroundColor,
          shape: BoxShape.circle,
        ),
        child: Icon(icon, size: AppSpacing.iconMedium, color: foregroundColor),
      ),
    );
  }
}

class _CircleMetaChipData {
  const _CircleMetaChipData({
    required this.label,
    required this.icon,
    this.accent = false,
  });

  final String label;
  final IconData icon;
  final bool accent;
}

class _CircleMetaChip extends StatelessWidget {
  const _CircleMetaChip({
    required this.label,
    required this.icon,
    this.accent = false,
  });

  final String label;
  final IconData icon;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    final foreground = accent
        ? AppColors.primaryColor
        : AppColors.iosSecondaryLabel(context);
    final background = accent
        ? AppColors.primaryColor.withValues(alpha: 0.08)
        : AppColors.iosGroupedSurface(context);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: AppSpacing.iconSmall, color: foreground),
          SizedBox(width: AppSpacing.intraGroupXs),
          Text(
            label,
            style: TextStyle(
              fontSize: AppTypography.xs,
              fontWeight: AppTypography.semiBold,
              color: foreground,
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionSurface extends StatelessWidget {
  const _SectionSurface({required this.isDark, required this.child});

  final bool isDark;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final bg = AppColors.iosGroupedSurface(context);
    final border = AppColors.iosSeparator(context);
    return Container(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(color: border.withValues(alpha: 0.12)),
        boxShadow: [
          BoxShadow(
            color: AppColors.black.withValues(alpha: isDark ? 0.14 : 0.05),
            blurRadius: AppSpacing.md,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: child,
    );
  }
}

class _TabSpec {
  const _TabSpec({required this.type, required this.label});

  final String type;
  final String label;
}
