// ignore_for_file: unnecessary_underscores

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/assistant/assistant_avatar.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';

/// 趣聊页
///
/// 1:1 复制自 趣我圈2026/src MessagePage.tsx + MessagesList.tsx
/// 一级 Tab 趣聊/同好；二级 Tab subTabsMap（趣聊→全部/@我/未读/密信，同好→全部/圈子/同好/趣群）；
/// 滚动时二级 Tab 显隐；私人助理会话置顶，onAssistantClick→助理主页。
class ChatPage extends ConsumerStatefulWidget {
  const ChatPage({super.key});

  @override
  ConsumerState<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends ConsumerState<ChatPage>
    with AutomaticKeepAliveClientMixin {
  int _mainTabIndex = 0; // 0=趣聊 1=同好
  int _subTabIndex = 0;
  bool _hideSecondaryTab = false;
  final ScrollController _scrollController = ScrollController();
  double _lastScrollY = 0;

  @override
  bool get wantKeepAlive => true;

  @override
  void dispose() {
    _scrollController.dispose();
    _secretPasswordController.dispose();
    super.dispose();
  }

  void _secretUnlock() {
    final pwd = _secretPasswordController.text.trim();
    if (pwd == '123456' || pwd == 'password') {
      setState(() {
        _secretUnlocked = true;
        _secretAuthError = '';
        _secretPasswordController.clear();
      });
    } else {
      setState(() => _secretAuthError = '密码错误，请重试');
    }
  }

  void _secretLock() {
    setState(() {
      _secretUnlocked = false;
      _secretAuthError = '';
    });
  }

  /// 与 MessagePage subTabsMap 一致
  static const List<String> _messageSubTabs = [
    '全部',
    '@我',
    '未读',
    '密信',
  ];
  static const List<String> _contactsSubTabs = [
    UITextConstants.contactsTabAll,
    UITextConstants.contactsTabCircles,
    UITextConstants.contactsTabSameInterest,
    UITextConstants.contactsTabFunGroup,
  ];

  /// 密信解锁状态（仅密信 Tab 使用）
  bool _secretUnlocked = false;
  final TextEditingController _secretPasswordController = TextEditingController();
  String _secretAuthError = '';
  bool _secretShowPassword = false;

  void _openAssistantHalfSheet() {
    final target = VisitTarget.page('chat');
    final service = ref.read(visitRecorderServiceProvider);
    final ctx = AssistantOpenContext(
      source: AssistantSource.chat,
      visitTarget: target,
      experienceLevel: service.getExperience(target),
    );
    AssistantHalfSheet.show(context, ctx);
  }

  void _onScroll() {
    final y = _scrollController.hasClients ? _scrollController.offset : 0.0;
    if (y > 50) {
      final diff = y - _lastScrollY;
      if (diff > 5) {
        if (!_hideSecondaryTab) setState(() => _hideSecondaryTab = true);
      } else if (diff < -5) {
        if (_hideSecondaryTab) setState(() => _hideSecondaryTab = false);
      }
    } else {
      if (_hideSecondaryTab) setState(() => _hideSecondaryTab = false);
    }
    _lastScrollY = y;
  }

  Future<List<Map<String, dynamic>>> _loadConversations() async {
    try {
      final repo = ref.read(chatRepositoryProvider);
      return await repo.listConversations(limit: 100);
    } catch (_) {
      return ref.read(appContentRepositoryProvider).chatMockConversations;
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final isDark = ref.watch(isDarkProvider);
    final bgColor =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fgPrimary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor =
        AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

    return Scaffold(
      backgroundColor: bgColor,
      body: SafeArea(
        bottom: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildMainTabs(context, bgColor, fgPrimary, fgSecondary),
            AnimatedSlide(
              offset: _hideSecondaryTab ? const Offset(0, -1) : Offset.zero,
              duration: const Duration(milliseconds: 200),
              child: AnimatedOpacity(
                opacity: _hideSecondaryTab ? 0 : 1,
                duration: const Duration(milliseconds: 200),
                child: _buildSubTabs(fgPrimary, fgSecondary, borderColor),
              ),
            ),
            Expanded(
              child: NotificationListener<ScrollNotification>(
                onNotification: (n) {
                  _onScroll();
                  return false;
                },
                child: _mainTabIndex == 0
                    ? (_messageSubTabs[_subTabIndex] == UITextConstants.secretMessage
                        ? _buildSecretMessageContent(context, fgPrimary, fgSecondary, borderColor)
                        : _buildMessagesContent(context, fgPrimary, fgSecondary, borderColor))
                    : _buildContactsContent(context, fgPrimary, fgSecondary, borderColor),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMainTabs(BuildContext context, Color bgColor, Color fgPrimary,
      Color fgSecondary) {
    final tabs = <TabItem>[
      TabItem(id: 'messages', label: AppConceptConstants.messages),
      TabItem(id: 'contacts', label: AppConceptConstants.contacts),
    ];
    final activeTabId = _mainTabIndex == 0 ? 'messages' : 'contacts';
    return Container(
      decoration: BoxDecoration(
        color: bgColor,
        border: Border(
          bottom: BorderSide(
            color: AppColorsFunctional.getColor(ref.read(isDarkProvider), ColorType.borderPrimary),
          ),
        ),
      ),
      child: CenteredScrollableTabBar(
        tabs: tabs,
        activeTab: activeTabId,
        isDark: ref.read(isDarkProvider),
        onTabChange: (id) {
          setState(() {
            _mainTabIndex = id == 'messages' ? 0 : 1;
            _subTabIndex = 0;
          });
        },
        trailingActions: [
          IconButton(
            icon: Icon(Icons.search, color: fgSecondary),
            onPressed: () {},
            style: IconButton.styleFrom(
              minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSubTabs(
      Color fgPrimary, Color fgSecondary, Color borderColor) {
    final subTabs = _mainTabIndex == 0 ? _messageSubTabs : _contactsSubTabs;
    return Container(
      padding: EdgeInsets.symmetric(vertical: 12, horizontal: AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(
            ref.read(isDarkProvider), ColorType.backgroundPrimary),
        border: Border(bottom: BorderSide(color: borderColor.withValues(alpha: 0.2))),
      ),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: List.generate(subTabs.length, (i) {
            final isActive = i == _subTabIndex;
            return Padding(
              padding: EdgeInsets.only(right: 10),
              child: GestureDetector(
                onTap: () => setState(() => _subTabIndex = i),
                child: Container(
                  padding: EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                  decoration: BoxDecoration(
                    color: isActive
                        ? AppColors.primaryColor
                        : (ref.read(isDarkProvider)
                            ? Colors.white.withValues(alpha: 0.08)
                            : Colors.black.withValues(alpha: 0.04)),
                    borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
                    border: isActive
                        ? null
                        : Border.all(color: Colors.transparent),
                  ),
                  child: Text(
                    subTabs[i],
                    style: TextStyle(
                      fontSize: AppTypography.smPlus,
                      fontWeight: FontWeight.w700,
                      color: isActive ? Colors.white : fgSecondary,
                    ),
                  ),
                ),
              ),
            );
          }),
        ),
      ),
    );
  }

  Widget _buildSecretMessageContent(
    BuildContext context,
    Color fgPrimary,
    Color fgSecondary,
    Color borderColor,
  ) {
    if (!_secretUnlocked) {
      return _buildSecretLockScreen(context, fgPrimary, fgSecondary);
    }
    final encrypted = ref.read(appContentRepositoryProvider).chatEncryptedConversations;
    return Column(
      children: [
        Container(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 12),
          decoration: BoxDecoration(
            color: AppColors.primaryColor.withValues(alpha: 0.08),
            border: Border(bottom: BorderSide(color: borderColor.withValues(alpha: 0.2))),
          ),
          child: Row(
            children: [
              Icon(
                Icons.shield,
                color: AppColors.primaryColor,
                size: AppSpacing.iconMedium,
              ),
              SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      UITextConstants.secretUnlockedBanner,
                      style: TextStyle(
                        fontSize: AppTypography.md,
                        fontWeight: FontWeight.w700,
                        color: fgPrimary,
                      ),
                    ),
                    Text(
                      '${encrypted.length} 个加密对话 · 安全保护中',
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              TextButton(
                onPressed: _secretLock,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.lock,
                      size: AppSpacing.iconSmall,
                      color: AppColors.primaryColor,
                    ),
                    SizedBox(width: AppSpacing.xs),
                    Text(UITextConstants.secretLockButton, style: TextStyle(fontWeight: FontWeight.w700, color: AppColors.primaryColor)),
                  ],
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: encrypted.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.shield_outlined,
                        size: AppSpacing.largeButtonSize,
                        color: fgSecondary,
                      ),
                      SizedBox(height: AppSpacing.md),
                      Text(
                        UITextConstants.noSecretConversations,
                        style: TextStyle(
                          fontSize: AppTypography.md,
                          color: fgSecondary,
                        ),
                      ),
                    ],
                  ),
                )
              : ListView.builder(
                  itemCount: encrypted.length,
                  itemBuilder: (context, i) {
                    final c = encrypted[i];
                    return _ConversationTile(
                      conversation: c,
                      isSpecial: false,
                      onTap: () => context.push(
                        AppRoutePaths.chatDetail(id: '${c['id']}'),
                      ),
                      fgPrimary: fgPrimary,
                      fgSecondary: fgSecondary,
                      borderColor: borderColor,
                      showEncryptedBadge: true,
                    );
                  },
                ),
        ),
      ],
    );
  }

  Widget _buildSecretLockScreen(BuildContext context, Color fgPrimary, Color fgSecondary) {
    final isDark = ref.read(isDarkProvider);
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    return SingleChildScrollView(
      padding: EdgeInsets.all(AppSpacing.xl),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          SizedBox(height: AppSpacing.forty),
          Container(
            width: AppSpacing.oneHundred,
            height: AppSpacing.oneHundred,
            decoration: BoxDecoration(
              color: isDark ? Colors.white.withValues(alpha: 0.08) : Colors.grey.shade200,
              shape: BoxShape.circle,
            ),
            child: Icon(
              Icons.lock,
              size: AppSpacing.largeButtonSize,
              color: fgSecondary,
            ),
          ),
          SizedBox(height: AppSpacing.lg),
          Text(
            UITextConstants.secretLockedTitle,
            style: TextStyle(
              fontSize: AppTypography.xxxl,
              fontWeight: FontWeight.w900,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.xl),
          SizedBox(
            width: AppSpacing.threeHundredTwenty,
            child: Column(
              children: [
                TextField(
                  controller: _secretPasswordController,
                  obscureText: !_secretShowPassword,
                  onChanged: (_) => setState(() => _secretAuthError = ''),
                  onSubmitted: (_) => _secretUnlock(),
                  decoration: InputDecoration(
                    hintText: UITextConstants.secretPasswordHint,
                    hintStyle: TextStyle(color: fgSecondary),
                    filled: true,
                    fillColor: isDark ? Colors.white.withValues(alpha: 0.08) : Colors.grey.shade100,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                      borderSide: BorderSide.none,
                    ),
                    suffixIcon: IconButton(
                      icon: Icon(_secretShowPassword ? Icons.visibility_off : Icons.visibility, color: fgSecondary),
                      onPressed: () => setState(() => _secretShowPassword = !_secretShowPassword),
                    ),
                  ),
                  style: TextStyle(color: fgPrimary),
                ),
                if (_secretAuthError.isNotEmpty) ...[
                  SizedBox(height: AppSpacing.interGroupSm),
                  Text(
                    _secretAuthError,
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      color: AppColors.error,
                    ),
                  ),
                ],
                SizedBox(height: AppSpacing.twenty),
                SizedBox(
                  width: double.infinity,
                  height: AppSpacing.bottomNavHeight,
                  child: FilledButton(
                    onPressed: () {
                      if (_secretPasswordController.text.trim().isEmpty) return;
                      _secretUnlock();
                    },
                    style: FilledButton.styleFrom(
                      backgroundColor: fgPrimary,
                      foregroundColor: bg,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(
                          AppSpacing.radiusTwentyEight,
                        ),
                      ),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.lock_open),
                        SizedBox(width: AppSpacing.sm),
                        Text(UITextConstants.secretUnlockButton),
                      ],
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

  Widget _buildMessagesContent(
    BuildContext context,
    Color fgPrimary,
    Color fgSecondary,
    Color borderColor,
  ) {
    final showAssistant =
        _mainTabIndex == 0 && _messageSubTabs[_subTabIndex] == '全部';

    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _loadConversations(),
      builder: (context, snapshot) {
        final rawList = snapshot.data ?? const <Map<String, dynamic>>[];
        final convs = _filterConversationListForSubTab(rawList);

        if (snapshot.connectionState == ConnectionState.waiting &&
            rawList.isEmpty) {
          return Center(
            child: Padding(
              padding: EdgeInsets.all(AppSpacing.lg),
              child: CircularProgressIndicator(color: AppColors.primaryColor),
            ),
          );
        }

        if (showAssistant == false && convs.isEmpty) {
          return Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.chat_bubble_outline,
                  size: AppSpacing.iconButtonMinSizeMd,
                  color: fgSecondary,
                ),
                SizedBox(height: AppSpacing.md),
                Text(
                  UITextConstants.noConversations,
                  style: TextStyle(fontSize: AppTypography.lg, color: fgSecondary),
                ),
                Text(
                  UITextConstants.startChatHint,
                  style: TextStyle(fontSize: AppTypography.md, color: fgSecondary),
                ),
              ],
            ),
          );
        }

        return ListView(
          controller: _scrollController,
          children: [
            if (showAssistant)
              _ConversationTile(
                conversation:
                    ref.read(appContentRepositoryProvider).chatAssistantConversation,
                isSpecial: true,
                onTap: _openAssistantHalfSheet,
                fgPrimary: fgPrimary,
                fgSecondary: fgSecondary,
                borderColor: borderColor,
              ),
            ...convs.map(
              (c) => _ConversationTile(
                conversation: c,
                onTap: () => context.push(
                  AppRoutePaths.chatDetail(id: '${c['id']}'),
                ),
                fgPrimary: fgPrimary,
                fgSecondary: fgSecondary,
                borderColor: borderColor,
              ),
            ),
            SizedBox(height: MediaQuery.of(context).padding.bottom + 80),
          ],
        );
      },
    );
  }

  List<Map<String, dynamic>> _filterConversationListForSubTab(
    List<Map<String, dynamic>> list,
  ) {
    if (_mainTabIndex != 0) return list;
    final sub = _messageSubTabs[_subTabIndex];
    if (sub == UITextConstants.atMe) {
      return list.where((c) => c['hasMention'] == true).toList();
    }
    if (sub == UITextConstants.unread) {
      return list.where((c) => (c['unreadCount'] as int? ?? 0) > 0).toList();
    }
    if (sub == UITextConstants.secretMessage) {
      return const <Map<String, dynamic>>[];
    }
    return list;
  }

  Widget _buildContactsContent(BuildContext context, Color fgPrimary, Color fgSecondary, Color borderColor) {
    final sub = _contactsSubTabs[_subTabIndex];
    final repository = ref.read(appContentRepositoryProvider);
    List<Map<String, dynamic>> list;
    if (sub == UITextConstants.contactsTabCircles) {
      list = repository.chatMockContactCircles;
    } else if (sub == UITextConstants.contactsTabSameInterest) {
      list = repository.chatMockContacts
          .where((c) => c['isFriend'] == true)
          .toList();
    } else if (sub == UITextConstants.contactsTabFunGroup) {
      list = repository.chatMockContactGroups;
    } else {
      list = repository.chatMockContacts;
    }
    if (list.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.people_outline,
              size: AppSpacing.iconButtonMinSizeMd,
              color: fgSecondary,
            ),
            SizedBox(height: AppSpacing.md),
            Text(
              '暂无$sub内容',
              style: TextStyle(fontSize: AppTypography.lg, color: fgSecondary),
            ),
          ],
        ),
      );
    }
    // 全部、同好：带右侧字母索引（1:1 ContactsList.tsx）
    if (sub == UITextConstants.contactsTabAll || sub == UITextConstants.contactsTabSameInterest) {
      return _ContactsListWithIndex(
        items: list,
        fgPrimary: fgPrimary,
        fgSecondary: fgSecondary,
        borderColor: borderColor,
      );
    }
    return ListView.builder(
      itemCount: list.length,
      itemBuilder: (context, i) {
        final item = list[i];
        final title = (item['displayName'] ?? item['name'] ?? item['title']) as String? ?? '';
        final avatar = item['avatar'] as String? ?? '';
        final subtitle = (item['bio'] ?? item['metFrom'] ?? item['lastInteraction']) as String? ?? '';
        return Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () {},
            child: Container(
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 12),
              decoration: BoxDecoration(border: Border(bottom: BorderSide(color: borderColor.withValues(alpha: 0.3)))),
              child: Row(
                children: [
                  CircleAvatar(radius: 28, backgroundImage: avatar.isNotEmpty ? NetworkImage(avatar) : null, onBackgroundImageError: (_, __) {}),
                  SizedBox(width: AppSpacing.interGroupSm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: TextStyle(
                            fontSize: AppTypography.lg,
                            fontWeight: FontWeight.w600,
                            color: fgPrimary,
                          ),
                        ),
                        if (subtitle.isNotEmpty)
                          Text(
                            subtitle,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.smPlus,
                              color: fgSecondary,
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
}

/// 同好列表带右侧字母索引（1:1 ContactsList.tsx ContactsContent）
class _ContactsListWithIndex extends StatefulWidget {
  const _ContactsListWithIndex({
    required this.items,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.borderColor,
  });

  final List<Map<String, dynamic>> items;
  final Color fgPrimary;
  final Color fgSecondary;
  final Color borderColor;

  @override
  State<_ContactsListWithIndex> createState() => _ContactsListWithIndexState();
}

String _getInitial(String name) {
  if (name.isEmpty) return '#';
  final first = name[0].toUpperCase();
  if (RegExp(r'[A-Z]').hasMatch(first)) return first;
  const map = {
    '赵': 'Z', '钱': 'Q', '孙': 'S', '李': 'L', '周': 'Z', '吴': 'W', '郑': 'Z', '王': 'W',
    '冯': 'F', '陈': 'C', '卫': 'W', '蒋': 'J', '沈': 'S', '韩': 'H', '杨': 'Y',
    '朱': 'Z', '秦': 'Q', '许': 'X', '何': 'H', '吕': 'L', '施': 'S', '张': 'Z',
    '孔': 'K', '曹': 'C', '严': 'Y', '华': 'H', '金': 'J', '魏': 'W', '陶': 'T', '姜': 'J',
    '谢': 'X', '邹': 'Z', '柏': 'B', '窦': 'D', '章': 'Z', '云': 'Y', '苏': 'S', '潘': 'P',
    '葛': 'G', '奚': 'X', '范': 'F', '彭': 'P', '郎': 'L', '鲁': 'L', '韦': 'W', '马': 'M',
    '苗': 'M', '方': 'F', '俞': 'Y', '任': 'R', '袁': 'Y', '柳': 'L', '史': 'S', '唐': 'T',
    '罗': 'L', '毕': 'B', '郝': 'H', '安': 'A', '常': 'C', '乐': 'L', '于': 'Y', '时': 'S',
    '傅': 'F', '齐': 'Q', '康': 'K', '伍': 'W', '余': 'Y', '顾': 'G', '孟': 'M', '平': 'P',
    '黄': 'H', '书': 'S', '小': 'X', '大': 'D', '老': 'L', '阿': 'A',
  };
  return map[name[0]] ?? 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[name.codeUnitAt(0) % 26];
}

const double _kSectionHeaderHeight = 28;
const double _kContactRowHeight = 56;

class _ContactsListWithIndexState extends State<_ContactsListWithIndex> {
  final Map<String, GlobalKey> _sectionKeys = {};
  final ScrollController _scrollController = ScrollController();
  String? _activeLetter;
  Map<String, double> _sectionOffsets = {};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _onScroll();
    });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (!_scrollController.hasClients || _sectionOffsets.isEmpty) return;
    final offset = _scrollController.offset;
    final ordered = _sectionOffsets.keys.toList()
      ..sort((a, b) => _sectionOffsets[a]!.compareTo(_sectionOffsets[b]!));
    String? current;
    for (final letter in ordered) {
      if (_sectionOffsets[letter]! <= offset + 40) current = letter;
    }
    if (current != null && current != _activeLetter && mounted) {
      setState(() => _activeLetter = current);
    }
  }

  @override
  Widget build(BuildContext context) {
    final items = widget.items;
    final withInitial = <Map<String, dynamic>>[];
    for (final item in items) {
      final name = (item['displayName'] ?? item['name'] ?? item['title']) as String? ?? '';
      withInitial.add({
        ...item,
        'initial': _getInitial(name),
        'displayName': name,
      });
    }
    withInitial.sort((a, b) {
      final starA = a['isStarred'] == true ? 1 : 0;
      final starB = b['isStarred'] == true ? 1 : 0;
      if (starB != starA) return starB - starA;
      final ia = a['initial'] as String;
      final ib = b['initial'] as String;
      if (ia != ib) return ia.compareTo(ib);
      return (a['displayName'] as String).compareTo(b['displayName'] as String);
    });
    final initials = <String>{};
    for (final item in withInitial) {
      initials.add(item['initial'] as String);
    }
    final hasStarred = withInitial.any((e) => e['isStarred'] == true);
    final allInitials = <String>[];
    if (hasStarred) allInitials.add('★');
    allInitials.addAll(initials.toList()..sort());
    for (final letter in allInitials) {
      _sectionKeys.putIfAbsent(letter, () => GlobalKey());
    }

    final listChildren = <Widget>[];
    final sectionOffsets = <String, double>{};
    double pos = 0;
    String? lastInitial;
    bool lastStarred = false;
    for (final item in withInitial) {
      final initial = item['initial'] as String;
      final starred = item['isStarred'] == true;
      final isFirstStarred = starred && !lastStarred;
      final isFirstOfInitial = initial != lastInitial;
      if (isFirstStarred) {
        sectionOffsets['★'] = pos;
        pos += _kSectionHeaderHeight;
        final key = _sectionKeys['★'];
        if (key != null) {
          listChildren.add(Container(
            key: key,
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 4),
            color: widget.borderColor.withValues(alpha: 0.15),
            child: Text(
              UITextConstants.starredFriends,
              style: TextStyle(
                fontSize: AppTypography.sm,
                fontWeight: FontWeight.w600,
                color: widget.fgSecondary,
              ),
            ),
          ));
        }
      }
      if (!starred && isFirstOfInitial) {
        sectionOffsets[initial] = pos;
        pos += _kSectionHeaderHeight;
        final key = _sectionKeys[initial];
        if (key != null) {
          listChildren.add(Container(
            key: key,
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 4),
            color: widget.borderColor.withValues(alpha: 0.15),
            child: Text(
              initial,
              style: TextStyle(
                fontSize: AppTypography.sm,
                fontWeight: FontWeight.w600,
                color: widget.fgSecondary,
              ),
            ),
          ));
        }
      }
      lastInitial = initial;
      lastStarred = starred;
      pos += _kContactRowHeight;
      final title = item['displayName'] as String? ?? '';
      final avatar = item['avatar'] as String? ?? '';
      final subtitle = (item['bio'] ?? item['metFrom'] ?? item['lastInteraction']) as String? ?? '';
      listChildren.add(
        Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () {},
            child: Container(
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 12),
              decoration: BoxDecoration(border: Border(bottom: BorderSide(color: widget.borderColor.withValues(alpha: 0.3)))),
              child: Row(
                children: [
                  CircleAvatar(radius: 28, backgroundImage: avatar.isNotEmpty ? NetworkImage(avatar) : null, onBackgroundImageError: (_, __) {}),
                  SizedBox(width: AppSpacing.interGroupSm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Text(
                              title,
                              style: TextStyle(
                                fontSize: AppTypography.lg,
                                fontWeight: FontWeight.w600,
                                color: widget.fgPrimary,
                              ),
                            ),
                            if (starred) ...[
                              SizedBox(width: AppSpacing.xs),
                              Icon(
                                Icons.star,
                                size: AppSpacing.iconSmall,
                                color: AppColors.warning,
                              ),
                            ],
                          ],
                        ),
                        if (subtitle.isNotEmpty)
                          Text(
                            subtitle,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.smPlus,
                              color: widget.fgSecondary,
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    }
    listChildren.add(SizedBox(height: AppSpacing.xl));
    _sectionOffsets = sectionOffsets;

    return Stack(
      children: [
        NotificationListener<ScrollNotification>(
          onNotification: (ScrollNotification n) {
            if (n is ScrollUpdateNotification || n is ScrollEndNotification) _onScroll();
            return false;
          },
          child: ListView(
            controller: _scrollController,
            padding: EdgeInsets.only(right: 32),
            children: listChildren,
          ),
        ),
        Positioned(
          right: 4,
          top: 0,
          bottom: 0,
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: allInitials.map((letter) {
                final isActive = _activeLetter == letter;
                return GestureDetector(
                  onTap: () {
                    setState(() => _activeLetter = letter);
                    final offset = _sectionOffsets[letter];
                    if (offset != null && _scrollController.hasClients) {
                      _scrollController.animateTo(
                        offset.clamp(0.0, _scrollController.position.maxScrollExtent),
                        duration: const Duration(milliseconds: 250),
                        curve: Curves.easeOut,
                      );
                    } else {
                      final key = _sectionKeys[letter];
                      if (key?.currentContext != null) {
                        Scrollable.ensureVisible(key!.currentContext!, duration: const Duration(milliseconds: 250), alignment: 0);
                      }
                    }
                  },
                  child: Container(
                    width: AppSpacing.twenty,
                    height: AppSpacing.twenty,
                    alignment: Alignment.center,
                    margin: EdgeInsets.symmetric(vertical: 1),
                    decoration: BoxDecoration(
                      color: isActive ? AppColors.primaryColor : Colors.transparent,
                      shape: BoxShape.circle,
                    ),
                    child: Text(
                      letter,
                      style: TextStyle(
                        fontSize: AppTypography.xs,
                        fontWeight: FontWeight.w700,
                        color: isActive ? Colors.white : widget.fgSecondary,
                      ),
                    ),
                  ),
                );
              }).toList(),
            ),
          ),
        ),
      ],
    );
  }
}

class _ConversationTile extends StatelessWidget {
  final Map<String, dynamic> conversation;
  final bool isSpecial;
  final VoidCallback onTap;
  final Color fgPrimary;
  final Color fgSecondary;
  final Color borderColor;
  final bool showEncryptedBadge;

  const _ConversationTile({
    required this.conversation,
    required this.onTap,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.borderColor,
    this.isSpecial = false,
    this.showEncryptedBadge = false,
  });

  @override
  Widget build(BuildContext context) {
    final unread = conversation['unreadCount'] as int? ?? 0;
    final isEncrypted = showEncryptedBadge || conversation['type'] == 'encrypted';
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Container(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: 12,
          ),
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(color: borderColor.withValues(alpha: 0.3)),
            ),
          ),
          child: Row(
            children: [
              Stack(
                clipBehavior: Clip.none,
                children: [
                  isSpecial
                      ? AssistantAvatar(radius: 28)
                      : CircleAvatar(
                          radius: 28,
                          backgroundImage: NetworkImage(
                            conversation['avatar'] as String? ?? '',
                          ),
                          onBackgroundImageError: (_, __) {},
                        ),
                  if (isEncrypted)
                    Positioned(
                      right: -2,
                      bottom: -2,
                      child: Container(
                        padding: EdgeInsets.all(AppSpacing.xs),
                        decoration: BoxDecoration(
                          color: AppColors.primaryColor,
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: Theme.of(context).scaffoldBackgroundColor,
                            width: AppSpacing.oneHalf,
                          ),
                        ),
                        child: Icon(
                          Icons.lock,
                          size: AppSpacing.fourteen,
                          color: Colors.white,
                        ),
                      ),
                    ),
                ],
              ),
              SizedBox(width: AppSpacing.interGroupSm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          conversation['title'] as String? ?? '',
                          style: TextStyle(
                            fontSize: AppTypography.lg,
                            fontWeight: FontWeight.w600,
                            color: fgPrimary,
                          ),
                        ),
                        if (isSpecial) ...[
                          SizedBox(width: AppSpacing.intraGroupSm),
                          Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.intraGroupSm,
                              vertical: AppSpacing.xs / 2,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.warning.withValues(alpha: 0.2),
                              borderRadius: BorderRadius.circular(
                                AppSpacing.radiusTen,
                              ),
                            ),
                            child: Text(
                              'AI',
                              style: TextStyle(
                                fontSize: AppTypography.xs,
                                fontWeight: FontWeight.w800,
                                color: AppColors.warning,
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                    SizedBox(height: AppSpacing.xs),
                    Row(
                      children: [
                        if (isEncrypted) ...[
                          Icon(
                            Icons.lock,
                            size: AppSpacing.interGroupSm,
                            color: fgSecondary,
                          ),
                          SizedBox(width: AppSpacing.xs),
                        ],
                        Expanded(
                          child: Text(
                            conversation['lastMessage'] as String? ?? '',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.smPlus,
                              color: fgSecondary,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    conversation['lastMessageTime'] as String? ?? '',
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      color: fgSecondary,
                    ),
                  ),
                  if (unread > 0) ...[
                    SizedBox(height: AppSpacing.xs),
                    Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.intraGroupSm,
                        vertical: AppSpacing.xs / 2,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.error,
                        borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
                      ),
                      child: Text(
                        unread > 99 ? '99+' : '$unread',
                        style: TextStyle(
                          fontSize: AppTypography.xsPlus,
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
