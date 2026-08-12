import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/conversation_dissolver.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/conversation_members_provider.dart';
import 'package:uuid/uuid.dart';

/// 群管理页 — 群主/管理员专属管理入口
class GroupManagePage extends ConsumerStatefulWidget {
  const GroupManagePage({
    super.key,
    required this.conversationId,
    required this.conversationDissolver,
  });

  final String conversationId;
  final ConversationDissolver conversationDissolver;

  @override
  ConsumerState<GroupManagePage> createState() => _GroupManagePageState();
}

class _GroupManagePageState extends ConsumerState<GroupManagePage> {
  bool _settingsSubmitting = false;

  Widget _buildLoadErrorCard(BuildContext context, Object error) {
    return AppSectionErrorCard(
      semantic: runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.sectionLoad,
        scope: UiErrorScope.section,
      ),
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await ref
              .read(conversationMembersProvider(widget.conversationId).notifier)
              .load();
        }
      },
    );
  }

  Future<void> _updateGroupSettings(
    bool value, {
    String? idempotencyKey,
  }) async {
    if (_settingsSubmitting) return;
    final key = idempotencyKey ?? const Uuid().v4();
    setState(() {
      _settingsSubmitting = true;
    });
    try {
      final notifier = ref.read(
        conversationMembersProvider(widget.conversationId).notifier,
      );
      final current = ref
          .read(conversationMembersProvider(widget.conversationId))
          .groupSettings;
      await notifier.updateGroupSettings(
        current.copyWith(nameEditableByAdminOnly: value),
        idempotencyKey: key,
      );
      if (mounted) {
        setState(() {
          _settingsSubmitting = false;
        });
      }
    } catch (error) {
      if (!mounted) return;
      setState(() => _settingsSubmitting = false);
      final resolved = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: UiErrorSemantic(
          category: resolved.category,
          scope: resolved.scope,
          title: resolved.title,
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
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _updateGroupSettings(value, idempotencyKey: key);
          }
        },
      );
    }
  }

  Future<void> _onConfirmDissolve() async {
    try {
      await widget.conversationDissolver.dissolveConversation(
        widget.conversationId,
      );
      await ref.read(chatInboxListCommandsProvider).refresh();
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
          : !membersState.isLoading && !membersState.isAdminOrOwner
          ? AppPageErrorState(
              semantic: runtimeErrorSemantic(
                context,
                error: StateError(
                  'group management requires an owner or administrator',
                ),
                category: UiErrorCategory.permissionRequired,
                scope: UiErrorScope.page,
              ),
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
                if (loadError != null) _buildLoadErrorCard(context, loadError),
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
                  if (loadError != null)
                    _buildLoadErrorCard(context, loadError),
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
                            onChanged:
                                membersState.isLoading ||
                                    _settingsSubmitting ||
                                    !membersState.isAdminOrOwner
                                ? null
                                : _updateGroupSettings,
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
