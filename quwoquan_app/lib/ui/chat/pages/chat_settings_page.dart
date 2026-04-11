// ignore_for_file: deprecated_member_use
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/conversation_members_provider.dart';

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
  String _groupName = '';

  static const int _memberColumns = 5;

  /// 收起时最多 4 行（5×4 格末格为「添加」）：超过则折叠，仅展示本容量内成员。
  static const int _memberRowsCollapsed = 4;
  static int get _collapsedMemberCapacity =>
      _memberColumns * _memberRowsCollapsed - 1;

  @override
  void initState() {
    super.initState();
    _loadConversation();
  }

  Future<void> _loadConversation() async {
    try {
      final repo = ref.read(chatRepositoryProvider);
      final conv = await repo.getConversation(widget.conversationId);
      if (mounted) {
        setState(() {
          _groupName = conv.title ?? '';
        });
      }
    } catch (_) {}
  }

  void _showEditGroupNameDialog() {
    final controller = TextEditingController(text: _groupName);
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
              if (newName.isNotEmpty && newName != _groupName) {
                try {
                  await ref
                      .read(
                        conversationMembersProvider(
                          widget.conversationId,
                        ).notifier,
                      )
                      .updateGroupDisplayTitle(newName);
                  if (mounted) {
                    setState(() => _groupName = newName);
                    AppToast.show(context, UITextConstants.groupNameUpdated);
                  }
                } catch (_) {}
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
    final membersState = ref.watch(
      conversationMembersProvider(widget.conversationId),
    );
    final members = membersState.members;
    final isAdminOrOwner = membersState.isAdminOrOwner;
    final privacyShield =
        membersState.groupSettings.privacyShieldAdminOnly;

    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    final memberCount = members.length;
    final memberGridOverflow = memberCount > _collapsedMemberCapacity;
    final visibleMemberCount = !memberGridOverflow || _membersExpanded
        ? memberCount
        : _collapsedMemberCapacity;

    final secondaryText = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final chevronColor =
        SettingsSemanticConstants.selectionChevronColor(isDark);
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: '${UITextConstants.chatInfoTitle}($memberCount)',
      onBack: () => context.pop(),
      trailing: memberCount > 5
          ? GlobalTopBarIconButton(
              icon: CupertinoIcons.search,
              onTap: () => context.push(
                AppRoutePaths.chatMemberSearch(id: widget.conversationId),
              ),
            )
          : null,
      body: SizedBox.expand(
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.only(
            left: SettingsSemanticConstants.insetFormListHorizontalPadding,
            right: SettingsSemanticConstants.insetFormListHorizontalPadding,
            top: AppSpacing.intraGroupSm,
            bottom: AppSpacing.xl + MediaQuery.paddingOf(context).bottom,
          ),
          children: [
            SettingsInsetGroupedSection(
              isDark: isDark,
              density: SettingsInsetSectionDensity.standard,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  LayoutBuilder(
                    builder: (context, constraints) {
                      final totalCells = visibleMemberCount + 1;
                      return GridView.builder(
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: _memberColumns,
                          childAspectRatio: 0.85,
                          crossAxisSpacing: AppSpacing.sm,
                          mainAxisSpacing: AppSpacing.sm,
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
                          final username =
                              m.userId.isNotEmpty ? m.userId : 'user_$index';
                          return _MemberAvatar(
                            name: m.displayName,
                            avatarUrl: m.avatarUrl,
                            textColor: fgPrimary,
                            username: username,
                            role: m.role,
                            onTap: () => context.push(
                              AppRoutePaths.userProfile(username: username),
                              extra: UserProfileRouteExtra(
                                profileSubjectId: username,
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
                                  ? Icons.keyboard_arrow_up
                                  : Icons.keyboard_arrow_down,
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
                            _groupName.isEmpty
                                ? UITextConstants.groupNameHint
                                : _groupName,
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
                    label: UITextConstants.qrCode,
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.qr_code_2,
                          size: AppSpacing.iconMedium,
                          color: fgPrimary,
                        ),
                        SizedBox(width: AppSpacing.containerSm),
                        Icon(
                          CupertinoIcons.chevron_forward,
                          size: AppSpacing.iconMedium,
                          color: chevronColor,
                        ),
                      ],
                    ),
                    onTap: () {},
                  ),
                  SettingsInsetFormSectionDivider(isDark: isDark),
                  if (isAdminOrOwner) ...[
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
                    SettingsInsetFormSectionDivider(isDark: isDark),
                  ],
                  SettingsInsetFormRow(
                    isDark: isDark,
                    label: UITextConstants.groupAnnouncement,
                    trailing: Icon(
                      CupertinoIcons.chevron_forward,
                      size: AppSpacing.iconMedium,
                      color: chevronColor,
                    ),
                    onTap: () {},
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
              child: Column(
                children: [
                  SettingsInsetFormRow(
                    isDark: isDark,
                    label: UITextConstants.setChatBackground,
                    trailing: Icon(
                      CupertinoIcons.chevron_forward,
                      size: AppSpacing.iconMedium,
                      color: chevronColor,
                    ),
                    onTap: () {},
                  ),
                  SettingsInsetFormSectionDivider(isDark: isDark),
                  SettingsInsetFormRow(
                    isDark: isDark,
                    label: UITextConstants.clearChatHistory,
                    trailing: Icon(
                      CupertinoIcons.chevron_forward,
                      size: AppSpacing.iconMedium,
                      color: chevronColor,
                    ),
                    onTap: () {},
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
              child: CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: () {
                  AppToast.show(
                    context,
                    '${UITextConstants.exitGroupChat}（开发中）',
                  );
                },
                child: SizedBox(
                  width: double.infinity,
                  height: AppSpacing.buttonHeight,
                  child: Center(
                    child: Text(
                      UITextConstants.exitGroupChat,
                      style: TextStyle(
                        fontSize: AppTypography.lg,
                        fontWeight: AppTypography.medium,
                        color: SettingsSemanticConstants.exitActionColor(
                          isDark,
                        ),
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
  /// 与 [_MemberAvatar] 中 [RoundedSquareAvatar] 边长一致。
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
            Icons.add,
            size: AppSpacing.iconMedium,
            color: borderColor,
          ),
        ),
      ),
    );
  }
}

