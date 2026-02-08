import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 粉丝/获赞/关注列表页（1:1 对应 AuthorStatsList.tsx 的 fans/likes/following 列表）
/// 路由：/profile/stats?type=following|fans|likes
class ProfileStatsPage extends ConsumerStatefulWidget {
  const ProfileStatsPage({super.key, this.type = 'fans'});

  final String type;

  static String _title(String type) {
    switch (type) {
      case 'following':
        return UITextConstants.follow;
      case 'fans':
        return UITextConstants.circleFans;
      case 'likes':
        return UITextConstants.circleLikes;
      default:
        return UITextConstants.circleFans;
    }
  }

  @override
  ConsumerState<ProfileStatsPage> createState() => _ProfileStatsPageState();
}

class _ProfileStatsPageState extends ConsumerState<ProfileStatsPage> {
  String get _type => widget.type;
  String _searchQuery = '';

  /// 1:1 AuthorStatsList.tsx mockUsers（粉丝/关注列表用），可修改 isFollowed
  late List<Map<String, dynamic>> _users;

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
  }

  /// 1:1 AuthorStatsList.tsx mockInteractions（获赞列表用）
  static List<Map<String, dynamic>> get _mockLikes => [
        {
          'id': 'i1',
          'userName': '陈一发',
          'userAvatar':
              'https://images.unsplash.com/photo-1630939687530-241d630735df?q=80&w=100',
          'content': '赞了你的作品',
          'targetTitle': '《川西秘境摄影集》',
          'time': '14:20',
        },
        {
          'id': 'i2',
          'userName': '王小明',
          'userAvatar':
              'https://images.unsplash.com/photo-1643816831234-e7cb32194e92?q=80&w=100',
          'content': '赞了你的评论：徕卡镜头确实有种空气感...',
          'targetTitle': '摄影器材交流区',
          'time': '10:05',
        },
      ];

  List<Map<String, dynamic>> get _filteredUsers {
    if (_searchQuery.isEmpty) return _users;
    final q = _searchQuery.toLowerCase();
    return _users.where((u) => (u['name'] as String?)?.toLowerCase().contains(q) == true).toList();
  }

  List<Map<String, dynamic>> get _filteredLikes {
    if (_searchQuery.isEmpty) return _mockLikes;
    final q = _searchQuery.toLowerCase();
    return _mockLikes.where((i) => (i['userName'] as String?)?.toLowerCase().contains(q) == true).toList();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor =
        AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);
    final inputBg =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary);

    return Scaffold(
      backgroundColor: bg,
      appBar: AppBar(
        backgroundColor: bg,
        foregroundColor: fg,
        leading: IconButton(
          icon: const Icon(Icons.close),
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
                hintText: _type == 'likes'
                    ? '搜索获赞记录...'
                    : _type == 'fans'
                        ? '搜索粉丝姓名...'
                        : '搜索关注...',
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
            child: _type == 'likes'
                ? _buildLikesList(fg, fgSecondary, borderColor, bg)
                : _buildUsersList(fg, fgSecondary, borderColor, bg),
          ),
        ],
      ),
    );
  }

  Widget _buildUsersList(
      Color fg, Color fgSecondary, Color borderColor, Color bg) {
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
      separatorBuilder: (_, __) => Divider(height: 1, color: borderColor.withValues(alpha: 0.3)),
      itemBuilder: (context, i) {
        final u = list[i];
        final name = u['name'] as String? ?? '';
        final avatar = u['avatar'] as String? ?? '';
        final worksCount = u['worksCount'] as String? ?? '0';
        final fansCount = u['fansCount'] as String? ?? '0';
        final likesCount = u['likesCount'] as String? ?? '0';
        final isFollowed = u['isFollowed'] as bool? ?? false;
        return InkWell(
          onTap: () {},
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 24,
                  backgroundImage: avatar.isNotEmpty ? NetworkImage(avatar) : null,
                  onBackgroundImageError: (_, __) {},
                  child: avatar.isEmpty ? Icon(Icons.person, color: fgSecondary) : null,
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
                        '$worksCount 作品 · $fansCount 粉丝 · $likesCount 获赞',
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
                const SizedBox(width: 12),
                TextButton(
                  onPressed: () {
                    setState(() {
                      final idx = _users.indexWhere((e) => e['id'] == u['id']);
                      if (idx >= 0) {
                        _users[idx] = Map<String, dynamic>.from(_users[idx])
                          ..['isFollowed'] = !(_users[idx]['isFollowed'] as bool? ?? false);
                      }
                    });
                  },
                  style: TextButton.styleFrom(
                    backgroundColor: isFollowed
                        ? borderColor.withValues(alpha: 0.3)
                        : AppColors.primaryColor.withValues(alpha: 0.12),
                    foregroundColor: isFollowed ? fgSecondary : AppColors.primaryColor,
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    minimumSize: const Size(72, 32),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(20),
                    ),
                  ),
                  child: Text(
                    isFollowed ? UITextConstants.following : UITextConstants.follow,
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

  Widget _buildLikesList(
      Color fg, Color fgSecondary, Color borderColor, Color bg) {
    final list = _filteredLikes;
    if (list.isEmpty) {
      return Center(
        child: Text(
          '暂无获赞记录',
          style: TextStyle(color: fgSecondary, fontSize: 14),
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      itemCount: list.length,
      separatorBuilder: (_, __) => Divider(height: 1, color: borderColor.withValues(alpha: 0.3)),
      itemBuilder: (context, i) {
        final item = list[i];
        final userName = item['userName'] as String? ?? '';
        final userAvatar = item['userAvatar'] as String? ?? '';
        final content = item['content'] as String? ?? '';
        final targetTitle = item['targetTitle'] as String? ?? '';
        final time = item['time'] as String? ?? '';
        return InkWell(
          onTap: () {},
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                CircleAvatar(
                  radius: 24,
                  backgroundImage: userAvatar.isNotEmpty ? NetworkImage(userAvatar) : null,
                  onBackgroundImageError: (_, __) {},
                  child: userAvatar.isEmpty ? Icon(Icons.person, color: fgSecondary) : null,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            userName,
                            style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w800,
                              color: fg,
                            ),
                          ),
                          Text(
                            time,
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w700,
                              color: fgSecondary,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        content,
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: fgSecondary,
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 8),
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: bg,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: borderColor.withValues(alpha: 0.3),
                          ),
                        ),
                        child: Text(
                          targetTitle,
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
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
        );
      },
    );
  }
}
