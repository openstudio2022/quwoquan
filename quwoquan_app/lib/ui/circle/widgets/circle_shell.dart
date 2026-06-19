import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/page_access_internal_routes.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_section.dart';
import 'package:quwoquan_app/components/object_page/object_page_shell.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/user/widgets/intersection_statement_card.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_edit_settings_page.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_impact_provider.dart';
import 'package:quwoquan_app/ui/circle/models/circle_page_tab.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_action_bar.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_header.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_chat.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_creations.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_members.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_storage.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_entry_arguments.dart';

part 'circle_shell_components.dart';
part 'circle_shell_builders.dart';

/// 圈子/组织详情壳层（V3 统一对象页骨架 ObjectPageShell + standard 吸顶模式）。
/// 几何/滚动/吸顶由 ObjectPageShell 收口；本壳只提供圈子业务插槽。
class CircleShell extends ConsumerStatefulWidget {
  const CircleShell({super.key, required this.circleId, this.onBack});

  final String circleId;
  final VoidCallback? onBack;

  @override
  ConsumerState<CircleShell> createState() => _CircleShellState();
}

class _CircleShellState extends ConsumerState<CircleShell> {
  static const double _cardRadius = AppSpacing.radiusTwentyFour;
  static const double _surfaceBridge = _cardRadius;

  late String _activeTabId;
  List<_TabSpec> _resolvedTabs = const <_TabSpec>[];

  @override
  void initState() {
    super.initState();
    _resolvedTabs = _resolveTabs(null);
    _activeTabId = _resolvedTabs.first.type;
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
        : CircleUIConfig.sections.map((section) => section.sectionType).toSet();
    final tabs = <_TabSpec>[];
    for (final tab in CircleUIConfig.tabs) {
      final hasVisibleSection = tab.sectionTypes.any(available.contains);
      if (!hasVisibleSection) {
        continue;
      }
      tabs.add(
        _TabSpec(type: tab.id, label: circleTabLabelForKey(tab.labelKey)),
      );
    }
    if (tabs.isNotEmpty) return tabs;
    return CircleUIConfig.tabs
        .map(
          (tab) =>
              _TabSpec(type: tab.id, label: circleTabLabelForKey(tab.labelKey)),
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
      await AppActionErrorFeedback.show(
        context,
        semantic: UiErrorSemantic(
          category: UiErrorCategory.sectionLoad,
          scope: UiErrorScope.global,
          title: UITextConstants.circleInfoUnavailableTitle,
          message: UITextConstants.contentLoadSoftFailed,
        ),
      );
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
    required CircleState state,
  }) async {
    final isManager =
        state.role == CircleRole.owner || state.role == CircleRole.admin;
    final sections = <AppActionSheetSection<_CircleMoreAction>>[];
    if (isManager) {
      sections.add(
        const AppActionSheetSection<_CircleMoreAction>(
          items: <AppActionSheetItem<_CircleMoreAction>>[
            AppActionSheetItem<_CircleMoreAction>(
              value: _CircleMoreAction.edit,
              label: UITextConstants.editCircle,
              icon: CupertinoIcons.pencil,
            ),
            AppActionSheetItem<_CircleMoreAction>(
              value: _CircleMoreAction.manage,
              label: UITextConstants.manageCenter,
              icon: CupertinoIcons.slider_horizontal_3,
            ),
          ],
        ),
      );
    }
    sections.addAll(const <AppActionSheetSection<_CircleMoreAction>>[
      AppActionSheetSection<_CircleMoreAction>(
        items: <AppActionSheetItem<_CircleMoreAction>>[
          AppActionSheetItem<_CircleMoreAction>(
            value: _CircleMoreAction.submitPost,
            label: UITextConstants.circleSubmitPost,
            icon: CupertinoIcons.add_circled,
          ),
        ],
      ),
      AppActionSheetSection<_CircleMoreAction>(
        items: <AppActionSheetItem<_CircleMoreAction>>[
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
      AppActionSheetSection<_CircleMoreAction>(
        items: <AppActionSheetItem<_CircleMoreAction>>[
          AppActionSheetItem<_CircleMoreAction>(
            value: _CircleMoreAction.report,
            label: UITextConstants.report,
            icon: CupertinoIcons.flag,
            isDestructive: true,
          ),
        ],
      ),
    ]);
    final action = await showAppActionSheet<_CircleMoreAction>(
      context,
      title: circleName.isEmpty ? AppConceptConstants.circles : circleName,
      sections: sections,
    );
    if (!context.mounted || action == null) return;
    switch (action) {
      case _CircleMoreAction.edit:
        await _openEditor(
          context,
          state: state,
          initialTab: CircleEditSettingsTab.info,
        );
      case _CircleMoreAction.manage:
        await _openEditor(
          context,
          state: state,
          initialTab: CircleEditSettingsTab.settings,
        );
      case _CircleMoreAction.submitPost:
        // /create 路由门负责未登录拦截；圈子锚点经 extra 注入 PublishSettings.circleIds。
        context.push(
          AppRoutePaths.create(),
          extra: CreateEntryArguments(
            circleId: widget.circleId,
            circleName: circleName.isEmpty ? null : circleName,
          ),
        );
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
    final state = ref.watch(circleStateProvider(widget.circleId));
    final circleCtrl = ref.read(circleStateProvider(widget.circleId).notifier);
    ref.listen<AuthSessionState>(authSessionControllerProvider, (
      AuthSessionState? previous,
      AuthSessionState next,
    ) {
      final justLoggedIn =
          next.isAuthenticated &&
          (previous == null || !previous.isAuthenticated);
      if (justLoggedIn) {
        maybeResumeJoinContinuation(circleCtrl);
      }
    });
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

    return AppScaffold(
      backgroundColor: bg,
      body: ObjectPageShell(
        keyPrefix: 'circle-shell',
        pinMode: ObjectPagePinMode.standard,
        identityPinExtent:
            CircleHeader.avatarOuterDiameter - CircleHeader.avatarIntrusion,
        onSwipe: _handleTabSwipeDragEnd,
        backgroundBuilder: (c, pull) =>
            _buildBackgroundLayer(bg: bg, coverUrl: coverUrl),
        summaryBuilder: (c) => _buildSummaryCard(
          c,
          isDark: isDark,
          state: state,
          notifier: circleCtrl,
          circleName: circleName,
          coverUrl: coverUrl,
        ),
        toolbarBuilder: (c, identity, bgOpacity) => _buildToolbar(
          c,
          isDark: isDark,
          fg: fg,
          border: border,
          circleName: circleName,
          state: state,
          avatarUrl: coverUrl,
          identityOpacity: identity,
          backgroundOpacity: bgOpacity,
        ),
        tabBarBuilder: (c, pinned, opacity) => _buildPrimaryTabBar(
          c,
          bg: surface,
          border: border,
          pinned: pinned,
          opacity: opacity,
        ),
        tabBodyBuilder: (c) =>
            _buildInlineTabBody(c, isDark: isDark, state: state),
      ),
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
