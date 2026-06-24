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
          _StatusMessage(
            text: UITextConstants.searchXiaoquLoading,
            isDark: isDark,
            loading: true,
          )
        else if ((_xiaoquResult?.citations?.length ?? 0) == 0)
          _StatusMessage(
            text: UITextConstants.searchNoNetworkReferences,
            isDark: isDark,
          )
        else
          ..._buildXiaoquCitationTiles(
            isDark: isDark,
            fgSecondary: fgSecondary,
          ),
      ];
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
    return withDegradeBanner(<Widget>[
      if (_isLoading)
        _StatusMessage(
          text: UITextConstants.pageLoadingA11y('${activeTab.label}结果'),
          isDark: isDark,
          loading: true,
        )
      else if (contentItems.isEmpty)
        _StatusMessage(text: UITextConstants.searchEmptyResult, isDark: isDark)
      else
        ..._buildContentMasonryTiles(
          isDark: isDark,
          fgSecondary: fgSecondary,
          items: contentItems,
          relatedSearchCard: _buildRelatedSearchCard(isDark: isDark),
        ),
    ]);
  }

  List<Widget> _buildAllResultChildren({
    required bool isDark,
    required Color fgSecondary,
    required _SearchNetworkTab activeTab,
  }) {
    if (_isLoading) {
      return <Widget>[
        _StatusMessage(
          text: UITextConstants.pageLoadingA11y('应用内结果'),
          isDark: isDark,
          loading: true,
        ),
      ];
    }

    final sections = <Widget>[];
    final entity = _entityTopResult();
    if (entity != null) {
      sections.add(
        _EntityTopResultCard(
          entity: entity,
          isDark: isDark,
          onTap: () => _openHomepage(entity.homepageId),
        ),
      );
    }
    final relatedSearchCard = _buildRelatedSearchCard(isDark: isDark);
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

    if (sections.isEmpty) {
      return <Widget>[
        _CategorySummaryCard(
          title: activeTab.label,
          description: activeTab.description,
          count: 0,
          isDark: isDark,
        ),
        _StatusMessage(
          text: UITextConstants.searchNoAppResults,
          isDark: isDark,
        ),
      ];
    }
    return sections;
  }

  List<Widget> _buildIntersectionResultChildren({
    required bool isDark,
    required Color fgSecondary,
  }) {
    if (_isLoading) {
      return <Widget>[
        _StatusMessage(text: '正在整理与你的交集', isDark: isDark, loading: true),
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
          title: '已形成的连接',
          subtitle: '基于你的互动、关注和加入',
          actionLabel: hasMore ? (_showAllConnections ? '收起' : '查看全部') : null,
          onAction: hasMore
              ? () => setState(() => _showAllConnections = !_showAllConnections)
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
          title: '发现更多交集',
          subtitle: _query.trim().isEmpty
              ? '为你推荐更多相关内容'
              : '为你推荐更多与“${_query.trim()}”相关的内容',
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
        _StatusMessage(
          text: UITextConstants.searchNoIntersectionResults,
          isDark: isDark,
        ),
      ];
    }
    return sections;
  }

  // 已形成的连接：展示用户与搜索词之间已经存在的真实连接（connectionState=connected）。
  // 仅展示连接态本身（你已加入 / 你关注过 / 你互动过），footer 用云侧真实计数，
  // 不拼装交集句、不伪造好友数、不编造互动数。
  List<_IntersectionCardModel> _connectionCardModels() {
    final models = <_IntersectionCardModel>[];
    for (final hit in _connectedGroupHits) {
      final card = _GroupResultCardModel.fromHit(hit);
      models.add(
        _IntersectionCardModel(
          targetType: _IntersectionTargetType.circle,
          targetId: card.circleId,
          coverUrl: card.coverUrl,
          categoryLabel: '圈子',
          categoryIcon: CupertinoIcons.person_3_fill,
          title: hit.title,
          reasonIcon: CupertinoIcons.person_2_fill,
          reasonText: '你已加入',
          footerText: card.footerLabel,
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
          categoryLabel: '地点',
          categoryIcon: CupertinoIcons.location_solid,
          title: hit.title,
          reasonIcon: CupertinoIcons.location_solid,
          reasonText: '你关注过',
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
          categoryLabel: isVideo ? '视频' : '图片',
          categoryIcon: isVideo
              ? CupertinoIcons.play_rectangle_fill
              : CupertinoIcons.photo_fill,
          title: card.title,
          reasonIcon: isVideo
              ? CupertinoIcons.chat_bubble_fill
              : CupertinoIcons.heart_fill,
          reasonText: isVideo ? '你互动过' : '你点赞过',
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
            return PostPreviewCard(
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
                  PostCardMetric(
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

  Future<void> _loadResults() async {
    final token = ++_requestToken;
    final stopwatch = Stopwatch()..start();
    final trimmedQuery = _query.trim();
    ref
        .read(pageLifecycleObservabilityProvider)
        .recordPageState(
          pageName: 'search_network_results',
          route: AppRoutePaths.globalSearch,
          surface: _activeTabId,
          phase: 'onlineLoading',
          copyKey: 'pageLoadingA11y',
        );
    setState(() {
      _isLoading = true;
      _errorSemantic = null;
      _degradeSignals = const <SearchDegradeSignal>[];
      if (_activeTabId == _SearchNetworkResultsPageState._tabXiaoqu) {
        _xiaoquResult = null;
      } else {
        _groupResults = const <SearchHit>[];
        _locationResults = const <SearchHit>[];
        _contentResults = const <PostSearchItemView>[];
        _contentCloudMetaById = const <String, _ContentCloudMeta>{};
        _relatedTerms = const <String>[];
      }
    });
    try {
      if (_activeTabId == _SearchNetworkResultsPageState._tabXiaoqu) {
        final result = await ref
            .read(assistantRepositoryProvider)
            .searchXiaoquResults(query: trimmedQuery);
        if (!mounted || token != _requestToken) {
          return;
        }
        setState(() {
          _xiaoquResult = result;
          _isLoading = false;
        });
        ref
            .read(pageLifecycleObservabilityProvider)
            .recordPageState(
              pageName: 'search_network_results',
              route: AppRoutePaths.globalSearch,
              surface: _activeTabId,
              phase: 'onlineSuccess',
              durationMs: stopwatch.elapsedMilliseconds,
              itemCount: result.citations?.length ?? 0,
            );
        return;
      }

      if (_activeTabId == _SearchNetworkResultsPageState._tabAll ||
          _activeTabId == _SearchNetworkResultsPageState._tabIntersection) {
        if (trimmedQuery.isEmpty) {
          if (!mounted || token != _requestToken) {
            return;
          }
          setState(() {
            _isLoading = false;
          });
          ref
              .read(pageLifecycleObservabilityProvider)
              .recordPageState(
                pageName: 'search_network_results',
                route: AppRoutePaths.globalSearch,
                surface: _activeTabId,
                phase: 'emptySuccess',
                durationMs: stopwatch.elapsedMilliseconds,
                itemCount: 0,
              );
          return;
        }
        if (_activeTabId == _SearchNetworkResultsPageState._tabAll) {
          final locationResponse = await _guardedSearchResponse(
            _loadLocationResponse(trimmedQuery),
          );
          final contentResponse = await _guardedSearchResponse(
            _loadContentResponse(trimmedQuery),
          );
          if (!mounted || token != _requestToken) {
            return;
          }
          setState(() {
            _locationResults = _locationHitsFromResponse(locationResponse);
            _contentResults = _contentItemsFromResponse(contentResponse);
            _relatedTerms = contentResponse.relatedTerms;
            _degradeSignals = _mergeDegradeSignals(<SearchResponse>[
              locationResponse,
              contentResponse,
            ]);
            _isLoading = false;
          });
          ref
              .read(pageLifecycleObservabilityProvider)
              .recordPageState(
                pageName: 'search_network_results',
                route: AppRoutePaths.globalSearch,
                surface: _activeTabId,
                phase: _contentResults.isEmpty && _locationResults.isEmpty
                    ? 'emptySuccess'
                    : 'onlineSuccess',
                durationMs: stopwatch.elapsedMilliseconds,
                itemCount: _contentResults.length + _locationResults.length,
              );
          return;
        }
        final groupResponse = await _guardedSearchResponse(
          _loadGroupResponse(trimmedQuery),
        );
        final locationResponse = await _guardedSearchResponse(
          _loadLocationResponse(trimmedQuery),
        );
        final contentResponse = await _guardedSearchResponse(
          _loadContentResponse(trimmedQuery),
        );
        if (!mounted || token != _requestToken) {
          return;
        }
        setState(() {
          _groupResults = _groupHitsFromResponse(groupResponse);
          _locationResults = _locationHitsFromResponse(locationResponse);
          _contentResults = _contentItemsFromResponse(contentResponse);
          _degradeSignals = _mergeDegradeSignals(<SearchResponse>[
            groupResponse,
            locationResponse,
            contentResponse,
          ]);
          _isLoading = false;
        });
        ref
            .read(pageLifecycleObservabilityProvider)
            .recordPageState(
              pageName: 'search_network_results',
              route: AppRoutePaths.globalSearch,
              surface: _activeTabId,
              phase:
                  _contentResults.isEmpty &&
                      _locationResults.isEmpty &&
                      _groupResults.isEmpty
                  ? 'emptySuccess'
                  : 'onlineSuccess',
              durationMs: stopwatch.elapsedMilliseconds,
              itemCount:
                  _contentResults.length +
                  _locationResults.length +
                  _groupResults.length,
            );
        return;
      }

      final response = trimmedQuery.isEmpty
          ? null
          : await _guardedSearchResponse(_loadContentResponse(trimmedQuery));
      final items = response == null
          ? const <PostSearchItemView>[]
          : _contentItemsFromResponse(response);
      if (!mounted || token != _requestToken) {
        return;
      }
      setState(() {
        _contentResults = items;
        _relatedTerms = response?.relatedTerms ?? const <String>[];
        _degradeSignals =
            response?.degradeSignals ?? const <SearchDegradeSignal>[];
        _isLoading = false;
      });
      ref
          .read(pageLifecycleObservabilityProvider)
          .recordPageState(
            pageName: 'search_network_results',
            route: AppRoutePaths.globalSearch,
            surface: _activeTabId,
            phase: items.isEmpty ? 'emptySuccess' : 'onlineSuccess',
            durationMs: stopwatch.elapsedMilliseconds,
            itemCount: items.length,
          );
    } catch (error) {
      if (!mounted || token != _requestToken) {
        return;
      }
      final resolved = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.page,
      );
      setState(() {
        _errorSemantic = UiErrorSemantic(
          category: resolved.category,
          scope: resolved.scope,
          title: UITextConstants.searchUnavailableTitle,
          message: UITextConstants.searchUnavailableMessage,
          secondaryMessage: resolved.secondaryMessage,
          primaryAction: resolved.primaryAction,
          secondaryAction: resolved.secondaryAction,
          dismissible: resolved.dismissible,
          sourceCode: resolved.sourceCode,
          failureKind: resolved.failureKind,
          copyKey: 'searchUnavailableTitle',
          recoveryAction: resolved.recoveryAction,
          presentation: resolved.presentation,
          tone: resolved.tone,
        );
        _isLoading = false;
      });
      ref
          .read(pageLifecycleObservabilityProvider)
          .recordPageState(
            pageName: 'search_network_results',
            route: AppRoutePaths.globalSearch,
            surface: _activeTabId,
            phase: 'blockingFailure',
            copyKey: 'searchUnavailableTitle',
            error: error,
            durationMs: stopwatch.elapsedMilliseconds,
          );
    }
  }

  List<PostSearchItemView> _contentItemsFromResponse(SearchResponse response) {
    final cloudMeta = <String, _ContentCloudMeta>{};
    final results = <PostSearchItemView>[];
    for (final hit in _hitsFromResponse(response)) {
      if (hit.objectType != SearchObjectType.contentPost) {
        continue;
      }
      final item =
          hit.asContentPostItem ??
          PostSearchItemView.fromMap(hit.payload.toWireMap());
      results.add(item);
      final meta = _ContentCloudMeta(
        rankPosition: hit.rankPosition,
        coverWidth: hit.coverWidth,
        coverHeight: hit.coverHeight,
        rankReasons: hit.rankReasons,
      );
      if (item.postId.isNotEmpty && meta.hasCloudSignal) {
        cloudMeta[item.postId] = meta;
      }
    }
    // R-001：命中携带云侧 rankPosition 时，按云侧排序而非端侧 publishedAt 兜底排序。
    final hasCloudRank = results.any(
      (item) => cloudMeta[item.postId]?.rankPosition != null,
    );
    if (hasCloudRank) {
      results.sort((left, right) {
        final leftRank = cloudMeta[left.postId]?.rankPosition;
        final rightRank = cloudMeta[right.postId]?.rankPosition;
        if (leftRank == null && rightRank == null) {
          return 0;
        }
        if (leftRank == null) {
          return 1;
        }
        if (rightRank == null) {
          return -1;
        }
        return leftRank.compareTo(rightRank);
      });
    } else {
      results.sort((left, right) {
        final leftTime = left.publishedAt;
        final rightTime = right.publishedAt;
        if (leftTime == null && rightTime == null) {
          return 0;
        }
        if (leftTime == null) {
          return 1;
        }
        if (rightTime == null) {
          return -1;
        }
        return rightTime.compareTo(leftTime);
      });
    }
    final sorted = results.take(12).toList(growable: false);
    _contentCloudMetaById = cloudMeta;
    return sorted;
  }

  Future<void> _openPost(String postId) async {
    if (postId.trim().isEmpty) {
      return;
    }
    try {
      final detail = await ref
          .read(contentRepositoryProvider)
          .getPost(postId: postId);
      applyConfirmedInteractionPost(ref, detail.post);
      if (!mounted) {
        return;
      }
      final dto = detail.post;
      final raw = detail.mergedArticleWireMap;
      final interactionSnapshot = buildMediaViewerInteractionSnapshot(
        posts: <PostBaseDto>[dto],
        discoveryState: ref.read(discoveryStateProvider),
        relationshipState: ref.read(userRelationshipStateProvider),
        postInteractionState: ref.read(postInteractionStateProvider),
      );
      primeMediaViewerInteractionSnapshot(ref, interactionSnapshot);
      final navFeedRequestId = ref
          .read(feedSessionProvider.notifier)
          .newFeedRequestId();
      final result = await context.push<Object?>(
        AppRoutePaths.workBrowser(
          workId: dto.id,
          filter: dto.isVideoLike
              ? 'video'
              : (dto.isArticleLike ? 'article' : 'image'),
          source: 'global-search-network',
          index: '0',
        ),
        extra: MediaViewerExtra(
          posts: <ContentSurfaceView>[
            ContentSurfaceViewMapper.fromDto(dto, wire: raw),
          ],
          dtoPosts: <PostBaseDto>[dto],
          initialIndex: 0,
          category: dto.isVideoLike
              ? 'video'
              : (dto.identity == 'moment' ? 'moment' : 'photo'),
          source: 'global-search-network',
          rawPostsById: searchNetworkSinglePostMediaRaws(dto: dto, wire: raw),
          interactionSnapshot: interactionSnapshot,
          referralSource: ReferralSource.search,
          feedRequestId: navFeedRequestId,
        ),
      );
      if (result is MediaViewerResult) {
        applyMediaViewerResultToInteractionState(ref, result);
      }
    } catch (error) {
      await _showOpenPostFailure(error);
    }
  }
}
