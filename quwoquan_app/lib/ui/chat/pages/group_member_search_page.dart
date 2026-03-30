import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/search/search_embedded.dart';
import 'package:quwoquan_app/core/constants/search_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/conversation_members_provider.dart';

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

  void _openProfile(Map<String, dynamic> m) {
    final username = m['userId'] as String? ?? '';
    if (username.isEmpty) return;
    context.push(
      AppRoutePaths.userProfile(username: username),
      extra: UserProfileRouteExtra(
        profileSubjectId: username,
        avatar: (m['avatarUrl'] as String?) ?? (m['avatar'] as String?),
        displayName: (m['displayName'] as String?) ?? (m['name'] as String?),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final pageBg =
        SearchSemanticConstants.embeddedMemberSearchPageBackground(isDark);
    final membersState = ref.watch(
      conversationMembersProvider(widget.conversationId),
    );
    final members = membersState.members;
    final memberMaps = members.map((e) => e.toMap()).toList();
    final filteredMaps = filterMemberMapsByQuery(memberMaps, _searchQuery);
    final sections = buildGroupedMemberSections(filteredMaps);

    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );

    Widget listContent;
    if (membersState.isLoading) {
      listContent = const Center(child: CupertinoActivityIndicator());
    } else if (filteredMaps.isEmpty) {
      listContent = Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.xl),
          child: Text(
            UITextConstants.noMatchingMembers,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.base,
              color: fgSecondary,
            ),
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
                        subtitleText: (m['nickname'] as String?)?.trim(),
                        onTap: () => _openProfile(m),
                      ),
                  ],
                ),
              ),
            ),
          ],
          SliverToBoxAdapter(
            child: SizedBox(height: AppSpacing.xl + MediaQuery.paddingOf(context).bottom),
          ),
        ],
      );
    }

    return ColoredBox(
      color: pageBg,
      child: EmbeddedMemberSearchPageShell(
        isDark: isDark,
        searchController: _searchController,
        placeholder: UITextConstants.searchGroupMembers,
        onQueryChanged: (v) => setState(() => _searchQuery = v),
        onCancel: () => context.pop(),
        listBody: ColoredBox(
          color: pageBg,
          child: listContent,
        ),
      ),
    );
  }
}
