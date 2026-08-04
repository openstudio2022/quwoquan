import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/rtc/call_session/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/rtc/rtc_call_entry_presenter.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/chat_interaction_telemetry_tracker.dart';
import 'package:quwoquan_app/ui/chat/providers/conversation_members_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/group_home_provider.dart';

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
                AppRequestFeedback.section(),
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
                        // owner/admin 追加「−」移出成员入口格（对齐微信成员网格治理语义）。
                        final actionCells = isCircleGroupManaged
                            ? 0
                            : (isAdminOrOwner ? 2 : 1);
                        final totalCells = visibleMemberCount + actionCells;
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
                            if (index == visibleMemberCount) {
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
                            if (index == visibleMemberCount + 1) {
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
                                        avatar: m.avatarUrl,
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
                        onChanged: (v) => setState(() => _mute = v),
                      ),
                    ),
                    SettingsInsetFormSectionDivider(isDark: isDark),
                    SettingsInsetFormRow(
                      isDark: isDark,
                      label: ChatText.pinChat,
                      trailing: _buildSettingSwitch(
                        isDark: isDark,
                        value: _pin,
                        onChanged: (v) => setState(() => _pin = v),
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

class _GroupCapabilityGrid extends StatelessWidget {
  const _GroupCapabilityGrid({
    required this.isDark,
    required this.enabledCapabilities,
    required this.onVoiceCall,
    required this.onVideoCall,
  });

  final bool isDark;
  final List<String> enabledCapabilities;
  final VoidCallback onVoiceCall;
  final VoidCallback onVideoCall;

  bool _enabled(String capability) {
    return enabledCapabilities.isEmpty ||
        enabledCapabilities.contains(capability);
  }

  @override
  Widget build(BuildContext context) {
    final items = <_GroupCapabilityItem>[
      _GroupCapabilityItem(
        label: ChatText.groupCapabilityAlbum,
        icon: CupertinoIcons.photo,
        enabled: _enabled('album'),
      ),
      _GroupCapabilityItem(
        label: ChatText.groupCapabilityFile,
        icon: CupertinoIcons.folder,
        enabled: _enabled('file'),
      ),
      _GroupCapabilityItem(
        label: CallText.callGroupVoice,
        icon: CupertinoIcons.phone,
        enabled: true,
        onPressed: onVoiceCall,
      ),
      _GroupCapabilityItem(
        label: CallText.callGroupVideo,
        icon: CupertinoIcons.video_camera,
        enabled: true,
        onPressed: onVideoCall,
      ),
    ];
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Row(
      children: items
          .map(
            (item) => Expanded(
              child: CupertinoButton(
                padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
                onPressed: item.enabled ? item.onPressed : null,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      item.icon,
                      size: AppSpacing.iconLarge,
                      color: item.enabled ? fgPrimary : fgSecondary,
                    ),
                    SizedBox(height: AppSpacing.xs),
                    Text(
                      item.label,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: item.enabled ? fgPrimary : fgSecondary,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          )
          .toList(growable: false),
    );
  }
}

class _GroupCapabilityItem {
  const _GroupCapabilityItem({
    required this.label,
    required this.icon,
    required this.enabled,
    this.onPressed,
  });

  final String label;
  final IconData icon;
  final bool enabled;
  final VoidCallback? onPressed;
}

class _MemberAvatar extends StatelessWidget {
  const _MemberAvatar({
    required this.name,
    required this.avatarUrl,
    required this.textColor,
    required this.onTap,
    this.role,
  });

  final String name;
  final String avatarUrl;
  final Color textColor;
  final VoidCallback? onTap;
  final String? role;

  static final double _settingsAvatarSize = AppSpacing.avatarUserLg;

  @override
  Widget build(BuildContext context) {
    final roleLabel = role == 'owner'
        ? ChatText.owner
        : role == 'admin'
        ? ChatText.admin
        : null;
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Stack(
            clipBehavior: Clip.none,
            children: [
              RoundedSquareAvatar(
                size: _settingsAvatarSize,
                imageUrl: avatarUrl,
                name: name,
              ),
              if (roleLabel != null)
                Positioned(
                  bottom: -2,
                  left: 0,
                  right: 0,
                  child: Center(
                    child: Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.xs,
                        vertical: AppSpacing.one,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.primaryColor,
                        borderRadius: BorderRadius.circular(
                          AppSpacing.borderRadius,
                        ),
                      ),
                      child: Text(
                        roleLabel,
                        style: TextStyle(
                          fontSize: AppTypography.xxs,
                          color: AppColors.white,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
          SizedBox(height: AppSpacing.xs),
          SizedBox(
            width: AppSpacing.largeButtonSize,
            child: Text(
              name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: AppTypography.xs, color: textColor),
            ),
          ),
        ],
      ),
    );
  }
}

class _AddMemberPlaceholder extends StatelessWidget {
  const _AddMemberPlaceholder({
    super.key,
    required this.borderColor,
    required this.size,
    required this.onTap,
    this.icon = CupertinoIcons.add,
  });

  final Color borderColor;
  final double size;
  final VoidCallback onTap;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: SizedBox(
        width: size,
        height: size,
        child: DecoratedBox(
          decoration: BoxDecoration(
            border: Border.all(color: borderColor, style: BorderStyle.solid),
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          ),
          child: Icon(icon, size: AppSpacing.iconMedium, color: borderColor),
        ),
      ),
    );
  }
}
