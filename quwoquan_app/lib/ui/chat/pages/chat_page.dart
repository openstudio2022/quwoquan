// ignore_for_file: unnecessary_underscores

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/avatar/group_avatar_grid.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/utils/chat_time_formatter.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/ui/chat/models/chat_list_item_view_model.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';

/// 趣信页
///
/// 1:1 复制自 趣我圈2026/src MessagePage.tsx + MessagesList.tsx
/// 一级 Tab 消息/联系人；二级 Tab subTabsMap（消息→全部/@我/未读/密信，联系人→全部/圈子/同好/趣群）；
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

  List<Map<String, dynamic>>? _conversations;
  bool _isLoading = true;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    if (!ref.read(chatInboxListEnabledProvider)) {
      _loadConversationsWithCache();
    }
  }

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

  /// 与 MessagePage subTabsMap 一致
  static const List<String> _messageSubTabs = [
    UITextConstants.contactsTabAll,
    UITextConstants.atMe,
    UITextConstants.unread,
    UITextConstants.secretMessage,
  ];
  static const List<String> _contactsSubTabs = [
    UITextConstants.contactsTabAll,
    UITextConstants.contactsTabCircles,
    UITextConstants.contactsTabSameInterest,
    UITextConstants.contactsTabFunGroup,
  ];

  /// 密信解锁状态（仅密信 Tab 使用）
  bool _secretUnlocked = false;
  final TextEditingController _secretPasswordController =
      TextEditingController();
  String _secretAuthError = '';
  bool _secretShowPassword = false;

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

  void _handleTabSwipeDragEnd(DragEndDetails details) {
    final direction = TabSwipeSwitchRegion.directionFromDragEnd(details);
    if (direction == null) {
      return;
    }
    _handleTabSwipe(direction);
  }

  void _handleTabSwipe(TabSwipeDirection direction) {
    if (_trySwitchSecondaryTab(direction)) {
      return;
    }
    final nextMainIndex = _mainTabIndex + direction.delta;
    if (nextMainIndex < 0 || nextMainIndex > 1) {
      return;
    }
    setState(() {
      _mainTabIndex = nextMainIndex;
      _subTabIndex = 0;
      _hideSecondaryTab = false;
    });
  }

  bool _trySwitchSecondaryTab(TabSwipeDirection direction) {
    if (_hideSecondaryTab) {
      return false;
    }
    final subTabs = _mainTabIndex == 0 ? _messageSubTabs : _contactsSubTabs;
    final nextSubIndex = _subTabIndex + direction.delta;
    if (nextSubIndex < 0 || nextSubIndex >= subTabs.length) {
      return false;
    }
    setState(() {
      _subTabIndex = nextSubIndex;
    });
    return true;
  }

  /// 本地缓存优先 → 异步云端同步 → 增量刷新
  Future<void> _loadConversationsWithCache() async {
    final cache = ref.read(conversationCacheProvider);
    final cached = cache.getAll();
    if (cached.isNotEmpty && mounted) {
      setState(() {
        _conversations = cached;
        _isLoading = false;
      });
    }

    try {
      final repo = ref.read(chatRepositoryProvider);
      final remote = await repo.listConversations(limit: 100);
      cache.putAll(remote);
      if (mounted) {
        setState(() {
          _conversations = remote;
          _isLoading = false;
        });
      }
    } catch (_) {
      if (_conversations == null || _conversations!.isEmpty) {
        final fallback = ref
            .read(appContentRepositoryProvider)
            .chatMockConversations;
        if (mounted) {
          setState(() {
            _conversations = fallback;
            _isLoading = false;
          });
        }
      } else if (mounted) {
        setState(() => _isLoading = false);
      }
    }

    try {
      final sync = ref.read(conversationSyncProvider);
      await sync.sync();
      final updated = cache.getAll();
      if (updated.isNotEmpty && mounted) {
        setState(() => _conversations = updated);
      }
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
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

    return AppScaffold(
      backgroundColor: bgColor,
      child: SafeArea(
        bottom: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildMainTabs(context, bgColor, fgPrimary, fgSecondary),
            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              curve: Curves.easeInOut,
              height: _hideSecondaryTab ? 0 : AppSpacing.subTabNavigationHeight,
              clipBehavior: Clip.hardEdge,
              decoration: const BoxDecoration(),
              child: _buildSubTabs(context, borderColor),
            ),
            Expanded(
              child: TabSwipeSwitchRegion(
                onSwipe: _handleTabSwipe,
                child: NotificationListener<ScrollNotification>(
                  onNotification: (n) {
                    _onScroll();
                    return false;
                  },
                  child: _buildActiveTabContent(
                    context,
                    fgPrimary,
                    fgSecondary,
                    borderColor,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildActiveTabContent(
    BuildContext context,
    Color fgPrimary,
    Color fgSecondary,
    Color borderColor,
  ) {
    if (_mainTabIndex != 0) {
      return _buildContactsContent(
        context,
        fgPrimary,
        fgSecondary,
        borderColor,
      );
    }
    final subTab = _messageSubTabs[_subTabIndex];
    if (subTab == UITextConstants.secretMessage) {
      return _buildSecretMessageContent(
        context,
        fgPrimary,
        fgSecondary,
        borderColor,
      );
    }
    if (ref.watch(chatInboxListEnabledProvider)) {
      return _buildInboxMessagesContent(context, fgPrimary, fgSecondary);
    }
    return _buildMessagesContent(context, fgPrimary, fgSecondary, borderColor);
  }

  Widget _buildMainTabs(
    BuildContext context,
    Color bgColor,
    Color fgPrimary,
    Color fgSecondary,
  ) {
    final tabs = <TabItem>[
      TabItem(id: 'messages', label: AppConceptConstants.messages),
      TabItem(id: 'contacts', label: AppConceptConstants.contacts),
    ];
    final activeTabId = _mainTabIndex == 0 ? 'messages' : 'contacts';

    return Container(
      height: AppSpacing.tabNavigationHeight,
      decoration: BoxDecoration(
        color: bgColor,
        border: Border(
          bottom: BorderSide(
            color: AppColorsFunctional.getColor(
              ref.read(isDarkProvider),
              ColorType.borderPrimary,
            ),
          ),
        ),
      ),
      child: Stack(
        children: [
          // Layer 1: Absolutely Centered Tabs
          Positioned.fill(
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
              onHorizontalDragEnd: _handleTabSwipeDragEnd,
              leadingActions: const [],
              trailingActions: const [],
              transparentBackground: true,
            ),
          ),
          // Layer 2: Trailing Actions
          Positioned(
            right:
                AppSpacing.feedContentHorizontal(context) -
                AppSpacing.intraGroupXs,
            top: 0,
            bottom: 0,
            child: const Center(
              child: GlobalTopActions(
                initialSearchScope: GlobalSearchScope.messages,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSubTabs(BuildContext context, Color borderColor) {
    final subTabs = _mainTabIndex == 0 ? _messageSubTabs : _contactsSubTabs;
    final useInboxList = ref.watch(chatInboxListEnabledProvider);

    Map<int, int>? numberBadges;
    Map<int, bool>? dotBadges;

    if (_mainTabIndex == 0) {
      int atMeCount = 0;
      int unreadCount = 0;
      bool hasSecretUnread = false;

      if (useInboxList) {
        final inboxItems = ref.watch(chatInboxListProvider).items;
        for (final item in inboxItems) {
          final isSecret = item.type == 'encrypted';
          if (isSecret) {
            if (item.hasUnread || item.hasMention) {
              hasSecretUnread = true;
            }
            continue;
          }
          atMeCount += item.mentionUnreadCount;
          unreadCount += item.unreadCount;
        }
      } else if (_conversations != null) {
        for (final c in _conversations!) {
          final isSecret = c['type'] == 'encrypted';
          final unread = c['unreadCount'] as int? ?? 0;
          final hasMention = c['hasMention'] == true;

          if (isSecret) {
            if (unread > 0 || hasMention) {
              hasSecretUnread = true;
            }
          } else {
            if (hasMention) {
              atMeCount += unread > 0 ? unread : 1;
            }
            unreadCount += unread;
          }
        }
      }

      numberBadges = {};
      dotBadges = {};

      final atMeIndex = _messageSubTabs.indexOf(UITextConstants.atMe);
      if (atMeIndex != -1 && atMeCount > 0) {
        numberBadges[atMeIndex] = atMeCount;
      }

      final unreadIndex = _messageSubTabs.indexOf(UITextConstants.unread);
      if (unreadIndex != -1 && unreadCount > 0) {
        numberBadges[unreadIndex] = unreadCount;
      }

      final secretIndex = _messageSubTabs.indexOf(
        UITextConstants.secretMessage,
      );
      if (secretIndex != -1 && hasSecretUnread) {
        dotBadges[secretIndex] = true;
      }
    }

    return SecondaryCapsuleTabBar(
      isDark: ref.read(isDarkProvider),
      tabs: subTabs,
      activeIndex: _subTabIndex,
      onTap: (index) => setState(() => _subTabIndex = index),
      onHorizontalDragEnd: _handleTabSwipeDragEnd,
      horizontalPadding: AppSpacing.feedContentHorizontal(context),
      border: Border(
        bottom: BorderSide(color: borderColor.withValues(alpha: 0.2)),
      ),
      numberBadges: numberBadges,
      dotBadges: dotBadges,
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
    final encrypted = ref
        .read(appContentRepositoryProvider)
        .chatEncryptedConversations;

    if (encrypted.isEmpty) {
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
              '暂无密信对话',
              style: TextStyle(fontSize: AppTypography.lg, color: fgSecondary),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      controller: _scrollController,
      itemCount: encrypted.length,
      itemBuilder: (context, i) {
        final c = encrypted[i];
        return _ConversationTile(
          conversation: c,
          isSpecial: false,
          onTap: () => context.push(AppRoutePaths.chatDetail(id: '${c['id']}')),
          fgPrimary: fgPrimary,
          fgSecondary: fgSecondary,
          borderColor: borderColor,
          showEncryptedBadge: false, // Do not show lock icon
        );
      },
    );
  }

  Widget _buildSecretLockScreen(
    BuildContext context,
    Color fgPrimary,
    Color fgSecondary,
  ) {
    final isDark = ref.read(isDarkProvider);
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: bg,
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            isDark
                ? Colors.white.withValues(alpha: 0.04)
                : Colors.black.withValues(alpha: 0.03),
            bg,
          ],
          stops: const [0.0, 0.5],
        ),
      ),
      child: SingleChildScrollView(
        padding: EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(height: AppSpacing.forty * 1.5),
            Icon(
              CupertinoIcons.lock_fill,
              size: AppSpacing.avatarUserLg,
              color: fgSecondary.withValues(alpha: 0.5),
            ),
            SizedBox(height: AppSpacing.lg),
            Text(
              UITextConstants.secretLockedTitle,
              style: TextStyle(
                fontSize: AppTypography.lg,
                fontWeight: AppTypography.semiBold,
                color: fgPrimary,
              ),
            ),
            SizedBox(height: AppSpacing.xs),
            Text(
              '输入密码以查看对话',
              style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary),
            ),
            SizedBox(height: AppSpacing.xl * 1.5),
            Padding(
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.lg),
              child: Column(
                children: [
                  CupertinoTextField(
                    controller: _secretPasswordController,
                    obscureText: !_secretShowPassword,
                    onChanged: (_) => setState(() => _secretAuthError = ''),
                    onSubmitted: (_) => _secretUnlock(),
                    placeholder: UITextConstants.secretPasswordHint,
                    placeholderStyle: TextStyle(
                      color: fgSecondary.withValues(alpha: 0.6),
                      fontSize: AppTypography.base,
                    ),
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.lg,
                      vertical: AppSpacing.md,
                    ),
                    decoration: BoxDecoration(
                      color: isDark
                          ? Colors.white.withValues(alpha: 0.06)
                          : Colors.black.withValues(alpha: 0.04),
                      borderRadius: BorderRadius.circular(
                        AppSpacing.fullBorderRadius,
                      ),
                    ),
                    suffix: CupertinoButton(
                      padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                      minimumSize: const Size(
                        AppSpacing.minInteractiveSize,
                        AppSpacing.minInteractiveSize,
                      ),
                      onPressed: () => setState(
                        () => _secretShowPassword = !_secretShowPassword,
                      ),
                      child: Icon(
                        _secretShowPassword
                            ? CupertinoIcons.eye_slash_fill
                            : CupertinoIcons.eye_fill,
                        color: fgSecondary.withValues(alpha: 0.6),
                        size: AppSpacing.iconMedium,
                      ),
                    ),
                    style: TextStyle(
                      color: fgPrimary,
                      fontSize: AppTypography.base,
                    ),
                  ),
                  if (_secretAuthError.isNotEmpty) ...[
                    SizedBox(height: AppSpacing.md),
                    Text(
                      _secretAuthError,
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: AppColors.error,
                      ),
                    ),
                  ],
                  SizedBox(height: AppSpacing.xl),
                  SizedBox(
                    width: double.infinity,
                    height: AppSpacing.buttonHeight,
                    child: CupertinoButton(
                      onPressed: () {
                        if (_secretPasswordController.text.trim().isEmpty) {
                          return;
                        }
                        _secretUnlock();
                      },
                      padding: EdgeInsets.zero,
                      color: AppColors.primaryColor,
                      borderRadius: BorderRadius.circular(
                        AppSpacing.fullBorderRadius,
                      ),
                      child: Text(
                        UITextConstants.secretUnlockButton,
                        style: TextStyle(
                          color: Colors.white,
                          fontWeight: AppTypography.semiBold,
                          fontSize: AppTypography.base,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInboxMessagesContent(
    BuildContext context,
    Color fgPrimary,
    Color fgSecondary,
  ) {
    final inboxState = ref.watch(chatInboxListProvider);
    final items = _filterInboxListForSubTab(
      inboxState.items
          .map(ChatListItemViewModel.fromDto)
          .toList(growable: false),
    );

    if (inboxState.isLoading && inboxState.items.isEmpty) {
      return Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.lg),
          child: CupertinoActivityIndicator(),
        ),
      );
    }

    if (items.isEmpty) {
      return _buildConversationEmptyState(
        fgSecondary: fgSecondary,
        subTab: _messageSubTabs[_subTabIndex],
      );
    }

    return ListView.builder(
      controller: _scrollController,
      padding: EdgeInsets.only(
        bottom:
            MediaQuery.of(context).padding.bottom + AppSpacing.bottomNavHeight,
      ),
      itemCount: items.length,
      itemBuilder: (context, index) {
        final item = items[index];
        return _InboxConversationTile(
          item: item,
          fgPrimary: fgPrimary,
          fgSecondary: fgSecondary,
          onTap: () => context.push(AppRoutePaths.chatDetail(id: item.id)),
        );
      },
    );
  }

  Widget _buildConversationEmptyState({
    required Color fgSecondary,
    required String subTab,
  }) {
    var title = UITextConstants.noConversations;
    var subtitle = UITextConstants.startChatHint;

    if (subTab == UITextConstants.atMe) {
      title = UITextConstants.noMentionsMessages;
      subtitle = UITextConstants.noMentionsHint;
    } else if (subTab == UITextConstants.unread) {
      title = UITextConstants.noUnreadMessages;
      subtitle = UITextConstants.noUnreadHint;
    }

    return Center(
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.xl),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              CupertinoIcons.chat_bubble_2,
              size: AppSpacing.iconButtonMinSizeMd,
              color: fgSecondary.withValues(alpha: 0.72),
            ),
            SizedBox(height: AppSpacing.md),
            Text(
              title,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.lg,
                fontWeight: AppTypography.medium,
                color: fgSecondary,
              ),
            ),
            SizedBox(height: AppSpacing.xs),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.base,
                color: fgSecondary.withValues(alpha: 0.82),
                height: AppTypography.lineHeightCompact,
              ),
            ),
          ],
        ),
      ),
    );
  }

  List<ChatListItemViewModel> _filterInboxListForSubTab(
    List<ChatListItemViewModel> list,
  ) {
    final sub = _messageSubTabs[_subTabIndex];
    if (sub == UITextConstants.atMe) {
      return list.where((item) => item.hasMention).toList(growable: false);
    }
    if (sub == UITextConstants.unread) {
      return list.where((item) => item.hasUnread).toList(growable: false);
    }
    return list;
  }

  Widget _buildMessagesContent(
    BuildContext context,
    Color fgPrimary,
    Color fgSecondary,
    Color borderColor,
  ) {
    final rawList = _conversations ?? const <Map<String, dynamic>>[];
    final convs = _filterConversationListForSubTab(rawList);

    if (_isLoading && rawList.isEmpty) {
      return Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.lg),
          child: CupertinoActivityIndicator(),
        ),
      );
    }

    if (convs.isEmpty) {
      final sub = _messageSubTabs[_subTabIndex];
      String title = '';
      String subtitle = '';

      if (sub == '全部') {
        title = '暂无对话';
        subtitle = '开始与圈友聊天吧！';
      } else if (sub == '@我') {
        title = '暂无@我的消息';
      } else if (sub == '未读') {
        title = '暂无未读消息';
      }

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
              title,
              style: TextStyle(fontSize: AppTypography.lg, color: fgSecondary),
            ),
            if (subtitle.isNotEmpty)
              Text(
                subtitle,
                style: TextStyle(
                  fontSize: AppTypography.md,
                  color: fgSecondary,
                ),
              ),
          ],
        ),
      );
    }

    {
      return ListView(
        controller: _scrollController,
        children: [
          ...convs.map(
            (c) => _ConversationTile(
              conversation: c,
              onTap: () =>
                  context.push(AppRoutePaths.chatDetail(id: '${c['id']}')),
              fgPrimary: fgPrimary,
              fgSecondary: fgSecondary,
              borderColor: borderColor,
            ),
          ),
          SizedBox(height: MediaQuery.of(context).padding.bottom + 80),
        ],
      );
    }
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

  Widget _buildContactsContent(
    BuildContext context,
    Color fgPrimary,
    Color fgSecondary,
    Color borderColor,
  ) {
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
    if (sub == UITextConstants.contactsTabAll ||
        sub == UITextConstants.contactsTabSameInterest) {
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
        final title =
            (item['displayName'] ?? item['name'] ?? item['title']) as String? ??
            '';
        final avatar = item['avatar'] as String? ?? '';
        final subtitle =
            (item['bio'] ?? item['metFrom'] ?? item['lastInteraction'])
                as String? ??
            '';
        return Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () {},
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
                  RoundedSquareAvatar(
                    size: AppSpacing.largeButtonSize,
                    imageUrl: avatar,
                    name: title,
                  ),
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
    '赵': 'Z',
    '钱': 'Q',
    '孙': 'S',
    '李': 'L',
    '周': 'Z',
    '吴': 'W',
    '郑': 'Z',
    '王': 'W',
    '冯': 'F',
    '陈': 'C',
    '卫': 'W',
    '蒋': 'J',
    '沈': 'S',
    '韩': 'H',
    '杨': 'Y',
    '朱': 'Z',
    '秦': 'Q',
    '许': 'X',
    '何': 'H',
    '吕': 'L',
    '施': 'S',
    '张': 'Z',
    '孔': 'K',
    '曹': 'C',
    '严': 'Y',
    '华': 'H',
    '金': 'J',
    '魏': 'W',
    '陶': 'T',
    '姜': 'J',
    '谢': 'X',
    '邹': 'Z',
    '柏': 'B',
    '窦': 'D',
    '章': 'Z',
    '云': 'Y',
    '苏': 'S',
    '潘': 'P',
    '葛': 'G',
    '奚': 'X',
    '范': 'F',
    '彭': 'P',
    '郎': 'L',
    '鲁': 'L',
    '韦': 'W',
    '马': 'M',
    '苗': 'M',
    '方': 'F',
    '俞': 'Y',
    '任': 'R',
    '袁': 'Y',
    '柳': 'L',
    '史': 'S',
    '唐': 'T',
    '罗': 'L',
    '毕': 'B',
    '郝': 'H',
    '安': 'A',
    '常': 'C',
    '乐': 'L',
    '于': 'Y',
    '时': 'S',
    '傅': 'F',
    '齐': 'Q',
    '康': 'K',
    '伍': 'W',
    '余': 'Y',
    '顾': 'G',
    '孟': 'M',
    '平': 'P',
    '黄': 'H',
    '书': 'S',
    '小': 'X',
    '大': 'D',
    '老': 'L',
    '阿': 'A',
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
      final name =
          (item['displayName'] ?? item['name'] ?? item['title']) as String? ??
          '';
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
          listChildren.add(
            Container(
              key: key,
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: 4,
              ),
              color: widget.borderColor.withValues(alpha: 0.15),
              child: Text(
                UITextConstants.starredFriends,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  fontWeight: FontWeight.w600,
                  color: widget.fgSecondary,
                ),
              ),
            ),
          );
        }
      }
      if (!starred && isFirstOfInitial) {
        sectionOffsets[initial] = pos;
        pos += _kSectionHeaderHeight;
        final key = _sectionKeys[initial];
        if (key != null) {
          listChildren.add(
            Container(
              key: key,
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: 4,
              ),
              color: widget.borderColor.withValues(alpha: 0.15),
              child: Text(
                initial,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  fontWeight: FontWeight.w600,
                  color: widget.fgSecondary,
                ),
              ),
            ),
          );
        }
      }
      lastInitial = initial;
      lastStarred = starred;
      pos += _kContactRowHeight;
      final title = item['displayName'] as String? ?? '';
      final avatar = item['avatar'] as String? ?? '';
      final subtitle =
          (item['bio'] ?? item['metFrom'] ?? item['lastInteraction'])
              as String? ??
          '';
      listChildren.add(
        Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () {},
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: 12,
              ),
              decoration: BoxDecoration(
                border: Border(
                  bottom: BorderSide(
                    color: widget.borderColor.withValues(alpha: 0.3),
                  ),
                ),
              ),
              child: Row(
                children: [
                  RoundedSquareAvatar(
                    size: AppSpacing.largeButtonSize,
                    imageUrl: avatar,
                    name: title,
                  ),
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
            if (n is ScrollUpdateNotification || n is ScrollEndNotification) {
              _onScroll();
            }
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
                        offset.clamp(
                          0.0,
                          _scrollController.position.maxScrollExtent,
                        ),
                        duration: const Duration(milliseconds: 250),
                        curve: Curves.easeOut,
                      );
                    } else {
                      final key = _sectionKeys[letter];
                      if (key?.currentContext != null) {
                        Scrollable.ensureVisible(
                          key!.currentContext!,
                          duration: const Duration(milliseconds: 250),
                          alignment: 0,
                        );
                      }
                    }
                  },
                  child: Container(
                    width: AppSpacing.twenty,
                    height: AppSpacing.twenty,
                    alignment: Alignment.center,
                    margin: EdgeInsets.symmetric(vertical: 1),
                    decoration: BoxDecoration(
                      color: isActive
                          ? AppColors.primaryColor
                          : Colors.transparent,
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

  static const double _avatarSize = 48;

  String _formatConversationTime(Map<String, dynamic> conv) {
    final isoStr =
        conv['lastMessageAt'] as String? ??
        conv['lastMessageTime'] as String? ??
        conv['updatedAt'] as String?;
    final dt = ChatTimeFormatter.tryParseServerTime(isoStr);
    if (dt == null) return '';
    return ChatTimeFormatter.formatForConversationList(dt);
  }

  Widget _buildConversationAvatar() {
    final type = conversation['type'] as String? ?? 'direct';
    final isGroup = type == 'group';

    if (isGroup) {
      final memberAvatars =
          (conversation['memberAvatars'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          <String>[];
      return GroupAvatarGrid(size: _avatarSize, avatarUrls: memberAvatars);
    }

    return RoundedSquareAvatar(
      size: _avatarSize,
      imageUrl:
          conversation['avatar'] as String? ??
          conversation['avatarUrl'] as String? ??
          '',
      name: conversation['title'] as String? ?? '',
    );
  }

  @override
  Widget build(BuildContext context) {
    final unread = conversation['unreadCount'] as int? ?? 0;
    final isEncrypted = showEncryptedBadge;
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(
              color: borderColor.withValues(alpha: 0.3),
              width: 0.5,
            ),
          ),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Stack(
              clipBehavior: Clip.none,
              children: [
                _buildConversationAvatar(),
                if (isEncrypted)
                  Positioned(
                    right: -2,
                    bottom: -2,
                    child: Container(
                      padding: EdgeInsets.all(2),
                      decoration: BoxDecoration(
                        color: AppColors.primaryColor,
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: Theme.of(context).scaffoldBackgroundColor,
                          width: 1.5,
                        ),
                      ),
                      child: Icon(Icons.lock, size: 10, color: Colors.white),
                    ),
                  ),
                if (unread > 0)
                  Positioned(
                    right: -6,
                    top: -6,
                    child: Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: unread > 9 ? 5 : 4,
                        vertical: 2,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.error,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: Theme.of(context).scaffoldBackgroundColor,
                          width: 1.5,
                        ),
                      ),
                      child: Text(
                        unread > 99 ? '99+' : '$unread',
                        style: TextStyle(
                          fontSize: 10,
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                          height: 1.1,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
            SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Row(
                          children: [
                            Flexible(
                              child: Text(
                                conversation['title'] as String? ?? '',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w500,
                                  color: fgPrimary,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            if (isSpecial) ...[
                              SizedBox(width: 4),
                              Container(
                                padding: EdgeInsets.symmetric(
                                  horizontal: 4,
                                  vertical: 2,
                                ),
                                decoration: BoxDecoration(
                                  color: AppColors.warning.withValues(
                                    alpha: 0.2,
                                  ),
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text(
                                  'AI',
                                  style: TextStyle(
                                    fontSize: 10,
                                    fontWeight: FontWeight.w800,
                                    color: AppColors.warning,
                                  ),
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                      SizedBox(width: 8),
                      Text(
                        _formatConversationTime(conversation),
                        style: TextStyle(
                          fontSize: 14,
                          color: fgSecondary.withValues(alpha: 0.8),
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: 4),
                  Row(
                    children: [
                      if (isEncrypted) ...[
                        Icon(
                          Icons.lock,
                          size: 14,
                          color: fgSecondary.withValues(alpha: 0.8),
                        ),
                        SizedBox(width: 4),
                      ],
                      Expanded(
                        child: Text(
                          conversation['lastMessage'] as String? ?? '',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 14,
                            color: fgSecondary.withValues(alpha: 0.8),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InboxConversationTile extends StatelessWidget {
  const _InboxConversationTile({
    required this.item,
    required this.onTap,
    required this.fgPrimary,
    required this.fgSecondary,
  });

  final ChatListItemViewModel item;
  final VoidCallback onTap;
  final Color fgPrimary;
  final Color fgSecondary;

  static const double _avatarSize = 52.0;

  Widget _buildAvatar() {
    if (item.isGroup) {
      return GroupAvatarGrid(
        size: _avatarSize,
        avatarUrls: item.avatarCompositeUrls,
      );
    }
    return RoundedSquareAvatar(
      size: _avatarSize,
      imageUrl: item.avatarUrl,
      name: item.title,
    );
  }

  @override
  Widget build(BuildContext context) {
    final scaffoldBackground = Theme.of(context).scaffoldBackgroundColor;
    final dividerColor = fgSecondary.withValues(alpha: 0.12);
    final subtitleColor = fgSecondary.withValues(alpha: 0.9);
    final timeColor = fgSecondary.withValues(alpha: 0.72);

    return InkWell(
      onTap: onTap,
      child: Container(
        color: item.isPinned
            ? fgSecondary.withValues(alpha: 0.04)
            : Colors.transparent,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.symmetric(
                vertical: AppSpacing.sm + AppSpacing.xs,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Stack(
                    clipBehavior: Clip.none,
                    children: [
                      _buildAvatar(),
                      if (item.hasUnread)
                        Positioned(
                          top: -4,
                          right: -4,
                          child: Container(
                            constraints: const BoxConstraints(minWidth: 20),
                            padding: EdgeInsets.symmetric(
                              horizontal: item.unreadCount > 9
                                  ? AppSpacing.xs + 1
                                  : AppSpacing.xs,
                              vertical: AppSpacing.two,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.error,
                              borderRadius: BorderRadius.circular(
                                AppSpacing.ten,
                              ),
                              border: Border.all(
                                color: scaffoldBackground,
                                width: 1.5,
                              ),
                            ),
                            child: Text(
                              item.unreadCount > 99
                                  ? '99+'
                                  : '${item.unreadCount}',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontSize: AppTypography.xs,
                                fontWeight: AppTypography.semiBold,
                                color: Colors.white,
                                height: 1,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                  SizedBox(width: AppSpacing.sm + AppSpacing.xs),
                  Expanded(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Text(
                                item.title,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: AppTypography.lg,
                                  fontWeight: AppTypography.medium,
                                  color: fgPrimary,
                                  height: AppTypography.lineHeightTight,
                                ),
                              ),
                            ),
                            SizedBox(width: AppSpacing.sm),
                            ConstrainedBox(
                              constraints: const BoxConstraints(minWidth: 64),
                              child: Text(
                                item.timeLabel,
                                textAlign: TextAlign.right,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: AppTypography.base,
                                  color: timeColor,
                                  height: AppTypography.lineHeightTight,
                                ),
                              ),
                            ),
                          ],
                        ),
                        SizedBox(height: AppSpacing.xs),
                        Row(
                          children: [
                            if (item.previewIcon != null) ...[
                              Icon(
                                item.previewIcon,
                                size: AppSpacing.fourteen,
                                color: subtitleColor,
                              ),
                              SizedBox(width: AppSpacing.xs),
                            ],
                            Expanded(
                              child: Text(
                                item.subtitle,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: AppTypography.base,
                                  color: subtitleColor,
                                  height: AppTypography.lineHeightCompact,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: EdgeInsets.only(
                left: _avatarSize + AppSpacing.sm + AppSpacing.xs,
              ),
              child: Divider(
                height: 0,
                thickness: AppSpacing.hairline,
                color: dividerColor,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
