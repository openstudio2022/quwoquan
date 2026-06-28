// ignore_for_file: deprecated_member_use
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
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

  static const int _memberColumns = 5;

  /// 收起时最多 4 行（5×4 格末格为「添加」）：超过则折叠，仅展示本容量内成员。
  static const int _memberRowsCollapsed = 4;
  static int get _collapsedMemberCapacity =>
      _memberColumns * _memberRowsCollapsed - 1;

  /// 退出群聊：二次确认 → removeMember(self) 走 Remote → 返回会话列表。
  Future<void> _confirmExitGroup() async {
    final confirmed = await showCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(UITextConstants.exitGroupChat),
        content: Text(UITextConstants.exitGroupChatConfirmMessage),
        actions: [
          CupertinoDialogAction(
            child: Text(UITextConstants.cancel),
            onPressed: () => Navigator.pop(dialogContext, false),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            child: Text(UITextConstants.exitGroupChat),
            onPressed: () => Navigator.pop(dialogContext, true),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    final selfId = ref.read(currentUserIdProvider);
    try {
      await ref
          .read(
            conversationMembersProvider(widget.conversationId).notifier,
          )
          .removeMember(selfId);
      if (!mounted) return;
      ref.invalidate(conversationMembersProvider(widget.conversationId));
      ref.invalidate(groupHomeProvider(widget.conversationId));
      AppToast.show(context, UITextConstants.exitGroupChatSuccess);
      context.go(AppRoutePaths.chat);
    } catch (error) {
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
      showCupertinoDialog<void>(
        context: context,
        builder: (_) => CupertinoAlertDialog(
          content: Text(UITextConstants.groupNameAdminOnly),
          actions: [
            CupertinoDialogAction(
              child: Text(UITextConstants.confirm),
              onPressed: () => Navigator.pop(context),
            ),
          ],
        ),
      );
      return;
    }

    showCupertinoDialog<void>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: Text(UITextConstants.editGroupName),
        content: Padding(
          padding: EdgeInsets.only(top: AppSpacing.sm),
          child: CupertinoTextField(
            controller: controller,
            placeholder: UITextConstants.groupNameHint,
            autofocus: true,
            maxLength: 30,
          ),
        ),
        actions: [
          CupertinoDialogAction(
            child: Text(UITextConstants.cancel),
            onPressed: () => Navigator.pop(ctx),
          ),
          CupertinoDialogAction(
            isDefaultAction: true,
            child: Text(UITextConstants.confirm),
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
                    AppToast.show(context, UITextConstants.groupNameUpdated);
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
                    title: '群名称修改未完成',
                    message: resolved.message,
                    secondaryMessage: resolved.secondaryMessage,
                    primaryAction: const UiErrorAction(
                      type: UiErrorActionType.retry,
                      label: UITextConstants.tryAgain,
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
    final privacyShield = membersState.groupSettings.privacyShieldAdminOnly;

    final memberCount = members.isNotEmpty
        ? members.length
        : (groupHome?.memberCount ?? 0);
    final groupTitle = groupHome?.title.trim().isNotEmpty == true
        ? groupHome!.title.trim()
        : UITextConstants.groupNameHint;
    final announcement = groupHome?.announcement.trim() ?? '';

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
      title: '${UITextConstants.chatInfoTitle}($memberCount)',
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
                const Center(child: CupertinoActivityIndicator()),
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
                        final totalCells = visibleMemberCount + 1;
                        final gridGap = AppSpacing.sm;
                        final availableWidth = constraints.maxWidth.isFinite
                            ? constraints.maxWidth
                            : MediaQuery.sizeOf(context).width -
                                  SettingsSemanticConstants
                                          .insetFormListHorizontalPadding *
                                      2;
                        final memberCellWidth =
                            (availableWidth -
                                gridGap * (_memberColumns - 1)) /
                            _memberColumns;
                        final memberLabelHeight =
                            AppTypography.xs *
                            AppTypography.lineHeightCompact;
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
                                  onTap: () => context.push(
                                    AppRoutePaths.chatAddMembers(
                                      id: widget.conversationId,
                                    ),
                                  ),
                                ),
                              );
                            }
                            final m = members[index];
                            final username = m.userId.isNotEmpty
                                ? m.userId
                                : 'user_$index';
                            return _MemberAvatar(
                              name: m.displayName,
                              avatarUrl: m.avatarUrl,
                              textColor: fgPrimary,
                              username: username,
                              role: m.role,
                              onTap: () => context.push(
                                AppRoutePaths.userProfile(username: username),
                                extra: UserProfileRouteExtra(
                                  subAccountId: username,
                                  avatar: m.avatarUrl,
                                  displayName: m.displayName,
                                ),
                              ),
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
                                    ? UITextConstants.collapseMembers
                                    : UITextConstants.moreMembers,
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
                      label: UITextConstants.groupName,
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
                      onTap: _showEditGroupNameDialog,
                    ),
                    SettingsInsetFormSectionDivider(isDark: isDark),
                    SettingsInsetFormRow(
                      isDark: isDark,
                      label: UITextConstants.groupAnnouncement,
                      trailing: Text(
                        announcement.isEmpty
                            ? UITextConstants.groupAnnouncementEmpty
                            : announcement,
                        style: TextStyle(
                          fontSize: AppTypography.base,
                          color: secondaryText,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    if (isAdminOrOwner) ...[
                      SettingsInsetFormSectionDivider(isDark: isDark),
                      SettingsInsetFormRow(
                        isDark: isDark,
                        label: UITextConstants.groupManagement,
                        trailing: Icon(
                          CupertinoIcons.chevron_forward,
                          size: AppSpacing.iconMedium,
                          color: chevronColor,
                        ),
                        onTap: () => context.push(
                          AppRoutePaths.chatManage(id: widget.conversationId),
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
                      label: UITextConstants.muteNotifications,
                      trailing: _buildSettingSwitch(
                        isDark: isDark,
                        value: _mute,
                        onChanged: (v) => setState(() => _mute = v),
                      ),
                    ),
                    SettingsInsetFormSectionDivider(isDark: isDark),
                    SettingsInsetFormRow(
                      isDark: isDark,
                      label: UITextConstants.pinChat,
                      trailing: _buildSettingSwitch(
                        isDark: isDark,
                        value: _pin,
                        onChanged: (v) => setState(() => _pin = v),
                      ),
                    ),
                    SettingsInsetFormSectionDivider(isDark: isDark),
                    SettingsInsetFormRow(
                      isDark: isDark,
                      label: UITextConstants.privacyShield,
                      trailing: _buildSettingSwitch(
                        isDark: isDark,
                        value: privacyShield,
                        onChanged: isAdminOrOwner
                            ? (v) {
                                final cur = ref.read(
                                  conversationMembersProvider(
                                    widget.conversationId,
                                  ),
                                );
                                ref
                                    .read(
                                      conversationMembersProvider(
                                        widget.conversationId,
                                      ).notifier,
                                    )
                                    .updateGroupSettings(
                                      cur.groupSettings.copyWith(
                                        privacyShieldAdminOnly: v,
                                      ),
                                    );
                              }
                            : null,
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
                  label: UITextConstants.exitGroupChat,
                  isDestructive: true,
                  onTap: _confirmExitGroup,
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
  });

  final bool isDark;
  final List<String> enabledCapabilities;

  bool _enabled(String capability) {
    return enabledCapabilities.isEmpty ||
        enabledCapabilities.contains(capability);
  }

  @override
  Widget build(BuildContext context) {
    final items = <_GroupCapabilityItem>[
      _GroupCapabilityItem(
        label: UITextConstants.groupCapabilityAlbum,
        icon: CupertinoIcons.photo,
        enabled: _enabled('album'),
      ),
      _GroupCapabilityItem(
        label: UITextConstants.groupCapabilityFile,
        icon: CupertinoIcons.folder,
        enabled: _enabled('file'),
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
                onPressed: null,
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
  });

  final String label;
  final IconData icon;
  final bool enabled;
}

class _MemberAvatar extends StatelessWidget {
  const _MemberAvatar({
    required this.name,
    required this.avatarUrl,
    required this.textColor,
    required this.username,
    required this.onTap,
    this.role,
  });

  final String name;
  final String avatarUrl;
  final Color textColor;
  final String username;
  final VoidCallback onTap;
  final String? role;

  static final double _settingsAvatarSize = AppSpacing.avatarUserLg;

  @override
  Widget build(BuildContext context) {
    final roleLabel = role == 'owner'
        ? UITextConstants.owner
        : role == 'admin'
        ? UITextConstants.admin
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
    required this.borderColor,
    required this.size,
    required this.onTap,
  });

  final Color borderColor;
  final double size;
  final VoidCallback onTap;

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
          child: Icon(
            CupertinoIcons.add,
            size: AppSpacing.iconMedium,
            color: borderColor,
          ),
        ),
      ),
    );
  }
}
