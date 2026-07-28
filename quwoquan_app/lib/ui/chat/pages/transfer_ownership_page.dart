import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/components/search/search_embedded.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/chat_interaction_telemetry_tracker.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/ui/chat/providers/conversation_members_provider.dart';

/// 群主转让页 — 选择成员后确认弹窗
class TransferOwnershipPage extends ConsumerStatefulWidget {
  const TransferOwnershipPage({super.key, required this.conversationId});

  final String conversationId;

  @override
  ConsumerState<TransferOwnershipPage> createState() =>
      _TransferOwnershipPageState();
}

class _TransferOwnershipPageState extends ConsumerState<TransferOwnershipPage> {
  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _onMemberSelected(ChatConversationMemberDto member) {
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
              try {
                await ref
                    .read(
                      conversationMembersProvider(
                        widget.conversationId,
                      ).notifier,
                    )
                    .transferOwnership(member.userId);
                unawaited(
                  ref
                      .read(chatInteractionTelemetryTrackerProvider)
                      .track(
                        action: ChatInteractionAction.groupGovernance,
                        outcome: ChatInteractionOutcome.succeeded,
                        governanceAction:
                            ChatGovernanceAction.ownershipTransfer,
                        pageName: PageNames.chatTransferOwnership,
                        surfaceId: AppUiSurfaces.chatTransferOwnership.id,
                      ),
                );
                if (mounted) context.pop();
              } catch (error) {
                unawaited(
                  ref
                      .read(chatInteractionTelemetryTrackerProvider)
                      .track(
                        action: ChatInteractionAction.groupGovernance,
                        outcome: ChatInteractionOutcome.failed,
                        governanceAction:
                            ChatGovernanceAction.ownershipTransfer,
                        pageName: PageNames.chatTransferOwnership,
                        surfaceId: AppUiSurfaces.chatTransferOwnership.id,
                        error: error,
                      ),
                );
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
                      _onMemberSelected(member);
                    }
                  },
                );
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
            child: membersState.isLoading
                ? AppRequestFeedback.section()
                : ListView(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      0,
                      AppSpacing.containerMd,
                      AppSpacing.containerLg,
                    ),
                    children: [
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
                                onTap: () => _onMemberSelected(m),
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
