// ignore_for_file: unnecessary_underscores, deprecated_member_use

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

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

  late List<Map<String, dynamic>> _users;
  late List<Map<String, dynamic>> _groups;
  static List<Map<String, dynamic>> get _mockLikes => [
    {
      'id': 'i1',
      'userName': '陈一发',
      'userAvatar':
          'https://images.unsplash.com/photo-1630939687530-241d630735df?q=80&w=100',
      'content': '赞了圈内作品',
      'targetTitle': '《川西秘境摄影集》',
      'time': '14:20',
    },
    {
      'id': 'i2',
      'userName': '王小明',
      'userAvatar':
          'https://images.unsplash.com/photo-1643816831234-e7cb32194e92?q=80&w=100',
      'content': '赞了圈内评论',
      'targetTitle': '摄影器材交流区',
      'time': '10:05',
    },
  ];

  @override
  void initState() {
    super.initState();
    _users = [
      {
        'id': 'u1',
        'name': '陈一发',
        'avatar':
            'https://images.unsplash.com/photo-1630939687530-241d630735df?q=80&w=100',
        'worksCount': '0',
        'fansCount': '230',
        'likesCount': '1.2k',
        'isFollowed': false,
      },
      {
        'id': 'u2',
        'name': '周杰伦',
        'avatar':
            'https://images.unsplash.com/photo-1603987248955-9c142c5ae89b?q=80&w=100',
        'worksCount': '0',
        'fansCount': '15.8M',
        'likesCount': '99M',
        'isFollowed': true,
      },
      {
        'id': 'u3',
        'name': '李青云',
        'avatar':
            'https://images.unsplash.com/photo-1603110502322-93cd2173d19a?q=80&w=100',
        'worksCount': '128',
        'fansCount': '45k',
        'likesCount': '128k',
        'isFollowed': true,
      },
    ];
    _groups = [
      {'id': 'g1', 'name': '摄影日常交流群', 'memberCount': '128'},
      {'id': 'g2', 'name': '器材二手交易', 'memberCount': '56'},
      {'id': 'g3', 'name': '线下活动报名', 'memberCount': '89'},
    ];
  }

  List<Map<String, dynamic>> get _filteredUsers {
    if (_searchQuery.isEmpty) return _users;
    final q = _searchQuery.toLowerCase();
    return _users
        .where((u) => (u['name'] as String?)?.toLowerCase().contains(q) == true)
        .toList();
  }

  List<Map<String, dynamic>> get _filteredGroups {
    if (_searchQuery.isEmpty) return _groups;
    final q = _searchQuery.toLowerCase();
    return _groups
        .where((u) => (u['name'] as String?)?.toLowerCase().contains(q) == true)
        .toList();
  }

  List<Map<String, dynamic>> get _filteredLikes {
    if (_searchQuery.isEmpty) return _mockLikes;
    final q = _searchQuery.toLowerCase();
    return _mockLikes
        .where(
          (i) => (i['userName'] as String?)?.toLowerCase().contains(q) == true,
        )
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
    final inputBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundTertiary,
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
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          child: const Icon(CupertinoIcons.back),
          onPressed: () => context.pop(),
        ),
        middle: Text(
          CircleStatsPage._title(_type),
          style: TextStyle(
            color: fg,
            fontSize: AppTypography.xl,
            fontWeight: AppTypography.bold,
          ),
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
            child: Container(
              padding: EdgeInsets.all(AppSpacing.containerSm),
              decoration: BoxDecoration(
                color: cardBg,
                borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
                border: Border.all(color: borderColor.withValues(alpha: 0.12)),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: isDark ? 0.14 : 0.05),
                    blurRadius: AppSpacing.md,
                    offset: const Offset(0, 8),
                  ),
                ],
              ),
              child: CupertinoSearchTextField(
                onChanged: (v) => setState(() => _searchQuery = v),
                placeholder: CircleStatsPage._searchHint(_type),
                placeholderStyle: TextStyle(
                  color: fgSecondary,
                  fontSize: AppTypography.base,
                ),
                prefixIcon: Icon(
                  CupertinoIcons.search,
                  size: AppSpacing.iconSmall + AppSpacing.xs,
                  color: fgSecondary,
                ),
                backgroundColor: inputBg,
                borderRadius: BorderRadius.circular(
                  AppSpacing.circularBorderRadius,
                ),
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.md,
                  vertical: AppSpacing.sm,
                ),
                style: TextStyle(color: fg, fontSize: AppTypography.base),
              ),
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
        final name = u['name'] as String? ?? '';
        final avatar = u['avatar'] as String? ?? '';
        final worksCount = u['worksCount'] as String? ?? '0';
        final fansCount = u['fansCount'] as String? ?? '0';
        final likesCount = u['likesCount'] as String? ?? '0';
        final isFollowed = u['isFollowed'] as bool? ?? false;
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
                        final idx = _users.indexWhere((e) => e['id'] == u['id']);
                        if (idx >= 0) {
                          final prev = _users[idx];
                          final cur = prev['isFollowed'] as bool? ?? false;
                          final updated = Map<String, dynamic>.from(prev);
                          updated['isFollowed'] = !cur;
                          _users[idx] = updated;
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
        final name = g['name'] as String? ?? '';
        final count = g['memberCount'] as String? ?? '0';
        return Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.sm),
          child: _buildCard(
            borderColor: borderColor,
            backgroundColor: Colors.transparent,
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
        final userName = item['userName'] as String? ?? '';
        final userAvatar = item['userAvatar'] as String? ?? '';
        final content = item['content'] as String? ?? '';
        final targetTitle = item['targetTitle'] as String? ?? '';
        final time = item['time'] as String? ?? '';
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
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: AppSpacing.md,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: child,
    );
  }
}
