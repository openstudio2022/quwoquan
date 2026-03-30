import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/search/search_embedded.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
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

    showCupertinoDialog<void>(
      context: context,
      builder: (_) => CupertinoAlertDialog(
        content: Text(
          '${UITextConstants.transferOwnershipConfirmPrefix}'
          '$name'
          '${UITextConstants.transferOwnershipConfirmSuffix}',
        ),
        actions: [
          CupertinoDialogAction(
            child: Text(UITextConstants.cancel),
            onPressed: () => Navigator.pop(context),
          ),
          CupertinoDialogAction(
            child: Text(UITextConstants.confirm),
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
                if (mounted) context.pop();
              } catch (_) {}
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
      title: UITextConstants.selectNewOwner,
      onBack: () => context.pop(),
      body: Column(
        children: [
          EmbeddedMemberSearchBarPlain(
            isDark: isDark,
            controller: _searchController,
            placeholder: UITextConstants.searchGroupMembers,
            onChanged: (v) => setState(() => _searchQuery = v),
          ),
          Expanded(
            child: membersState.isLoading
                ? const Center(child: CupertinoActivityIndicator())
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
                              UITextConstants.noMatchingMembers,
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
