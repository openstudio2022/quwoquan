part of 'global_search_page.dart';

extension _GlobalSearchPageStateSuggestions on _GlobalSearchPageState {
  Widget _buildSuggestionView({
    required Key key,
    required SearchSessionState state,
    required Color fgPrimary,
    required Color fgSecondary,
    required bool isDark,
  }) {
    if (state.isLoading && state.suggestionSections.isEmpty) {
      return AppRequestFeedback.page(
        key: const ValueKey<String>('global_search_primary_progress'),
        showSlowHint: state.isSlow,
        loadingLabel: UITextConstants.loading,
        slowLabel: UITextConstants.searchWaitSlow,
      );
    }
    if (state.failure case final failure?
        when state.suggestionSections.isEmpty) {
      final semantic = runtimeErrorSemantic(
        context,
        error: failure,
        category: state.isPartial
            ? UiErrorCategory.sectionLoad
            : UiErrorCategory.pageLoad,
        scope: state.isPartial ? UiErrorScope.section : UiErrorScope.page,
        sourceRouteId: AppRoutePaths.globalSearch,
        sourceSurfaceId: 'globalSearch',
      );
      if (state.isPartial) {
        return AppSectionErrorState(
          key: key,
          semantic: semantic,
          onAction: (_) async => _coordinator.scheduleSearch(immediate: true),
        );
      }
      return AppPageErrorState(
        key: key,
        semantic: semantic,
        onAction: (_) async => _coordinator.scheduleSearch(immediate: true),
      );
    }
    if (state.suggestionSections.isEmpty) {
      return Center(
        key: key,
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerLg),
          child: Text(
            UITextConstants.searchEmptyResult,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              color: fgSecondary,
            ),
          ),
        ),
      );
    }
    return ListView(
      key: key,
      padding: EdgeInsets.only(
        top: AppSpacing.containerXs,
        bottom: AppSpacing.containerMd,
      ),
      children: <Widget>[
        if (state.isPartial)
          AppTransientErrorNotice(
            semantic: const UiErrorSemantic(
              category: UiErrorCategory.sectionLoad,
              scope: UiErrorScope.section,
              title: UITextConstants.searchPartialResult,
              message: UITextConstants.searchPartialResult,
              presentation: UiErrorPresentation.transientNotice,
              tone: UiErrorTone.caution,
              primaryAction: UiErrorAction(
                type: UiErrorActionType.retry,
                label: UITextConstants.tryAgain,
              ),
              sourceRouteId: AppRoutePaths.globalSearch,
              sourceSurfaceId: 'globalSearch',
            ),
            onAction: (_) async => _coordinator.scheduleSearch(immediate: true),
          ),
        for (var index = 0; index < state.suggestionSections.length; index++)
          Padding(
            padding: EdgeInsets.only(
              bottom:
                  index == state.suggestionSections.length - 1 &&
                      !state.isNetworkLoading
                  ? 0
                  : _SearchTokens.sectionGap,
            ),
            child: _buildSuggestionSection(
              section: state.suggestionSections[index],
              query: state.query.trim(),
              fgPrimary: fgPrimary,
              fgSecondary: fgSecondary,
              isDark: isDark,
            ),
          ),
        if (state.isNetworkLoading)
          AppRequestFeedback.section(
            key: const ValueKey<String>('global_search_network_progress'),
            showSlowHint: state.isSlow,
            loadingLabel: UITextConstants.loading,
            slowLabel: UITextConstants.searchWaitSlow,
          ),
      ],
    );
  }

  Widget _buildSuggestionSection({
    required SearchSuggestionSection section,
    required String query,
    required Color fgPrimary,
    required Color fgSecondary,
    required bool isDark,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SearchSectionHeader(title: section.title),
        SizedBox(height: _SearchTokens.headerContentGap),
        switch (section.kind) {
          SearchSuggestionSectionKind.network => _buildKeywordSuggestionList(
            section: section,
            query: query,
            isDark: isDark,
          ),
          SearchSuggestionSectionKind.contacts ||
          SearchSuggestionSectionKind.followedPeople ||
          SearchSuggestionSectionKind.circles ||
          SearchSuggestionSectionKind.locations ||
          SearchSuggestionSectionKind.chatRecords => _buildPlainSuggestionList(
            section: section,
            query: query,
            isDark: isDark,
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
        },
      ],
    );
  }

  Widget _buildPlainSuggestionList({
    required SearchSuggestionSection section,
    required String query,
    required bool isDark,
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    return Column(
      children: [
        for (var i = 0; i < section.visibleItems.length; i++) ...[
          _buildSuggestionItem(
            item: section.visibleItems[i],
            query: query,
            isDark: isDark,
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
          if (i != section.visibleItems.length - 1)
            _DividerLine(isDark: isDark),
        ],
      ],
    );
  }

  Widget _buildKeywordSuggestionList({
    required SearchSuggestionSection section,
    required String query,
    required bool isDark,
  }) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    return Column(
      children: [
        for (var i = 0; i < section.visibleItems.length; i++) ...[
          _KeywordSuggestionRow(
            entry: section.visibleItems[i],
            query: query,
            color: fgPrimary,
            onTap: () => _handleGridSuggestionTap(section.visibleItems[i]),
          ),
          if (i != section.visibleItems.length - 1)
            _DividerLine(isDark: isDark),
        ],
      ],
    );
  }

  void _handleGridSuggestionTap(SearchSuggestionEntry entry) {
    switch (entry.kind) {
      case SearchSuggestionEntryKind.contact:
        final contact = entry.cast<ContactSearchSuggestion>();
        if (contact.conversationId.isEmpty) {
          _openUserProfile(contact.contactId);
        } else {
          _openConversation(contact.conversationId);
        }
      case SearchSuggestionEntryKind.chatRecord:
        final record = entry.cast<ChatRecordSearchSuggestion>();
        _openConversation(
          record.conversationId,
          messageAnchorId: record.messageAnchorId,
        );
      case SearchSuggestionEntryKind.circle:
        final circle = entry.cast<CircleSearchItemView>();
        _openCircle(circle.circleId);
      case SearchSuggestionEntryKind.location:
        final location = entry.cast<LocationPoiDto>();
        _openNetworkResults(location.name, initialTabId: 'all');
      case SearchSuggestionEntryKind.followedPerson:
        final person = entry.cast<SocialRelationSearchItemView>();
        _openUserProfile(person.subAccountId);
      case SearchSuggestionEntryKind.network:
        final network = entry.cast<NetworkSearchSuggestion>();
        if (network.isHomepagePreview) {
          _openHomepage(network.homepageId!);
        } else {
          _openNetworkResults(
            network.query,
            initialTabId: network.initialTabId,
          );
        }
    }
  }

  Widget _buildSuggestionItem({
    required SearchSuggestionEntry item,
    required String query,
    required bool isDark,
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    switch (item.kind) {
      case SearchSuggestionEntryKind.contact:
        final contact = item.cast<ContactSearchSuggestion>();
        return _BasicSuggestionTile(
          leading: _buildConversationLeading(
            avatarUrl: contact.avatarUrl,
            isDark: isDark,
            fallbackIcon: CupertinoIcons.person_fill,
          ),
          title: _highlightedText(
            contact.displayName,
            query,
            TextStyle(
              fontSize: _SearchTokens.bodySize,
              fontWeight: _SearchTokens.bodyWeight,
              color: fgPrimary,
            ),
          ),
          subtitle: Text(
            contact.subtitle ?? ChatText.searchContactFallback,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: fgSecondary,
            ),
          ),
          onTap: () {
            if (contact.conversationId.isEmpty) {
              _openUserProfile(contact.contactId);
            } else {
              _openConversation(contact.conversationId);
            }
          },
        );
      case SearchSuggestionEntryKind.chatRecord:
        final record = item.cast<ChatRecordSearchSuggestion>();
        return _ChatRecordTile(
          suggestion: record,
          query: query,
          isDark: isDark,
          onTap: () => _openConversation(
            record.conversationId,
            messageAnchorId: record.messageAnchorId,
          ),
        );
      case SearchSuggestionEntryKind.circle:
        final circle = item.cast<CircleSearchItemView>();
        return _BasicSuggestionTile(
          leading: _buildConversationLeading(
            avatarUrl: circle.coverUrl,
            isDark: isDark,
            fallbackIcon: CupertinoIcons.person_3_fill,
          ),
          title: _highlightedText(
            circle.name,
            query,
            TextStyle(
              fontSize: _SearchTokens.bodySize,
              fontWeight: _SearchTokens.bodyWeight,
              color: fgPrimary,
            ),
          ),
          subtitle: Text(
            circle.description?.trim().isNotEmpty == true
                ? circle.description!.trim()
                : (circle.subCategory?.trim().isNotEmpty == true
                      ? circle.subCategory!.trim()
                      : UITextConstants.searchCategoryCircle),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: fgSecondary,
            ),
          ),
          onTap: () => _openCircle(circle.circleId),
        );
      case SearchSuggestionEntryKind.location:
        final location = item.cast<LocationPoiDto>();
        return _BasicSuggestionTile(
          leading: _buildConversationLeading(
            avatarUrl: null,
            isDark: isDark,
            fallbackIcon: CupertinoIcons.location_solid,
          ),
          title: _highlightedText(
            location.name,
            query,
            TextStyle(
              fontSize: _SearchTokens.bodySize,
              fontWeight: _SearchTokens.bodyWeight,
              color: fgPrimary,
            ),
          ),
          subtitle: Text(
            (location.address ?? '').trim().isNotEmpty
                ? location.address!.trim()
                : UITextConstants.searchFollowedLocation,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: fgSecondary,
            ),
          ),
          onTap: () => _openNetworkResults(location.name, initialTabId: 'all'),
        );
      case SearchSuggestionEntryKind.followedPerson:
        final person = item.cast<SocialRelationSearchItemView>();
        return _BasicSuggestionTile(
          leading: _buildConversationLeading(
            avatarUrl: person.avatarUrl,
            isDark: isDark,
            fallbackIcon: CupertinoIcons.person_crop_circle_fill,
          ),
          title: _highlightedText(
            person.displayName,
            query,
            TextStyle(
              fontSize: _SearchTokens.bodySize,
              fontWeight: _SearchTokens.bodyWeight,
              color: fgPrimary,
            ),
          ),
          subtitle: Text(
            person.headline?.trim().isNotEmpty == true
                ? person.headline!.trim()
                : UITextConstants.searchFollowed,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: fgSecondary,
            ),
          ),
          onTap: () => _openUserProfile(person.subAccountId),
        );
      case SearchSuggestionEntryKind.network:
        return _KeywordSuggestionRow(
          entry: item,
          query: query,
          color: fgPrimary,
          onTap: () => _handleGridSuggestionTap(item),
        );
    }
  }
}
