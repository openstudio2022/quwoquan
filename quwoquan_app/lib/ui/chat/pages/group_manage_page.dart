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
  Future<void> _onConfirmDissolve() async {
    try {
      await ref.read(chatRepositoryProvider).dissolveConversation(
            widget.conversationId,
          );
      await ref.read(chatInboxListProvider.notifier).refresh();
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
    final groupSettings = membersState.groupSettings;
    final isOwner = membersState.isOwner;
    final notifier = ref.read(
      conversationMembersProvider(widget.conversationId).notifier,
    );
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
                      value: groupSettings.qrCodeJoinEnabled,
                      onChanged: membersState.isLoading
                          ? null
                          : (v) {
                              notifier.updateGroupSettings(
                                groupSettings.copyWith(
                                  qrCodeJoinEnabled: v,
                                ),
                              );
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
                      value: groupSettings.joinRequiresApproval,
                      onChanged: membersState.isLoading
                          ? null
                          : (v) {
                              notifier.updateGroupSettings(
                                groupSettings.copyWith(
                                  joinRequiresApproval: v,
                                ),
                              );
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
                      value: groupSettings.nameEditableByAdminOnly,
                      onChanged: membersState.isLoading
                          ? null
                          : (v) {
                              notifier.updateGroupSettings(
                                groupSettings.copyWith(
                                  nameEditableByAdminOnly: v,
                                ),
                              );
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
              if (groupSettings.conversationType != 'circle') ...[
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
