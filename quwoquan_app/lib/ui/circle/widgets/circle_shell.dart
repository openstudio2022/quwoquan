import 'dart:math';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
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

class _CircleShellState extends ConsumerState<CircleShell>
    with TickerProviderStateMixin {
  static const _defaultSections = ['content', 'discussion', 'assets'];

  late final PageController _pageController;
  late final AnimationController _pullBackController;
  int _activeTabIndex = 0;
  double _pullOffset = 0;
  double _rawPullOffset = 0;
  bool _isPulling = false;
  bool _isHeaderCollapsed = false;
  List<_TabSpec> _resolvedTabs = [];

  @override
  void initState() {
    super.initState();
    _resolvedTabs = _resolveTabs(null);
    _pageController = PageController();
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

  List<_TabSpec> _resolveTabs(CircleState? circleState) {
    final sectionConfig = circleState?.circleData?.sectionConfig ?? [];
    final visible =
        sectionConfig
            .where((section) => section.visible)
            .toList(growable: false)
          ..sort((a, b) => a.order.compareTo(b.order));
    final availableTypes = visible.isNotEmpty
        ? visible.map((section) => section.sectionType).toSet()
        : <String>{'works', 'interaction', 'chat', 'storage'};
    final tabs = <_TabSpec>[];
    if (availableTypes.contains('works')) {
      tabs.add(_TabSpec(type: 'content', label: _sectionLabel('content')));
    }
    if (availableTypes.contains('interaction')) {
      tabs.add(
        _TabSpec(type: 'discussion', label: _sectionLabel('discussion')),
      );
    }
    if (availableTypes.contains('chat') || availableTypes.contains('storage')) {
      tabs.add(_TabSpec(type: 'assets', label: _sectionLabel('assets')));
    }
    return tabs.isEmpty
        ? _defaultSections
              .map((type) => _TabSpec(type: type, label: _sectionLabel(type)))
              .toList(growable: false)
        : tabs;
  }

  String _sectionLabel(String type) {
    return switch (type) {
      'content' => UITextConstants.circleWorksTab,
      'discussion' => UITextConstants.circleInteractionTab,
      'assets' => UITextConstants.circleAssetsTab,
      _ => type,
    };
  }

  void _syncTabs(List<_TabSpec> newTabs) {
    _resolvedTabs = newTabs;
    if (_activeTabIndex >= _resolvedTabs.length) {
      _activeTabIndex = 0;
      if (_pageController.hasClients) {
        _pageController.jumpToPage(0);
      }
    }
  }

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
        final maxPull = screenHeight * 0.22;
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
    final members = _formatCount(
      state.stats['members'] ??
          state.stats['totalMembers'] ??
          circle?.memberCount,
    );
    final posts = _formatCount(
      state.stats['posts'] ?? state.stats['totalPosts'] ?? circle?.postCount,
    );
    return [
      '$members ${UITextConstants.circleMembers}',
      '$posts ${UITextConstants.circlePosts}',
      _joinPolicyLabel(circle?.joinPolicy),
    ].join(' · ');
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
        builder: (_) => CircleEditSettingsPage(
          circleId: widget.circleId,
          initialCircle: circle,
          initialTab: initialTab,
        ),
      ),
    );
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

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final notifier = ref.watch(circleStateProvider(widget.circleId));
    final circleState = notifier.state;
    final circleData = circleState.circleData;
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final bgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );

    final newTabs = _resolveTabs(circleState);
    if (newTabs.length != _resolvedTabs.length ||
        !_tabsEqual(newTabs, _resolvedTabs)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          setState(() => _syncTabs(newTabs));
        }
      });
    }

    final circleName = circleData?.name ?? '';
    final coverUrl = circleData?.coverUrl;

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
                  if (mounted) {
                    setState(() => _isHeaderCollapsed = innerBoxIsScrolled);
                  }
                });
              }

              return [
                CupertinoSliverNavigationBar(
                  largeTitle: Text(
                    circleName.isEmpty
                        ? AppConceptConstants.circles
                        : circleName,
                  ),
                  automaticallyImplyLeading: false,
                  backgroundColor: bg.withValues(alpha: 0.92),
                  border: Border(
                    bottom: BorderSide(
                      color: border.withValues(alpha: 0.25),
                      width: AppSpacing.hairline,
                    ),
                  ),
                  leading: CupertinoButton(
                    padding: EdgeInsets.zero,
                    minimumSize: Size.square(AppSpacing.minInteractiveSize),
                    onPressed:
                        widget.onBack ?? () => Navigator.of(context).pop(),
                    child: const Icon(CupertinoIcons.back),
                  ),
                  trailing: CupertinoButton(
                    padding: EdgeInsets.zero,
                    minimumSize: Size.square(AppSpacing.minInteractiveSize),
                    onPressed: () =>
                        _showMoreOptions(context, circleName: circleName),
                    child: const Icon(CupertinoIcons.ellipsis_circle),
                  ),
                ),
                SliverToBoxAdapter(
                  child: _buildCircleSummary(
                    context: context,
                    isDark: isDark,
                    bg: bg,
                    bgSecondary: bgSecondary,
                    border: border,
                    state: circleState,
                    notifier: notifier,
                    coverUrl: coverUrl,
                  ),
                ),
                SliverPersistentHeader(
                  pinned: true,
                  delegate: _TabBarDelegate(
                    height: AppSpacing.tabNavigationHeight,
                    child: _buildPrimaryTabSurface(
                      isDark: isDark,
                      bg: bg,
                      border: border,
                    ),
                  ),
                ),
              ];
            },
            body: PageView(
              controller: _pageController,
              physics: const BouncingScrollPhysics(),
              onPageChanged: (index) => setState(() => _activeTabIndex = index),
              children: _resolvedTabs
                  .map(
                    (tab) => _buildSectionBody(
                      type: tab.type,
                      isDark: isDark,
                      state: circleState,
                    ),
                  )
                  .toList(growable: false),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildCircleSummary({
    required BuildContext context,
    required bool isDark,
    required Color bg,
    required Color bgSecondary,
    required Color border,
    required CircleState state,
    required CircleStateNotifier notifier,
    required String? coverUrl,
  }) {
    final circle = state.circleData;
    final coverHeight =
        max(236.0, MediaQuery.sizeOf(context).height * 0.27) + _pullOffset;
    final shadowColor = isDark
        ? Colors.black.withValues(alpha: 0.18)
        : Colors.black.withValues(alpha: 0.08);

    return ColoredBox(
      color: bg,
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerSm,
          AppSpacing.containerMd,
          AppSpacing.sm,
        ),
        child: Container(
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.vertical(
              top: Radius.circular(
                AppSpacing.largeBorderRadius + AppSpacing.sm,
              ),
              bottom: Radius.circular(AppSpacing.largeBorderRadius),
            ),
            border: Border.all(color: border.withValues(alpha: 0.12)),
            boxShadow: [
              BoxShadow(
                color: shadowColor,
                blurRadius: AppSpacing.xl,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.vertical(
                  top: Radius.circular(
                    AppSpacing.largeBorderRadius + AppSpacing.sm,
                  ),
                ),
                child: SizedBox(
                  height: coverHeight,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      if (coverUrl != null && coverUrl.isNotEmpty)
                        Image.network(
                          coverUrl,
                          fit: BoxFit.cover,
                          errorBuilder: (context, error, stackTrace) =>
                              ColoredBox(color: bgSecondary),
                        )
                      else
                        ColoredBox(
                          color: AppColors.primaryColor.withValues(alpha: 0.12),
                        ),
                      DecoratedBox(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [
                              Colors.black.withValues(alpha: 0.08),
                              Colors.black.withValues(alpha: 0.02),
                              bg.withValues(alpha: 0.92),
                            ],
                          ),
                        ),
                      ),
                      Positioned(
                        left: AppSpacing.containerMd,
                        right: AppSpacing.containerMd,
                        bottom: AppSpacing.containerMd,
                        child: Row(
                          children: [
                            Container(
                              padding: EdgeInsets.symmetric(
                                horizontal: AppSpacing.sm,
                                vertical: AppSpacing.xs,
                              ),
                              decoration: BoxDecoration(
                                color: Colors.white.withValues(alpha: 0.16),
                                borderRadius: BorderRadius.circular(
                                  AppSpacing.circularBorderRadius,
                                ),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const Icon(
                                    CupertinoIcons.photo_camera_solid,
                                    color: Colors.white,
                                    size: AppSpacing.iconSmall,
                                  ),
                                  SizedBox(width: AppSpacing.intraGroupXs),
                                  Text(
                                    UITextConstants.circleAssetsTab,
                                    style: TextStyle(
                                      color: Colors.white,
                                      fontSize: AppTypography.xs,
                                      fontWeight: AppTypography.semiBold,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const Spacer(),
                            if (state.role == CircleRole.owner ||
                                state.role == CircleRole.admin)
                              CupertinoButton(
                                padding: EdgeInsets.zero,
                                minimumSize: Size.square(
                                  AppSpacing.minInteractiveSize,
                                ),
                                onPressed: () => _openEditor(
                                  context,
                                  state: state,
                                  initialTab: CircleEditSettingsTab.info,
                                ),
                                child: Container(
                                  padding: EdgeInsets.symmetric(
                                    horizontal: AppSpacing.sm,
                                    vertical: AppSpacing.xs,
                                  ),
                                  decoration: BoxDecoration(
                                    color: Colors.white.withValues(alpha: 0.16),
                                    borderRadius: BorderRadius.circular(
                                      AppSpacing.circularBorderRadius,
                                    ),
                                  ),
                                  child: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      const Icon(
                                        CupertinoIcons.pencil,
                                        color: Colors.white,
                                        size: AppSpacing.iconSmall,
                                      ),
                                      SizedBox(width: AppSpacing.intraGroupXs),
                                      Text(
                                        UITextConstants.editCircle,
                                        style: TextStyle(
                                          color: Colors.white,
                                          fontSize: AppTypography.xs,
                                          fontWeight: AppTypography.semiBold,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(
                  AppSpacing.containerMd,
                  CircleHeader.avatarIntrusion + AppSpacing.sm,
                  AppSpacing.containerMd,
                  AppSpacing.containerMd,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    CircleHeader(
                      isDark: isDark,
                      avatarUrl: coverUrl,
                      name: circle?.name ?? '',
                      description: circle?.description,
                      tags: circle?.tags ?? const [],
                      badgeLabel: UITextConstants.circleOfficialBadge,
                      metaLine: _metaLine(state),
                    ),
                    SizedBox(height: AppSpacing.md),
                    CircleStatsRow(
                      isDark: isDark,
                      stats: {
                        ...state.stats,
                        if (circle != null) 'posts': circle.postCount,
                        if (circle != null)
                          'weeklyActive': circle.weeklyActiveCount,
                        if (circle != null) 'members': circle.memberCount,
                      },
                    ),
                    SizedBox(height: AppSpacing.sm),
                    CircleActionBar(
                      isDark: isDark,
                      role: state.role,
                      joinStatus: state.joinStatus,
                      isFollowed: state.isFollowed,
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
                      onJoinCircle: state.joinStatus == 'joined'
                          ? null
                          : notifier.joinCircle,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPrimaryTabSurface({
    required bool isDark,
    required Color bg,
    required Color border,
  }) {
    final tabs = _resolvedTabs
        .map((tab) => TabItem(id: tab.type, label: tab.label))
        .toList(growable: false);
    return Container(
      color: bg,
      padding: EdgeInsets.only(bottom: AppSpacing.intraGroupXs / 2),
      child: Container(
        decoration: BoxDecoration(
          color: bg,
          border: Border(
            top: BorderSide(color: border.withValues(alpha: 0.2)),
            bottom: BorderSide(color: border.withValues(alpha: 0.45)),
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: isDark ? 0.14 : 0.05),
              blurRadius: AppSpacing.md,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: SizedBox(
          height: AppSpacing.tabNavigationHeight,
          child: CenteredScrollableTabBar(
            tabs: tabs,
            activeTab: _resolvedTabs[_activeTabIndex].type,
            onTabChange: (tabId) {
              final index = _resolvedTabs.indexWhere(
                (tab) => tab.type == tabId,
              );
              if (index < 0 || index == _activeTabIndex) return;
              setState(() => _activeTabIndex = index);
              _pageController.animateToPage(
                index,
                duration: const Duration(milliseconds: 280),
                curve: Curves.easeInOut,
              );
            },
            isDark: isDark,
            transparentBackground: true,
          ),
        ),
      ),
    );
  }

  Widget _buildSectionBody({
    required String type,
    required bool isDark,
    required CircleState state,
  }) {
    final circle = state.circleData;
    return switch (type) {
      'content' => Padding(
        padding: EdgeInsets.only(
          top: AppSpacing.sm,
          bottom:
              MediaQuery.viewPaddingOf(context).bottom + AppSpacing.containerLg,
        ),
        child: SectionCreations(
          circleId: widget.circleId,
          isDark: isDark,
          role: state.role,
        ),
      ),
      'discussion' => SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerSm,
          AppSpacing.containerMd,
          MediaQuery.viewPaddingOf(context).bottom + AppSpacing.containerLg,
        ),
        child: _SectionSurface(
          isDark: isDark,
          child: SectionInteraction(circleId: widget.circleId, isDark: isDark),
        ),
      ),
      'assets' => SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerSm,
          AppSpacing.containerMd,
          MediaQuery.viewPaddingOf(context).bottom + AppSpacing.containerLg,
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
                storageQuotaBytes: circle?.storageQuotaBytes ?? 1073741824,
              ),
            ),
          ],
        ),
      ),
      _ => const SizedBox.shrink(),
    };
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

class _SectionSurface extends StatelessWidget {
  const _SectionSurface({required this.isDark, required this.child});

  final bool isDark;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    return Container(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(color: border.withValues(alpha: 0.12)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.14 : 0.05),
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
    return height != oldDelegate.height || child != oldDelegate.child;
  }
}
