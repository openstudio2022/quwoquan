import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 发起群聊页（图一：创建新群聊 + 相关同好）
class StartGroupChatPage extends ConsumerStatefulWidget {
  const StartGroupChatPage({
    super.key,
    required this.conversationId,
    required this.onBack,
  });

  final String conversationId;
  final VoidCallback onBack;

  @override
  ConsumerState<StartGroupChatPage> createState() => _StartGroupChatPageState();
}

class _StartGroupChatPageState extends ConsumerState<StartGroupChatPage> {
  final TextEditingController _searchController = TextEditingController();
  final ScrollController _listScrollController = ScrollController();
  final Map<String, bool> _relatedSelected = {};

  static const List<Map<String, String>> _mockGroupChats = [
    {'id': 'g1', 'name': '兴趣小组A', 'count': '9'},
    {'id': 'g2', 'name': '兴趣小组B', 'count': '12'},
    {'id': 'g3', 'name': '兴趣小组C', 'count': '15'},
    {'id': 'g4', 'name': '兴趣小组D', 'count': '5'},
    {'id': 'g5', 'name': '兴趣小组E', 'count': '8'},
    {'id': 'g6', 'name': '兴趣小组F', 'count': '6'},
  ];

  static const List<Map<String, String>> _mockCircles = [
    {'id': 'c1', 'name': '摄影圈', 'count': '20'},
    {'id': 'c2', 'name': '读书会', 'count': '15'},
    {'id': 'c3', 'name': '跑步同好', 'count': '30'},
  ];

  static const List<Map<String, String>> _mockGroupMembers = [
    {
      'name': '用户一',
      'username': 'user1',
      'avatar':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200',
    },
    {
      'name': '用户二',
      'username': 'user2',
      'avatar':
          'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=200',
    },
    {
      'name': '用户三',
      'username': 'user3',
      'avatar':
          'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=200',
    },
    {
      'name': '用户四',
      'username': 'user4',
      'avatar':
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200',
    },
    {
      'name': '用户五',
      'username': 'user5',
      'avatar':
          'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200',
    },
    {
      'name': '用户六',
      'username': 'user6',
      'avatar':
          'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=200',
    },
    {
      'name': '用户七',
      'username': 'user7',
      'avatar':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200',
    },
    {
      'name': '用户八',
      'username': 'user8',
      'avatar':
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200',
    },
    {
      'name': '用户九',
      'username': 'user9',
      'avatar':
          'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=200',
    },
  ];

  /// 相关同好 mock：带首字母用于分组（A-Z, #），仅用通用占位名
  static const List<Map<String, dynamic>> _mockRelatedFriends = [
    {
      'name': '同好A1',
      'username': 'friend_a1',
      'avatar':
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200',
      'letter': 'A',
    },
    {
      'name': '同好A2',
      'username': 'friend_a2',
      'avatar':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200',
      'letter': 'A',
    },
    {
      'name': '同好A3',
      'username': 'friend_a3',
      'avatar':
          'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=200',
      'letter': 'A',
    },
    {
      'name': '同好B1',
      'username': 'friend_b1',
      'avatar':
          'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=200',
      'letter': 'B',
    },
    {
      'name': '同好B2',
      'username': 'friend_b2',
      'avatar':
          'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=200',
      'letter': 'B',
    },
    {
      'name': '同好C1',
      'username': 'friend_c1',
      'avatar':
          'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200',
      'letter': 'C',
    },
    {
      'name': '同好C2',
      'username': 'friend_c2',
      'avatar':
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=200',
      'letter': 'C',
    },
    {
      'name': '同好D1',
      'username': 'friend_d1',
      'avatar':
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200',
      'letter': 'D',
    },
  ];

  @override
  void dispose() {
    _searchController.dispose();
    _listScrollController.dispose();
    super.dispose();
  }

  void _openSelectGroupChatSheet() {
    final messenger = ScaffoldMessenger.of(context);
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => _SelectGroupChatSheet(
        groups: _mockGroupChats,
        onSelectGroup: (group) {
          Navigator.of(context).pop();
          _openMemberSelectSheet(
            title:
                '${group['name']} (${group['count']}${UITextConstants.friendsCount})',
            members: _mockGroupMembers,
            onConfirm: (selected) {
              messenger.showSnackBar(
                SnackBar(content: Text('已选 ${selected.length} 人（开发中）')),
              );
            },
          );
        },
        onClose: () => Navigator.of(context).pop(),
      ),
    );
  }

  void _openSelectCircleSheet() {
    final messenger = ScaffoldMessenger.of(context);
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => _SelectCircleSheet(
        circles: _mockCircles,
        onSelectCircle: (circle) {
          Navigator.of(context).pop();
          _openMemberSelectSheet(
            title:
                '${circle['name']} (${circle['count']}${UITextConstants.friendsCount})',
            members: _mockGroupMembers,
            onConfirm: (selected) {
              messenger.showSnackBar(
                SnackBar(content: Text('已选 ${selected.length} 人（开发中）')),
              );
            },
          );
        },
        onClose: () => Navigator.of(context).pop(),
      ),
    );
  }

  void _openMemberSelectSheet({
    required String title,
    required List<Map<String, String>> members,
    required void Function(List<Map<String, String>>) onConfirm,
  }) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => _MemberSelectSheet(
        title: title,
        members: members,
        onConfirm: onConfirm,
        onBack: () => Navigator.of(context).pop(),
      ),
    );
  }

  /// 按首字母分组：A-Z, #，返回有序 keys 与 map
  static ({List<String> keys, Map<String, List<Map<String, dynamic>>> map})
  _groupByLetter(List<Map<String, dynamic>> list) {
    final map = <String, List<Map<String, dynamic>>>{};
    for (final m in list) {
      final name = m['name'] as String? ?? '';
      final letter =
          m['letter'] as String? ??
          (name.isNotEmpty ? name.substring(0, 1).toUpperCase() : '#');
      final key = RegExp(r'[A-Za-z]').hasMatch(letter)
          ? letter.toUpperCase()
          : '#';
      map.putIfAbsent(key, () => []).add(m);
    }
    for (final key in map.keys) {
      map[key]!.sort(
        (a, b) => (a['name'] as String).compareTo(b['name'] as String),
      );
    }
    final keys = map.keys.toList()..sort();
    if (keys.contains('#')) {
      keys.remove('#');
      keys.add('#');
    }
    return (keys: keys, map: map);
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bgColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
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
    final grouped = _groupByLetter(List.from(_mockRelatedFriends));
    final indexLetters = ['↑', '☆', ...grouped.keys];

    final letterKeys = <String, GlobalKey>{};
    for (final k in grouped.keys) {
      letterKeys[k] = GlobalKey();
    }

    final topChildren = <Widget>[
      Text(
        UITextConstants.createNewGroupChat,
        style: TextStyle(
          fontSize: AppTypography.md,
          color: fgPrimary.withValues(alpha: 0.6),
        ),
      ),
      SizedBox(height: AppSpacing.sm),
      _SectionRow(
        label: UITextConstants.selectFriendsFromGroupChat,
        fgPrimary: fgPrimary,
        onTap: _openSelectGroupChatSheet,
      ),
      Divider(
        height: AppSpacing.one,
        color: borderColor.withValues(alpha: 0.3),
      ),
      _SectionRow(
        label: UITextConstants.selectFriendsFromCircle,
        fgPrimary: fgPrimary,
        onTap: _openSelectCircleSheet,
      ),
      SizedBox(height: AppSpacing.lg),
      Text(
        UITextConstants.relatedSameInterest,
        style: TextStyle(
          fontSize: AppTypography.md,
          color: fgPrimary.withValues(alpha: 0.6),
        ),
      ),
      SizedBox(height: AppSpacing.sm),
    ];

    final relatedChildren = <Widget>[];
    for (final letter in grouped.keys) {
      relatedChildren.add(
        Container(
          key: letterKeys[letter],
          margin: EdgeInsets.only(
            top: relatedChildren.isEmpty ? 0 : AppSpacing.sm,
          ),
          padding: EdgeInsets.symmetric(
            horizontal:
                AppSpacing.semantic[DesignSemanticConstants
                    .container]?[DesignSemanticConstants.md] ??
                AppSpacing.containerMd,
            vertical: AppSpacing.xs,
          ),
          color: borderColor.withValues(alpha: 0.15),
          alignment: Alignment.centerLeft,
          child: Text(
            letter,
            style: TextStyle(
              fontSize: AppTypography.sm,
              fontWeight: FontWeight.w600,
              color: fgSecondary,
            ),
          ),
        ),
      );
      for (final m in grouped.map[letter]!) {
        final username = m['username'] as String? ?? '';
        final selected = _relatedSelected[username] ?? false;
        relatedChildren.add(
          _RelatedFriendRow(
            name: m['name'] as String,
            username: username,
            avatarUrl: m['avatar'] as String? ?? '',
            selected: selected,
            fgPrimary: fgPrimary,
            onTap: () => setState(() => _relatedSelected[username] = !selected),
            onAvatarTap: () => context.push('/user/$username'),
          ),
        );
      }
    }

    return Scaffold(
      backgroundColor: bgColor,
      appBar: AppBar(
        backgroundColor: bgColor,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: widget.onBack,
        ),
        title: Text(
          UITextConstants.startGroupChat,
          style: TextStyle(
            color: fgPrimary,
            fontSize: AppTypography.xl,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.symmetric(
              horizontal:
                  AppSpacing.semantic[DesignSemanticConstants
                      .container]?[DesignSemanticConstants.md] ??
                  AppSpacing.containerMd,
              vertical: AppSpacing.sm,
            ),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: UITextConstants.search,
                prefixIcon: Icon(
                  Icons.search,
                  size: AppSpacing.iconMedium,
                  color: fgPrimary.withValues(alpha: 0.5),
                ),
                filled: true,
                fillColor: isDark
                    ? Colors.white.withValues(alpha: 0.08)
                    : Colors.white,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(
                    AppSpacing.borderRadius * 2,
                  ),
                  borderSide: BorderSide.none,
                ),
                contentPadding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.md,
                  vertical: AppSpacing.sm,
                ),
              ),
            ),
          ),
          Expanded(
            child: Stack(
              children: [
                ListView(
                  controller: _listScrollController,
                  padding: EdgeInsets.only(
                    left:
                        AppSpacing.semantic[DesignSemanticConstants
                            .container]?[DesignSemanticConstants.md] ??
                        AppSpacing.containerMd,
                    right:
                        (AppSpacing.semantic[DesignSemanticConstants
                                .container]?[DesignSemanticConstants.md] ??
                            AppSpacing.containerMd) +
                        28,
                    bottom: AppSpacing.lg,
                  ),
                  children: [...topChildren, ...relatedChildren],
                ),
                Positioned(
                  right: AppSpacing.sm,
                  top: 0,
                  bottom: 0,
                  child: _LetterIndex(
                    letters: indexLetters,
                    onTap: (i) {
                      if (i <= 1) {
                        _listScrollController.animateTo(
                          0,
                          duration: const Duration(milliseconds: 300),
                          curve: Curves.easeOut,
                        );
                        return;
                      }
                      final letter = indexLetters[i];
                      final key = letterKeys[letter];
                      if (key?.currentContext != null) {
                        Scrollable.ensureVisible(
                          key!.currentContext!,
                          duration: const Duration(milliseconds: 300),
                          curve: Curves.easeOut,
                          alignment: 0,
                        );
                      }
                    },
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

class _SectionRow extends StatelessWidget {
  const _SectionRow({
    required this.label,
    required this.fgPrimary,
    required this.onTap,
  });

  final String label;
  final Color fgPrimary;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.md),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: TextStyle(fontSize: AppTypography.lg, color: fgPrimary),
              ),
            ),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconMedium,
              color: fgPrimary.withValues(alpha: 0.5),
            ),
          ],
        ),
      ),
    );
  }
}

class _RelatedFriendRow extends StatelessWidget {
  const _RelatedFriendRow({
    required this.name,
    required this.username,
    required this.avatarUrl,
    required this.selected,
    required this.fgPrimary,
    required this.onTap,
    required this.onAvatarTap,
  });

  final String name;
  final String username;
  final String avatarUrl;
  final bool selected;
  final Color fgPrimary;
  final VoidCallback onTap;
  final VoidCallback onAvatarTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
        child: Row(
          children: [
            _SelectionIndicator(selected: selected, onTap: onTap),
            GestureDetector(
              onTap: onAvatarTap,
              child: CircleAvatar(
                radius: AppSpacing.avatarSize / 2,
                backgroundImage: NetworkImage(avatarUrl),
              ),
            ),
            SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                name,
                style: TextStyle(fontSize: AppTypography.lg, color: fgPrimary),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LetterIndex extends StatelessWidget {
  const _LetterIndex({required this.letters, required this.onTap});

  final List<String> letters;
  final void Function(int index) onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final fgSecondary = isDark
        ? Colors.white.withValues(alpha: 0.45)
        : Colors.black87.withValues(alpha: 0.45);
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(letters.length, (i) {
        return GestureDetector(
          onTap: () => onTap(i),
          child: Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpacing.xs),
            child: Text(
              letters[i],
              style: TextStyle(
                fontSize: AppTypography.xs,
                color: fgSecondary,
                fontWeight: FontWeight.normal,
              ),
            ),
          ),
        );
      }),
    );
  }
}

class _SelectionIndicator extends StatelessWidget {
  const _SelectionIndicator({required this.selected, required this.onTap});

  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      iconSize: AppSpacing.iconMedium,
      padding: EdgeInsets.zero,
      constraints: BoxConstraints(
        minWidth: AppSpacing.minInteractiveSize,
        minHeight: AppSpacing.minInteractiveSize,
      ),
      onPressed: onTap,
      icon: Icon(
        selected
            ? CupertinoIcons.check_mark_circled_solid
            : CupertinoIcons.circle,
        color: selected ? AppColors.primaryColor : CupertinoColors.systemGrey2,
      ),
    );
  }
}

/// 选择群聊底部 sheet（图二）
class _SelectGroupChatSheet extends StatelessWidget {
  const _SelectGroupChatSheet({
    required this.groups,
    required this.onSelectGroup,
    required this.onClose,
  });

  final List<Map<String, String>> groups;
  final void Function(Map<String, String> group) onSelectGroup;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bgColor = isDark ? AppColors.dark.backgroundPrimary : AppColors.white;
    final fgPrimary = isDark ? Colors.white : Colors.black87;

    return Container(
      height: MediaQuery.of(context).size.height * 0.7,
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(AppSpacing.interGroupMd),
        ),
      ),
      child: Column(
        children: [
          Padding(
            padding: EdgeInsets.all(AppSpacing.sm),
            child: Row(
              children: [
                IconButton(
                  icon: Icon(Icons.keyboard_arrow_down, color: fgPrimary),
                  onPressed: onClose,
                ),
                Expanded(
                  child: Text(
                    UITextConstants.selectGroupChat,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: AppTypography.xl,
                      fontWeight: FontWeight.w600,
                      color: fgPrimary,
                    ),
                  ),
                ),
                SizedBox(width: AppSpacing.largeButtonSize),
              ],
            ),
          ),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
            child: TextField(
              decoration: InputDecoration(
                hintText: UITextConstants.searchGroupChatHint,
                prefixIcon: Icon(
                  Icons.search,
                  size: AppSpacing.iconMedium,
                  color: fgPrimary.withValues(alpha: 0.5),
                ),
                filled: true,
                fillColor: fgPrimary.withValues(alpha: 0.08),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                  borderSide: BorderSide.none,
                ),
                contentPadding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                  vertical: AppSpacing.sm,
                ),
              ),
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          Expanded(
            child: ListView.builder(
              itemCount: groups.length,
              itemBuilder: (context, index) {
                final g = groups[index];
                return ListTile(
                  leading: CircleAvatar(
                    radius: AppSpacing.avatarUserXs,
                    backgroundColor: AppColors.primaryColor.withValues(
                      alpha: 0.2,
                    ),
                    child: Icon(
                      Icons.group,
                      color: AppColors.primaryColor,
                      size: AppSpacing.iconLarge,
                    ),
                  ),
                  title: Text(
                    g['name']!,
                    style: TextStyle(
                      fontSize: AppTypography.lg,
                      color: fgPrimary,
                    ),
                  ),
                  subtitle: Text(
                    '${g['count']}${UITextConstants.friendsCount}',
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      color: fgPrimary.withValues(alpha: 0.6),
                    ),
                  ),
                  trailing: Icon(
                    CupertinoIcons.chevron_forward,
                    color: fgPrimary.withValues(alpha: 0.5),
                  ),
                  onTap: () => onSelectGroup(g),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

/// 选择圈子底部 sheet
class _SelectCircleSheet extends StatelessWidget {
  const _SelectCircleSheet({
    required this.circles,
    required this.onSelectCircle,
    required this.onClose,
  });

  final List<Map<String, String>> circles;
  final void Function(Map<String, String> circle) onSelectCircle;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bgColor = isDark ? AppColors.dark.backgroundPrimary : AppColors.white;
    final fgPrimary = isDark ? Colors.white : Colors.black87;

    return Container(
      height: MediaQuery.of(context).size.height * 0.7,
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(AppSpacing.interGroupMd),
        ),
      ),
      child: Column(
        children: [
          Padding(
            padding: EdgeInsets.all(AppSpacing.sm),
            child: Row(
              children: [
                IconButton(
                  icon: Icon(Icons.keyboard_arrow_down, color: fgPrimary),
                  onPressed: onClose,
                ),
                Expanded(
                  child: Text(
                    UITextConstants.selectCircle,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: AppTypography.xl,
                      fontWeight: FontWeight.w600,
                      color: fgPrimary,
                    ),
                  ),
                ),
                SizedBox(width: AppSpacing.largeButtonSize),
              ],
            ),
          ),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
            child: TextField(
              decoration: InputDecoration(
                hintText: UITextConstants.searchCircleHint,
                prefixIcon: Icon(
                  Icons.search,
                  size: AppSpacing.iconMedium,
                  color: fgPrimary.withValues(alpha: 0.5),
                ),
                filled: true,
                fillColor: fgPrimary.withValues(alpha: 0.08),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                  borderSide: BorderSide.none,
                ),
                contentPadding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                  vertical: AppSpacing.sm,
                ),
              ),
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          Expanded(
            child: ListView.builder(
              itemCount: circles.length,
              itemBuilder: (context, index) {
                final c = circles[index];
                return ListTile(
                  leading: CircleAvatar(
                    radius: AppSpacing.avatarUserXs,
                    backgroundColor: AppColors.secondaryColor.withValues(
                      alpha: 0.2,
                    ),
                    child: Icon(
                      Icons.people_outline,
                      color: AppColors.secondaryColor,
                      size: AppSpacing.iconLarge,
                    ),
                  ),
                  title: Text(
                    c['name']!,
                    style: TextStyle(
                      fontSize: AppTypography.lg,
                      color: fgPrimary,
                    ),
                  ),
                  subtitle: Text(
                    '${c['count']}${UITextConstants.friendsCount}',
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      color: fgPrimary.withValues(alpha: 0.6),
                    ),
                  ),
                  trailing: Icon(
                    CupertinoIcons.chevron_forward,
                    color: fgPrimary.withValues(alpha: 0.5),
                  ),
                  onTap: () => onSelectCircle(c),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

/// 群成员/圈成员多选 sheet（图三）
class _MemberSelectSheet extends StatefulWidget {
  const _MemberSelectSheet({
    required this.title,
    required this.members,
    required this.onConfirm,
    required this.onBack,
  });

  final String title;
  final List<Map<String, String>> members;
  final void Function(List<Map<String, String>> selected) onConfirm;
  final VoidCallback onBack;

  @override
  State<_MemberSelectSheet> createState() => _MemberSelectSheetState();
}

class _MemberSelectSheetState extends State<_MemberSelectSheet> {
  final Set<int> _selected = {};

  bool get _allSelected => _selected.length == widget.members.length;

  void _toggleAll() {
    setState(() {
      if (_allSelected) {
        _selected.clear();
      } else {
        _selected.addAll(List.generate(widget.members.length, (i) => i));
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bgColor = isDark ? AppColors.dark.backgroundPrimary : AppColors.white;
    final fgPrimary = isDark ? Colors.white : Colors.black87;

    return Container(
      height: MediaQuery.of(context).size.height * 0.75,
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(AppSpacing.interGroupMd),
        ),
      ),
      child: Column(
        children: [
          AppBar(
            backgroundColor: Colors.transparent,
            elevation: 0,
            leading: IconButton(
              icon: Icon(Icons.arrow_back, color: fgPrimary),
              onPressed: widget.onBack,
            ),
            title: Text(
              widget.title,
              style: TextStyle(
                fontSize: AppTypography.xl,
                fontWeight: FontWeight.w600,
                color: fgPrimary,
              ),
            ),
          ),
          Expanded(
            child: ListView.builder(
              itemCount: widget.members.length,
              itemBuilder: (context, index) {
                final m = widget.members[index];
                final selected = _selected.contains(index);
                return InkWell(
                  onTap: () {
                    setState(() {
                      if (selected) {
                        _selected.remove(index);
                      } else {
                        _selected.add(index);
                      }
                    });
                  },
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.md,
                      vertical: AppSpacing.sm,
                    ),
                    child: Row(
                      children: [
                        _SelectionIndicator(
                          selected: selected,
                          onTap: () {
                            setState(() {
                              if (selected) {
                                _selected.remove(index);
                              } else {
                                _selected.add(index);
                              }
                            });
                          },
                        ),
                        CircleAvatar(
                          radius: AppSpacing.avatarSize / 2,
                          backgroundImage: NetworkImage(m['avatar'] ?? ''),
                        ),
                        SizedBox(width: AppSpacing.sm),
                        Expanded(
                          child: Text(
                            m['name'] ?? '',
                            style: TextStyle(
                              fontSize: AppTypography.lg,
                              color: fgPrimary,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
          Padding(
            padding: EdgeInsets.all(AppSpacing.md),
            child: Row(
              children: [
                InkWell(
                  onTap: _toggleAll,
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _SelectionIndicator(
                        selected: _allSelected,
                        onTap: _toggleAll,
                      ),
                      Text(
                        UITextConstants.selectAll,
                        style: TextStyle(
                          fontSize: AppTypography.lg,
                          color: fgPrimary,
                        ),
                      ),
                    ],
                  ),
                ),
                const Spacer(),
                Material(
                  color: _selected.isEmpty
                      ? SettingsSemanticConstants.actionButtonDisabledBackground(
                          isDark,
                        )
                      : SettingsSemanticConstants.actionButtonPrimaryBackground,
                  borderRadius: BorderRadius.circular(
                    SettingsSemanticConstants.actionButtonBorderRadius,
                  ),
                  child: InkWell(
                    onTap: _selected.isEmpty
                        ? null
                        : () {
                            final list = _selected
                                .map((i) => widget.members[i])
                                .toList();
                            Navigator.of(context).pop();
                            widget.onConfirm(list);
                          },
                    borderRadius: BorderRadius.circular(
                      SettingsSemanticConstants.actionButtonBorderRadius,
                    ),
                    child: SizedBox(
                      height:
                          SettingsSemanticConstants.actionButtonHeightMedium,
                      child: Padding(
                        padding: EdgeInsets.symmetric(
                          horizontal: SettingsSemanticConstants
                              .actionButtonPaddingHorizontal,
                          vertical: SettingsSemanticConstants
                              .actionButtonPaddingVertical,
                        ),
                        child: Center(
                          child: Text(
                            UITextConstants.selectAction,
                            style: TextStyle(
                              fontSize: AppTypography.lg,
                              fontWeight: FontWeight.w500,
                              color: _selected.isEmpty
                                  ? SettingsSemanticConstants.actionButtonDisabledForeground(
                                      isDark,
                                    )
                                  : SettingsSemanticConstants
                                        .actionButtonPrimaryForeground,
                            ),
                          ),
                        ),
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
