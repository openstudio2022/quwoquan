// ignore_for_file: unnecessary_import, unnecessary_underscores, curly_braces_in_flow_control_structures, unused_catch_stack, deprecated_member_use
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 圈子/关注/粉丝列表页。根据 type 调用 Repository 获取数据，移除硬编码。
/// 路由：/profile/stats?type=circles|following|fans&userId=...
class ProfileStatsPage extends ConsumerStatefulWidget {
  const ProfileStatsPage({
    super.key,
    this.type = 'fans',
    this.userId = '',
  });

  final String type;
  final String userId;

  static String _title(String type) {
    switch (type) {
      case 'circles':
        return UITextConstants.contactsTabCircles;
      case 'following':
        return UITextConstants.follow;
      case 'fans':
        return UITextConstants.circleFans;
      default:
        return UITextConstants.circleFans;
    }
  }

  @override
  ConsumerState<ProfileStatsPage> createState() => _ProfileStatsPageState();
}

class _ProfileStatsPageState extends ConsumerState<ProfileStatsPage> {
  String get _type => widget.type;
  String get _userId => widget.userId;
  String _searchQuery = '';

  List<Map<String, dynamic>>? _circles;
  List<Map<String, dynamic>>? _users;
  bool _loading = true;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant ProfileStatsPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.type != widget.type || oldWidget.userId != widget.userId) {
      _load();
    }
  }

  Future<void> _load() async {
    if (_userId.isEmpty) {
      setState(() {
        _circles = [];
        _users = [];
        _loading = false;
      });
      return;
    }
    setState(() => _loading = true);
    final repo = ref.read(userProfileRepositoryProvider);
    try {
      if (_type == 'circles') {
        final list = await repo.listUserCircles(_userId);
        if (mounted) setState(() {
          _circles = list;
          _loading = false;
          _error = null;
        });
      } else {
        final list = _type == 'following'
            ? await repo.listFollowing(_userId)
            : await repo.listFollowers(_userId);
        if (mounted) setState(() {
          _users = list;
          _loading = false;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() {
        _circles = null;
        _users = null;
        _loading = false;
        _error = e;
      });
    }
  }

  List<Map<String, dynamic>> get _filteredCircles {
    final list = _circles ?? [];
    if (_searchQuery.isEmpty) return list;
    final q = _searchQuery.toLowerCase();
    return list
        .where((c) =>
            (c['name'] as String?)?.toLowerCase().contains(q) == true)
        .toList();
  }

  List<Map<String, dynamic>> get _filteredUsers {
    final list = _users ?? [];
    if (_searchQuery.isEmpty) return list;
    final q = _searchQuery.toLowerCase();
    return list
        .where((u) =>
            (u['nickname'] as String?)?.toLowerCase().contains(q) == true)
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bg =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fg =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor =
        AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);
    final inputBg =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary);

    String searchHint;
    switch (_type) {
      case 'circles':
        searchHint = UITextConstants.searchCircleHint;
        break;
      case 'following':
        searchHint = '搜索关注';
        break;
      case 'fans':
        searchHint = UITextConstants.searchFansHint;
        break;
      default:
        searchHint = UITextConstants.searchFansHint;
    }

    return AppScaffold(
      backgroundColor: bg,
      navigationBar: AppNavigationBar(
        backgroundColor: bg,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          child: const Icon(CupertinoIcons.back),
          onPressed: () => context.pop(),
        ),
        middle: Text(
          ProfileStatsPage._title(_type),
          style: TextStyle(
            color: fg,
            fontSize: AppTypography.xl,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      child: Column(
        children: [
          Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.intraGroupLg,
            ),
            child: CupertinoSearchTextField(
              onChanged: (v) => setState(() => _searchQuery = v),
              placeholder: searchHint,
              placeholderStyle: TextStyle(
                color: fgSecondary,
                fontSize: AppTypography.base,
              ),
              style: TextStyle(color: fg, fontSize: AppTypography.base),
              backgroundColor: inputBg,
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              prefixIcon: Icon(
                CupertinoIcons.search,
                size: 20,
                color: fgSecondary,
              ),
            ),
          ),
          Expanded(
            child: _loading
                ? Center(
                    child: CupertinoActivityIndicator(),
                  )
                : _error != null
                    ? Center(
                        child: Text(
                          '加载失败',
                          style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
                        ),
                      )
                    : _type == 'circles'
                        ? _buildCirclesList(
                            fg, fgSecondary, borderColor, bg)
                        : _buildUsersList(
                            fg, fgSecondary, borderColor, bg),
          ),
        ],
      ),
    );
  }

  Widget _buildCirclesList(
    Color fg, Color fgSecondary, Color borderColor, Color bg,
  ) {
    final list = _filteredCircles;
    if (list.isEmpty) {
      return Center(
        child: Text(
          UITextConstants.noData,
          style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      itemCount: list.length,
      separatorBuilder: (_, __) => Divider(
        height: AppSpacing.one,
        color: borderColor.withValues(alpha: 0.3),
      ),
      itemBuilder: (context, i) {
        final c = list[i];
        final id = c['id'] as String? ?? '';
        final name = c['name'] as String? ?? '';
        final coverUrl = c['coverUrl'] as String? ?? '';
        final postCount = c['postCount'] as int? ?? 0;
        return CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            if (id.isNotEmpty) {
              context.push(AppRoutePaths.circleDetail(id: id));
            }
          },
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 24,
                  backgroundImage:
                      coverUrl.isNotEmpty ? NetworkImage(coverUrl) : null,
                  onBackgroundImageError: (_, __) {},
                  child: coverUrl.isEmpty
                      ? Icon(CupertinoIcons.group, color: fgSecondary)
                      : null,
                ),
                const SizedBox(width: AppSpacing.intraGroupLg),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name,
                        style: TextStyle(
                          fontSize: AppTypography.lg,
                          fontWeight: FontWeight.w800,
                          color: fg,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: AppSpacing.intraGroupXs),
                      Text(
                        '$postCount 创作',
                        style: TextStyle(
                          fontSize: AppTypography.xsPlus,
                          fontWeight: FontWeight.w700,
                          color: fgSecondary,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildUsersList(
    Color fg, Color fgSecondary, Color borderColor, Color bg,
  ) {
    final list = _filteredUsers;
    if (list.isEmpty) {
      return Center(
        child: Text(
          '暂无数据',
          style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      itemCount: list.length,
      separatorBuilder: (_, __) => Divider(
        height: AppSpacing.one,
        color: borderColor.withValues(alpha: 0.3),
      ),
      itemBuilder: (context, i) {
        final u = list[i];
        final userId = u['userId'] as String? ?? '';
        final nickname = u['nickname'] as String? ?? '';
        final avatarUrl = u['avatarUrl'] as String? ?? '';
        final isFollowing = u['isFollowing'] as bool? ?? false;
        return CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            if (userId.isNotEmpty) {
              context.push(
                AppRoutePaths.userProfile(username: userId),
                extra: UserProfileRouteExtra(
                  avatar: avatarUrl.isNotEmpty ? avatarUrl : null,
                  displayName: nickname.isNotEmpty ? nickname : null,
                ),
              );
            }
          },
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 24,
                  backgroundImage:
                      avatarUrl.isNotEmpty ? NetworkImage(avatarUrl) : null,
                  onBackgroundImageError: (_, __) {},
                  child: avatarUrl.isEmpty
                      ? Icon(CupertinoIcons.person, color: fgSecondary)
                      : null,
                ),
                const SizedBox(width: AppSpacing.intraGroupLg),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        nickname,
                        style: TextStyle(
                          fontSize: AppTypography.lg,
                          fontWeight: FontWeight.w800,
                          color: fg,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: AppSpacing.intraGroupLg),
                CupertinoButton(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 8,
                  ),
                  color: isFollowing
                      ? borderColor.withValues(alpha: 0.3)
                      : AppColors.primaryColor.withValues(alpha: 0.12),
                  minimumSize: const Size(72, 32),
                  borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                  onPressed: () {},
                  child: Text(
                    isFollowing
                        ? UITextConstants.following
                        : UITextConstants.follow,
                    style: TextStyle(
                      fontSize: AppTypography.xsPlus,
                      fontWeight: FontWeight.w800,
                      color: isFollowing ? fgSecondary : AppColors.primaryColor,
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
