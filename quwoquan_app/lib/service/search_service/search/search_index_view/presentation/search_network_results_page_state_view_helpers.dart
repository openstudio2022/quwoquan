part of 'search_network_results_page.dart';

extension _SearchNetworkResultsPageStateViewHelpers
    on _SearchNetworkResultsPageState {
  Widget? _buildDegradeBanner() {
    if (_degradeSignals.isEmpty) {
      return null;
    }
    return AppTransientErrorNotice(
      semantic: AppUserRecoveryContract.semanticFor(
        group: AppUserRecoveryGroup.reloadLater,
        category: UiErrorCategory.backgroundAction,
        scope: UiErrorScope.section,
        presentation: UiErrorPresentation.transientNotice,
      ),
    );
  }

  List<Widget> _buildXiaoquCitationTiles({
    required bool isDark,
    required Color fgSecondary,
  }) {
    final citations =
        _xiaoquResult?.processes
            .expand((process) => process.acceptedReferences)
            .toList(growable: false) ??
        const <AssistantRunVisibleReferenceView>[];
    return <Widget>[
      for (var i = 0; i < citations.length; i++) ...[
        PostPreviewListTile(
          isDark: isDark,
          title: citations[i].title,
          supportingText: citations[i].snippet.trim().isEmpty
              ? SearchText.searchOpenRelatedClue
              : citations[i].snippet,
          coverUrl: '',
          eyebrowText: citations[i].source,
          showVideoBadge: false,
          footer: Text(
            citations[i].source,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
          onTap: () {
            unawaited(_openAssistantCitation(citations[i]));
          },
        ),
        if (i != citations.length - 1) SizedBox(height: AppSpacing.containerSm),
      ],
    ];
  }

  List<Widget> _buildIntersectionGrid({required List<Widget> cells}) =>
      _buildAdaptiveMasonry(cells: cells);

  // 双列瀑布流：每个 cell 按自身内容高度排布，避免固定宽高比造成的卡片底部留白。
  List<Widget> _buildAdaptiveMasonry({required List<Widget> cells}) {
    if (cells.isEmpty) {
      return const <Widget>[];
    }
    return <Widget>[
      MasonryGridView.count(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        padding: EdgeInsets.zero,
        crossAxisCount: 2,
        crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
        mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
        itemCount: cells.length,
        itemBuilder: (context, index) => cells[index],
      ),
    ];
  }

  // 发现更多交集：基于已有连接继续延展的结果，混入相关搜索卡。
  List<Widget> _discoverCells({required bool isDark}) {
    final models = _discoverCardModels();
    final cells = <Widget>[
      for (final model in models)
        _IntersectionCard(
          model: model,
          isDark: isDark,
          onTap: () => _openIntersectionTarget(model),
        ),
    ];
    final related = _buildRelatedSearchCard(isDark: isDark);
    if (related != null) {
      final insertAt = (cells.length / 2).floor();
      cells.insert(insertAt, related);
    }
    return cells;
  }

  List<_IntersectionCardModel> _discoverCardModels() {
    final models = <_IntersectionCardModel>[];
    for (final item in _discoveryContentItems) {
      final card = _NetworkResultCardModel.fromSearchItem(item);
      final isVideo = item.contentType == 'video';
      final isArticle = item.contentType == 'article';
      // §3：发现/交集线索区的交集句只来自云侧 primaryText；无 primaryText 不拼装。
      final intersectionSentence =
          _SearchNetworkResultsPageState._contentIntersectionPrimaryText(item);
      models.add(
        _IntersectionCardModel(
          targetType: _IntersectionTargetType.post,
          targetId: item.postId,
          coverUrl: item.coverUrl ?? '',
          coverBinding: card.coverBinding,
          categoryLabel: isVideo
              ? SearchText.searchCategoryVideo
              : (isArticle
                    ? SearchText.searchCategoryArticle
                    : SearchText.searchCategoryImage),
          categoryIcon: isVideo
              ? CupertinoIcons.play_rectangle_fill
              : (isArticle
                    ? CupertinoIcons.doc_text_fill
                    : CupertinoIcons.photo_fill),
          title: card.title,
          reasonIcon: CupertinoIcons.sparkles,
          reasonText: intersectionSentence,
          footerText: card.footerLabel,
          metricLabel: item.likeCount > 0 ? '${item.likeCount}' : null,
          metricIcon: CupertinoIcons.heart,
          showVideoBadge: isVideo,
        ),
      );
    }
    for (final hit in _discoveryGroupHits) {
      final card = _GroupResultCardModel.fromHit(hit);
      models.add(
        _IntersectionCardModel(
          targetType: _IntersectionTargetType.circle,
          targetId: card.circleId,
          coverUrl: card.coverUrl,
          categoryLabel: SearchText.searchCategoryCircle,
          categoryIcon: CupertinoIcons.person_3_fill,
          title: hit.title,
          reasonIcon: CupertinoIcons.person_2_fill,
          reasonText:
              _SearchNetworkResultsPageState._hitIntersectionPrimaryText(hit),
          footerText: card.footerLabel,
        ),
      );
    }
    for (final hit in _discoveryUserHits) {
      final user = hit.asUserProfileItem;
      models.add(
        _IntersectionCardModel(
          targetType: _IntersectionTargetType.user,
          targetId: user?.userId ?? hit.objectId,
          coverUrl: '',
          categoryLabel: SearchText.searchCategoryUser,
          categoryIcon: CupertinoIcons.person_fill,
          title: user?.displayName ?? hit.title,
          reasonIcon: CupertinoIcons.person_2_fill,
          reasonText:
              _SearchNetworkResultsPageState._hitIntersectionPrimaryText(hit),
          footerText: user?.bio ?? hit.snippet ?? '',
        ),
      );
    }
    return models;
  }

  // 交集 Tab 顶部实体卡：只消费命中实体真实字段；连接说明只来自云侧 primaryText，
  // 无 primaryText 不展示句子，关注/内容计数不在端侧编造。
  _EntityTopResultModel? _intersectionEntityResult() {
    final hit = _intersectionEntityHit;
    if (hit == null) {
      return null;
    }
    final primaryText =
        _SearchNetworkResultsPageState._hitIntersectionPrimaryText(hit);
    return _EntityTopResultModel(
      homepageId: hit.objectId,
      title: hit.title,
      badge: SearchText.searchCategoryLocation,
      subtitle: hit.subtitle ?? SearchText.searchLocationHomepage,
      connectionReason: primaryText.isNotEmpty ? primaryText : null,
      description: hit.snippet ?? '',
      meta: '',
      actionLabel: SearchText.searchVisitHomepage,
    );
  }

  void _openIntersectionTarget(_IntersectionCardModel model) {
    final id = model.targetId.trim();
    switch (model.targetType) {
      case _IntersectionTargetType.circle:
        if (id.isNotEmpty) {
          _reportSearchClick(
            objectId: id,
            target: 'circles',
            objectType: SearchObjectType.circleCircle,
          );
          context.push(
            AppRoutePaths.circleDetail(id: id),
            extra: const CircleDetailPageRouteExtra(
              referralSource: ReferralSource.search,
            ),
          );
        }
      case _IntersectionTargetType.homepage:
        _openHomepage(id);
      case _IntersectionTargetType.locationPlace:
        _openLocationPlace(
          SearchLocationPlaceHitView(
            placeId: id,
            name: model.title,
            address: model.footerText,
          ),
        );
      case _IntersectionTargetType.post:
        unawaited(_openPost(id));
      case _IntersectionTargetType.user:
        if (id.isNotEmpty) {
          _reportSearchClick(
            objectId: id,
            target: 'users',
            objectType: SearchObjectType.userProfile,
          );
          context.push(AppRoutePaths.userProfile(userHandle: id));
        }
    }
  }

  void _openLocationPlace(SearchLocationPlaceHitView place) {
    final placeId = place.placeId.trim();
    if (placeId.isEmpty) {
      return;
    }
    _reportSearchClick(
      objectId: placeId,
      target: 'locations',
      objectType: SearchObjectType.locationPlace,
    );
    context.push(
      AppRoutePaths.locationPlaceLanding(placeId: placeId),
      extra: LocationPlaceLandingPageRouteExtra(
        placeName: place.name,
        address: place.address ?? '',
        referralSource: ReferralSource.search,
      ),
    );
  }

  Widget? _buildRelatedSearchCard({required bool isDark}) {
    final terms = _relatedSearchTerms();
    if (terms.isEmpty) {
      return null;
    }
    return _RelatedSearchCard(
      card: RelatedSearchTermCardView(terms: terms).limited(),
      isDark: isDark,
      onTap: _submitRelatedSearch,
    );
  }

  List<NetworkSearchSuggestion> _relatedSearchTerms() {
    final seen = <String>{};
    return _relatedTerms
        .map((term) => term.trim())
        .where((term) => term.isNotEmpty && seen.add(term.toLowerCase()))
        .map((term) => NetworkSearchSuggestion(query: term, title: term))
        .toList(growable: false);
  }

  void _submitRelatedSearch(NetworkSearchSuggestion term) {
    final nextQuery = term.query.trim();
    if (nextQuery.isEmpty) {
      return;
    }
    _reportSearchRefine(action: 'related_term');
    _setState(() {
      _query = nextQuery;
      _controller.text = nextQuery;
      _activeTabId = _SearchNetworkResultsPageState._tabAll;
    });
    _scheduleRefresh(immediate: true);
  }

  void _scheduleRefresh({bool immediate = false}) {
    _debounceTimer?.cancel();
    _requestToken += 1;
    _waitController.cancel();
    if (immediate) {
      unawaited(_loadResults());
      return;
    }
    _debounceTimer = Timer(
      _SearchNetworkResultsPageState._queryDebounce,
      () => unawaited(_loadResults()),
    );
  }
}
