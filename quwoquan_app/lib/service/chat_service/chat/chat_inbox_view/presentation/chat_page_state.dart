part of 'chat_page.dart';

class _ChatPageState extends ConsumerState<ChatPage>
    with AutomaticKeepAliveClientMixin {
  int _mainTabIndex = 0;
  int _subTabIndex = 0;
  bool _hideSecondaryTab = false;
  final ScrollController _scrollController = ScrollController();
  double _lastScrollY = 0;
  bool _visibilityInitialized = false;
  bool _isChatVisible = true;
  bool _authoritativeRefreshInFlight = false;
  bool _authoritativeRefreshPending = false;
  @override
  bool get wantKeepAlive => true;
  @override
  void initState() {
    super.initState();
    unawaited(_refreshAuthoritativePageState());
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => mounted
          ? recordChatPageVisit(ref, _mainTabIndex, _subTabIndex)
          : null,
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final visible = TickerMode.valuesOf(context).enabled;
    if (!_visibilityInitialized) {
      _visibilityInitialized = true;
      _isChatVisible = visible;
      return;
    }
    final reentered = visible && !_isChatVisible;
    _isChatVisible = visible;
    if (reentered) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _isChatVisible) {
          unawaited(_refreshAuthoritativePageState());
        }
      });
    }
  }

  Future<void> _refreshAuthoritativePageState() async {
    if (_authoritativeRefreshInFlight) {
      _authoritativeRefreshPending = true;
      return;
    }
    _authoritativeRefreshInFlight = true;
    try {
      final messageFilters = <String>{'all', 'unread'};
      if (_mainTabIndex == 0) {
        final active = _messageHomeFilterForSubTab(
          _messageSubTabs[_subTabIndex],
        );
        if (active != 'notification') {
          messageFilters.add(active);
        }
      }
      final contactFilters = <ChatContactHomeFilter>{ChatContactHomeFilter.all};
      if (_mainTabIndex == 1) {
        contactFilters.add(
          _contactHomeFilterForSubTab(_contactsSubTabs[_subTabIndex]),
        );
      }

      for (final filter in messageFilters) {
        refreshMessageHomeRows(ref, filter);
      }
      for (final filter in contactFilters) {
        ref.invalidate(chatContactsRowsForSubTabProvider(filter));
      }
      ref.invalidate(chatGreetingInboxProvider(20));
      ref.invalidate(notificationInboxProvider);
      ref.invalidate(appMessageUnreadCountProvider);

      await Future.wait(<Future<void>>[
        for (final filter in messageFilters)
          _settleRefresh(ref.read(messageHomeRowsProvider(filter).future)),
        for (final filter in contactFilters)
          _settleRefresh(
            ref.read(chatContactsRowsForSubTabProvider(filter).future),
          ),
        _settleRefresh(ref.read(chatGreetingInboxProvider(20).future)),
        _settleRefresh(ref.read(notificationInboxProvider.future)),
        _settleRefresh(ref.read(appMessageUnreadCountProvider.future)),
      ]);
    } finally {
      _authoritativeRefreshInFlight = false;
      final shouldRefreshAgain =
          _authoritativeRefreshPending && mounted && _isChatVisible;
      _authoritativeRefreshPending = false;
      if (shouldRefreshAgain) {
        unawaited(_refreshAuthoritativePageState());
      }
    }
  }

  Future<void> _settleRefresh<T>(Future<T> refresh) async {
    try {
      await refresh;
    } catch (_) {
      // Each owning provider retains its typed error for its own section.
    }
  }

  Future<void> _retryMessageHome(String filter) async {
    if (ref.read(messageHomeRowsProvider(filter)).isLoading) {
      return;
    }
    refreshMessageHomeRows(ref, filter);
    await _settleRefresh(ref.read(messageHomeRowsProvider(filter).future));
  }

  Future<void> _retryGreetingInbox() async {
    if (ref.read(chatGreetingInboxProvider(20)).isLoading) {
      return;
    }
    ref.invalidate(chatGreetingInboxProvider(20));
    await _settleRefresh(ref.read(chatGreetingInboxProvider(20).future));
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
          .watch(messageHomeRowsProvider('unread'))
          .maybeWhen(
            data: (state) => totalUnreadMessages(state.rows),
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
    final messageRows = ref.watch(messageHomeRowsProvider(messageFilter));
    final greetingInbox = _subTabIndex == 0
        ? ref.watch(chatGreetingInboxProvider(20))
        : null;
    final pendingGreetings =
        greetingInbox?.value
            ?.where((greeting) => greeting.isPending)
            .toList(growable: false) ??
        const <GreetingRequestViewData>[];
    final shouldShowGreetingInbox =
        _subTabIndex == 0 && pendingGreetings.isNotEmpty;
    final rowsState = messageRows.value;
    final items =
        rowsState?.rows
            .map(ChatListItemViewModel.fromMessageHomeDto)
            .toList(growable: false) ??
        const <ChatListItemViewModel>[];
    final rowError = messageRows.hasError && !messageRows.isLoading
        ? messageRows.error
        : null;
    final greetingError =
        greetingInbox != null &&
            greetingInbox.hasError &&
            !greetingInbox.isLoading
        ? greetingInbox.error
        : null;
    final messageInitialLoading = messageRows.isLoading && rowsState == null;
    final greetingInitialLoading =
        greetingInbox != null &&
        greetingInbox.isLoading &&
        greetingInbox.value == null;

    if (messageInitialLoading && greetingInitialLoading) {
      return AppRequestFeedback.page();
    }

    if (items.isEmpty &&
        !shouldShowGreetingInbox &&
        rowError == null &&
        greetingError == null &&
        !messageInitialLoading &&
        !greetingInitialLoading) {
      return _buildConversationEmptyState(
        fgSecondary: fgSecondary,
        subTab: _messageSubTabs[_subTabIndex],
      );
    }

    final sectionRows = <Widget>[
      if (rowError != null)
        AppSectionErrorCard(
          key: const ValueKey<String>('chat-message-home-error-section'),
          semantic: _chatListSectionErrorSemantic(context, rowError),
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              await _retryMessageHome(messageFilter);
            }
          },
        )
      else if (messageInitialLoading)
        const KeyedSubtree(
          key: ValueKey<String>('chat-message-home-loading-section'),
          child: AppSkeletonListRows(),
        ),
      if (greetingError != null)
        AppSectionErrorCard(
          key: const ValueKey<String>('chat-greeting-inbox-error-section'),
          semantic: _chatListSectionErrorSemantic(context, greetingError),
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              await _retryGreetingInbox();
            }
          },
        )
      else if (greetingInitialLoading)
        KeyedSubtree(
          key: const ValueKey<String>('chat-greeting-inbox-loading-section'),
          child: AppRequestFeedback.section(),
        ),
      if (shouldShowGreetingInbox)
        _GreetingInboxTile(
          pendingCount: pendingGreetings.length,
          latest: pendingGreetings.first,
          fgPrimary: fgPrimary,
          fgSecondary: fgSecondary,
          backgroundColor: listItemBackground,
          dividerColor: listDividerColor,
          onTap: () => context.push(AppRoutePaths.greetingInbox),
        ),
    ];

    return ListView.builder(
      controller: _scrollController,
      padding: EdgeInsets.only(
        bottom:
            MediaQuery.viewPaddingOf(context).bottom +
            AppSpacing.bottomNavBarHeight(context),
      ),
      itemCount: sectionRows.length + items.length,
      itemBuilder: (context, index) {
        if (index < sectionRows.length) {
          return sectionRows[index];
        }
        final itemIndex = index - sectionRows.length;
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
      loading: AppRequestFeedback.page,
      error: (error, _) => AppPageErrorState(
        semantic: _chatListBlockingErrorSemantic(context, error),
        onRecovery: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            ref.invalidate(notificationInboxProvider);
            return UiRecoveryOutcome.superseded;
          }
          return UiRecoveryOutcome.cancelled;
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
            // Gathering 邀请专卡：pending 邀请直接在收件箱 accept/decline
            // （circle 域组件，动作携带消息 action intent 的 owner versions）。
            final invitation = message.gatheringInvitation;
            if (invitation != null && invitation.actionIntents.isNotEmpty) {
              return buildChatInboxGatheringInvitationSlot(
                message: message,
                invitation: invitation,
                fgPrimary: fgPrimary,
                fgSecondary: fgSecondary,
                backgroundColor: listItemBackground,
                onResolved: () async {
                  if (!message.read) {
                    await markAppMessageReadAndRefresh(ref, message.messageId);
                  }
                  ref.invalidate(notificationInboxProvider);
                },
              );
            }
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
    // 飞轮通知打开辅证：促成通知（漏斗③）与催回顾通知（漏斗②）。
    // 域事实只见结果（续发/回顾），看不到打开行为，故补 product_action 轨。
    final flywheelOpenAction = switch (message.source.trim()) {
      'intersection_facilitation' => 'notification_facilitation_open',
      'gathering_recap_nudge' => 'notification_recap_nudge_open',
      _ => null,
    };
    if (flywheelOpenAction != null) {
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'gathering_flywheel',
              action: flywheelOpenAction,
              pageName: 'chat_list',
              targetType: 'gathering',
              targetKey: message.target.targetId,
            ),
      );
    }
    final navigation = AppMessageNavigationTarget.fromMessage(message);
    if (navigation != null && context.mounted) {
      context.push(navigation.location);
    }
    if (!message.read) {
      try {
        await markAppMessageReadAndRefresh(ref, message.messageId);
      } catch (error, stackTrace) {
        // 已读标记失败会让红点不消失且不可观测，必须结构化上报。
        unawaited(
          ref
              .read(exceptionTelemetryPortProvider)
              .recordHandledException(
                source: 'chat.notification_inbox.mark_read',
                error: error,
                stackTrace: stackTrace,
              ),
        );
      }
    }
  }

  UiErrorSemantic _chatListBlockingErrorSemantic(
    BuildContext context,
    Object error,
  ) {
    return runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
  }

  UiErrorSemantic _chatListSectionErrorSemantic(
    BuildContext context,
    Object error,
  ) {
    return runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.sectionLoad,
      scope: UiErrorScope.section,
      presentation: UiErrorPresentation.sectionSoftCard,
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

    return AppTerminalViewport(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.xl,
        vertical: AppSpacing.containerMd,
      ),
      child: AppEmptyState(
        icon: CupertinoIcons.chat_bubble_2,
        title: title,
        subtitle: subtitle,
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

  ChatContactHomeFilter _contactHomeFilterForSubTab(String subTab) {
    return switch (subTab) {
      ChatText.contactsTabMutualFollow => ChatContactHomeFilter.mutual,
      ChatText.contactsTabCircles => ChatContactHomeFilter.circle,
      ChatText.contactsTabGroups => ChatContactHomeFilter.group,
      _ => ChatContactHomeFilter.all,
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
    final filter = _contactHomeFilterForSubTab(sub);
    final asyncRows = ref.watch(chatContactsRowsForSubTabProvider(filter));
    return asyncRows.when(
      data: (list) {
        if (list.isEmpty) {
          return AppTerminalViewport(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.xl,
              vertical: AppSpacing.containerMd,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  CupertinoIcons.person_2,
                  size: AppSpacing.iconButtonMinSizeMd,
                  color: fgSecondary,
                ),
                SizedBox(height: AppSpacing.md),
                Text(
                  CommunityText.noData,
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
                openChatContactsRow(context, row);
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
                              ? ref.watch(conversationAvatarBuilderProvider)(
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
      loading: () => AppRequestFeedback.section(),
      error: (error, _) => AppPageErrorState(
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        ),
        onRecovery: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            ref.invalidate(chatContactsRowsForSubTabProvider(filter));
            return UiRecoveryOutcome.superseded;
          }
          return UiRecoveryOutcome.cancelled;
        },
      ),
    );
  }
}
