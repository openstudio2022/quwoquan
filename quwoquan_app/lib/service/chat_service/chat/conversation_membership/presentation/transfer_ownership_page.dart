import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";
import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/search/search_embedded.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';
import 'package:quwoquan_app/runtime/observability/trackers/chat_interaction_telemetry_tracker.dart';
import 'package:quwoquan_app/runtime/di/conversation_members_provider.dart';
import 'package:uuid/uuid.dart';

/// 群主转让页 — 选择成员后确认弹窗
class TransferOwnershipPage extends ConsumerStatefulWidget {
  const TransferOwnershipPage({
    super.key,
    required this.conversationId,
    required this.telemetryTracker,
  });

  final String conversationId;
  final ChatInteractionTelemetryTracker telemetryTracker;

  @override
  ConsumerState<TransferOwnershipPage> createState() =>
      _TransferOwnershipPageState();
}

class _TransferOwnershipPageState extends ConsumerState<TransferOwnershipPage> {
  String _searchQuery = '';
  bool _submitting = false;
  String? _pendingMemberId;
  String? _pendingIdempotencyKey;
  final TextEditingController _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _onMemberSelected(ConversationMemberListRow member) {
    if (_submitting) return;
    final name = member.displayName;

    showAppCupertinoDialog<void>(
      context: context,
      builder: (_) => CupertinoAlertDialog(
        content: Text(
          '${ChatText.transferOwnershipConfirmPrefix}'
          '$name'
          '${ChatText.transferOwnershipConfirmSuffix}',
        ),
        actions: [
          CupertinoDialogAction(
            child: Text(FoundationText.cancel),
            onPressed: () => Navigator.pop(context),
          ),
          CupertinoDialogAction(
            child: Text(FoundationText.confirm),
            onPressed: () async {
              Navigator.pop(context);
              await _submitTransfer(member);
            },
          ),
        ],
      ),
    );
  }

  Future<void> _submitTransfer(ConversationMemberListRow member) async {
    if (_submitting) return;
    final sameIntent = _pendingMemberId == member.userId;
    final idempotencyKey = sameIntent && _pendingIdempotencyKey != null
        ? _pendingIdempotencyKey!
        : const Uuid().v4();
    setState(() {
      _submitting = true;
      _pendingMemberId = member.userId;
      _pendingIdempotencyKey = idempotencyKey;
    });
    try {
      await ref
          .read(conversationMembersProvider(widget.conversationId).notifier)
          .transferOwnership(member.userId, idempotencyKey: idempotencyKey);
      unawaited(
        widget.telemetryTracker.track(
          action: ChatInteractionAction.groupGovernance,
          outcome: ChatInteractionOutcome.succeeded,
          governanceAction: ChatGovernanceAction.ownershipTransfer,
          pageName: PageNames.chatTransferOwnership,
          surfaceId: AppUiSurfaces.chatTransferOwnership.id,
        ),
      );
      if (mounted) {
        setState(() => _submitting = false);
        context.pop();
      }
    } catch (error) {
      unawaited(
        widget.telemetryTracker.track(
          action: ChatInteractionAction.groupGovernance,
          outcome: ChatInteractionOutcome.failed,
          governanceAction: ChatGovernanceAction.ownershipTransfer,
          pageName: PageNames.chatTransferOwnership,
          surfaceId: AppUiSurfaces.chatTransferOwnership.id,
          error: error,
        ),
      );
      if (!mounted) return;
      setState(() => _submitting = false);
      final resolved = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      final semantic = UiErrorSemantic(
        category: resolved.category,
        scope: resolved.scope,
        title: ChatText.transferOwnershipIncompleteTitle,
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
            await _submitTransfer(member);
          }
        },
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);

    final membersState = ref.watch(
      conversationMembersProvider(widget.conversationId),
    );

    // 排除群主（当前用户）自身
    final candidates = membersState.members
        .where((m) => m.role != 'owner' && !m.isCurrentUser)
        .toList();

    final filtered = filterMemberDtosByQuery(candidates, _searchQuery);

    return SettingsInsetMemberPickerPageScaffold(
      isDark: isDark,
      title: ChatText.selectNewOwner,
      onBack: () => context.pop(),
      body: Column(
        children: [
          EmbeddedMemberSearchBarPlain(
            isDark: isDark,
            controller: _searchController,
            placeholder: ChatText.searchGroupMembers,
            onChanged: (v) => setState(() => _searchQuery = v),
          ),
          Expanded(
            child: membersState.isLoading && membersState.members.isEmpty
                ? AppRequestFeedback.section()
                : !membersState.isOwner
                ? AppPageErrorState(
                    semantic: runtimeErrorSemantic(
                      context,
                      error: StateError(
                        'ownership transfer requires the current owner',
                      ),
                      category: UiErrorCategory.permissionRequired,
                      scope: UiErrorScope.page,
                    ),
                  )
                : membersState.error != null && membersState.members.isEmpty
                ? AppPageErrorState(
                    semantic: runtimeErrorSemantic(
                      context,
                      error: membersState.error!,
                      category: UiErrorCategory.pageLoad,
                      scope: UiErrorScope.page,
                    ),
                    onRecovery: (action) async {
                      if (action.type != UiErrorActionType.retry &&
                          action.type != UiErrorActionType.resubmit) {
                        return UiRecoveryOutcome.cancelled;
                      }
                      return await ref
                              .read(
                                conversationMembersProvider(
                                  widget.conversationId,
                                ).notifier,
                              )
                              .load()
                          ? UiRecoveryOutcome.recovered
                          : UiRecoveryOutcome.stillBlocked;
                    },
                  )
                : ListView(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      0,
                      AppSpacing.containerMd,
                      AppSpacing.containerLg,
                    ),
                    children: [
                      if (membersState.error != null)
                        AppSectionErrorCard(
                          semantic: runtimeErrorSemantic(
                            context,
                            error: membersState.error!,
                            category: UiErrorCategory.sectionLoad,
                            scope: UiErrorScope.section,
                          ),
                          onAction: (action) async {
                            if (action.type != UiErrorActionType.retry &&
                                action.type != UiErrorActionType.resubmit) {
                              return;
                            }
                            await ref
                                .read(
                                  conversationMembersProvider(
                                    widget.conversationId,
                                  ).notifier,
                                )
                                .load();
                          },
                        ),
                      if (filtered.isNotEmpty)
                        InsetGroupedMemberListCard(
                          isDark: isDark,
                          dividerKind: MemberListDividerInsetKind.navigate,
                          tileWidgets: [
                            for (final m in filtered)
                              MemberListNavigateTile(
                                isDark: isDark,
                                member: m,
                                subtitleText: null,
                                onTap: () {
                                  if (!_submitting) {
                                    _onMemberSelected(m);
                                  }
                                },
                              ),
                          ],
                        ),
                      if (filtered.isEmpty)
                        Padding(
                          padding: EdgeInsets.only(top: AppSpacing.xl),
                          child: Center(
                            child: Text(
                              ChatText.noMatchingMembers,
                              style: TextStyle(
                                fontSize: AppTypography.base,
                                color: fgSecondary,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}
