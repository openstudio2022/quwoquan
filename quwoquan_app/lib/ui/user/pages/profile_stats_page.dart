import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
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
    } catch (e, st) {
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

    return Scaffold(
      backgroundColor: bg,
      appBar: AppBar(
        backgroundColor: bg,
        foregroundColor: fg,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.pop(),
        ),
        title: Text(
          ProfileStatsPage._title(_type),
          style: TextStyle(
            color: fg,
            fontSize: 18,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: TextField(
              onChanged: (v) => setState(() => _searchQuery = v),
              decoration: InputDecoration(
                hintText: searchHint,
                hintStyle: TextStyle(color: fgSecondary, fontSize: 14),
                prefixIcon: Icon(Icons.search, size: 20, color: fgSecondary),
                filled: true,
                fillColor: inputBg,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(20),
                  borderSide: BorderSide.none,
                ),
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 12,
                ),
              ),
              style: TextStyle(color: fg, fontSize: 14),
            ),
          ),
          Expanded(
            child: _loading
                ? Center(
                    child: CircularProgressIndicator(
                      color: AppColors.primaryColor,
                    ),
                  )
                : _error != null
                    ? Center(
                        child: Text(
                          '加载失败',
                          style: TextStyle(color: fgSecondary, fontSize: 14),
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
          style: TextStyle(color: fgSecondary, fontSize: 14),
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      itemCount: list.length,
      separatorBuilder: (_, __) => Divider(
        height: 1,
        color: borderColor.withValues(alpha: 0.3),
      ),
      itemBuilder: (context, i) {
        final c = list[i];
        final id = c['id'] as String? ?? '';
        final name = c['name'] as String? ?? '';
        final coverUrl = c['coverUrl'] as String? ?? '';
        final postCount = c['postCount'] as int? ?? 0;
        return InkWell(
          onTap: () {
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
                      ? Icon(Icons.group, color: fgSecondary)
                      : null,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name,
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w800,
                          color: fg,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '$postCount 创作',
                        style: TextStyle(
                          fontSize: 11,
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
          style: TextStyle(color: fgSecondary, fontSize: 14),
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      itemCount: list.length,
      separatorBuilder: (_, __) => Divider(
        height: 1,
        color: borderColor.withValues(alpha: 0.3),
      ),
      itemBuilder: (context, i) {
        final u = list[i];
        final userId = u['userId'] as String? ?? '';
        final nickname = u['nickname'] as String? ?? '';
        final avatarUrl = u['avatarUrl'] as String? ?? '';
        final isFollowing = u['isFollowing'] as bool? ?? false;
        return InkWell(
          onTap: () {
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
                      ? Icon(Icons.person, color: fgSecondary)
                      : null,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        nickname,
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w800,
                          color: fg,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                TextButton(
                  onPressed: () {},
                  style: TextButton.styleFrom(
                    backgroundColor: isFollowing
                        ? borderColor.withValues(alpha: 0.3)
                        : AppColors.primaryColor.withValues(alpha: 0.12),
                    foregroundColor:
                        isFollowing ? fgSecondary : AppColors.primaryColor,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 8,
                    ),
                    minimumSize: const Size(72, 32),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(20),
                    ),
                  ),
                  child: Text(
                    isFollowing
                        ? UITextConstants.following
                        : UITextConstants.follow,
                    style: const TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w800,
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
