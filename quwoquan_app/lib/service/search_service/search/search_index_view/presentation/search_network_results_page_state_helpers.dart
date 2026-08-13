part of 'search_network_results_page.dart';

extension _SearchNetworkResultsPageStateHelpers
    on _SearchNetworkResultsPageState {
  List<Widget> _buildResultChildren({
    required bool isDark,
    required Color fgSecondary,
    required _SearchNetworkTab activeTab,
  }) {
    List<Widget> withDegradeBanner(List<Widget> children) {
      final banner = _buildDegradeBanner();
      if (banner == null) {
        return children;
      }
      return <Widget>[
        banner,
        SizedBox(height: AppSpacing.containerMd),
        ...children,
      ];
    }

    if (_activeTabId == _SearchNetworkResultsPageState._tabXiaoqu) {
      return <Widget>[
        _XiaoquSummaryCard(
          query: _query,
          result: _xiaoquResult,
          isDark: isDark,
        ),
        SizedBox(height: AppSpacing.containerMd),
        if (_isLoading)
          AppRequestFeedback.section(
            loadingLabel: SearchText.searchXiaoquLoading,
            showSlowHint: true,
            slowLabel: SearchText.searchXiaoquLoading,
          )
        else if ((_xiaoquResult?.processes.any(
                  (process) => process.acceptedReferences.isNotEmpty,
                ) ??
                false) ==
            false)
          _StatusMessage(
            text: SearchText.searchNoNetworkReferences,
            isDark: isDark,
          )
        else
          ..._buildXiaoquCitationTiles(
            isDark: isDark,
            fgSecondary: fgSecondary,
          ),
      ];
    }

    if (_pageItems.isNotEmpty) {
      return withDegradeBanner(_buildSearchPageFlatCards(isDark: isDark));
    }

    if (_activeTabId == _SearchNetworkResultsPageState._tabAll) {
      return withDegradeBanner(
        _buildAllResultChildren(
          isDark: isDark,
          fgSecondary: fgSecondary,
          activeTab: activeTab,
        ),
      );
    }

    if (_activeTabId == _SearchNetworkResultsPageState._tabIntersection) {
      return withDegradeBanner(
        _buildIntersectionResultChildren(
          isDark: isDark,
          fgSecondary: fgSecondary,
        ),
      );
    }

    final contentItems = _contentItemsForActiveTab();
    final relatedSearchCard = _buildRelatedSearchCard(isDark: isDark);
    if (_isLoading) {
      return withDegradeBanner(<Widget>[
        AppRequestFeedback.page(
          showSlowHint: _isSlow,
          loadingLabel: UITextConstants.pageLoadingA11y(
            UITextConstants.searchTabResults(activeTab.label),
          ),
          slowLabel: SearchText.searchWaitSlow,
        ),
      ]);
    }
    if (contentItems.isEmpty) {
      return withDegradeBanner(<Widget>[
        AppEmptyState(
          icon: CupertinoIcons.search,
          title: UITextConstants.searchNoResultsForQuery(_query),
          subtitle: SearchText.searchEmptySuggestion,
          actionLabel: SearchText.searchEditQuery,
          onAction: _editEmptySearchQuery,
        ),
        if (relatedSearchCard != null) ...[
          SizedBox(height: AppSpacing.containerLg),
          relatedSearchCard,
        ],
      ]);
    }
    return withDegradeBanner(
      _buildContentMasonryTiles(
        isDark: isDark,
        fgSecondary: fgSecondary,
        items: contentItems,
        relatedSearchCard: relatedSearchCard,
      ),
    );
  }

  List<Widget> _buildSearchPageFlatCards({required bool isDark}) {
    final sections = <Widget>[];
    for (final item in _pageItems) {
      sections.add(
        _SearchPageFlatCard(
          item: item,
          isDark: isDark,
          onTap: () => _openSearchPageResult(item),
        ),
      );
      sections.add(SizedBox(height: AppSpacing.intraGroupSm));
    }
    final relatedSearchCard = _buildRelatedSearchCard(isDark: isDark);
    if (relatedSearchCard != null) {
      sections.add(SizedBox(height: AppSpacing.containerSm));
      sections.add(relatedSearchCard);
    }
    return sections;
  }

  List<Widget> _buildAllResultChildren({
    required bool isDark,
    required Color fgSecondary,
    required _SearchNetworkTab activeTab,
  }) {
    if (_isLoading) {
      return <Widget>[
        AppRequestFeedback.page(
          showSlowHint: _isSlow,
          loadingLabel: UITextConstants.pageLoadingA11y(
            SearchText.searchAppResults,
          ),
          slowLabel: SearchText.searchWaitSlow,
        ),
      ];
    }

    final entity = _entityTopResult();
    final locationPlace = _locationPlaceTopResult();
    final relatedSearchCard = _buildRelatedSearchCard(isDark: isDark);
    final hasPrimaryResults =
        entity != null ||
        locationPlace != null ||
        _userResults.isNotEmpty ||
        _contentResults.isNotEmpty;
    if (!hasPrimaryResults) {
      return <Widget>[
        _CategorySummaryCard(
          title: activeTab.label,
          description: activeTab.description,
          count: 0,
          isDark: isDark,
        ),
        AppEmptyState(
          icon: CupertinoIcons.search,
          title: UITextConstants.searchNoResultsForQuery(_query),
          subtitle: SearchText.searchEmptySuggestion,
          actionLabel: SearchText.searchEditQuery,
          onAction: _editEmptySearchQuery,
        ),
        if (relatedSearchCard != null) ...[
          SizedBox(height: AppSpacing.containerLg),
          relatedSearchCard,
        ],
      ];
    }

    final sections = <Widget>[];
    if (entity != null) {
      sections.add(
        _EntityTopResultCard(
          entity: entity,
          isDark: isDark,
          onTap: () => _openHomepage(entity.homepageId),
        ),
      );
    } else if (locationPlace != null) {
      sections.add(
        _LocationPlaceTopResultCard(
          place: locationPlace.place,
          isDark: isDark,
          onTap: () => _openLocationPlace(locationPlace.place),
        ),
      );
    }
    if (_userResults.isNotEmpty) {
      if (sections.isNotEmpty) {
        sections.add(SizedBox(height: AppSpacing.containerLg));
      }
      sections.add(
        const _SearchResultSectionHeader(
          title: SearchText.searchUserResultsTitle,
        ),
      );
      sections.add(SizedBox(height: AppSpacing.intraGroupSm));
      for (final hit in _userResults) {
        sections.add(
          _UserSearchResultCard(
            hit: hit,
            isDark: isDark,
            onTap: () => _openUserProfile(hit),
          ),
        );
        sections.add(SizedBox(height: AppSpacing.intraGroupSm));
      }
    }
    final mixedTiles = _buildContentMasonryTiles(
      isDark: isDark,
      fgSecondary: fgSecondary,
      items: _contentResults,
      relatedSearchCard: relatedSearchCard,
    );
    if (mixedTiles.isNotEmpty) {
      if (sections.isNotEmpty) {
        sections.add(SizedBox(height: AppSpacing.containerLg));
      }
      sections.addAll(mixedTiles);
    }

    return sections;
  }

  List<Widget> _buildIntersectionResultChildren({
    required bool isDark,
    required Color fgSecondary,
  }) {
    if (_isLoading) {
      return <Widget>[
        AppRequestFeedback.page(
          showSlowHint: _isSlow,
          loadingLabel: SearchText.searchIntersectionLoading,
          slowLabel: SearchText.searchWaitSlow,
        ),
      ];
    }

    final sections = <Widget>[];

    final connections = _connectionCardModels();
    if (connections.isNotEmpty) {
      final hasMore =
          connections.length >
          _SearchNetworkResultsPageState._connectionCollapsedCap;
      final visible = _showAllConnections
          ? connections
          : connections
                .take(_SearchNetworkResultsPageState._connectionCollapsedCap)
                .toList(growable: false);
      sections.add(
        _SearchResultSectionHeader(
          title: SearchText.searchEstablishedConnections,
          subtitle: SearchText.searchEstablishedConnectionsSubtitle,
          actionLabel: hasMore
              ? (_showAllConnections
                    ? SearchText.searchHistoryCollapse
                    : SearchText.searchViewAll)
              : null,
          onAction: hasMore
              ? () => _setMountedState(
                  () => _showAllConnections = !_showAllConnections,
                )
              : null,
        ),
      );
      sections.add(SizedBox(height: AppSpacing.intraGroupMd));
      sections.addAll(
        _buildIntersectionGrid(
          cells: visible
              .map(
                (model) => _IntersectionCard(
                  model: model,
                  isDark: isDark,
                  onTap: () => _openIntersectionTarget(model),
                ),
              )
              .toList(growable: false),
        ),
      );
    }

    final entity = _intersectionEntityResult();
    final discoverCells = _discoverCells(isDark: isDark);
    if (entity != null || discoverCells.isNotEmpty) {
      if (sections.isNotEmpty) {
        sections.add(SizedBox(height: AppSpacing.containerXl));
      }
      sections.add(
        _SearchResultSectionHeader(
          title: SearchText.searchDiscoverMoreIntersections,
          subtitle: _query.trim().isEmpty
              ? SearchText.searchRecommendMoreContent
              : UITextConstants.searchRecommendForQuery(_query.trim()),
        ),
      );
      sections.add(SizedBox(height: AppSpacing.intraGroupMd));
      if (entity != null) {
        sections.add(
          _EntityTopResultCard(
            entity: entity,
            isDark: isDark,
            onTap: () => _openHomepage(entity.homepageId),
          ),
        );
        if (discoverCells.isNotEmpty) {
          sections.add(SizedBox(height: AppSpacing.intraGroupMd));
        }
      }
      sections.addAll(_buildIntersectionGrid(cells: discoverCells));
    }

    if (sections.isEmpty) {
      return <Widget>[
        AppEmptyState(
          icon: CupertinoIcons.search,
          title: UITextConstants.searchNoIntersectionForQuery(_query),
          subtitle: SearchText.searchEmptySuggestion,
          actionLabel: SearchText.searchEditQuery,
          onAction: _editEmptySearchQuery,
        ),
      ];
    }
    return sections;
  }

  // 已形成的连接：connectionState 只负责分组；可见事实句必须来自云侧
  // intersectionReason.primaryText。端侧禁止把 connected 擅自翻译成
  // 「你已加入 / 你关注过 / 你互动过」。
  List<_IntersectionCardModel> _connectionCardModels() {
    final models = <_IntersectionCardModel>[];
    for (final hit in _connectedGroupHits) {
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
    for (final hit in _connectedUserHits) {
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
    for (final hit in _connectedLocations) {
      // 一方地点 location.place：未绑定实体主页，落地到临时地点卡（WP-D / R-S05e-1），
      // 不再误导向 homepage 详情。
      models.add(
        _IntersectionCardModel(
          targetType: _IntersectionTargetType.locationPlace,
          targetId: hit.objectId,
          coverUrl: '',
          categoryLabel: SearchText.searchCategoryLocation,
          categoryIcon: CupertinoIcons.location_solid,
          title: hit.title,
          reasonIcon: CupertinoIcons.location_solid,
          reasonText:
              _SearchNetworkResultsPageState._hitIntersectionPrimaryText(hit),
          footerText: hit.subtitle?.trim() ?? '',
        ),
      );
    }
    for (final item in _connectedContentItems) {
      final isVideo = item.contentType == 'video';
      final card = _NetworkResultCardModel.fromSearchItem(item);
      models.add(
        _IntersectionCardModel(
          targetType: _IntersectionTargetType.post,
          targetId: item.postId,
          coverUrl: item.coverUrl ?? '',
          categoryLabel: isVideo
              ? SearchText.searchCategoryVideo
              : SearchText.searchCategoryImage,
          categoryIcon: isVideo
              ? CupertinoIcons.play_rectangle_fill
              : CupertinoIcons.photo_fill,
          title: card.title,
          reasonIcon: isVideo
              ? CupertinoIcons.chat_bubble_fill
              : CupertinoIcons.heart_fill,
          reasonText:
              _SearchNetworkResultsPageState._contentIntersectionPrimaryText(
                item,
              ),
          footerText: card.footerLabel,
          metricLabel: item.likeCount > 0 ? '${item.likeCount}' : null,
          metricIcon: CupertinoIcons.heart,
          showVideoBadge: isVideo,
        ),
      );
    }
    return models;
  }

  List<Widget> _buildContentMasonryTiles({
    required bool isDark,
    required Color fgSecondary,
    required List<PostSearchItemView> items,
    Widget? relatedSearchCard,
  }) {
    final cards = items
        .map(_NetworkResultCardModel.fromSearchItem)
        .toList(growable: false);
    if (cards.isEmpty && relatedSearchCard == null) {
      return const <Widget>[];
    }
    final cells = <Widget>[
      ?relatedSearchCard,
      for (final card in cards)
        Builder(
          builder: (context) {
            final meta = _contentCloudMetaById[card.postId];
            // R-003：优先用云侧封面真实宽高比 / 排序理由；缺失时回退既有端侧渲染。
            final aspectRatio =
                meta?.aspectRatio ?? (card.showVideoBadge ? 16 / 9 : 1);
            final supportingText = meta?.topRankReason ?? card.supportingText;
            return ContentPreviewCard(
              isDark: isDark,
              title: card.title,
              supportingText: supportingText,
              coverUrl: card.coverUrl,
              showVideoBadge: card.showVideoBadge,
              mediaAspectRatio: aspectRatio,
              footer: Row(
                children: [
                  Expanded(
                    child: Text(
                      card.footerLabel,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: fgSecondary,
                      ),
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupXs),
                  ContentCardMetric(
                    icon: CupertinoIcons.heart,
                    label: '${card.likeCount}',
                    color: fgSecondary,
                  ),
                ],
              ),
              onTap: () {
                unawaited(_openPost(card.postId));
              },
            );
          },
        ),
    ];
    return _buildAdaptiveMasonry(cells: cells);
  }
}
