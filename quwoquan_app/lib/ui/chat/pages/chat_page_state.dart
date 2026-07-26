part of 'chat_page.dart';

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
    ChatText.contactsTabAll,
    ChatText.unread,
    ChatText.groupChat,
    ChatText.chatPrivateMessages,
    ChatText.chatNotifications,
  ];
  static const List<String> _contactsSubTabs = [
    ChatText.contactsTabAll,
    ChatText.contactsTabMutualFollow,
    ChatText.contactsTabCircles,
    ChatText.contactsTabGroups,
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
      TabItem(id: 'contacts', label: ChatText.chatPrimaryContacts),
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
      final unreadCount = ref
          .watch(messageHomeRowsStateProvider('unread'))
          .maybeWhen(
            data: (state) => totalUnreadMessages(state.items),
            orElse: () => null,
          );

      numberBadges = {};
      dotBadges = {};

      final unreadIndex = _messageSubTabs.indexOf(ChatText.unread);
      if (unreadIndex != -1 && unreadCount != null && unreadCount > 0) {
        numberBadges[unreadIndex] = unreadCount;
      }
      final notificationUnread = ref
          .watch(appMessageUnreadCountProvider)
          .maybeWhen(data: (count) => count, orElse: () => 0);
      final notificationIndex = _messageSubTabs.indexOf(
        ChatText.chatNotifications,
      );
      if (notificationIndex != -1 && notificationUnread > 0) {
        numberBadges[notificationIndex] = notificationUnread;
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
    if (messageFilter == 'notification') {
      return _buildNotificationInboxContent(
        context,
        fgPrimary,
        fgSecondary,
        listItemBackground,
        listDividerColor,
      );
    }
    final messageRows = ref.watch(messageHomeRowsStateProvider(messageFilter));
    final greetingInbox = ref.watch(chatGreetingInboxProvider(20));
    final pendingGreetings = greetingInbox.maybeWhen(
      data: (items) =>
          items.where((greeting) => greeting.isPending).toList(growable: false),
      orElse: () => const <GreetingRequestDto>[],
    );
    final shouldShowGreetingInbox =
        _subTabIndex == 0 && pendingGreetings.isNotEmpty;
    final items = messageRows.maybeWhen(
      data: (state) => state.items,
      orElse: () => const <ChatListItemViewModel>[],
    );
    final rowsState = messageRows.value;
    final cacheFallbackError = rowsState?.cacheFallbackError;
    final shouldShowCacheFallback = cacheFallbackError != null;

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
        semantic: _chatListBlockingErrorSemantic(context, rowError),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            ref.invalidate(messageHomeRowsStateProvider(messageFilter));
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
      itemCount:
          items.length +
          (shouldShowGreetingInbox ? 1 : 0) +
          (shouldShowCacheFallback ? 1 : 0),
      itemBuilder: (context, index) {
        if (shouldShowCacheFallback && index == 0) {
          return AppTransientErrorNotice(
            semantic: _chatListCacheFallbackSemantic(
              context,
              cacheFallbackError,
            ),
          );
        }
        final adjustedIndex = shouldShowCacheFallback ? index - 1 : index;
        if (shouldShowGreetingInbox && adjustedIndex == 0) {
          return _GreetingInboxTile(
            pendingCount: pendingGreetings.length,
            latest: pendingGreetings.first,
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
            backgroundColor: listItemBackground,
            dividerColor: listDividerColor,
            onTap: () => context.push(AppRoutePaths.greetingInbox),
          );
        }
        final itemIndex = shouldShowGreetingInbox
            ? adjustedIndex - 1
            : adjustedIndex;
        final item = items[itemIndex];
        return _InboxConversationTile(
          item: item,
          fgPrimary: fgPrimary,
          fgSecondary: fgSecondary,
          backgroundColor: listItemBackground,
          dividerColor: listDividerColor,
          onTap: () {
            context.push(AppRoutePaths.chatDetail(id: item.id));
          },
        );
      },
    );
  }

  Widget _buildNotificationInboxContent(
    BuildContext context,
    Color fgPrimary,
    Color fgSecondary,
    Color listItemBackground,
    Color listDividerColor,
  ) {
    final inbox = ref.watch(notificationInboxProvider);
    return inbox.when(
      loading: () => Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.lg),
          child: CupertinoActivityIndicator(),
        ),
      ),
      error: (error, _) => AppPageErrorState(
        semantic: _chatListBlockingErrorSemantic(context, error),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            ref.invalidate(notificationInboxProvider);
          }
        },
      ),
      data: (messages) {
        if (messages.isEmpty) {
          return _buildConversationEmptyState(
            fgSecondary: fgSecondary,
            subTab: ChatText.chatNotifications,
          );
        }
        return ListView.builder(
          controller: _scrollController,
          padding: EdgeInsets.only(
            bottom:
                MediaQuery.viewPaddingOf(context).bottom +
                AppSpacing.bottomNavBarHeight(context),
          ),
          itemCount: messages.length,
          itemBuilder: (context, index) {
            final message = messages[index];
            return _NotificationInboxTile(
              message: message,
              fgPrimary: fgPrimary,
              fgSecondary: fgSecondary,
              backgroundColor: listItemBackground,
              dividerColor: listDividerColor,
              onTap: () => _openNotificationMessage(context, message),
            );
          },
        );
      },
    );
  }

  Future<void> _openNotificationMessage(
    BuildContext context,
    AppMessage message,
  ) async {
    unawaited(
      ref
          .read(journeyEventTrackerProvider)
          .trackAction(
            journey: 'notification_inbox',
            action: 'notification_row_tap',
            pageName: 'chat_list',
            targetType: message.target.targetType,
            targetKey: message.messageId,
          ),
    );
    final navigation = AppMessageNavigationTarget.fromMessage(message);
    if (navigation != null && context.mounted) {
      context.push(navigation.location);
    }
    if (!message.read) {
      try {
        await markAppMessageReadAndRefresh(ref, message.messageId);
      } catch (error, stackTrace) {
        developer.log(
          'mark app message read failed',
          name: 'notification_inbox',
          error: error,
          stackTrace: stackTrace,
        );
      }
    }
  }

  UiErrorSemantic _chatListBlockingErrorSemantic(
    BuildContext context,
    Object error,
  ) {
    final base = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
    return UiErrorSemantic(
      category: base.category,
      scope: base.scope,
      title: ChatText.chatListLoadFailedTitle,
      message: ChatText.chatListLoadFailedMessage,
      secondaryMessage: base.secondaryMessage,
      primaryAction: base.primaryAction,
      secondaryAction: base.secondaryAction,
      dismissible: base.dismissible,
      sourceCode: base.sourceCode,
      failureKind: base.failureKind,
      copyKey: 'chatListLoadFailedTitle',
      recoveryAction: base.recoveryAction,
      presentation: base.presentation,
      tone: base.tone,
    );
  }

  UiErrorSemantic _chatListCacheFallbackSemantic(
    BuildContext context,
    Object error,
  ) {
    final base = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.backgroundAction,
      scope: UiErrorScope.section,
      allowRetry: false,
      presentation: UiErrorPresentation.transientNotice,
    );
    return UiErrorSemantic(
      category: base.category,
      scope: base.scope,
      title: ChatText.chatListLoadFailedTitle,
      message: ChatText.chatListCacheFallback,
      secondaryMessage: base.secondaryMessage,
      primaryAction: base.primaryAction,
      secondaryAction: base.secondaryAction,
      dismissible: base.dismissible,
      sourceCode: base.sourceCode,
      failureKind: base.failureKind,
      copyKey: 'chatListCacheFallback',
      recoveryAction: base.recoveryAction,
      presentation: base.presentation,
      tone: UiErrorTone.caution,
    );
  }

  Widget _buildConversationEmptyState({
    required Color fgSecondary,
    required String subTab,
  }) {
    var title = ChatText.noConversations;
    var subtitle = ChatText.startChatHint;

    if (subTab == ChatText.unread) {
      title = ChatText.noUnreadMessages;
      subtitle = ChatText.noUnreadHint;
    } else if (subTab == ChatText.groupChat) {
      title = ChatText.chatEmptyGroupTitle;
      subtitle = ChatText.chatEmptyGroupSubtitle;
    } else if (subTab == ChatText.chatPrivateMessages) {
      title = ChatText.chatEmptyDirectTitle;
      subtitle = ChatText.chatEmptyDirectSubtitle;
    } else if (subTab == ChatText.chatNotifications) {
      title = ChatText.noReminderMessages;
      subtitle = ChatText.noReminderHint;
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
      ChatText.unread => 'unread',
      ChatText.groupChat => 'group',
      ChatText.chatPrivateMessages => 'direct',
      ChatText.chatNotifications => 'notification',
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
        if (sub == ChatText.contactsTabAll ||
            sub == ChatText.contactsTabMutualFollow) {
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
              onPressed: () {
                unawaited(
                  ref
                      .read(journeyEventTrackerProvider)
                      .trackAction(
                        journey: 'relationship',
                        action: 'open_contact',
                        pageName: 'ChatPage',
                        targetType: row.kind.name,
                        targetKey: row.id,
                        payload: <String, dynamic>{
                          'source': row.source,
                          'relationState': row.relationState,
                        },
                      ),
                );
                row.open(context);
              },
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
