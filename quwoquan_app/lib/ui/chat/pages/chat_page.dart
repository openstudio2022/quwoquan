// ignore_for_file: unnecessary_underscores

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/avatar/conversation_avatar.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/cloud/services/user/greeting_repository.dart';
import 'package:quwoquan_app/ui/chat/models/chat_contacts_row.dart';
import 'package:quwoquan_app/ui/chat/models/chat_list_item_view_model.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_contacts_rows_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/message_home_rows_provider.dart';
import 'package:quwoquan_app/ui/chat/widgets/chat_conversation_avatar_tokens.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page_visit_recorder.dart';

final chatGreetingInboxProvider = FutureProvider.autoDispose
    .family<List<GreetingRequestDto>, int>((ref, limit) async {
      return ref.read(greetingRepositoryProvider).listInbox(limit: limit);
    });

class ChatPage extends ConsumerStatefulWidget {
  const ChatPage({super.key});

  @override
  ConsumerState<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends ConsumerState<ChatPage>
    with AutomaticKeepAliveClientMixin {
  int _mainTabIndex = 0;
  int _subTabIndex = 0;
  bool _hideSecondaryTab = false;
  final ScrollController _scrollController = ScrollController();
  double _lastScrollY = 0;
  @override
  bool get wantKeepAlive => true;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => mounted
          ? recordChatPageVisit(ref, _mainTabIndex, _subTabIndex)
          : null,
    );
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  static const List<String> _messageSubTabs = [
    UITextConstants.contactsTabAll,
    UITextConstants.unread,
    UITextConstants.groupChat,
    UITextConstants.chatPrivateMessages,
    UITextConstants.chatNotifications,
  ];
  static const List<String> _contactsSubTabs = [
    UITextConstants.contactsTabAll,
    UITextConstants.contactsTabMutualFollow,
    UITextConstants.contactsTabCircles,
    UITextConstants.contactsTabGroups,
  ];
  void _onScroll() {
    final y = _scrollController.hasClients ? _scrollController.offset : 0.0;
    if (y > 50) {
      final diff = y - _lastScrollY;
      if (diff > 5 && !_hideSecondaryTab) {
        setState(() => _hideSecondaryTab = true);
      } else if (diff < -5 && _hideSecondaryTab) {
        setState(() => _hideSecondaryTab = false);
      }
    } else if (_hideSecondaryTab) {
      setState(() => _hideSecondaryTab = false);
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
    recordChatPageVisit(ref, _mainTabIndex, _subTabIndex);
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
    recordChatPageVisit(ref, _mainTabIndex, _subTabIndex);
    return true;
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final safeTop = MediaQuery.viewPaddingOf(context).top;
    final effectiveTopInset = AppSpacing.appChromeTopSafeInset(
      safeTop,
      context,
    );
    final isDark = ref.watch(isDarkProvider);
    final bgColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.pageBackground,
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
      ColorType.separatorSubtle,
    );
    final listItemBackground =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final listDividerColor =
        SettingsSemanticConstants.conversationSheetDividerColor(
          isDark,
        ).withValues(alpha: 0.9);

    return AppScaffold(
      backgroundColor: bgColor,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(height: effectiveTopInset),
          _buildMainTabs(context, bgColor, fgPrimary, fgSecondary),
          AnimatedContainer(
            key: const ValueKey<String>('chat-secondary-tabs-slot'),
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeInOut,
            height: _hideSecondaryTab ? 0 : AppSpacing.subTabNavigationHeight,
            clipBehavior: Clip.hardEdge,
            decoration: BoxDecoration(color: bgColor),
            child: _buildSubTabs(context),
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
                  listItemBackground,
                  listDividerColor,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActiveTabContent(
    BuildContext context,
    Color fgPrimary,
    Color fgSecondary,
    Color borderColor,
    Color listItemBackground,
    Color listDividerColor,
  ) {
    if (_mainTabIndex != 0) {
      return _buildContactsContent(
        context,
        fgPrimary,
        fgSecondary,
        borderColor,
        listItemBackground,
        listDividerColor,
      );
    }
    return _buildInboxMessagesContent(
      context,
      fgPrimary,
      fgSecondary,
      listItemBackground,
      listDividerColor,
    );
  }

  Widget _buildMainTabs(
    BuildContext context,
    Color bgColor,
    Color fgPrimary,
    Color fgSecondary,
  ) {
    final tabs = <TabItem>[
      TabItem(id: 'messages', label: AppConceptConstants.messages),
      TabItem(id: 'contacts', label: UITextConstants.chatPrimaryContacts),
    ];
    final activeTabId = _mainTabIndex == 0 ? 'messages' : 'contacts';

    return Container(
      key: const ValueKey<String>('chat-main-tabs-chrome'),
      height: AppSpacing.appChromeTopBarHeight(context),
      decoration: BoxDecoration(color: bgColor),
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
                recordChatPageVisit(ref, _mainTabIndex, _subTabIndex);
              },
              onHorizontalDragEnd: _handleTabSwipeDragEnd,
              leadingActions: const [],
              trailingActions: const [],
              transparentBackground: true,
            ),
          ),
          // Layer 2: Trailing Actions
          Positioned(
            right: AppSpacing.topBarTrailingAssistantButtonInset(context),
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

  Widget _buildSubTabs(BuildContext context) {
    final subTabs = _mainTabIndex == 0 ? _messageSubTabs : _contactsSubTabs;

    Map<int, int>? numberBadges;
    Map<int, bool>? dotBadges;

    if (_mainTabIndex == 0) {
      int unreadCount = 0;

      final inboxItems = ref.watch(chatInboxListProvider).items;
      for (final item in inboxItems) {
        final isSecret = item.type == 'encrypted';
        if (isSecret) {
          continue;
        }
        unreadCount += item.unreadCount;
      }

      numberBadges = {};
      dotBadges = {};

      final unreadIndex = _messageSubTabs.indexOf(UITextConstants.unread);
      if (unreadIndex != -1 && unreadCount > 0) {
        numberBadges[unreadIndex] = unreadCount;
      }
    }

    return SecondaryCapsuleTabBar(
      key: const ValueKey<String>('chat-secondary-capsule-tabs'),
      isDark: ref.read(isDarkProvider),
      tabs: subTabs,
      activeIndex: _subTabIndex,
      onTap: (index) {
        setState(() => _subTabIndex = index);
        recordChatPageVisit(ref, _mainTabIndex, _subTabIndex);
      },
      onHorizontalDragEnd: _handleTabSwipeDragEnd,
      horizontalPadding: AppSpacing.feedContentHorizontal(context),
      numberBadges: numberBadges,
      dotBadges: dotBadges,
    );
  }

  Widget _buildInboxMessagesContent(
    BuildContext context,
    Color fgPrimary,
    Color fgSecondary,
    Color listItemBackground,
    Color listDividerColor,
  ) {
    final messageFilter = _messageHomeFilterForSubTab(
      _messageSubTabs[_subTabIndex],
    );
    final messageRows = ref.watch(messageHomeRowsProvider(messageFilter));
    final greetingInbox = ref.watch(chatGreetingInboxProvider(20));
    final pendingGreetings = greetingInbox.maybeWhen(
      data: (items) =>
          items.where((greeting) => greeting.isPending).toList(growable: false),
      orElse: () => const <GreetingRequestDto>[],
    );
    final shouldShowGreetingInbox =
        _subTabIndex == 0 && pendingGreetings.isNotEmpty;
    final items = messageRows.maybeWhen(
      data: (rows) => rows,
      orElse: () => const <ChatListItemViewModel>[],
    );

    final isLoading = messageRows.maybeWhen(
      loading: () => true,
      orElse: () => false,
    );
    final rowError = messageRows.maybeWhen(
      error: (error, _) => error,
      orElse: () => null,
    );

    if (isLoading && items.isEmpty && greetingInbox.isLoading) {
      return Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.lg),
          child: CupertinoActivityIndicator(),
        ),
      );
    }

    if (rowError != null && items.isEmpty) {
      return AppPageErrorState(
        semantic: runtimeErrorSemantic(
          context,
          error: rowError,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            ref.invalidate(messageHomeRowsProvider(messageFilter));
          }
        },
      );
    }

    if (items.isEmpty && !shouldShowGreetingInbox) {
      return _buildConversationEmptyState(
        fgSecondary: fgSecondary,
        subTab: _messageSubTabs[_subTabIndex],
      );
    }

    return ListView.builder(
      controller: _scrollController,
      padding: EdgeInsets.only(
        bottom:
            MediaQuery.viewPaddingOf(context).bottom +
            AppSpacing.bottomNavBarHeight(context),
      ),
      itemCount: items.length + (shouldShowGreetingInbox ? 1 : 0),
      itemBuilder: (context, index) {
        if (shouldShowGreetingInbox && index == 0) {
          return _GreetingInboxTile(
            pendingCount: pendingGreetings.length,
            latest: pendingGreetings.first,
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
            backgroundColor: listItemBackground,
            dividerColor: listDividerColor,
            onTap: () => _showGreetingInboxSheet(context, pendingGreetings),
          );
        }
        final itemIndex = shouldShowGreetingInbox ? index - 1 : index;
        final item = items[itemIndex];
        return _InboxConversationTile(
          item: item,
          fgPrimary: fgPrimary,
          fgSecondary: fgSecondary,
          backgroundColor: listItemBackground,
          dividerColor: listDividerColor,
          onTap: () {
            if (item.isNotification) {
              return;
            }
            context.push(AppRoutePaths.chatDetail(id: item.id));
          },
        );
      },
    );
  }

  void _showGreetingInboxSheet(
    BuildContext context,
    List<GreetingRequestDto> greetings,
  ) {
    showCupertinoModalPopup<void>(
      context: context,
      builder: (sheetContext) => _GreetingInboxSheet(
        greetings: greetings,
        onReply: (request) async {
          final result = await ref
              .read(greetingRepositoryProvider)
              .replyGreeting(request.id);
          ref.invalidate(chatGreetingInboxProvider);
          if (!context.mounted) {
            return;
          }
          Navigator.of(sheetContext).pop();
          final conversationId = result.conversationId.trim();
          if (conversationId.isNotEmpty) {
            context.push(AppRoutePaths.chatDetail(id: conversationId));
          }
        },
        onIgnore: (request) async {
          await ref.read(greetingRepositoryProvider).ignoreGreeting(request.id);
          ref.invalidate(chatGreetingInboxProvider);
          if (sheetContext.mounted) {
            Navigator.of(sheetContext).pop();
          }
        },
      ),
    );
  }

  Widget _buildConversationEmptyState({
    required Color fgSecondary,
    required String subTab,
  }) {
    var title = UITextConstants.noConversations;
    var subtitle = UITextConstants.startChatHint;

    if (subTab == UITextConstants.unread) {
      title = UITextConstants.noUnreadMessages;
      subtitle = UITextConstants.noUnreadHint;
    } else if (subTab == UITextConstants.groupChat) {
      title = '暂无群聊消息';
      subtitle = '加入群聊后的最近动态会出现在这里';
    } else if (subTab == UITextConstants.chatPrivateMessages) {
      title = '暂无私聊消息';
      subtitle = '与互关用户或已建立连接的人交流后会出现在这里';
    } else if (subTab == UITextConstants.chatNotifications) {
      title = UITextConstants.noReminderMessages;
      subtitle = UITextConstants.noReminderHint;
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
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
                color: fgSecondary,
              ),
            ),
            SizedBox(height: AppSpacing.xs),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: fgSecondary.withValues(alpha: 0.82),
                height: AppTypography.lineHeightCompact,
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _messageHomeFilterForSubTab(String subTab) {
    return switch (subTab) {
      UITextConstants.unread => 'unread',
      UITextConstants.groupChat => 'group',
      UITextConstants.chatPrivateMessages => 'direct',
      UITextConstants.chatNotifications => 'notification',
      _ => 'all',
    };
  }

  Widget _buildContactsContent(
    BuildContext context,
    Color fgPrimary,
    Color fgSecondary,
    Color borderColor,
    Color listItemBackground,
    Color listDividerColor,
  ) {
    final sub = _contactsSubTabs[_subTabIndex];
    final asyncRows = ref.watch(chatContactsRowsForSubTabProvider(sub));
    return asyncRows.when(
      data: (list) {
        if (list.isEmpty) {
          return Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  CupertinoIcons.person_2,
                  size: AppSpacing.iconButtonMinSizeMd,
                  color: fgSecondary,
                ),
                SizedBox(height: AppSpacing.md),
                Text(
                  UITextConstants.noData,
                  style: TextStyle(
                    fontSize: AppTypography.iosTitle3,
                    color: fgSecondary,
                  ),
                ),
                SizedBox(height: AppSpacing.xs),
                Text(
                  sub,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: fgSecondary.withValues(alpha: 0.8),
                  ),
                ),
              ],
            ),
          );
        }
        if (sub == UITextConstants.contactsTabAll ||
            sub == UITextConstants.contactsTabMutualFollow) {
          return _ContactsListWithIndex(
            items: list,
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
            borderColor: borderColor,
            rowBackgroundColor: listItemBackground,
            rowDividerColor: listDividerColor,
            sectionBandColor:
                SettingsSemanticConstants.conversationSheetPanelBackground(
                  ref.read(isDarkProvider),
                ),
          );
        }
        return ListView.builder(
          itemCount: list.length,
          itemBuilder: (context, i) {
            final row = list[i];
            return CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: Size.zero,
              onPressed: () => row.open(context),
              child: Container(
                key: ValueKey<String>('chat-contact-row-${row.id}'),
                color: listItemBackground,
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
                          row.kind == ChatContactsRowKind.group
                              ? ConversationAvatar(
                                  conversationId: row.conversationId ?? row.id,
                                  conversationType: 'group',
                                  title: row.displayName,
                                  avatarUrl: row.avatarUrl,
                                  size: _kContactAvatarSize,
                                )
                              : RoundedSquareAvatar(
                                  size: _kContactAvatarSize,
                                  imageUrl: row.avatarUrl,
                                  name: row.displayName,
                                ),
                          SizedBox(
                            width: ChatConversationAvatarTokens.leadingGap,
                          ),
                          Expanded(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  row.displayName,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                    fontSize: AppTypography.iosBody,
                                    fontWeight: AppTypography.regular,
                                    color: fgPrimary,
                                    height: AppTypography.lineHeightTight,
                                  ),
                                ),
                                if (row.subtitle.isNotEmpty) ...[
                                  SizedBox(height: AppSpacing.xs),
                                  Text(
                                    row.subtitle,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: AppTypography.iosFootnote,
                                      color: fgSecondary.withValues(alpha: 0.9),
                                      height: AppTypography.lineHeightCompact,
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                    Padding(
                      padding: EdgeInsets.only(
                        left: ChatConversationAvatarTokens.dividerInset(
                          _kContactAvatarSize,
                        ),
                      ),
                      child: Divider(
                        key: ValueKey<String>(
                          'chat-contact-row-divider-${row.id}',
                        ),
                        height: AppSpacing.one,
                        thickness: AppSpacing.hairline,
                        color: listDividerColor,
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
      loading: () => const Center(child: CupertinoActivityIndicator()),
      error: (error, _) => AppPageErrorState(
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            ref.invalidate(chatContactsRowsForSubTabProvider(sub));
          }
        },
      ),
    );
  }
}

class _ContactsListWithIndex extends StatefulWidget {
  const _ContactsListWithIndex({
    required this.items,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.borderColor,
    required this.rowBackgroundColor,
    required this.rowDividerColor,
    required this.sectionBandColor,
  });

  final List<ChatContactsRow> items;
  final Color fgPrimary;
  final Color fgSecondary;
  final Color borderColor;
  final Color rowBackgroundColor;
  final Color rowDividerColor;
  final Color sectionBandColor;

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

const double _kSectionHeaderHeight = AppSpacing.twenty;
const double _kContactRowHeight = 56;
const double _kContactAvatarSize = ChatConversationAvatarTokens.listSize;

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
    final sorted = List<ChatContactsRow>.from(widget.items);
    sorted.sort((a, b) {
      final starA = a.isStarred ? 1 : 0;
      final starB = b.isStarred ? 1 : 0;
      if (starB != starA) return starB.compareTo(starA);
      final ia = _getInitial(a.displayName);
      final ib = _getInitial(b.displayName);
      if (ia != ib) return ia.compareTo(ib);
      return a.displayName.compareTo(b.displayName);
    });
    final withInitial = <(ChatContactsRow row, String initial)>[];
    for (final row in sorted) {
      withInitial.add((row, _getInitial(row.displayName)));
    }
    final initials = <String>{};
    for (final (_, ini) in withInitial) {
      initials.add(ini);
    }
    final hasStarred = sorted.any((r) => r.isStarred);
    final allInitials = <String>[];
    if (hasStarred) allInitials.add('★');
    allInitials.addAll(initials.toList()..sort());
    for (final letter in allInitials) {
      _sectionKeys.putIfAbsent(letter, () => GlobalKey());
    }

    final listIsDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final activeIndexLetterColor = AppColorsFunctional.getColor(
      listIsDark,
      ColorType.selectionForeground,
    );

    final listChildren = <Widget>[];
    final sectionOffsets = <String, double>{};
    double pos = 0;
    String? lastInitial;
    bool lastStarred = false;
    for (final (row, initial) in withInitial) {
      final starred = row.isStarred;
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
              height: _kSectionHeaderHeight,
              alignment: Alignment.centerLeft,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
              color: widget.sectionBandColor,
              child: Text(
                key: const ValueKey<String>('chat-contact-section-label-star'),
                UITextConstants.starredFriends,
                style: TextStyle(
                  fontSize: AppTypography.xs,
                  fontWeight: AppTypography.semiBold,
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
              height: _kSectionHeaderHeight,
              alignment: Alignment.centerLeft,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
              color: widget.sectionBandColor,
              child: Text(
                key: ValueKey<String>('chat-contact-section-label-$initial'),
                initial,
                style: TextStyle(
                  fontSize: AppTypography.xs,
                  fontWeight: AppTypography.semiBold,
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
      final title = row.displayName;
      final avatar = row.avatarUrl;
      final subtitle = row.subtitle;
      listChildren.add(
        CupertinoButton(
          padding: EdgeInsets.zero,
          minimumSize: Size.zero,
          onPressed: () => row.open(context),
          child: Container(
            key: ValueKey<String>('chat-contact-row-${row.id}'),
            color: widget.rowBackgroundColor,
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
                      RoundedSquareAvatar(
                        size: _kContactAvatarSize,
                        imageUrl: avatar,
                        name: title,
                      ),
                      SizedBox(width: ChatConversationAvatarTokens.leadingGap),
                      Expanded(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    title,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: AppTypography.iosBody,
                                      fontWeight: AppTypography.regular,
                                      color: widget.fgPrimary,
                                      height: AppTypography.lineHeightTight,
                                    ),
                                  ),
                                ),
                                if (starred) ...[
                                  SizedBox(width: AppSpacing.xs),
                                  Icon(
                                    CupertinoIcons.star_fill,
                                    size: AppSpacing.iconSmall,
                                    color: AppColors.warning,
                                  ),
                                ],
                              ],
                            ),
                            if (subtitle.isNotEmpty) ...[
                              SizedBox(height: AppSpacing.xs),
                              Text(
                                subtitle,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: AppTypography.iosFootnote,
                                  color: widget.fgSecondary.withValues(
                                    alpha: 0.9,
                                  ),
                                  height: AppTypography.lineHeightCompact,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                Padding(
                  padding: EdgeInsets.only(
                    left: ChatConversationAvatarTokens.dividerInset(
                      _kContactAvatarSize,
                    ),
                  ),
                  child: Divider(
                    key: ValueKey<String>('chat-contact-row-divider-${row.id}'),
                    height: AppSpacing.one,
                    thickness: AppSpacing.hairline,
                    color: widget.rowDividerColor,
                  ),
                ),
              ],
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
            padding: EdgeInsets.zero,
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
                return CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: () {
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
                    key: ValueKey<String>('chat-contact-index-letter-$letter'),
                    width: AppSpacing.twenty,
                    height: AppSpacing.twenty,
                    alignment: Alignment.center,
                    margin: EdgeInsets.symmetric(vertical: 1),
                    child: Text(
                      letter,
                      style: TextStyle(
                        fontSize: AppTypography.xs,
                        fontWeight: AppTypography.semiBold,
                        color: isActive
                            ? activeIndexLetterColor
                            : widget.fgSecondary,
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

class _InboxConversationTile extends StatelessWidget {
  const _InboxConversationTile({
    required this.item,
    required this.onTap,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.backgroundColor,
    required this.dividerColor,
  });

  final ChatListItemViewModel item;
  final VoidCallback onTap;
  final Color fgPrimary;
  final Color fgSecondary;
  final Color backgroundColor;
  final Color dividerColor;

  static const double _avatarSize = ChatConversationAvatarTokens.listSize;

  Widget _buildAvatar(BuildContext context) {
    return ConversationAvatar(
      conversationId: item.id,
      conversationType: item.isGroup ? 'group' : 'direct',
      title: item.title,
      avatarUrl: item.avatarUrl,
      groupAvatarVersion: item.groupAvatarVersion,
      size: _avatarSize,
    );
  }

  @override
  Widget build(BuildContext context) {
    final inboxTileIsDark =
        CupertinoTheme.of(context).brightness == Brightness.dark;
    final onAccentFg = AppColorsFunctional.getColor(
      inboxTileIsDark,
      ColorType.badgeForeground,
    );
    final subtitleColor = fgSecondary.withValues(alpha: 0.9);
    final timeColor = fgSecondary.withValues(alpha: 0.72);
    final rowBackground = item.isPinned
        ? Color.alphaBlend(fgSecondary.withValues(alpha: 0.04), backgroundColor)
        : backgroundColor;

    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        key: ValueKey<String>('chat-inbox-row-${item.id}'),
        color: rowBackground,
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
                      _buildAvatar(context),
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
                                color: rowBackground,
                                width: AppSpacing.oneHalf,
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
                                color: onAccentFg,
                                height: AppTypography.lineHeightTight,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                  SizedBox(width: ChatConversationAvatarTokens.leadingGap),
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
                                  fontSize: AppTypography.iosBody,
                                  fontWeight: AppTypography.regular,
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
                                  fontSize: AppTypography.iosFootnote,
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
                                  fontSize: AppTypography.iosFootnote,
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
                left: ChatConversationAvatarTokens.dividerInset(_avatarSize),
              ),
              child: Divider(
                key: ValueKey<String>('chat-inbox-row-divider-${item.id}'),
                height: AppSpacing.one,
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

class _GreetingInboxTile extends StatelessWidget {
  const _GreetingInboxTile({
    required this.pendingCount,
    required this.latest,
    required this.fgPrimary,
    required this.fgSecondary,
    required this.backgroundColor,
    required this.dividerColor,
    required this.onTap,
  });

  final int pendingCount;
  final GreetingRequestDto latest;
  final Color fgPrimary;
  final Color fgSecondary;
  final Color backgroundColor;
  final Color dividerColor;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final message = latest.requestMessage?.trim();
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        color: backgroundColor,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.symmetric(
                vertical: AppSpacing.sm + AppSpacing.xs,
              ),
              child: Row(
                children: [
                  RoundedSquareAvatar(
                    size: ChatConversationAvatarTokens.listSize,
                    imageUrl: '',
                    name: UITextConstants.chatGreetingInboxTitle,
                    backgroundColor: AppColors.primaryColor.withValues(
                      alpha: 0.12,
                    ),
                  ),
                  SizedBox(width: ChatConversationAvatarTokens.leadingGap),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          pendingCount > 1
                              ? '${UITextConstants.chatGreetingInboxTitle}（$pendingCount）'
                              : UITextConstants.chatGreetingInboxTitle,
                          style: TextStyle(
                            fontSize: AppTypography.iosBody,
                            fontWeight: AppTypography.semiBold,
                            color: fgPrimary,
                          ),
                        ),
                        SizedBox(height: AppSpacing.xs),
                        Text(
                          message != null && message.isNotEmpty
                              ? message
                              : '有人想和你建立正式会话',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosFootnote,
                            color: fgSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Icon(
                    CupertinoIcons.chevron_forward,
                    size: AppSpacing.iconSmall,
                    color: fgSecondary,
                  ),
                ],
              ),
            ),
            Padding(
              padding: EdgeInsets.only(
                left: ChatConversationAvatarTokens.dividerInset(
                  ChatConversationAvatarTokens.listSize,
                ),
              ),
              child: Divider(
                height: AppSpacing.one,
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

class _GreetingInboxSheet extends StatelessWidget {
  const _GreetingInboxSheet({
    required this.greetings,
    required this.onReply,
    required this.onIgnore,
  });

  final List<GreetingRequestDto> greetings;
  final Future<void> Function(GreetingRequestDto request) onReply;
  final Future<void> Function(GreetingRequestDto request) onIgnore;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return SafeArea(
      top: false,
      child: Container(
        height: MediaQuery.sizeOf(context).height * 0.72,
        decoration: BoxDecoration(
          color: SettingsSemanticConstants.pageBackground(isDark),
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(AppSpacing.radiusTwenty),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerMd,
                AppSpacing.lg,
                AppSpacing.containerMd,
                AppSpacing.sm,
              ),
              child: Text(
                UITextConstants.chatGreetingInboxTitle,
                style: TextStyle(
                  color: fgPrimary,
                  fontSize: AppTypography.iosTitle3,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
            Expanded(
              child: ListView.separated(
                padding: EdgeInsets.all(AppSpacing.containerMd),
                itemCount: greetings.length,
                separatorBuilder: (_, _) => SizedBox(height: AppSpacing.sm),
                itemBuilder: (context, index) {
                  final request = greetings[index];
                  final message = request.requestMessage?.trim();
                  return DecoratedBox(
                    decoration: BoxDecoration(
                      color: SettingsSemanticConstants.blockBackground(isDark),
                      borderRadius: BorderRadius.circular(
                        AppSpacing.radiusTwenty,
                      ),
                    ),
                    child: Padding(
                      padding: EdgeInsets.all(AppSpacing.md),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(
                            request.requesterSubAccountId,
                            style: TextStyle(
                              color: fgPrimary,
                              fontSize: AppTypography.iosBody,
                              fontWeight: AppTypography.semiBold,
                            ),
                          ),
                          if (message != null && message.isNotEmpty) ...[
                            SizedBox(height: AppSpacing.xs),
                            Text(
                              message,
                              style: TextStyle(
                                color: fgSecondary,
                                fontSize: AppTypography.iosFootnote,
                              ),
                            ),
                          ],
                          SizedBox(height: AppSpacing.md),
                          Row(
                            children: [
                              Expanded(
                                child: CupertinoButton(
                                  padding: EdgeInsets.symmetric(
                                    vertical: AppSpacing.sm,
                                  ),
                                  color: AppColors.primaryColor,
                                  onPressed: () => onReply(request),
                                  child: Text(
                                    UITextConstants.chatGreetingInboxReply,
                                  ),
                                ),
                              ),
                              SizedBox(width: AppSpacing.sm),
                              CupertinoButton(
                                padding: EdgeInsets.symmetric(
                                  horizontal: AppSpacing.md,
                                  vertical: AppSpacing.sm,
                                ),
                                onPressed: () => onIgnore(request),
                                child: Text(
                                  UITextConstants.chatGreetingInboxIgnore,
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
