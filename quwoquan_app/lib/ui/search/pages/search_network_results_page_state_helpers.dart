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
            loadingLabel: UITextConstants.searchXiaoquLoading,
            showSlowHint: true,
            slowLabel: UITextConstants.searchXiaoquLoading,
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
        AppRequestFeedback.page(
          showSlowHint: _isSlow,
          loadingLabel: UITextConstants.pageLoadingA11y('${activeTab.label}结果'),
          slowLabel: UITextConstants.searchWaitSlow,
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
        AppRequestFeedback.page(
          showSlowHint: _isSlow,
          loadingLabel: UITextConstants.pageLoadingA11y('应用内结果'),
          slowLabel: UITextConstants.searchWaitSlow,
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
        AppRequestFeedback.page(
          showSlowHint: _isSlow,
          loadingLabel: '正在整理与你的交集',
          slowLabel: UITextConstants.searchWaitSlow,
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
          title: '已形成的连接',
          subtitle: '基于你的互动、关注和加入',
          actionLabel: hasMore ? (_showAllConnections ? '收起' : '查看全部') : null,
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
    final activeTabId = _activeTabId;
    ref
        .read(pageLifecycleObservabilityProvider)
        .recordPageState(
          pageName: 'search_network_results',
          route: AppRoutePaths.globalSearch,
          surface: _activeTabId,
          phase: 'onlineLoading',
          copyKey: 'pageLoadingA11y',
          waitMode: _activeTabId == _SearchNetworkResultsPageState._tabXiaoqu
              ? 'long_task'
              : 'foreground',
        );
    _setMountedState(() {
      _isLoading = true;
      _isSlow = false;
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
    late final int generation;
    try {
      if (_activeTabId == _SearchNetworkResultsPageState._tabXiaoqu) {
        generation = _waitController.start(
          mode: AppRequestWaitMode.longTask,
          showSlowHint: false,
        );
        final result = await ref
            .read(assistantRepositoryProvider)
            .searchXiaoquResults(query: trimmedQuery);
        if (!_isCurrentRequest(token, generation, activeTabId)) {
          return;
        }
        _setMountedState(() {
          _xiaoquResult = result;
          _isLoading = false;
          _isSlow = false;
        });
        _waitController.complete(generation);
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

      final cancellation = CloudOperationCancellationSignal();
      generation = _waitController.start(
        mode: AppRequestWaitMode.foreground,
        cancellation: cancellation,
        onSlow: (_) {
          if (!_isCurrentRequest(token, generation, activeTabId)) return;
          _setMountedState(() => _isSlow = true);
        },
        onTimeout: (_) {
          if (!mounted ||
              token != _requestToken ||
              _activeTabId != activeTabId) {
            return;
          }
          final error = TimeoutException(
            'Canonical search exceeded the 6 second foreground budget.',
          );
          _setMountedState(() {
            _errorSemantic = _searchFailureSemantic(error);
            _isLoading = false;
            _isSlow = false;
          });
        },
        observer: (phase, durationMilliseconds) {
          if (phase == 'complete') return;
          ref
              .read(pageLifecycleObservabilityProvider)
              .recordPageState(
                pageName: 'search_network_results',
                route: AppRoutePaths.globalSearch,
                surface: activeTabId,
                phase: phase,
                durationMs: durationMilliseconds,
                waitMode: 'foreground',
              );
        },
      );
      if (trimmedQuery.isEmpty) {
        if (!_isCurrentRequest(token, generation, activeTabId)) return;
        _setMountedState(() {
          _isLoading = false;
          _isSlow = false;
        });
        _waitController.complete(generation);
        ref
            .read(pageLifecycleObservabilityProvider)
            .recordPageState(
              pageName: 'search_network_results',
              route: AppRoutePaths.globalSearch,
              surface: activeTabId,
              phase: 'emptySuccess',
              durationMs: stopwatch.elapsedMilliseconds,
              itemCount: 0,
              waitMode: 'foreground',
            );
        return;
      }

      // 正式结果页只调用 canonical POST /search 一次；云侧负责跨域 fan-out。
      final response = await ref
          .read(searchRepositoryProvider)
          .search(
            SearchRequest(
              query: trimmedQuery,
              mode: SearchMode.result,
              objectTypes: _canonicalObjectTypes(activeTabId),
              contentTypes: _canonicalContentTypes(activeTabId),
              limit: 12,
            ),
            cancellation: cancellation,
            deadlineAt: DateTime.now().add(
              AppRequestWaitTimings.foregroundReadDeadline,
            ),
          );
      if (!_isCurrentRequest(token, generation, activeTabId)) {
        return;
      }
      _setMountedState(() {
        _groupResults = _groupHitsFromResponse(response);
        _locationResults = _locationHitsFromResponse(response);
        _contentResults = _contentItemsFromResponse(response);
        _relatedTerms = response.relatedTerms;
        _degradeSignals = response.degradeSignals;
        _isLoading = false;
        _isSlow = false;
      });
      _waitController.complete(generation);
      final itemCount =
          _contentResults.length +
          _locationResults.length +
          _groupResults.length;
      ref
          .read(pageLifecycleObservabilityProvider)
          .recordPageState(
            pageName: 'search_network_results',
            route: AppRoutePaths.globalSearch,
            surface: activeTabId,
            phase: response.degradeSignals.isNotEmpty
                ? 'partial'
                : (itemCount == 0 ? 'emptySuccess' : 'onlineSuccess'),
            durationMs: stopwatch.elapsedMilliseconds,
            itemCount: itemCount,
            waitMode: 'foreground',
          );
    } catch (error) {
      if (!mounted || token != _requestToken || _activeTabId != activeTabId) {
        return;
      }
      if (!_waitController.isCurrent(generation)) return;
      _setMountedState(() {
        _errorSemantic = _searchFailureSemantic(error);
        _isLoading = false;
        _isSlow = false;
      });
      _waitController.complete(generation);
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
            waitMode: activeTabId == _SearchNetworkResultsPageState._tabXiaoqu
                ? 'long_task'
                : 'foreground',
          );
    }
  }

  bool _isCurrentRequest(int token, int generation, String activeTabId) {
    return mounted &&
        token == _requestToken &&
        _activeTabId == activeTabId &&
        _waitController.isCurrent(generation);
  }

  Set<SearchObjectType> _canonicalObjectTypes(String activeTabId) {
    if (activeTabId == _SearchNetworkResultsPageState._tabIntersection) {
      return const <SearchObjectType>{
        SearchObjectType.contentPost,
        SearchObjectType.entityHomepage,
        SearchObjectType.locationPlace,
        SearchObjectType.circleGroup,
        SearchObjectType.circleCircle,
      };
    }
    if (activeTabId == _SearchNetworkResultsPageState._tabAll) {
      return const <SearchObjectType>{
        SearchObjectType.contentPost,
        SearchObjectType.entityHomepage,
        SearchObjectType.locationPlace,
      };
    }
    return const <SearchObjectType>{SearchObjectType.contentPost};
  }

  Set<SearchContentTypeFilter> _canonicalContentTypes(String activeTabId) {
    return switch (activeTabId) {
      _SearchNetworkResultsPageState._tabVideo =>
        const <SearchContentTypeFilter>{SearchContentTypeFilter.video},
      _SearchNetworkResultsPageState._tabImage =>
        const <SearchContentTypeFilter>{SearchContentTypeFilter.image},
      _SearchNetworkResultsPageState._tabArticle =>
        const <SearchContentTypeFilter>{SearchContentTypeFilter.article},
      _ => widget.launchContext.searchObjectSelection.normalized().contentTypes,
    };
  }

  UiErrorSemantic _searchFailureSemantic(Object error) {
    final resolved = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
    return UiErrorSemantic(
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
          .read(globalSearchContentPostDetailReaderProvider)
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
