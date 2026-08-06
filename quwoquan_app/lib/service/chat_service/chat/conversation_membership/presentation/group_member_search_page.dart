import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";
// settings-canonical-shell: search_embedded — 见 scripts/runtime/page/settings_canonical_manifest.yaml 与 page-layout-semantics L3 spec。
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/search/search_embedded.dart';
import 'package:quwoquan_app/design_system/semantics/search_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/di/conversation_members_provider.dart';

/// 聊天信息顶栏进入的群成员嵌入式搜索（端侧过滤）。
class GroupMemberSearchPage extends ConsumerStatefulWidget {
  const GroupMemberSearchPage({super.key, required this.conversationId});

  final String conversationId;

  @override
  ConsumerState<GroupMemberSearchPage> createState() =>
      _GroupMemberSearchPageState();
}

class _GroupMemberSearchPageState extends ConsumerState<GroupMemberSearchPage> {
  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _openProfile(ConversationMemberListRow m) {
    final userHandle = m.userHandle.trim();
    if (userHandle.isEmpty) return;
    context.push(
      AppRoutePaths.userProfile(userHandle: userHandle),
      extra: UserProfileRouteExtra(
        personaId: m.userId.trim().isEmpty ? null : m.userId.trim(),
        avatarUrl: m.avatarUrl,
        displayName: m.displayName,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final pageBg = SearchSemanticConstants.embeddedMemberSearchPageBackground(
      isDark,
    );
    final membersState = ref.watch(
      conversationMembersProvider(widget.conversationId),
    );
    final members = membersState.members;
    final filteredMembers = filterMemberDtosByQuery(members, _searchQuery);
    final sections = buildGroupedMemberDtoSections(filteredMembers);

    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );

    Widget listContent;
    if (membersState.isLoading) {
      listContent = AppRequestFeedback.section();
    } else if (membersState.error case final error?) {
      listContent = AppPageErrorState(
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        ),
        onRecovery: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await ref
                .read(
                  conversationMembersProvider(widget.conversationId).notifier,
                )
                .load();
            return ref
                        .read(
                          conversationMembersProvider(widget.conversationId),
                        )
                        .error ==
                    null
                ? UiRecoveryOutcome.recovered
                : UiRecoveryOutcome.stillBlocked;
          }
          return UiRecoveryOutcome.cancelled;
        },
      );
    } else if (filteredMembers.isEmpty) {
      listContent = Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.xl),
          child: Text(
            ChatText.noMatchingMembers,
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: AppTypography.base, color: fgSecondary),
          ),
        ),
      );
    } else {
      listContent = CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          for (final section in sections) ...[
            SliverToBoxAdapter(
              child: MemberListSectionHeader(
                isDark: isDark,
                title: section.header,
              ),
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding: EdgeInsets.fromLTRB(
                  AppSpacing.containerMd,
                  0,
                  AppSpacing.containerMd,
                  AppSpacing.sm,
                ),
                child: InsetGroupedMemberListCard(
                  isDark: isDark,
                  dividerKind: MemberListDividerInsetKind.navigate,
                  tileWidgets: [
                    for (final m in section.members)
                      MemberListNavigateTile(
                        isDark: isDark,
                        member: m,
                        subtitleText: null,
                        onTap: () => _openProfile(m),
                      ),
                  ],
                ),
              ),
            ),
          ],
          SliverToBoxAdapter(
            child: SizedBox(
              height: AppSpacing.xl + MediaQuery.paddingOf(context).bottom,
            ),
          ),
        ],
      );
    }

    return ColoredBox(
      color: pageBg,
      child: EmbeddedMemberSearchPageShell(
        isDark: isDark,
        searchController: _searchController,
        placeholder: ChatText.searchGroupMembers,
        onQueryChanged: (v) => setState(() => _searchQuery = v),
        onCancel: () => context.pop(),
        listBody: ColoredBox(color: pageBg, child: listContent),
      ),
    );
  }
}
