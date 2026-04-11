// ignore_for_file: unnecessary_underscores, deprecated_member_use

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/models/circle_stats_list_view_data.dart';
import 'package:quwoquan_app/ui/circle/services/circle_stats_row_wire.dart';

/// 圈子成员/群聊/粉丝/获赞列表页（1:1 对应 AuthorStatsList 的 members/groups/fans/likes 圈子维度）
/// 路由：/circle/:id/stats?type=members|groups|fans|likes
class CircleStatsPage extends ConsumerStatefulWidget {
  const CircleStatsPage({
    super.key,
    required this.circleId,
    this.type = 'members',
  });

  final String circleId;
  final String type;

  static String _title(String type) {
    switch (type) {
      case 'members':
        return UITextConstants.circleMembers;
      case 'groups':
        return UITextConstants.circleGroups;
      case 'fans':
        return UITextConstants.circleFans;
      case 'likes':
        return UITextConstants.circleLikes;
      default:
        return UITextConstants.circleMembers;
    }
  }

  static String _searchHint(String type) {
    switch (type) {
      case 'members':
        return UITextConstants.searchMembersHint;
      case 'groups':
        return UITextConstants.searchGroupsHint;
      case 'fans':
        return UITextConstants.searchFansHint;
      case 'likes':
        return UITextConstants.searchLikesHint;
      default:
        return UITextConstants.searchMembersHint;
    }
  }

  @override
  ConsumerState<CircleStatsPage> createState() => _CircleStatsPageState();
}

class _CircleStatsPageState extends ConsumerState<CircleStatsPage> {
  String get _type => widget.type;
  String _searchQuery = '';

  List<CircleStatsMemberRowViewData> _users = [];
  List<CircleStatsGroupRowViewData> _groups = [];
  List<CircleStatsLikeRowViewData> _likes = [];

  @override
  void initState() {
    super.initState();
    unawaited(_loadFromRepository());
  }

  Future<void> _loadFromRepository() async {
    final repo = ref.read(circleRepositoryProvider);
    try {
      switch (_type) {
        case 'groups':
          final groups = await repo.listCircleGroups(widget.circleId, limit: 200);
          if (!mounted) {
            return;
          }
          setState(() {
            _groups = groups
                .map(circleStatsGroupRowFromGroupDto)
                .toList(growable: false);
          });
          break;
        case 'likes':
          if (!mounted) {
            return;
          }
          setState(() => _likes = const []);
          break;
        case 'members':
        case 'fans':
        default:
          final roster = await repo.listMembers(widget.circleId, limit: 200);
          if (!mounted) {
            return;
          }
          setState(() {
            _users = roster.map(circleStatsMemberRowFromRosterItem).toList(
                  growable: false,
                );
          });
      }
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _users = [];
        _groups = [];
        _likes = [];
      });
    }
  }

  List<CircleStatsMemberRowViewData> get _filteredUsers {
    if (_searchQuery.isEmpty) return _users;
    final q = _searchQuery.toLowerCase();
    return _users
        .where((u) => u.name.toLowerCase().contains(q))
        .toList();
  }

  List<CircleStatsGroupRowViewData> get _filteredGroups {
    if (_searchQuery.isEmpty) return _groups;
    final q = _searchQuery.toLowerCase();
    return _groups
        .where((u) => u.name.toLowerCase().contains(q))
        .toList();
  }

  List<CircleStatsLikeRowViewData> get _filteredLikes {
    if (_searchQuery.isEmpty) return _likes;
    final q = _searchQuery.toLowerCase();
    return _likes
        .where((i) => i.userName.toLowerCase().contains(q))
        .toList();
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
            child: _type == 'likes'
                ? _buildLikesList(fg, fgSecondary, borderColor, bg)
                : _type == 'groups'
                ? _buildGroupsList(fg, fgSecondary, borderColor)
                : _buildUsersList(fg, fgSecondary, borderColor, bg),
          ),
        ],
      ),
    );
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
          UITextConstants.noData,
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
        final u = list[i];
        final name = u.name;
        final avatar = u.avatarUrl;
        final worksCount = u.worksCountLabel;
        final fansCount = u.fansCountLabel;
        final likesCount = u.likesCountLabel;
        final isFollowed = u.isFollowed;
        return Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.sm),
          child: _buildCard(
            borderColor: borderColor,
            backgroundColor: bg,
            child: CupertinoButton(
              padding: EdgeInsets.all(AppSpacing.containerSm),
              onPressed: () {},
              child: Row(
                children: [
                  CircleAvatar(
                    radius: AppSpacing.lg,
                    backgroundImage: avatar.isNotEmpty
                        ? NetworkImage(avatar)
                        : null,
                    onBackgroundImageError: (_, __) {},
                    child: avatar.isEmpty
                        ? Icon(CupertinoIcons.person, color: fgSecondary)
                        : null,
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
                          '$worksCount 作品 · $fansCount 粉丝 · $likesCount 获赞',
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
                  CupertinoButton(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.md,
                      vertical: AppSpacing.sm,
                    ),
                    color: isFollowed
                        ? borderColor.withValues(alpha: 0.18)
                        : AppColors.primaryColor.withValues(alpha: 0.12),
                    minimumSize: Size(
                      AppSpacing.largeButtonSize + AppSpacing.lg,
                      AppSpacing.xl,
                    ),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.circularBorderRadius,
                    ),
                    onPressed: () {
                      setState(() {
                        final idx = _users.indexWhere((e) => e.id == u.id);
                        if (idx >= 0) {
                          final row = _users[idx];
                          row.isFollowed = !row.isFollowed;
                        }
                      });
                    },
                    child: Text(
                      isFollowed
                          ? UITextConstants.following
                          : UITextConstants.follow,
                      style: TextStyle(
                        fontSize: AppTypography.xsPlus,
                        fontWeight: AppTypography.extraBold,
                        color: isFollowed
                            ? fgSecondary
                            : AppColors.primaryColor,
                      ),
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

  Widget _buildGroupsList(Color fg, Color fgSecondary, Color borderColor) {
    final list = _filteredGroups;
    if (list.isEmpty) {
      return Center(
        child: Text(
          UITextConstants.noData,
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
        return Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.sm),
          child: _buildCard(
            borderColor: borderColor,
            backgroundColor: AppColors.transparent,
            child: CupertinoButton(
              padding: EdgeInsets.all(AppSpacing.containerSm),
              onPressed: () {},
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
                          '$count 人',
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
          UITextConstants.noLikesRecord,
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
                  CircleAvatar(
                    radius: AppSpacing.lg,
                    backgroundImage: userAvatar.isNotEmpty
                        ? NetworkImage(userAvatar)
                        : null,
                    onBackgroundImageError: (_, __) {},
                    child: userAvatar.isEmpty
                        ? Icon(CupertinoIcons.person, color: fgSecondary)
                        : null,
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
