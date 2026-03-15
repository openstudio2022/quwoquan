// ignore_for_file: unnecessary_underscores, unused_local_variable
import 'dart:math';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_header.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_stats_row.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_action_bar.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_creations.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_chat.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_storage.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_interaction.dart';

class CircleShell extends ConsumerStatefulWidget {
  const CircleShell({
    super.key,
    required this.circleId,
    this.onBack,
  });

  final String circleId;
  final VoidCallback? onBack;

  @override
  ConsumerState<CircleShell> createState() => _CircleShellState();
}

class _CircleShellState extends ConsumerState<CircleShell>
    with TickerProviderStateMixin {
  late PageController _pageController;
  late AnimationController _pullBackController;
  int _activeTabIndex = 0;
  double _pullOffset = 0;
  double _rawPullOffset = 0;
  bool _isPulling = false;
  bool _isHeaderCollapsed = false;

  List<_TabSpec> _resolvedTabs = [];

  static const _defaultSections = ['content', 'discussion', 'assets'];

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
    final visible = sectionConfig
        .where((s) => s.visible)
        .toList()
      ..sort((a, b) => a.order.compareTo(b.order));

    final availableTypes = visible.isNotEmpty
        ? visible.map((s) => s.sectionType).toSet()
        : <String>{'works', 'interaction', 'chat', 'storage'};
    final tabs = <_TabSpec>[];
    if (availableTypes.contains('works')) {
      tabs.add(_TabSpec(type: 'content', label: _sectionLabel('content')));
    }
    if (availableTypes.contains('interaction')) {
      tabs.add(_TabSpec(type: 'discussion', label: _sectionLabel('discussion')));
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
      'content' => '内容',
      'discussion' => '讨论',
      'assets' => '资料',
      _ => type,
    };
  }

  void _syncTabs(List<_TabSpec> newTabs) {
    if (newTabs.length != _resolvedTabs.length) {
      _resolvedTabs = newTabs;
      // Reset page? Or clamp?
      if (_activeTabIndex >= _resolvedTabs.length) {
        _activeTabIndex = 0;
        if (_pageController.hasClients) _pageController.jumpToPage(0);
      }
    } else {
      _resolvedTabs = newTabs;
    }
  }

  // — Spring-damped pull-to-stretch —

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

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final notifier = ref.watch(circleStateProvider(widget.circleId));
    final circleState = notifier.state;
    final circleData = circleState.circleData;

    final newTabs = _resolveTabs(circleState);
    if (newTabs.length != _resolvedTabs.length ||
        !_tabsEqual(newTabs, _resolvedTabs)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          setState(() => _syncTabs(newTabs));
        }
      });
    }

    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final avatarUrl = circleData?.coverUrl;
    final circleName = circleData?.name ?? '';
    final description = circleData?.description;
    final tags = circleData?.tags ?? [];
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
                  if (mounted) setState(() => _isHeaderCollapsed = innerBoxIsScrolled);
                });
              }

              return [
                SliverAppBar(
                  expandedHeight: 380,
                  pinned: true,
                  backgroundColor: bg,
                  foregroundColor: fg,
                  leading: IconButton(
                    icon: const Icon(CupertinoIcons.back),
                    onPressed: widget.onBack ?? () => Navigator.of(context).pop(),
                  ),
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
                          circleName,
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
                    IconButton(
                      icon: const Icon(Icons.more_horiz),
                      onPressed: () {},
                    ),
                  ],
                  flexibleSpace: FlexibleSpaceBar(
                    background: Stack(
                      fit: StackFit.expand,
                      children: [
                        if (coverUrl != null && coverUrl.isNotEmpty)
                          Transform.scale(
                            scale: 1 + (_pullOffset / (MediaQuery.of(context).size.height * 0.25 + 1) / 2),
                            child: Image.network(
                              coverUrl,
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
                                CircleHeader(
                                  isDark: isDark,
                                  avatarUrl: avatarUrl,
                                  name: circleName,
                                  description: description,
                                  tags: tags,
                                ),
                                SizedBox(height: AppSpacing.md),
                                CircleStatsRow(
                                  isDark: isDark,
                                  stats: circleState.stats,
                                  onStatTap: (type) {},
                                ),
                                SizedBox(height: AppSpacing.sm),
                                CircleActionBar(
                                  isDark: isDark,
                                  role: circleState.role,
                                  joinStatus: circleState.joinStatus,
                                  isFollowed: circleState.isFollowed,
                                  onEditCircle: () {},
                                  onManageCenter: () {},
                                  onFollow: notifier.toggleFollow,
                                  onJoinCircle: notifier.joinCircle,
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
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Center(
                        child: CupertinoSlidingSegmentedControl<int>(
                          groupValue: _activeTabIndex,
                          children: Map.fromEntries(
                            _resolvedTabs.asMap().entries.map(
                                  (e) => MapEntry(
                                    e.key,
                                    Padding(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 12),
                                      child: Text(e.value.label),
                                    ),
                                  ),
                                ),
                          ),
                          onValueChanged: (index) {
                            if (index != null) {
                              setState(() => _activeTabIndex = index);
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
            body: PageView(
              controller: _pageController,
              physics: const BouncingScrollPhysics(),
              onPageChanged: (index) => setState(() => _activeTabIndex = index),
              children: _resolvedTabs.map((tab) {
                return _buildSectionBody(tab.type, isDark, circleData, circleState);
              }).toList(),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSectionBody(String type, bool isDark, dynamic circleData, CircleState circleState) {
    return switch (type) {
      'content' => SectionCreations(
          circleId: widget.circleId,
          isDark: isDark,
          role: circleState.role,
        ),
      'discussion' => SectionInteraction(
          circleId: widget.circleId,
          isDark: isDark,
        ),
      'assets' => SingleChildScrollView(
          padding: EdgeInsets.only(bottom: AppSpacing.containerLg),
          child: Column(
            children: [
              SectionChat(
                circleId: widget.circleId,
                conversationId: circleData?.conversationId,
                isDark: isDark,
              ),
              SizedBox(height: AppSpacing.interGroupSm),
              SectionStorage(
                circleId: widget.circleId,
                isDark: isDark,
                storageUsedBytes: circleData?.storageUsedBytes ?? 0,
                storageQuotaBytes: circleData?.storageQuotaBytes ?? 1073741824,
              ),
            ],
          ),
        ),
      _ => SectionCreations(
          circleId: widget.circleId,
          isDark: isDark,
          role: circleState.role,
        ),
    };
  }

  bool _tabsEqual(List<_TabSpec> a, List<_TabSpec> b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i].type != b[i].type || a[i].label != b[i].label) return false;
    }
    return true;
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
  Widget build(BuildContext context, double shrinkOffset, bool overlapsContent) {
    return SizedBox.expand(child: child);
  }

  @override
  bool shouldRebuild(_TabBarDelegate oldDelegate) {
    return height != oldDelegate.height;
  }
}
