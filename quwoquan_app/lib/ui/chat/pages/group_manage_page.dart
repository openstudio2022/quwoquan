import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/chat/chat/chat_inbox_view/application/chat_inbox_provider.dart';
import 'package:quwoquan_app/chat/chat/conversation/application/conversation_members_provider.dart';

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
      await ref
          .read(chatGroupAdminRepositoryProvider)
          .dissolveConversation(widget.conversationId);
      await ref.read(chatInboxListProvider.notifier).refresh();
      if (!mounted) {
        return;
      }
      AppToast.show(context, ChatText.groupChatDissolvedToast);
      context.go(AppRoutePaths.chat);
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
        title: ChatText.dissolveIncompleteTitle,
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
            await _onConfirmDissolve();
          }
        },
      );
    }
  }

  void _showDissolveDialog() {
    showAppCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(ChatText.dissolveGroupChat),
        content: Padding(
          padding: EdgeInsets.only(top: AppSpacing.sm),
          child: Text(ChatText.dissolveGroupChatConfirmMessage),
        ),
        actions: [
          CupertinoDialogAction(
            child: Text(FoundationText.cancel),
            onPressed: () => Navigator.pop(dialogContext),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            child: Text(FoundationText.confirm),
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
    final chevronColor = SettingsSemanticConstants.selectionChevronColor(
      isDark,
    );
    final loadError = membersState.error;
    final circleGroupID = membersState.groupSettings.circleGroupId.trim();
    final circleID = membersState.groupSettings.circleId.trim();

    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: ChatText.groupManagement,
      onBack: () => context.pop(),
      body: loadError != null && membersState.members.isEmpty
          ? AppPageErrorState(
              semantic: runtimeErrorSemantic(
                context,
                error: loadError,
                category: UiErrorCategory.pageLoad,
                scope: UiErrorScope.page,
              ),
              onRecovery: (action) async {
                if (action.type == UiErrorActionType.retry ||
                    action.type == UiErrorActionType.resubmit) {
                  await notifier.load();
                  return ref
                              .read(
                                conversationMembersProvider(
                                  widget.conversationId,
                                ),
                              )
                              .error ==
                          null
                      ? UiRecoveryOutcome.recovered
                      : UiRecoveryOutcome.stillBlocked;
                }
                return UiRecoveryOutcome.cancelled;
              },
            )
          : circleGroupID.isNotEmpty
          ? ListView(
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
                  child: SettingsInsetFormRow(
                    isDark: isDark,
                    label: ChatText.circleGroupManagedNotice,
                    trailing: Icon(
                      CupertinoIcons.chevron_forward,
                      size: AppSpacing.iconMedium,
                      color: chevronColor,
                    ),
                    onTap: circleID.isEmpty
                        ? null
                        : () => context.go(
                            AppRoutePaths.circleDetail(id: circleID),
                          ),
                  ),
                ),
                SizedBox(
                  height: SettingsSemanticConstants.insetFormSectionVerticalGap,
                ),
                Text(
                  ChatText.openCircleGroupManagement,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    color: SettingsSemanticConstants.labelColor(isDark),
                  ),
                ),
              ],
            )
          : SizedBox.expand(
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: EdgeInsets.only(
                  left:
                      SettingsSemanticConstants.insetFormListHorizontalPadding,
                  right:
                      SettingsSemanticConstants.insetFormListHorizontalPadding,
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
                          label: ChatText.nameEditableByAdminOnly,
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
                            activeTrackColor: SettingsSemanticConstants
                                .switchActiveTrackColor,
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
                      height:
                          SettingsSemanticConstants.insetFormSectionVerticalGap,
                    ),
                    SettingsInsetGroupedSection(
                      isDark: isDark,
                      density: SettingsInsetSectionDensity.compact,
                      child: Column(
                        children: [
                          SettingsInsetFormRow(
                            isDark: isDark,
                            label: ChatText.transferOwnership,
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
                            label: ChatText.groupAdmins,
                            trailing: Icon(
                              CupertinoIcons.chevron_forward,
                              size: AppSpacing.iconMedium,
                              color: chevronColor,
                            ),
                            onTap: () => context.push(
                              AppRoutePaths.chatAdmins(
                                id: widget.conversationId,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (groupSettings.circleId.isEmpty) ...[
                      SizedBox(
                        height: SettingsSemanticConstants
                            .insetFormSectionVerticalGap,
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
                                ChatText.dissolveGroupChat,
                                style: TextStyle(
                                  fontSize: AppTypography.lg,
                                  fontWeight: AppTypography.medium,
                                  color:
                                      SettingsSemanticConstants.exitActionColor(
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
