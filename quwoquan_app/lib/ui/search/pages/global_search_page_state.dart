part of 'global_search_page.dart';

class _GlobalSearchPageState extends ConsumerState<GlobalSearchPage> {
  late final TextEditingController _controller;
  late final FocusNode _focusNode;
  _SearchHomeTab _activeHomeTab = _SearchHomeTab.guess;
  late final DateTime _pageEnteredAt;
  bool _didTrackPageImpression = false;
  ContentBehaviorTracker? _behaviorTracker;
  String? _feedRequestIdAtEnter;

  SearchCoordinator get _coordinator =>
      ref.read(searchCoordinatorProvider(widget.launchContext).notifier);

  SearchSessionState get _searchSession =>
      ref.read(searchCoordinatorProvider(widget.launchContext));

  void _setState(VoidCallback update) {
    setState(update);
  }

  @override
  void initState() {
    super.initState();
    _pageEnteredAt = DateTime.now();
    _controller = TextEditingController(
      text: widget.launchContext.prefilledQuery,
    );
    _focusNode = FocusNode();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _focusNode.requestFocus();
      _trackPageImpressionIfNeeded();
    });
  }

  @override
  void dispose() {
    _trackPageDwell();
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _trackPageImpressionIfNeeded() {
    if (_didTrackPageImpression) {
      return;
    }
    _didTrackPageImpression = true;
    _behaviorTracker = ref.read(contentBehaviorTrackerProvider);
    _feedRequestIdAtEnter = ref
        .read(feedSessionProvider.notifier)
        .currentFeedRequestId;
    _behaviorTracker!.trackImpression(
      'global_search',
      contentType: 'search_page',
      referralSource: ReferralSource.search,
      feedRequestId: _feedRequestIdAtEnter,
      tags: <String>[widget.launchContext.entrySurfaceId],
    );
  }

  void _trackPageDwell() {
    final tracker = _behaviorTracker;
    if (tracker == null) {
      return;
    }
    final elapsedSeconds =
        DateTime.now().difference(_pageEnteredAt).inMilliseconds / 1000.0;
    tracker.trackDwell(
      'global_search',
      durationSeconds: elapsedSeconds,
      contentType: 'search_page',
      referralSource: ReferralSource.search,
      feedRequestId: _feedRequestIdAtEnter,
      tags: <String>[widget.launchContext.entrySurfaceId],
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(searchCoordinatorProvider(widget.launchContext));
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final backgroundColor = SettingsSemanticConstants.pageBackground(isDark);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    _syncControllerText(state.query);

    return AppFullscreenModalSurface(
      surfaceKey: TestKeys.fullscreenModalSurface,
      backgroundColor: backgroundColor,
      safeAreaTop: false,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildSearchChrome(state, isDark, fgSecondary, backgroundColor),
          Expanded(
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                _SearchTokens.contentHorizontal(context),
                AppSpacing.containerSm,
                _SearchTokens.contentHorizontal(context),
                AppSpacing.containerLg,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(
                    child: AnimatedSwitcher(
                      duration: const Duration(milliseconds: 180),
                      child: switch (state.viewMode) {
                        SearchViewMode.historyBrowse => _buildHistoryView(
                          key: const ValueKey<String>('search_history_browse'),
                          state: state,
                          fgSecondary: fgSecondary,
                          isDark: isDark,
                        ),
                        SearchViewMode.historyManage => _buildHistoryView(
                          key: const ValueKey<String>('search_history_manage'),
                          state: state,
                          fgSecondary: fgSecondary,
                          isDark: isDark,
                        ),
                        SearchViewMode.liveSuggestions => _buildSuggestionView(
                          key: const ValueKey<String>(
                            'search_live_suggestions',
                          ),
                          state: state,
                          fgPrimary: fgPrimary,
                          fgSecondary: fgSecondary,
                          isDark: isDark,
                        ),
                      },
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSearchChrome(
    SearchSessionState state,
    bool isDark,
    Color fgSecondary,
    Color backgroundColor,
  ) {
    final topInset = AppSpacing.appChromeTopSafeInset(
      MediaQuery.viewPaddingOf(context).top,
      context,
    );
    return DecoratedBox(
      decoration: BoxDecoration(color: backgroundColor),
      child: Padding(
        padding: EdgeInsets.only(top: topInset),
        child: SizedBox(
          height: AppSpacing.appChromeTopBarHeight(context),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: _SearchTokens.contentHorizontal(context),
            ),
            child: _buildSearchBar(state, isDark, fgSecondary),
          ),
        ),
      ),
    );
  }

  Widget _buildSearchBar(
    SearchSessionState state,
    bool isDark,
    Color fgSecondary,
  ) {
    final fieldBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    const trailingInset = AppSpacing.containerSm;
    final hasSearchText = state.query.trim().isNotEmpty;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        CupertinoButton(
          padding: EdgeInsets.zero,
          minimumSize: Size.square(AppSpacing.appChromeActionButtonSize),
          onPressed: _handleClose,
          child: Icon(
            CupertinoIcons.chevron_back,
            color: fgSecondary,
            size: AppSpacing.appChromeActionIconSize,
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupXs),
        Expanded(
          child: AppSearchField(
            key: const ValueKey<String>('global_search_field'),
            controller: _controller,
            focusNode: _focusNode,
            autofocus: true,
            placeholder: ContactText.globalSearchTitle,
            onChanged: (value) => _coordinator.updateQuery(value),
            onSubmitted: _handleSearchSubmitted,
            backgroundColor: fieldBackground,
            elevated: false,
            padding: const EdgeInsetsDirectional.only(
              start: AppSpacing.containerSm,
              end: trailingInset,
            ),
          ),
        ),
        AnimatedSwitcher(
          duration: const Duration(milliseconds: 160),
          child: hasSearchText
              ? Padding(
                  key: const ValueKey<String>('global_search_submit_visible'),
                  padding: EdgeInsetsDirectional.only(
                    start: AppSpacing.intraGroupXs,
                  ),
                  child: CupertinoButton(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerXs,
                    ),
                    minimumSize: const Size(
                      0,
                      AppSpacing.appChromeTextActionMinHeight,
                    ),
                    onPressed: () => _handleSearchSubmitted(_controller.text),
                    child: Text(
                      DiscoveryText.search,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.medium,
                        color: AppColors.primaryColor,
                      ),
                    ),
                  ),
                )
              : const SizedBox.shrink(
                  key: ValueKey<String>('global_search_submit_hidden'),
                ),
        ),
      ],
    );
  }

  bool _allowsNetworkResults(SearchObjectSelection selection) {
    return selection.normalized().enabledContentTypes.isNotEmpty;
  }
}
