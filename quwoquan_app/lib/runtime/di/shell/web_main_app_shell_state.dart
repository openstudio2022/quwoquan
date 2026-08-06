part of 'web_main_app_shell.dart';

class _WebMainAppShellState extends ConsumerState<WebMainAppShell> {
  static const String _defaultHomeChannelId = 'recommend';
  static const String _defaultFeaturedFilterId = 'all';
  static const String _defaultCreateTabId = 'gallery';
  static const String _defaultMessageTabId = 'messages';
  static const String _interestMatchContextId = 'interest_match';
  static const String _profileContextId = 'profile';

  final ScrollController _scrollController = ScrollController();
  String _homeChannelId = _defaultHomeChannelId;
  String _featuredFilterId = _defaultFeaturedFilterId;
  String _createTabId = _defaultCreateTabId;
  String _messageTabId = _defaultMessageTabId;
  double _toolbarProgress = 0;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_handleScroll);
  }

  @override
  void didUpdateWidget(WebMainAppShell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.currentLocation != widget.currentLocation) {
      final destination = mainTabFromLocation(widget.currentLocation);
      if (destination == MainTabDestination.home) {
        _homeChannelId = _defaultHomeChannelId;
      }
    }
  }

  @override
  void dispose() {
    _scrollController
      ..removeListener(_handleScroll)
      ..dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final destination = widget.currentDestination;
    return DefaultTextStyle.merge(
      style: const TextStyle(
        decoration: TextDecoration.none,
        decorationThickness: 0,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(color: widget.backgroundColor),
        child: LayoutBuilder(
          builder: (context, constraints) {
            const heroHeight = AppSpacing.webPcWelcomeHeroHeight;
            return CustomScrollView(
              key: const ValueKey<String>('web-shell-scroll'),
              controller: _scrollController,
              slivers: [
                SliverToBoxAdapter(
                  child: SizedBox(
                    height: heroHeight,
                    child: _WebWelcomeHero(
                      scrollProgress: _toolbarProgress,
                      onEnter: () => _enterWebHome(heroHeight),
                    ),
                  ),
                ),
                SliverPersistentHeader(
                  pinned: true,
                  delegate: _WebToolbarHeaderDelegate(
                    progress: _toolbarProgress,
                    child: SafeArea(
                      top: false,
                      bottom: false,
                      child: _WebTopToolbar(
                        destination: destination,
                        toolbarProgress: _toolbarProgress,
                        contextTabs: _contextTabsFor(destination),
                        activeContextId: _activeContextIdFor(destination),
                        searchHint: _searchHintFor(destination),
                        onContextTabSelected: (id) =>
                            _selectContext(destination, id),
                        onPrimarySelected: _selectPrimary,
                      ),
                    ),
                  ),
                ),
                SliverFillRemaining(
                  hasScrollBody: true,
                  child: _buildContent(destination),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  void _handleScroll() {
    if (!_scrollController.hasClients) {
      return;
    }
    final nextProgress =
        (_scrollController.offset / AppSpacing.webPcHeroPinnedProgressDistance)
            .clamp(0.0, 1.0)
            .toDouble();
    if ((nextProgress - _toolbarProgress).abs() < 0.01) {
      return;
    }
    setState(() {
      _toolbarProgress = nextProgress;
    });
  }

  void _enterWebHome(double heroHeight) {
    unawaited(
      _scrollController.animateTo(
        heroHeight,
        duration: AppSpacing.webPcScrollToContentDuration,
        curve: Curves.easeOutCubic,
      ),
    );
    _selectPrimary(MainTabDestination.home);
  }

  void _selectPrimary(MainTabDestination destination) {
    if (!_selectWebShellPrimaryDestination(
      context: context,
      ref: ref,
      destination: destination,
    )) {
      return;
    }
    widget.onPrimarySelected(destination);
  }

  List<_WebContextTabSpec> _contextTabsFor(MainTabDestination destination) {
    switch (destination) {
      case MainTabDestination.home:
        return ref
            .watch(homeChannelsProvider)
            .map(
              (channel) => _WebContextTabSpec(
                id: channel.id,
                label: UITextConstants.homeChannelLabel(channel.labelKey),
              ),
            )
            .toList(growable: false);
      case MainTabDestination.featured:
        return ContentUIConfig.workFormatFilters
            .map(
              (filter) => _WebContextTabSpec(
                id: filter.id,
                label: UITextConstants.contentLabelForKey(filter.labelKey),
              ),
            )
            .toList(growable: false);
      case MainTabDestination.create:
        return const <_WebContextTabSpec>[
          _WebContextTabSpec(
            id: 'video',
            label: DiscoveryText.webPcCreateTabVideo,
          ),
          _WebContextTabSpec(
            id: 'gallery',
            label: DiscoveryText.webPcCreateTabGallery,
          ),
          _WebContextTabSpec(
            id: 'write',
            label: DiscoveryText.webPcCreateTabText,
          ),
          _WebContextTabSpec(
            id: 'drafts',
            label: DiscoveryText.webPcCreateTabDrafts,
          ),
        ];
      case MainTabDestination.chat:
        return const <_WebContextTabSpec>[
          _WebContextTabSpec(
            id: 'messages',
            label: ChatText.webPcMessagesTabMessages,
          ),
          _WebContextTabSpec(
            id: 'contacts',
            label: ChatText.webPcMessagesTabContacts,
          ),
          _WebContextTabSpec(
            id: 'groups',
            label: ChatText.webPcMessagesTabGroups,
          ),
        ];
      case MainTabDestination.interestMatch:
        return const <_WebContextTabSpec>[
          _WebContextTabSpec(
            id: _interestMatchContextId,
            label: AppConceptConstants.interestMatch,
          ),
        ];
      case MainTabDestination.profile:
        return const <_WebContextTabSpec>[
          _WebContextTabSpec(
            id: _profileContextId,
            label: DiscoveryText.webPcProfileContextTitle,
          ),
        ];
    }
  }

  String _activeContextIdFor(MainTabDestination destination) {
    switch (destination) {
      case MainTabDestination.home:
        return _homeChannelId;
      case MainTabDestination.featured:
        return _featuredFilterId;
      case MainTabDestination.create:
        return _createTabId;
      case MainTabDestination.chat:
        return _messageTabId;
      case MainTabDestination.interestMatch:
        return _interestMatchContextId;
      case MainTabDestination.profile:
        return _profileContextId;
    }
  }

  String _searchHintFor(MainTabDestination destination) {
    switch (destination) {
      case MainTabDestination.home:
        return DiscoveryText.webPcSearchHintHome;
      case MainTabDestination.featured:
        return DiscoveryText.webPcSearchHintFeatured;
      case MainTabDestination.create:
        return DiscoveryText.webPcSearchHintCreate;
      case MainTabDestination.chat:
        return ChatText.webPcSearchHintMessages;
      case MainTabDestination.interestMatch:
        return DiscoveryText.webPcSearchHintHome;
      case MainTabDestination.profile:
        return DiscoveryText.webPcSearchHintProfile;
    }
  }

  void _selectContext(MainTabDestination destination, String id) {
    setState(() {
      switch (destination) {
        case MainTabDestination.home:
          _homeChannelId = id;
          break;
        case MainTabDestination.featured:
          _featuredFilterId = id;
          break;
        case MainTabDestination.create:
          _createTabId = id;
          break;
        case MainTabDestination.chat:
          _messageTabId = id;
          break;
        case MainTabDestination.interestMatch:
          break;
        case MainTabDestination.profile:
          break;
      }
    });
  }

  Widget _buildContent(MainTabDestination destination) {
    switch (destination) {
      case MainTabDestination.home:
        return _WebHomeWorkspace(channelId: _homeChannelId);
      case MainTabDestination.featured:
        return _WebFeaturedWorkspace(filterId: _featuredFilterId);
      case MainTabDestination.create:
        return _WebCreateWorkspace(activeTabId: _createTabId);
      case MainTabDestination.chat:
        return const _WebDesktopFrame(child: ChatPage());
      case MainTabDestination.interestMatch:
        return _WebDesktopFrame(
          child: InterestMatchPage(
            visitRecorderService: ref.read(visitRecorderServiceProvider),
          ),
        );
      case MainTabDestination.profile:
        return const _WebDesktopFrame(child: MyProfilePage());
    }
  }
}
