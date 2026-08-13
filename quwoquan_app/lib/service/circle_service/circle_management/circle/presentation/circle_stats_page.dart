// ignore_for_file: unnecessary_underscores, deprecated_member_use

import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_stats_visit_recorder.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group/application/public/circle_group_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_app/design_system/actions/app_follow_button.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/design_system/search/app_search_field.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_stats_list_view_data.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_stats_row_mapper.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart'
    show currentUserIdProvider;
import 'package:quwoquan_app/runtime/di/media_viewer_interaction_facade.dart';
import 'package:quwoquan_app/runtime/di/user_relationship_state_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 圈子成员/群聊/粉丝/获赞列表页（1:1 对应 AuthorStatsList 的 members/groups/fans/likes 圈子维度）
/// 路由：/circle/:id/stats?type=members|groups|fans|likes
class CircleStatsPage extends ConsumerStatefulWidget {
  const CircleStatsPage({
    super.key,
    required this.circleId,
    required this.recordVisit,
    required this.groupQueries,
    required this.membershipQueries,
    this.type = 'members',
  });

  final String circleId;
  final CircleStatsVisitRecorder recordVisit;
  final CircleGroupQueries groupQueries;
  final CircleMembershipQueries membershipQueries;
  final String type;

  static String _title(String type) {
    switch (type) {
      case 'members':
        return CommunityText.circleMembers;
      case 'groups':
        return CommunityText.circleGroups;
      case 'fans':
        return CommunityText.circleFans;
      case 'likes':
        return CommunityText.circleLikes;
      default:
        return CommunityText.circleMembers;
    }
  }

  static String _searchHint(String type) {
    switch (type) {
      case 'members':
        return CommunityText.searchMembersHint;
      case 'groups':
        return CommunityText.searchGroupsHint;
      case 'fans':
        return CommunityText.searchFansHint;
      case 'likes':
        return CommunityText.searchLikesHint;
      default:
        return CommunityText.searchMembersHint;
    }
  }

  @override
  ConsumerState<CircleStatsPage> createState() => _CircleStatsPageState();
}

class _CircleStatsPageState extends ConsumerState<CircleStatsPage> {
  String get _type => widget.type;
  String _searchQuery = '';
  bool _isLoading = true;
  UiErrorSemantic? _pageErrorSemantic;

  List<CircleStatsMemberRowViewData> _users = [];
  List<CircleStatsGroupRowViewData> _groups = [];
  List<CircleStatsLikeRowViewData> _likes = [];

  UiErrorSemantic _resolvePageErrorSemantic(Object error) {
    return runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
  }

  @override
  void initState() {
    super.initState();
    unawaited(_loadFromRepository());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      unawaited(widget.recordVisit(widget.circleId));
    });
  }

  Future<void> _loadFromRepository() async {
    if (mounted) {
      setState(() {
        _isLoading = true;
        _pageErrorSemantic = null;
      });
    }
    try {
      switch (_type) {
        case 'groups':
          final groups = await widget.groupQueries.list(
            CircleGroupListQuery(circleId: widget.circleId, limit: 100),
          );
          if (!mounted) {
            return;
          }
          setState(() {
            _groups = groups.items
                .map(circleStatsGroupRowFromGroupSlice)
                .toList(growable: false);
            _pageErrorSemantic = null;
            _isLoading = false;
          });
          break;
        case 'likes':
          if (!mounted) {
            return;
          }
          setState(() {
            _likes = const [];
            _pageErrorSemantic = null;
            _isLoading = false;
          });
          break;
        case 'members':
        case 'fans':
        default:
          final roster = await widget.membershipQueries.listMemberships(
            CircleMembershipListQuery(circleId: widget.circleId, limit: 100),
          );
          if (!mounted) {
            return;
          }
          setState(() {
            _users = roster.items
                .map(circleStatsMemberRowFromMembership)
                .toList(growable: false);
            _pageErrorSemantic = null;
            _isLoading = false;
          });
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _users = [];
        _groups = [];
        _likes = [];
        _pageErrorSemantic = _resolvePageErrorSemantic(error);
        _isLoading = false;
      });
    }
  }

  List<CircleStatsMemberRowViewData> get _filteredUsers {
    if (_searchQuery.isEmpty) return _users;
    final q = _searchQuery.toLowerCase();
    return _users.where((u) => u.name.toLowerCase().contains(q)).toList();
  }

  List<CircleStatsGroupRowViewData> get _filteredGroups {
    if (_searchQuery.isEmpty) return _groups;
    final q = _searchQuery.toLowerCase();
    return _groups.where((u) => u.name.toLowerCase().contains(q)).toList();
  }

  List<CircleStatsLikeRowViewData> get _filteredLikes {
    if (_searchQuery.isEmpty) return _likes;
    final q = _searchQuery.toLowerCase();
    return _likes.where((i) => i.userName.toLowerCase().contains(q)).toList();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final cardBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    return AppScaffold(
      backgroundColor: bg,
      navigationBar: AppNavigationBar(
        backgroundColor: cardBg.withValues(alpha: 0.94),
        border: Border(
          bottom: BorderSide(
            color: borderColor.withValues(alpha: 0.25),
            width: AppSpacing.hairline,
          ),
        ),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => context.pop(),
        ),
        middle: Text(
          CircleStatsPage._title(_type),
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      child: Column(
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.containerSm,
              AppSpacing.containerMd,
              AppSpacing.containerSm,
            ),
            child: AppSearchField(
              onChanged: (v) => setState(() => _searchQuery = v),
              placeholder: CircleStatsPage._searchHint(_type),
            ),
          ),
          Expanded(
            child: _isLoading
                ? AppRequestFeedback.section()
                : _pageErrorSemantic != null
                ? AppPageErrorState(
                    semantic: _pageErrorSemantic!,
                    onRecovery: (action) async {
                      if (action.type == UiErrorActionType.retry ||
                          action.type == UiErrorActionType.resubmit) {
                        await _loadFromRepository();
                        return _pageErrorSemantic == null
                            ? UiRecoveryOutcome.recovered
                            : UiRecoveryOutcome.stillBlocked;
                      }
                      return UiRecoveryOutcome.cancelled;
                    },
                  )
                : _type == 'likes'
                ? _buildLikesList(fg, fgSecondary, borderColor, bg)
                : _type == 'groups'
                ? _buildGroupsList(fg, fgSecondary, borderColor)
                : _buildUsersList(fg, fgSecondary, borderColor, bg),
          ),
        ],
      ),
    );
  }

  /// 成员/粉丝行：整行进入用户主页（建联承接：关注/打招呼/私聊由主页既有能力承担）。
  void _openMemberProfile(CircleStatsMemberRowViewData member) {
    final personaId = member.id.trim();
    if (personaId.isEmpty) {
      return;
    }
    context.push(
      AppRoutePaths.userProfile(userHandle: personaId),
      extra: UserProfileRouteExtra(
        personaId: personaId,
        avatarUrl: member.avatarUrl.trim().isEmpty ? null : member.avatarUrl,
        displayName: member.name.trim().isEmpty ? null : member.name,
      ),
    );
  }

  /// 关注真相源是 `userRelationshipStateProvider`，写意图统一走
  /// `syncProfileFollowIntent`（含持久 outbox）；禁止页面级本地假开关。
  void _toggleMemberFollow(CircleStatsMemberRowViewData member) {
    final personaId = member.id.trim();
    if (personaId.isEmpty) {
      return;
    }
    runWhenLoggedIn(ref, context, AuthGateReason.follow, () {
      final wasFollowing = effectiveProfileFollowing(ref, personaId);
      syncProfileFollowIntent(
        ref,
        personaId: personaId,
        previousFollowing: wasFollowing,
        isFollowing: !wasFollowing,
        sourceSurfaceId: AppUiSurfaces.circleStats.id,
      );
    });
  }

  Widget _buildUsersList(
    Color fg,
    Color fgSecondary,
    Color borderColor,
    Color bg,
  ) {
    final list = _filteredUsers;
    if (list.isEmpty) {
      return Center(
        child: Text(
          CommunityText.noData,
          style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
        ),
      );
    }
    final relationshipState = ref.watch(userRelationshipStateProvider);
    return ListView.builder(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        0,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
      ),
      itemCount: list.length,
      itemBuilder: (context, i) {
        final u = list[i];
        final name = u.name;
        final avatar = u.avatarUrl;
        final worksCount = u.worksCountLabel;
        final fansCount = u.fansCountLabel;
        final likesCount = u.likesCountLabel;
        final isFollowing = relationshipState.isFollowing(u.id);
        final isSelf = u.id.trim() == ref.read(currentUserIdProvider).trim();
        return Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.sm),
          child: _buildCard(
            borderColor: borderColor,
            backgroundColor: bg,
            child: CupertinoButton(
              key: ValueKey<String>('circle-stats-member-row-${u.id}'),
              padding: EdgeInsets.all(AppSpacing.containerSm),
              onPressed: () => _openMemberProfile(u),
              child: Row(
                children: [
                  AppCircularAvatar(
                    imageUrl: avatar,
                    size: AppSpacing.lg * 2,
                    backgroundColor: AppColors.iosFill(context),
                    fallback: Icon(CupertinoIcons.person, color: fgSecondary),
                  ),
                  SizedBox(width: AppSpacing.largeBorderRadius),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name,
                          style: TextStyle(
                            fontSize: AppTypography.lg,
                            fontWeight: AppTypography.extraBold,
                            color: fg,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        SizedBox(height: AppSpacing.xs),
                        Text(
                          CommunityText.circleProfileStats(
                            worksCount: worksCount,
                            fansCount: fansCount,
                            likesCount: likesCount,
                          ),
                          style: TextStyle(
                            fontSize: AppTypography.xsPlus,
                            fontWeight: AppTypography.bold,
                            color: fgSecondary,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  SizedBox(width: AppSpacing.largeBorderRadius),
                  if (!isSelf)
                    AppFollowButton(
                      isFollowing: isFollowing,
                      pillKey: ValueKey<String>(
                        'circle-stats-member-follow-${u.id}',
                      ),
                      onPressed: () => _toggleMemberFollow(u),
                    ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildGroupsList(Color fg, Color fgSecondary, Color borderColor) {
    final list = _filteredGroups;
    if (list.isEmpty) {
      return Center(
        child: Text(
          CommunityText.noData,
          style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
        ),
      );
    }
    return ListView.builder(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        0,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
      ),
      itemCount: list.length,
      itemBuilder: (context, i) {
        final g = list[i];
        final name = g.name;
        final count = g.memberCountLabel;
        final conversationId = (g.conversationId ?? '').trim();
        return Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.sm),
          child: _buildCard(
            borderColor: borderColor,
            backgroundColor: AppColors.transparent,
            child: CupertinoButton(
              key: ValueKey<String>('circle-stats-group-row-${g.id}'),
              padding: EdgeInsets.all(AppSpacing.containerSm),
              // 群会话由 Chat 绑定写回；未绑定时不提供假聊天入口。
              onPressed: conversationId.isEmpty
                  ? null
                  : () => context.push(
                      AppRoutePaths.chatDetail(id: conversationId),
                    ),
              child: Row(
                children: [
                  Container(
                    width: AppSpacing.largeButtonSize,
                    height: AppSpacing.largeButtonSize,
                    decoration: BoxDecoration(
                      color: borderColor.withValues(alpha: 0.16),
                      borderRadius: BorderRadius.circular(
                        AppSpacing.largeBorderRadius,
                      ),
                    ),
                    child: Icon(
                      CupertinoIcons.group,
                      color: fgSecondary,
                      size: AppSpacing.iconMedium + AppSpacing.xs,
                    ),
                  ),
                  SizedBox(width: AppSpacing.largeBorderRadius),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name,
                          style: TextStyle(
                            fontSize: AppTypography.lg,
                            fontWeight: AppTypography.extraBold,
                            color: fg,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        SizedBox(height: AppSpacing.xs),
                        Text(
                          CommunityText.circleMemberCount(count),
                          style: TextStyle(
                            fontSize: AppTypography.xsPlus,
                            fontWeight: AppTypography.bold,
                            color: fgSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Icon(
                    CupertinoIcons.chevron_forward,
                    color: fgSecondary,
                    size: AppSpacing.iconMedium,
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildLikesList(
    Color fg,
    Color fgSecondary,
    Color borderColor,
    Color bg,
  ) {
    final list = _filteredLikes;
    if (list.isEmpty) {
      return Center(
        child: Text(
          CommunityText.noLikesRecord,
          style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
        ),
      );
    }
    return ListView.builder(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        0,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
      ),
      itemCount: list.length,
      itemBuilder: (context, i) {
        final item = list[i];
        final userName = item.userName;
        final userAvatar = item.userAvatarUrl;
        final content = item.content;
        final targetTitle = item.targetTitle;
        final time = item.time;
        return Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.sm),
          child: _buildCard(
            borderColor: borderColor,
            backgroundColor: bg,
            child: CupertinoButton(
              padding: EdgeInsets.all(AppSpacing.containerSm),
              onPressed: () {},
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  AppCircularAvatar(
                    imageUrl: userAvatar,
                    size: AppSpacing.lg * 2,
                    backgroundColor: AppColors.iosFill(context),
                    fallback: Icon(CupertinoIcons.person, color: fgSecondary),
                  ),
                  SizedBox(width: AppSpacing.largeBorderRadius),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Expanded(
                              child: Text(
                                userName,
                                style: TextStyle(
                                  fontSize: AppTypography.lg,
                                  fontWeight: AppTypography.extraBold,
                                  color: fg,
                                ),
                              ),
                            ),
                            SizedBox(width: AppSpacing.sm),
                            Text(
                              time,
                              style: TextStyle(
                                fontSize: AppTypography.xs,
                                fontWeight: AppTypography.bold,
                                color: fgSecondary,
                              ),
                            ),
                          ],
                        ),
                        SizedBox(height: AppSpacing.xs),
                        Text(
                          content,
                          style: TextStyle(
                            fontSize: AppTypography.smPlus,
                            fontWeight: AppTypography.semiBold,
                            color: fgSecondary,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        SizedBox(height: AppSpacing.sm),
                        Container(
                          padding: EdgeInsets.all(AppSpacing.largeBorderRadius),
                          decoration: BoxDecoration(
                            color: bg.withValues(alpha: 0.72),
                            borderRadius: BorderRadius.circular(
                              AppSpacing.largeBorderRadius,
                            ),
                            border: Border.all(
                              color: borderColor.withValues(alpha: 0.22),
                            ),
                          ),
                          child: Text(
                            targetTitle,
                            style: TextStyle(
                              fontSize: AppTypography.xsPlus,
                              fontWeight: AppTypography.bold,
                              color: fgSecondary,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildCard({
    required Color borderColor,
    required Color backgroundColor,
    required Widget child,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(color: borderColor.withValues(alpha: 0.12)),
        boxShadow: [
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.05),
            blurRadius: AppSpacing.md,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: child,
    );
  }
}
