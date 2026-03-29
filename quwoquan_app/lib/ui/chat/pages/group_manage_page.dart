import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/conversation_members_provider.dart';

/// 群管理页 — 群主/管理员专属管理入口
class GroupManagePage extends ConsumerStatefulWidget {
  const GroupManagePage({super.key, required this.conversationId});

  final String conversationId;

  @override
  ConsumerState<GroupManagePage> createState() => _GroupManagePageState();
}

class _GroupManagePageState extends ConsumerState<GroupManagePage> {
  bool _qrCodeJoinEnabled = true;
  bool _joinRequiresApproval = false;
  bool _nameEditableByAdminOnly = false;
  String _conversationType = 'group';

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    try {
      final repo = ref.read(chatRepositoryProvider);
      final settings = await repo.getGroupSettings(widget.conversationId);
      if (mounted) {
        setState(() {
          _qrCodeJoinEnabled = settings['qrCodeJoinEnabled'] as bool? ?? true;
          _joinRequiresApproval =
              settings['joinRequiresApproval'] as bool? ?? false;
          _nameEditableByAdminOnly =
              settings['nameEditableByAdminOnly'] as bool? ?? false;
          _conversationType =
              (settings['type'] as String?) ??
              (settings['conversationType'] as String?) ??
              _conversationType;
        });
      }
    } catch (_) {}
  }

  Future<void> _updateSetting(String key, bool value) async {
    try {
      final repo = ref.read(chatRepositoryProvider);
      await repo.updateGroupSettings(widget.conversationId, {key: value});
    } catch (_) {}
  }

  Future<void> _onConfirmDissolve() async {
    try {
      await ref.read(chatRepositoryProvider).dissolveConversation(
            widget.conversationId,
          );
      if (ref.read(chatInboxListEnabledProvider)) {
        await ref.read(chatInboxListProvider.notifier).refresh();
      } else {
        await ref.read(conversationSyncProvider).sync(force: true);
      }
      if (!mounted) {
        return;
      }
      AppToast.show(context, UITextConstants.groupChatDissolvedToast);
      context.go(AppRoutePaths.chat);
    } catch (_) {
      if (!mounted) {
        return;
      }
      AppToast.show(context, UITextConstants.dissolveGroupChatFailedToast);
    }
  }

  void _showDissolveDialog() {
    showCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(UITextConstants.dissolveGroupChat),
        content: Padding(
          padding: EdgeInsets.only(top: AppSpacing.sm),
          child: Text(UITextConstants.dissolveGroupChatConfirmMessage),
        ),
        actions: [
          CupertinoDialogAction(
            child: Text(UITextConstants.cancel),
            onPressed: () => Navigator.pop(dialogContext),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            child: Text(UITextConstants.confirm),
            onPressed: () async {
              Navigator.pop(dialogContext);
              await _onConfirmDissolve();
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
    final isOwner = membersState.isOwner;
    final chevronColor =
        SettingsSemanticConstants.selectionChevronColor(isDark);

    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: UITextConstants.groupManagement,
      onBack: () => context.pop(),
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
              density: SettingsInsetSectionDensity.compact,
              child: Column(
                children: [
                  SettingsInsetFormRow(
                    isDark: isDark,
                    label: UITextConstants.qrCodeJoin,
                    trailing: CupertinoSwitch(
                      value: _qrCodeJoinEnabled,
                      onChanged: (v) {
                        setState(() => _qrCodeJoinEnabled = v);
                        _updateSetting('qrCodeJoinEnabled', v);
                      },
                      activeTrackColor:
                          SettingsSemanticConstants.switchActiveTrackColor,
                      inactiveTrackColor:
                          SettingsSemanticConstants.switchInactiveTrackColor(
                            isDark,
                          ),
                    ),
                  ),
                  SettingsInsetFormSectionDivider(isDark: isDark),
                  SettingsInsetFormRow(
                    isDark: isDark,
                    label: UITextConstants.joinRequiresApproval,
                    trailing: CupertinoSwitch(
                      value: _joinRequiresApproval,
                      onChanged: (v) {
                        setState(() => _joinRequiresApproval = v);
                        _updateSetting('joinRequiresApproval', v);
                      },
                      activeTrackColor:
                          SettingsSemanticConstants.switchActiveTrackColor,
                      inactiveTrackColor:
                          SettingsSemanticConstants.switchInactiveTrackColor(
                            isDark,
                          ),
                    ),
                  ),
                  SettingsInsetFormSectionDivider(isDark: isDark),
                  SettingsInsetFormRow(
                    isDark: isDark,
                    label: UITextConstants.nameEditableByAdminOnly,
                    trailing: CupertinoSwitch(
                      value: _nameEditableByAdminOnly,
                      onChanged: (v) {
                        setState(() => _nameEditableByAdminOnly = v);
                        _updateSetting('nameEditableByAdminOnly', v);
                      },
                      activeTrackColor:
                          SettingsSemanticConstants.switchActiveTrackColor,
                      inactiveTrackColor:
                          SettingsSemanticConstants.switchInactiveTrackColor(
                            isDark,
                          ),
                    ),
                  ),
                ],
              ),
            ),
            if (isOwner) ...[
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
                      label: UITextConstants.transferOwnership,
                      trailing: Icon(
                        CupertinoIcons.chevron_forward,
                        size: AppSpacing.iconMedium,
                        color: chevronColor,
                      ),
                      onTap: () => context.push(
                        AppRoutePaths.chatTransferOwnership(
                          id: widget.conversationId,
                        ),
                      ),
                    ),
                    SettingsInsetFormSectionDivider(isDark: isDark),
                    SettingsInsetFormRow(
                      isDark: isDark,
                      label: UITextConstants.groupAdmins,
                      trailing: Icon(
                        CupertinoIcons.chevron_forward,
                        size: AppSpacing.iconMedium,
                        color: chevronColor,
                      ),
                      onTap: () => context.push(
                        AppRoutePaths.chatAdmins(id: widget.conversationId),
                      ),
                    ),
                  ],
                ),
              ),
              if (_conversationType != 'circle') ...[
                SizedBox(
                  height:
                      SettingsSemanticConstants.insetFormSectionVerticalGap,
                ),
                SettingsInsetGroupedSection(
                  isDark: isDark,
                  density: SettingsInsetSectionDensity.compact,
                  child: CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: _showDissolveDialog,
                    child: SizedBox(
                      width: double.infinity,
                      height: AppSpacing.buttonHeight,
                      child: Center(
                        child: Text(
                          UITextConstants.dissolveGroupChat,
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
            ],
          ],
        ),
      ),
    );
  }
}
