part of 'global_search_page.dart';

extension _GlobalSearchPageStateNavigation on _GlobalSearchPageState {
  void _openConversation(String conversationId, {String? messageAnchorId}) {
    if (conversationId.trim().isEmpty) {
      return;
    }
    unawaited(_coordinator.rememberCurrentQuery());
    context.push(
      AppRoutePaths.chatDetail(id: conversationId),
      extra: messageAnchorId == null
          ? null
          : SearchConversationAnchorContext(
              messageAnchorId: messageAnchorId,
              sourceQuery: _searchSession.query.trim(),
            ),
    );
  }

  void _openCircle(String circleId) {
    unawaited(_coordinator.rememberCurrentQuery());
    context.push(
      AppRoutePaths.circleDetail(id: circleId),
      extra: const CircleDetailPageRouteExtra(
        referralSource: ReferralSource.search,
      ),
    );
  }

  void _openUserProfile(String userId) {
    final normalized = userId.trim();
    if (normalized.isEmpty) {
      return;
    }
    unawaited(_coordinator.rememberCurrentQuery());
    context.push(AppRoutePaths.userProfile(username: normalized));
  }

  void _openHomepage(String homepageId) {
    final normalized = homepageId.trim();
    if (normalized.isEmpty) return;
    unawaited(_coordinator.rememberCurrentQuery());
    context.push(AppRoutePaths.homepageDetail(id: normalized));
  }

  void _openNetworkResults(String query, {String? initialTabId}) {
    final trimmedQuery = query.trim();
    if (trimmedQuery.isEmpty) {
      return;
    }
    final selection = _searchSession.selection.normalized();
    final effectiveInitialTabId =
        initialTabId ?? _defaultNetworkTabIdForSelection(selection);
    unawaited(_coordinator.rememberCurrentQuery(query: trimmedQuery));
    context.push(
      AppRoutePaths.globalSearchNetworkResults(
        query: trimmedQuery,
        tab: effectiveInitialTabId,
      ),
      extra: widget.launchContext.copyWith(
        prefilledQuery: trimmedQuery,
        initialNetworkTabId: effectiveInitialTabId,
        initialScope: _searchSession.scope,
        initialFacet: selection.toFacet(),
        searchObjectSelection: selection,
        restoreState: false,
      ),
    );
  }

  String _defaultNetworkTabIdForSelection(SearchObjectSelection selection) {
    return 'all';
  }

  void _handleSearchSubmitted(String value) {
    final trimmedValue = value.trim();
    _coordinator.updateQuery(trimmedValue, immediate: true);
    if (trimmedValue.isEmpty) {
      return;
    }
    if (!_allowsNetworkResults(_searchSession.selection)) {
      _focusNode.unfocus();
      return;
    }
    _openNetworkResults(trimmedValue);
  }

  Future<void> _confirmClearHistory() async {
    final confirmed = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return CupertinoAlertDialog(
          title: const Text(UITextConstants.searchHistoryClearTitle),
          content: const Padding(
            padding: EdgeInsets.only(top: AppSpacing.containerXs),
            child: Text(UITextConstants.searchHistoryClearMessage),
          ),
          actions: [
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text(UITextConstants.cancel),
            ),
            CupertinoDialogAction(
              isDestructiveAction: true,
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text(UITextConstants.searchHistoryClearAction),
            ),
          ],
        );
      },
    );
    if (confirmed == true) {
      await _coordinator.clearRecentSearches();
    }
  }

  void _handleClose() {
    if (context.canPop()) {
      context.pop();
      return;
    }
    context.go(AppRoutePaths.home);
  }

  void _syncControllerText(String query) {
    if (_controller.text == query) {
      return;
    }
    _controller.value = TextEditingValue(
      text: query,
      selection: TextSelection.collapsed(offset: query.length),
    );
  }
}
