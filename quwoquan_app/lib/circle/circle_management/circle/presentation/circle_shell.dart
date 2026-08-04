import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/app/navigation/generated/page_access_internal_routes.g.dart';
import 'package:quwoquan_app/app/shell/object_detail_global_bottom_nav.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/application/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_ui_config.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/components/object_page/object_chrome_actions.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/object_impact_preview_card.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/application/object_intersection_provider.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/object_intersection_section.dart';
import 'package:quwoquan_app/content/media/media_asset/presentation/app_media_image.dart';
import 'package:quwoquan_app/components/object_page/object_page_shell.dart';
import 'package:quwoquan_app/components/object_page/object_slogan_card.dart';
import 'package:quwoquan_app/components/object_page/object_stats_row.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/presentation/rtc_call_entry_presenter.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/links/app_public_content_links.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/content_report_reason_sheet.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CircleJoinPolicy,
        CircleVisibility,
        ReportTargetType,
        CreateContentReportCommand;
import 'package:share_plus/share_plus.dart';
import 'package:quwoquan_app/circle/circle_management/circle/presentation/circle_edit_settings_page.dart';
import 'package:quwoquan_app/circle/circle_management/circle_membership/presentation/circle_membership_approval_page.dart';
import 'package:quwoquan_app/circle/circle_management/circle/domain/circle_page_tab.dart';
import 'package:quwoquan_app/circle/circle_management/circle/application/circle_state_provider.dart';
import 'package:quwoquan_app/circle/circle_management/circle/presentation/circle_action_bar.dart';
import 'package:quwoquan_app/circle/circle_management/circle/presentation/circle_header.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_chat.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_creations.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_members.dart';
import 'package:quwoquan_app/ui/circle/widgets/section_storage.dart';
import 'package:quwoquan_app/content/content/post/domain/create_entry_arguments.dart';

part 'circle_shell_components.dart';
part 'circle_shell_builders.dart';

/// 圈子/组织详情壳层（统一对象页骨架 ObjectPageShell + standard 吸顶模式）。
/// 几何/滚动/吸顶由 ObjectPageShell 收口；本壳只提供圈子业务插槽。
class CircleShell extends ConsumerStatefulWidget {
  const CircleShell({
    super.key,
    required this.circleId,
    this.onBack,
    this.sourceAppearanceMode = UiErrorAppearanceMode.inherit,
  });

  final String circleId;
  final VoidCallback? onBack;
  final UiErrorAppearanceMode sourceAppearanceMode;

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

  List<_TabSpec> _resolveTabs(CircleState? _) {
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

  /// 圈子轻统计：成员（主统计，高保口径 #6）+ 记录 + 讨论；下沉到共享 [ObjectStatsRow]。
  /// 仅展示云侧可枚举字段，缺失字段不臆造、不补占位。
  List<ObjectStatItem> _circleStatItems(CircleState state) {
    final circle = state.circleData;
    final cs = state.circleStats;
    final members = cs.members != 0 ? cs.members : (circle?.memberCount ?? 0);
    final posts = cs.posts != 0 ? cs.posts : (circle?.postCount ?? 0);
    final discussions = cs.discussions;
    return <ObjectStatItem>[
      if (members > 0)
        ObjectStatItem(
          value: formatCompactActionCount(members),
          label: CommunityText.circleMembers,
        ),
      if (posts > 0)
        ObjectStatItem(
          value: formatCompactActionCount(posts),
          label: ObjectHomepageText.objectTabRecord,
        ),
      if (discussions > 0)
        ObjectStatItem(
          value: formatCompactActionCount(discussions),
          label: ObjectHomepageText.objectTabDiscussion,
        ),
    ];
  }

  bool _isMemberLike(CircleState state) {
    return state.joinStatus == 'joined' &&
        (state.role == CircleRole.owner ||
            state.role == CircleRole.admin ||
            state.role == CircleRole.member);
  }

  bool _canAccessPrimaryContent(CircleState state) {
    final visibility = state.circleData?.visibility ?? CircleVisibility.public;
    return visibility == CircleVisibility.public || _isMemberLike(state);
  }

  bool _canAccessMemberSpaces(CircleState state) {
    return _isMemberLike(state);
  }

  String _joinGateDescription(CircleJoinPolicy? policy) => switch (policy ??
      CircleJoinPolicy.open) {
    CircleJoinPolicy.open => CommunityText.circleJoinOpenDescription,
    CircleJoinPolicy.approval => CommunityText.circleJoinApprovalDescription,
    CircleJoinPolicy.inviteOnly =>
      CommunityText.circleJoinInviteOnlyDescription,
  };

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
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
          title: ObjectHomepageText.circleInfoUnavailableTitle,
          message: FoundationText.contentLoadSoftFailed,
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

  Future<void> _startCircleCall(
    BuildContext context, {
    required CircleState state,
    required RtcCallEntryMediaType mediaType,
  }) {
    final group = state.defaultPublicGroup;
    return ref
        .read(rtcCallEntryPresenterProvider)
        .start(
          context: context,
          ref: ref,
          intent: RtcCallEntryIntent.circle(
            mediaType: mediaType,
            circleId: widget.circleId,
            conversationId: group?.conversationId ?? '',
            participantCount: group?.memberCount ?? 0,
          ),
          sourceSurface: AppUiSurfaces.circleDetail,
        );
  }

  Future<void> _showMoreOptions(
    BuildContext context, {
    required String circleName,
    required CircleState state,
  }) async {
    final isManager =
        state.role == CircleRole.owner || state.role == CircleRole.admin;
    final isMember = state.role != CircleRole.visitor;
    final sections = <AppActionSheetSection<_CircleMoreAction>>[];
    if (isManager) {
      sections.add(
        AppActionSheetSection<_CircleMoreAction>(
          items: <AppActionSheetItem<_CircleMoreAction>>[
            const AppActionSheetItem<_CircleMoreAction>(
              value: _CircleMoreAction.edit,
              label: CommunityText.editCircle,
              icon: CupertinoIcons.pencil,
            ),
            const AppActionSheetItem<_CircleMoreAction>(
              value: _CircleMoreAction.manage,
              label: CommunityText.manageCenter,
              icon: CupertinoIcons.slider_horizontal_3,
            ),
            // 审批入口仅 approval 圈子展示（open 圈子无 pending 队列语义）。
            if (state.circleData?.joinPolicy == CircleJoinPolicy.approval)
              const AppActionSheetItem<_CircleMoreAction>(
                value: _CircleMoreAction.approval,
                label: CommunityText.circleApprovalTitle,
                icon: CupertinoIcons.person_crop_circle_badge_checkmark,
              ),
          ],
        ),
      );
    }
    if (isMember) {
      sections.add(
        const AppActionSheetSection<_CircleMoreAction>(
          items: <AppActionSheetItem<_CircleMoreAction>>[
            AppActionSheetItem<_CircleMoreAction>(
              value: _CircleMoreAction.voiceCall,
              label: CallText.callGroupVoice,
              icon: CupertinoIcons.phone,
            ),
            AppActionSheetItem<_CircleMoreAction>(
              value: _CircleMoreAction.videoCall,
              label: CallText.callGroupVideo,
              icon: CupertinoIcons.video_camera,
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
            label: ContactText.circleSubmitPost,
            icon: CupertinoIcons.add_circled,
          ),
          AppActionSheetItem<_CircleMoreAction>(
            value: _CircleMoreAction.invite,
            label: CommunityText.circleInviteMembers,
            icon: CupertinoIcons.person_badge_plus,
          ),
        ],
      ),
      AppActionSheetSection<_CircleMoreAction>(
        items: <AppActionSheetItem<_CircleMoreAction>>[
          AppActionSheetItem<_CircleMoreAction>(
            value: _CircleMoreAction.share,
            label: FoundationText.share,
            icon: CupertinoIcons.share,
          ),
          AppActionSheetItem<_CircleMoreAction>(
            value: _CircleMoreAction.copyLink,
            label: FoundationText.copyLink,
            icon: CupertinoIcons.link,
          ),
        ],
      ),
      AppActionSheetSection<_CircleMoreAction>(
        items: <AppActionSheetItem<_CircleMoreAction>>[
          AppActionSheetItem<_CircleMoreAction>(
            value: _CircleMoreAction.report,
            label: ContentText.report,
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
      case _CircleMoreAction.approval:
        await Navigator.of(context).push(
          CupertinoPageRoute<void>(
            settings: const RouteSettings(
              name: PageAccessInternalRoutes.circleMembershipApproval,
            ),
            builder: (_) =>
                CircleMembershipApprovalPage(circleId: widget.circleId),
          ),
        );
      case _CircleMoreAction.voiceCall:
        await _startCircleCall(
          context,
          state: state,
          mediaType: RtcCallEntryMediaType.audio,
        );
      case _CircleMoreAction.videoCall:
        await _startCircleCall(
          context,
          state: state,
          mediaType: RtcCallEntryMediaType.video,
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
      case _CircleMoreAction.invite:
        await _shareCircle(context, circleName: circleName, asInvite: true);
      case _CircleMoreAction.share:
        await _shareCircle(context, circleName: circleName);
      case _CircleMoreAction.copyLink:
        await Clipboard.setData(
          ClipboardData(
            text: AppPublicContentLinks.circleWebUrl(widget.circleId),
          ),
        );
        if (context.mounted) {
          AppToast.show(context, ChatText.shareLinkCopied);
        }
      case _CircleMoreAction.report:
        _gatedReportCircle(context);
    }
  }

  /// 系统分享圈子深链；[asInvite] 时使用邀请语气文案（同链路，不另建通道）。
  Future<void> _shareCircle(
    BuildContext context, {
    required String circleName,
    bool asInvite = false,
  }) async {
    final url = AppPublicContentLinks.circleWebUrl(widget.circleId);
    final resolvedName = circleName.isEmpty
        ? AppConceptConstants.circles
        : circleName;
    final headline = asInvite
        ? UITextConstants.circleInviteShareText(resolvedName)
        : UITextConstants.circleShareSubject(resolvedName);
    final journeyTracker = ref.read(journeyEventTrackerProvider);
    try {
      final result = await SharePlus.instance.share(
        ShareParams(
          title: resolvedName,
          subject: headline,
          text: '$headline\n$url',
        ),
      );
      if (result.status == ShareResultStatus.dismissed) {
        return;
      }
      unawaited(
        journeyTracker.trackAction(
          journey: 'circle_share',
          action: asInvite ? 'invite_members' : 'share_circle',
          pageName: 'circle_shell',
          targetType: 'circle',
          targetKey: widget.circleId,
          payload: const {'result': 'success'},
        ),
      );
    } catch (_) {
      if (context.mounted) {
        AppToast.show(context, ChatText.shareFailed);
      }
    }
  }

  /// 举报圈子：登录门保障 + 原因选择，与用户主页举报共用统一举报链路。
  void _gatedReportCircle(BuildContext context) {
    runWhenLoggedIn(ref, context, AuthGateReason.report, () async {
      final reason = await showContentReportReasonSheet(context);
      if (reason == null || !context.mounted) return;
      final journeyTracker = ref.read(journeyEventTrackerProvider);
      final startedAt = DateTime.now();
      try {
        await ref
            .read(circleDetailContentReportCommandWriterProvider)
            .createReport(
              CreateContentReportCommand(
                targetId: widget.circleId,
                targetType: ReportTargetType.circle,
                reason: reason,
              ),
            );
        await journeyTracker.trackAction(
          journey: 'content_report',
          action: 'submit_report',
          pageName: 'circle_shell',
          payload: {
            'result': 'success',
            'durationMs': DateTime.now().difference(startedAt).inMilliseconds,
          },
        );
        if (context.mounted) {
          AppToast.show(context, ContentText.commentReportSubmitted);
        }
      } catch (error) {
        await journeyTracker.trackAction(
          journey: 'content_report',
          action: 'submit_report',
          pageName: 'circle_shell',
          payload: {
            'result': 'failure',
            'failReasonCode': error is CloudException
                ? (error.code ?? error.type.name)
                : error.runtimeType.toString(),
            'durationMs': DateTime.now().difference(startedAt).inMilliseconds,
          },
        );
        if (!context.mounted) {
          return;
        }
        final resolved = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        );
        await AppActionErrorFeedback.show(context, semantic: resolved);
      }
    });
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

    if (!state.isLoading &&
        state.circleData == null &&
        state.loadError != null) {
      return AppScaffold(
        backgroundColor: bg,
        navigationBar: AppNavigationBar(
          automaticallyImplyLeading: false,
          backgroundColor: bg,
          leading: AppNavigationBarIconButton(
            key: const ValueKey<String>('circle-shell-error-back'),
            icon: CupertinoIcons.back,
            onPressed:
                widget.onBack ??
                () {
                  Navigator.of(context).maybePop();
                },
          ),
        ),
        body: AppPageErrorState(
          semantic: ensureRetryUiErrorSemantic(
            runtimeErrorSemantic(
              context,
              error: state.loadError!,
              category: UiErrorCategory.pageLoad,
              scope: UiErrorScope.page,
              appearanceMode: widget.sourceAppearanceMode,
              sourceRouteId: AppRoutePaths.circleDetailPathTemplate,
            ),
          ),
          onRecovery: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              await circleCtrl.loadCircle();
              return ref
                          .read(circleStateProvider(widget.circleId))
                          .loadError ==
                      null
                  ? UiRecoveryOutcome.recovered
                  : UiRecoveryOutcome.stillBlocked;
            } else if (action.type == UiErrorActionType.dismiss) {
              final onBack = widget.onBack;
              if (onBack != null) {
                onBack();
              } else {
                await Navigator.of(context).maybePop();
              }
              return UiRecoveryOutcome.handedOff;
            }
            return UiRecoveryOutcome.cancelled;
          },
        ),
      );
    }

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
        contentHorizontalPadding: 0,
        surfaceBridgeOverride: 0,
        tabSurfaceHorizontalPadding: 0,
        tabSurfaceTopRadius: _cardRadius,
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
        // 高保口径：圈子详情页底部保留全局导航栏（首页/视频书/+/联系/我）。
        bottomBar: const ObjectDetailGlobalBottomNav(),
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
