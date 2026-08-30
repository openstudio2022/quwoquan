import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/public/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/runtime/di/rtc_call_entry_dependencies.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/conversation_assets_sheet.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart'
    show ConversationAssetView;
import 'package:quwoquan_app/design_system/feedback/skeleton/app_skeleton.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/conversation_message_search_sheet.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/design_system/layout/web_page_max_width_frame.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/observability/trackers/chat_interaction_telemetry_tracker.dart';
import 'package:quwoquan_app/runtime/di/conversation_members_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/group_home_provider.dart';

part 'chat_settings_page_widgets.part.dart';

/// 聊天设置/聊天信息页；全屏表单布局复用 [SettingsInsetFormPageScaffold]。
class ChatSettingsPage extends ConsumerStatefulWidget {
  const ChatSettingsPage({super.key, required this.conversationId});

  final String conversationId;

  @override
  ConsumerState<ChatSettingsPage> createState() => _ChatSettingsPageState();
}

class _ChatSettingsPageState extends ConsumerState<ChatSettingsPage> {
  bool _mute = false;
  bool _pin = false;
  bool _membersExpanded = false;

  @override
  void initState() {
    super.initState();
    // 开关初值从 inbox 本地副本水合（真相源是服务端 ConversationUserState，
    // 下一次 inbox 同步以服务端值收敛）。
    final entry = ref
        .read(chatInboxCacheProvider)
        .readInboxEntry(widget.conversationId);
    _mute = entry?.muted ?? false;
    _pin = entry?.pinned ?? false;
  }

  /// 免打扰/置顶是真实 ConversationUserState 命令：乐观切换，
  /// 远端失败回滚并提示，禁止只改本地 setState 的假状态。
  Future<void> _updateUserSetting({bool? muted, bool? pinned}) async {
    final previousMute = _mute;
    final previousPin = _pin;
    setState(() {
      if (muted != null) _mute = muted;
      if (pinned != null) _pin = pinned;
    });
    try {
      await ref
          .read(chatConversationRepositoryProvider)
          .updateConversationSettings(
            conversationId: widget.conversationId,
            muted: muted,
            pinned: pinned,
          );
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _mute = previousMute;
        _pin = previousPin;
      });
      AppToast.show(context, ChatText.settingUpdateFailed);
    }
  }

  /// 移出成员模式（owner/admin 经「−」进入；点成员头像确认移出）。
  bool _removeMemberMode = false;

  /// 移出成员：确认对话框 → RemoveMember（治理动作）→ roster 刷新。
  Future<void> _confirmRemoveMember(String userId, String displayName) async {
    final confirmed = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(ChatText.removeMemberEntry),
        content: Text(
          '${ChatText.removeMemberConfirmPrefix}$displayName'
          '${ChatText.removeMemberConfirmSuffix}',
        ),
        actions: [
          CupertinoDialogAction(
            child: Text(FoundationText.cancel),
            onPressed: () => Navigator.pop(dialogContext, false),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            child: Text(FoundationText.confirm),
            onPressed: () => Navigator.pop(dialogContext, true),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await ref
          .read(conversationMembersProvider(widget.conversationId).notifier)
          .removeMember(userId);
      unawaited(
        ref
            .read(chatInteractionTelemetryTrackerProvider)
            .track(
              action: ChatInteractionAction.groupGovernance,
              outcome: ChatInteractionOutcome.succeeded,
              governanceAction: ChatGovernanceAction.memberRemove,
              pageName: PageNames.chatSettings,
              surfaceId: AppUiSurfaces.chatSettings.id,
            ),
      );
      if (!mounted) return;
      AppToast.show(context, ChatText.removeMemberSuccess);
    } catch (error) {
      unawaited(
        ref
            .read(chatInteractionTelemetryTrackerProvider)
            .track(
              action: ChatInteractionAction.groupGovernance,
              outcome: ChatInteractionOutcome.failed,
              governanceAction: ChatGovernanceAction.memberRemove,
              pageName: PageNames.chatSettings,
              surfaceId: AppUiSurfaces.chatSettings.id,
              error: error,
            ),
      );
      if (!mounted) return;
      final resolved = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      await AppActionErrorFeedback.show(context, semantic: resolved);
    }
  }

  static const int _memberColumns = 5;

  /// 收起时最多 4 行（5×4 格末格为「添加」）：超过则折叠，仅展示本容量内成员。
  static const int _memberRowsCollapsed = 4;
  static int get _collapsedMemberCapacity =>
      _memberColumns * _memberRowsCollapsed - 1;

  /// 退出群聊：二次确认 → LeaveConversation（自愿离开语义；owner 须先转让）。
  /// 相册资产点击：全屏大图（与会话页图片消息同一消费链）。
  void _openAssetImage(ConversationAssetView asset) {
    final rawUrl = asset.mediaDeliveryUrl?.trim() ?? '';
    if (rawUrl.isEmpty) {
      AppToast.show(context, ChatText.chatMediaUnavailable);
      return;
    }
    unawaited(
      showAppFloatingModal<void>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) {
          return ColoredBox(
            key: const ValueKey<String>('chat_image_viewer_surface'),
            color: AppColors.black,
            child: SafeArea(
              child: Stack(
                children: [
                  Positioned.fill(
                    child: GestureDetector(
                      onTap: () => Navigator.of(dialogContext).pop(),
                      child: InteractiveViewer(
                        maxScale: 4,
                        child: Center(
                          child: AppCachedNetworkImage(
                            imageUrl: rawUrl,
                            fit: BoxFit.contain,
                            errorWidget: Icon(
                              CupertinoIcons.photo,
                              color: AppColors.white.withValues(alpha: 0.6),
                              size: AppSpacing.iconLarge,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    top: AppSpacing.intraGroupSm,
                    left: AppSpacing.intraGroupSm,
                    child: CupertinoButton(
                      key: const ValueKey<String>('chat_image_viewer_close'),
                      padding: EdgeInsets.all(AppSpacing.intraGroupXs),
                      onPressed: () => Navigator.of(dialogContext).pop(),
                      child: Icon(CupertinoIcons.xmark, color: AppColors.white),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  /// 文件资产点击：经平台能力打开交付 URL（与会话页文件消息同一消费链）。
  Future<void> _openAssetFile(ConversationAssetView asset) async {
    final rawUrl = asset.mediaDeliveryUrl?.trim() ?? '';
    if (rawUrl.isEmpty) {
      AppToast.show(context, ChatText.chatMediaUnavailable);
      return;
    }
    try {
      final launched = await launchUrl(
        Uri.parse(rawUrl),
        mode: ref.read(platformCapabilitiesProvider).hasLocalFileSystem
            ? LaunchMode.externalApplication
            : LaunchMode.platformDefault,
      );
      if (!launched) {
        throw StateError('platform rejected the file delivery URL');
      }
    } catch (_) {
      if (!mounted) return;
      AppToast.show(context, ChatText.chatFileOpenFailed);
    }
  }

  Future<void> _confirmExitGroup() async {
    final confirmed = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(ChatText.exitGroupChat),
        content: Text(ChatText.exitGroupChatConfirmMessage),
        actions: [
          CupertinoDialogAction(
            child: Text(FoundationText.cancel),
            onPressed: () => Navigator.pop(dialogContext, false),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            child: Text(ChatText.exitGroupChat),
            onPressed: () => Navigator.pop(dialogContext, true),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await ref
          .read(conversationMembersProvider(widget.conversationId).notifier)
          .leaveConversation();
      unawaited(
        ref
            .read(chatInteractionTelemetryTrackerProvider)
            .track(
              action: ChatInteractionAction.groupGovernance,
              outcome: ChatInteractionOutcome.succeeded,
              governanceAction: ChatGovernanceAction.memberLeave,
              pageName: PageNames.chatSettings,
              surfaceId: AppUiSurfaces.chatSettings.id,
            ),
      );
      if (!mounted) return;
      ref.invalidate(conversationMembersProvider(widget.conversationId));
      ref.invalidate(groupHomeProvider(widget.conversationId));
      AppToast.show(context, ChatText.exitGroupChatSuccess);
      context.go(AppRoutePaths.chat);
    } catch (error) {
      unawaited(
        ref
            .read(chatInteractionTelemetryTrackerProvider)
            .track(
              action: ChatInteractionAction.groupGovernance,
              outcome: ChatInteractionOutcome.failed,
              governanceAction: ChatGovernanceAction.memberLeave,
              pageName: PageNames.chatSettings,
              surfaceId: AppUiSurfaces.chatSettings.id,
              error: error,
            ),
      );
      if (!mounted) return;
      final resolved = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      await AppActionErrorFeedback.show(context, semantic: resolved);
    }
  }

  void _showEditGroupNameDialog() {
    final groupHome = ref.read(groupHomeProvider(widget.conversationId)).value;
    final currentName = groupHome?.title ?? '';
    final controller = TextEditingController(text: currentName);
    final membersState = ref.read(
      conversationMembersProvider(widget.conversationId),
    );
    final isAdminOrOwner = membersState.isAdminOrOwner;
    final nameEditableByAdminOnly =
        membersState.groupSettings.nameEditableByAdminOnly;

    if (nameEditableByAdminOnly && !isAdminOrOwner) {
      showAppCupertinoDialog<void>(
        context: context,
        builder: (_) => CupertinoAlertDialog(
          content: Text(ChatText.groupNameAdminOnly),
          actions: [
            CupertinoDialogAction(
              child: Text(FoundationText.confirm),
              onPressed: () => Navigator.pop(context),
            ),
          ],
        ),
      );
      return;
    }

    showAppCupertinoDialog<void>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: Text(ChatText.editGroupName),
        content: Padding(
          padding: EdgeInsets.only(top: AppSpacing.sm),
          child: CupertinoTextField(
            controller: controller,
            placeholder: ChatText.groupNameHint,
            autofocus: true,
            maxLength: 30,
          ),
        ),
        actions: [
          CupertinoDialogAction(
            child: Text(FoundationText.cancel),
            onPressed: () => Navigator.pop(ctx),
          ),
          CupertinoDialogAction(
            isDefaultAction: true,
            child: Text(FoundationText.confirm),
            onPressed: () async {
              final newName = controller.text.trim();
              Navigator.pop(ctx);
              if (newName.isNotEmpty && newName != currentName) {
                try {
                  await ref
                      .read(
                        conversationMembersProvider(
                          widget.conversationId,
                        ).notifier,
                      )
                      .updateGroupDisplayTitle(newName);
                  if (mounted) {
                    ref.invalidate(groupHomeProvider(widget.conversationId));
                    AppToast.show(context, ChatText.groupNameUpdated);
                  }
                } catch (error) {
                  if (!mounted) {
                    return;
                  }
                  final resolved = runtimeErrorSemantic(
                    context,
                    error: error,
                    category: UiErrorCategory.submit,
                    scope: UiErrorScope.global,
                  );
                  final semantic = UiErrorSemantic(
                    category: resolved.category,
                    scope: resolved.scope,
                    title: ChatText.groupNameUpdateIncompleteTitle,
                    message: resolved.message,
                    secondaryMessage: resolved.secondaryMessage,
                    primaryAction: const UiErrorAction(
                      type: UiErrorActionType.retry,
                      label: ContentText.tryAgain,
                    ),
                    secondaryAction: resolved.secondaryAction,
                    dismissible: resolved.dismissible,
                    sourceCode: resolved.sourceCode,
                    failureKind: resolved.failureKind,
                    recoveryAction: resolved.recoveryAction,
                    presentation: resolved.presentation,
                    tone: resolved.tone,
                  );
                  await AppActionErrorFeedback.show(
                    context,
                    semantic: semantic,
                    onAction: (action) async {
                      if (action.type == UiErrorActionType.retry ||
                          action.type == UiErrorActionType.resubmit) {
                        _showEditGroupNameDialog();
                      }
                    },
                  );
                }
              }
            },
          ),
        ],
      ),
    );
  }

  Future<void> _startGroupCall(
    RtcCallEntryMediaType mediaType, {
    required int participantCount,
  }) {
    return ref
        .read(rtcCallEntryPresenterProvider)
        .start(
          context: context,
          ref: ref,
          intent: RtcCallEntryIntent.conversation(
            mediaType: mediaType,
            conversationId: widget.conversationId,
            participantCount: participantCount,
          ),
          sourceSurface: AppUiSurfaces.chatSettings,
        );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final groupHomeAsync = ref.watch(groupHomeProvider(widget.conversationId));
    final groupHome = groupHomeAsync.value;
    final membersState = ref.watch(
      conversationMembersProvider(widget.conversationId),
    );
    final members = membersState.members;
    final isAdminOrOwner = membersState.isAdminOrOwner;
    final loadError = groupHomeAsync.hasError
        ? groupHomeAsync.error
        : membersState.error;

    if (loadError != null && groupHome == null && members.isEmpty) {
      return SettingsInsetFormPageScaffold(
        isDark: isDark,
        title: ChatText.chatInfoTitle,
        onBack: () => context.pop(),
        body: AppPageErrorState(
          semantic: runtimeErrorSemantic(
            context,
            error: loadError,
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
          ),
          onRecovery: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              ref.invalidate(groupHomeProvider(widget.conversationId));
              await ref
                  .read(
                    conversationMembersProvider(widget.conversationId).notifier,
                  )
                  .load();
              return UiRecoveryOutcome.superseded;
            }
            return UiRecoveryOutcome.cancelled;
          },
        ),
      );
    }

    final memberCount = members.isNotEmpty
        ? members.length
        : (groupHome?.memberCount ?? 0);
    final groupTitle = groupHome?.title.trim().isNotEmpty == true
        ? groupHome!.title.trim()
        : ChatText.groupNameHint;
    final announcement = groupHome?.announcement.trim() ?? '';
    final circleGroupID = groupHome?.circleGroupId.trim().isNotEmpty == true
        ? groupHome!.circleGroupId.trim()
        : membersState.groupSettings.circleGroupId.trim();
    final circleID = groupHome?.circleId.trim().isNotEmpty == true
        ? groupHome!.circleId.trim()
        : membersState.groupSettings.circleId.trim();
    final isCircleGroupManaged = circleGroupID.isNotEmpty;
    final VoidCallback? openCircleGroupManagement = circleID.isEmpty
        ? null
        : () => context.go(AppRoutePaths.circleDetail(id: circleID));

    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    final memberGridCount = members.length;
    final memberGridOverflow = memberGridCount > _collapsedMemberCapacity;
    final visibleMemberCount = !memberGridOverflow || _membersExpanded
        ? memberGridCount
        : _collapsedMemberCapacity;

    final secondaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final chevronColor = SettingsSemanticConstants.selectionChevronColor(
      isDark,
    );
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: '${ChatText.chatInfoTitle}($memberCount)',
      onBack: () => context.pop(),
      body: WebPageMaxWidthFrame(
        child: SafeArea(
          bottom: false,
          child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: EdgeInsets.only(
              left: SettingsSemanticConstants.insetFormListHorizontalPadding,
              right: SettingsSemanticConstants.insetFormListHorizontalPadding,
              top: AppSpacing.intraGroupSm,
              bottom: AppSpacing.xl + MediaQuery.paddingOf(context).bottom,
            ),
            children: [
              if (groupHomeAsync.isLoading && groupHome == null) ...[
                const AppSkeletonListRows(rowCount: 3),
                SizedBox(
                  height: SettingsSemanticConstants.insetFormSectionVerticalGap,
                ),
              ],
              SettingsInsetGroupedSection(
                isDark: isDark,
                density: SettingsInsetSectionDensity.compact,
                child: _GroupCapabilityGrid(
                  isDark: isDark,
                  enabledCapabilities:
                      groupHome?.capabilities ?? const <String>[],
                  onVoiceCall: () => _startGroupCall(
                    RtcCallEntryMediaType.audio,
                    participantCount: memberCount,
                  ),
                  onVideoCall: () => _startGroupCall(
                    RtcCallEntryMediaType.video,
                    participantCount: memberCount,
                  ),
                  // 活动群空间：绑定 Gathering 的会话直达 Board（DEC-002）。
                  onOpenBoard:
                      (groupHome?.gatheringId.trim().isNotEmpty ?? false)
                      ? () => context.push(
                          AppRoutePaths.gatheringBoard(
                            id: widget.conversationId,
                          ),
                        )
                      : null,
                  onOpenAlbum: () => unawaited(
                    ConversationAssetsSheet.show(
                      context,
                      conversationId: widget.conversationId,
                      kind: 'image',
                      onOpenImage: _openAssetImage,
                    ),
                  ),
                  onOpenFiles: () => unawaited(
                    ConversationAssetsSheet.show(
                      context,
                      conversationId: widget.conversationId,
                      kind: 'file',
                      onOpenFile: _openAssetFile,
                    ),
                  ),
                ),
              ),
              SizedBox(
                height: SettingsSemanticConstants.insetFormSectionVerticalGap,
              ),
              SettingsInsetGroupedSection(
                isDark: isDark,
                density: SettingsInsetSectionDensity.standard,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    LayoutBuilder(
                      builder: (context, constraints) {
                        // owner/admin 追加「−」移出成员入口格（对齐微信成员网格治理语义）；
                        // 搜索格对所有群形态可用（含圈群），大群按名检索成员。
                        final managementCells = isCircleGroupManaged
                            ? 0
                            : (isAdminOrOwner ? 2 : 1);
                        final searchCellIndex =
                            visibleMemberCount + managementCells;
                        final totalCells = searchCellIndex + 1;
                        final gridGap = AppSpacing.sm;
                        final availableWidth = constraints.maxWidth.isFinite
                            ? constraints.maxWidth
                            : MediaQuery.sizeOf(context).width -
                                  SettingsSemanticConstants
                                          .insetFormListHorizontalPadding *
                                      2;
                        final memberCellWidth =
                            (availableWidth - gridGap * (_memberColumns - 1)) /
                            _memberColumns;
                        final memberLabelHeight =
                            AppTypography.xs * AppTypography.lineHeightCompact;
                        final memberCellHeight =
                            AppSpacing.avatarUserLg +
                            AppSpacing.xs +
                            memberLabelHeight +
                            AppSpacing.xs;
                        return GridView.builder(
                          shrinkWrap: true,
                          physics: const NeverScrollableScrollPhysics(),
                          gridDelegate:
                              SliverGridDelegateWithFixedCrossAxisCount(
                                crossAxisCount: _memberColumns,
                                childAspectRatio:
                                    memberCellWidth / memberCellHeight,
                                crossAxisSpacing: gridGap,
                                mainAxisSpacing: gridGap,
                              ),
                          itemCount: totalCells,
                          itemBuilder: (context, index) {
                            if (index == searchCellIndex) {
                              return Align(
                                alignment: Alignment.topCenter,
                                child: _AddMemberPlaceholder(
                                  key: const ValueKey(
                                    'chat_settings_member_search_entry',
                                  ),
                                  borderColor: borderColor,
                                  size: AppSpacing.avatarUserLg,
                                  icon: CupertinoIcons.search,
                                  onTap: () => context.push(
                                    AppRoutePaths.chatMemberSearch(
                                      id: widget.conversationId,
                                    ),
                                  ),
                                ),
                              );
                            }
                            if (!isCircleGroupManaged &&
                                index == visibleMemberCount) {
                              return Align(
                                alignment: Alignment.topCenter,
                                child: _AddMemberPlaceholder(
                                  borderColor: borderColor,
                                  size: AppSpacing.avatarUserLg,
                                  onTap: () {
                                    if (_removeMemberMode) {
                                      setState(() => _removeMemberMode = false);
                                      return;
                                    }
                                    context.push(
                                      AppRoutePaths.chatAddMembers(
                                        id: widget.conversationId,
                                      ),
                                    );
                                  },
                                ),
                              );
                            }
                            if (!isCircleGroupManaged &&
                                isAdminOrOwner &&
                                index == visibleMemberCount + 1) {
                              return Align(
                                alignment: Alignment.topCenter,
                                child: _AddMemberPlaceholder(
                                  key: const ValueKey(
                                    'chat_settings_remove_member_entry',
                                  ),
                                  borderColor: borderColor,
                                  size: AppSpacing.avatarUserLg,
                                  icon: _removeMemberMode
                                      ? CupertinoIcons.checkmark
                                      : CupertinoIcons.minus,
                                  onTap: () => setState(
                                    () =>
                                        _removeMemberMode = !_removeMemberMode,
                                  ),
                                ),
                              );
                            }
                            final m = members[index];
                            final personaId = m.userId.trim();
                            final userHandle = m.userHandle.trim();
                            // 服务端为强制门（owner 不可移出、admin 仅可移出普通成员）；
                            // UI 侧同源预判避免必败请求。
                            final removable =
                                !isCircleGroupManaged &&
                                _removeMemberMode &&
                                !m.isCurrentUser &&
                                m.role != 'owner' &&
                                (membersState.isOwner || m.role == 'member');
                            final avatar = _MemberAvatar(
                              name: m.displayName,
                              avatarUrl: m.avatarUrl,
                              textColor: fgPrimary,
                              role: m.role,
                              onTap: removable
                                  ? () => _confirmRemoveMember(
                                      m.userId,
                                      m.displayName,
                                    )
                                  : userHandle.isEmpty
                                  ? null
                                  : () => context.push(
                                      AppRoutePaths.userProfile(
                                        userHandle: userHandle,
                                      ),
                                      extra: UserProfileRouteExtra(
                                        personaId: personaId.isEmpty
                                            ? null
                                            : personaId,
                                        avatarUrl: m.avatarUrl,
                                        displayName: m.displayName,
                                      ),
                                    ),
                            );
                            if (!removable) {
                              return avatar;
                            }
                            return Stack(
                              clipBehavior: Clip.none,
                              children: [
                                avatar,
                                Positioned(
                                  top: -AppSpacing.xs,
                                  right: AppSpacing.xs,
                                  child: IgnorePointer(
                                    child: Icon(
                                      CupertinoIcons.minus_circle_fill,
                                      key: ValueKey(
                                        'chat_settings_remove_badge_'
                                        '${m.userId}',
                                      ),
                                      size: AppSpacing.iconMedium,
                                      color: AppColors.error,
                                    ),
                                  ),
                                ),
                              ],
                            );
                          },
                        );
                      },
                    ),
                    if (memberGridOverflow) ...[
                      SizedBox(height: AppSpacing.xs),
                      Center(
                        child: GestureDetector(
                          onTap: () => setState(
                            () => _membersExpanded = !_membersExpanded,
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                _membersExpanded
                                    ? ChatText.collapseMembers
                                    : ChatText.moreMembers,
                                style: TextStyle(
                                  fontSize: AppTypography.md,
                                  color: fgPrimary.withValues(alpha: 0.75),
                                ),
                              ),
                              SizedBox(width: AppSpacing.xs),
                              Icon(
                                _membersExpanded
                                    ? CupertinoIcons.chevron_up
                                    : CupertinoIcons.chevron_down,
                                size: AppSpacing.iconMedium,
                                color: fgPrimary.withValues(alpha: 0.75),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              SizedBox(
                height: SettingsSemanticConstants.insetFormSectionVerticalGap,
              ),
              SettingsInsetGroupedSection(
                isDark: isDark,
                density: SettingsInsetSectionDensity.compact,
                child: Column(
                  children: [
                    SettingsInsetFormRow(
                      isDark: isDark,
                      label: ChatText.groupName,
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          ConstrainedBox(
                            constraints: BoxConstraints(
                              maxWidth: MediaQuery.of(context).size.width * 0.4,
                            ),
                            child: Text(
                              groupTitle,
                              style: TextStyle(
                                fontSize: AppTypography.base,
                                fontWeight: AppTypography.medium,
                                color: secondaryText,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              textAlign: TextAlign.right,
                            ),
                          ),
                          SizedBox(width: AppSpacing.containerSm),
                          Icon(
                            CupertinoIcons.chevron_forward,
                            size: AppSpacing.iconMedium,
                            color: chevronColor,
                          ),
                        ],
                      ),
                      onTap: isCircleGroupManaged
                          ? openCircleGroupManagement
                          : _showEditGroupNameDialog,
                    ),
                    SettingsInsetFormSectionDivider(isDark: isDark),
                    SettingsInsetFormRow(
                      isDark: isDark,
                      label: ChatText.groupAnnouncement,
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          ConstrainedBox(
                            constraints: BoxConstraints(
                              maxWidth: MediaQuery.of(context).size.width * 0.4,
                            ),
                            child: Text(
                              announcement.isEmpty
                                  ? ChatText.groupAnnouncementEmpty
                                  : announcement,
                              style: TextStyle(
                                fontSize: AppTypography.base,
                                color: secondaryText,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          SizedBox(width: AppSpacing.containerSm),
                          Icon(
                            CupertinoIcons.chevron_forward,
                            size: AppSpacing.iconMedium,
                            color: chevronColor,
                          ),
                        ],
                      ),
                      onTap: isCircleGroupManaged
                          ? openCircleGroupManagement
                          : () => context.push(
                              AppRoutePaths.chatAnnouncement(
                                id: widget.conversationId,
                              ),
                            ),
                    ),
                    if (isCircleGroupManaged || isAdminOrOwner) ...[
                      SettingsInsetFormSectionDivider(isDark: isDark),
                      SettingsInsetFormRow(
                        isDark: isDark,
                        label: isCircleGroupManaged
                            ? ChatText.circleGroupManagedNotice
                            : ChatText.groupManagement,
                        trailing: Icon(
                          CupertinoIcons.chevron_forward,
                          size: AppSpacing.iconMedium,
                          color: chevronColor,
                        ),
                        onTap: isCircleGroupManaged
                            ? openCircleGroupManagement
                            : () => context.push(
                                AppRoutePaths.chatManage(
                                  id: widget.conversationId,
                                ),
                              ),
                      ),
                    ],
                  ],
                ),
              ),
              SizedBox(
                height: SettingsSemanticConstants.insetFormSectionVerticalGap,
              ),
              SettingsInsetGroupedSection(
                isDark: isDark,
                density: SettingsInsetSectionDensity.compact,
                child: Column(
                  children: [
                    SettingsInsetFormRow(
                      isDark: isDark,
                      label: ChatText.muteNotifications,
                      trailing: _buildSettingSwitch(
                        isDark: isDark,
                        value: _mute,
                        onChanged: (v) =>
                            unawaited(_updateUserSetting(muted: v)),
                      ),
                    ),
                    SettingsInsetFormSectionDivider(isDark: isDark),
                    SettingsInsetFormRow(
                      isDark: isDark,
                      label: ChatText.pinChat,
                      trailing: _buildSettingSwitch(
                        isDark: isDark,
                        value: _pin,
                        onChanged: (v) =>
                            unawaited(_updateUserSetting(pinned: v)),
                      ),
                    ),
                    SettingsInsetFormSectionDivider(isDark: isDark),
                    SettingsInsetFormRow(
                      key: const ValueKey<String>(
                        'chat_settings_search_in_conversation',
                      ),
                      isDark: isDark,
                      label: ChatText.searchInConversation,
                      trailing: const SizedBox.shrink(),
                      onTap: () => unawaited(
                        ConversationMessageSearchSheet.show(
                          context,
                          conversationId: widget.conversationId,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(
                height: SettingsSemanticConstants.insetFormSectionVerticalGap,
              ),
              SettingsInsetGroupedSection(
                isDark: isDark,
                density: SettingsInsetSectionDensity.compact,
                child: SettingsInsetCenteredActionRow(
                  isDark: isDark,
                  label: isCircleGroupManaged
                      ? ChatText.openCircleGroupManagement
                      : ChatText.exitGroupChat,
                  isDestructive: !isCircleGroupManaged,
                  onTap: isCircleGroupManaged
                      ? () => openCircleGroupManagement?.call()
                      : _confirmExitGroup,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// 设置项开关：语义 token。选中时轨道蓝、拇指白；未选中时轨道浅灰、拇指纯白（避免与背景融在一起）
  Widget _buildSettingSwitch({
    required bool isDark,
    required bool value,
    ValueChanged<bool>? onChanged,
  }) {
    return CupertinoSwitch(
      value: value,
      onChanged: onChanged,
      activeTrackColor: SettingsSemanticConstants.switchActiveTrackColor,
      inactiveTrackColor: SettingsSemanticConstants.switchInactiveTrackColor(
        isDark,
      ),
    );
  }
}
