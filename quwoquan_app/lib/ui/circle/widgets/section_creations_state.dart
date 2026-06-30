part of 'section_creations.dart';

class _SectionCreationsState extends ConsumerState<SectionCreations> {
  bool _isLoading = true;
  UiErrorSemantic? _errorSemantic;
  List<CircleHubFeedPostEntry> _feedEntries = const [];
  String? _circleCategoryId;

  List<UserProfileSubTabConfig> get _creationFilters =>
      UserProfileUIConfig.creationSubTabs;

  static const double _creationGridCoverAspectRatio = 0.92;
  static const ArticleDistributionProfileConfig
  _circleArticleDistributionProfile = ArticleDistributionProfileConfig(
    id: 'circle_dual_column_with_optional_cover',
    surface: 'circle_dual_column',
    layout: 'cover_top_title_summary_or_text_card',
    coverMode: 'optional_cover',
    summaryLineLimit: 3,
  );

  static const _sortLabels = {
    CreationSortMode.latest: UITextConstants.circleSortLatest,
    CreationSortMode.hot: UITextConstants.circleSortHot,
    CreationSortMode.featured: UITextConstants.circleSortFeatured,
  };

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadFeed());
  }

  @override
  Widget build(BuildContext context) {
    final circleState = ref.watch(circleStateProvider(widget.circleId));
    final circleCtrl = ref.read(circleStateProvider(widget.circleId).notifier);
    final fg = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    final bgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.backgroundSecondary,
    );
    final bgTertiary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.backgroundTertiary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundSecondary,
    );
    final borderColor = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.borderPrimary,
    );

    final content = _buildContent(circleState, fgSecondary);
    final contentSurface = widget.inlineScroll
        ? content
        : _buildSurface(
            backgroundColor: bgSecondary,
            borderColor: borderColor,
            padding: EdgeInsets.zero,
            child: content,
          );

    return LayoutBuilder(
      builder: (context, constraints) {
        final compactHeight = constraints.maxHeight < 320;
        final compactEmptyState =
            compactHeight &&
            !_isLoading &&
            _errorSemantic == null &&
            _feedEntries.isEmpty;
        final outerHorizontal = compactHeight
            ? AppSpacing.containerSm
            : AppSpacing.containerMd;
        final outerTop = compactHeight
            ? (compactEmptyState ? AppSpacing.zero : AppSpacing.intraGroupXs)
            : AppSpacing.containerSm;
        final outerBottom = compactHeight
            ? (compactEmptyState
                  ? AppSpacing.intraGroupXs
                  : AppSpacing.containerSm)
            : AppSpacing.containerLg;
        final sectionGap = compactHeight
            ? AppSpacing.intraGroupXs
            : AppSpacing.sm;
        final filterGap = compactHeight ? AppSpacing.xs : AppSpacing.sm;

        final filterSurface = Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildCreationFilterRow(circleState, circleCtrl),
            if (_isAdminOrOwner && !compactHeight) ...[
              SizedBox(height: filterGap),
              Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerMd,
                ),
                child: _buildSortControls(
                  circleState,
                  circleCtrl,
                  fg,
                  fgSecondary,
                ),
              ),
              SizedBox(
                height: compactHeight ? AppSpacing.intraGroupXs : AppSpacing.xs,
              ),
              Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerMd,
                ),
                child: _buildViewModeToggle(
                  circleState,
                  circleCtrl,
                  fgSecondary: fgSecondary,
                  borderColor: borderColor,
                  backgroundColor: bgTertiary,
                ),
              ),
            ],
          ],
        );

        if (compactEmptyState) {
          return Padding(
            padding: EdgeInsets.fromLTRB(
              outerHorizontal,
              outerTop,
              outerHorizontal,
              outerBottom,
            ),
            child: contentSurface,
          );
        }

        final child = Column(
          mainAxisSize: MainAxisSize.max,
          children: [
            if (!compactEmptyState && compactHeight)
              Flexible(
                fit: FlexFit.loose,
                child: SingleChildScrollView(child: filterSurface),
              )
            else if (!compactEmptyState)
              filterSurface,
            if (!compactEmptyState) SizedBox(height: sectionGap),
            if (widget.inlineScroll)
              contentSurface
            else
              Flexible(fit: FlexFit.tight, child: contentSurface),
          ],
        );

        return Padding(
          padding: EdgeInsets.fromLTRB(
            outerHorizontal,
            outerTop,
            outerHorizontal,
            outerBottom,
          ),
          child: child,
        );
      },
    );
  }

  bool get _isAdminOrOwner =>
      widget.role == CircleRole.owner || widget.role == CircleRole.admin;

  ({String? identity, String? type}) _feedQueryForState(CircleState state) {
    switch (state.activeSubTab) {
      case CreationSubTab.image:
        return (identity: 'work', type: 'image');
      case CreationSubTab.video:
        return (identity: 'work', type: 'video');
      case CreationSubTab.article:
        return (identity: 'work', type: 'article');
      case CreationSubTab.all:
        return (identity: null, type: null);
    }
  }

  /// 二级过滤（全部/图片/视频/长文）：高保口径横向胶囊条，左对齐、选中淡蓝底，
  /// 与实体主页共用 [ObjectSecondaryFilterBar]（漏斗 + 弹层改回胶囊，单一真相源）。
  Widget _buildCreationFilterRow(
    CircleState circleState,
    CircleStateNotifier circleCtrl,
  ) {
    final activeFilter = _creationFilters.firstWhere(
      (filter) => _creationSubTabForId(filter.id) == circleState.activeSubTab,
      orElse: () => _creationFilters.first,
    );
    return ObjectSecondaryFilterBar(
      barKey: const ValueKey<String>('circle-creations-filter-bar'),
      optionKeyPrefix: 'circle-creations-filter-option-',
      items: _creationFilters
          .map(
            (filter) => ObjectSecondaryFilterItem(
              id: filter.id,
              label: UITextConstants.contentLabelForKey(filter.labelKey),
            ),
          )
          .toList(growable: false),
      activeId: activeFilter.id,
      onSelect: (id) {
        final next = _creationSubTabForId(id);
        if (next != circleState.activeSubTab) {
          circleCtrl.setSubTab(next);
          _loadFeed();
        }
      },
    );
  }

  CreationSubTab _creationSubTabForId(String id) {
    switch (id) {
      case 'image':
        return CreationSubTab.image;
      case 'video':
        return CreationSubTab.video;
      case 'article':
        return CreationSubTab.article;
      default:
        return CreationSubTab.all;
    }
  }

  bool _matchesIdentityFilter(
    CircleHubFeedPostEntry entry,
    CreationSubTab tab,
  ) {
    switch (tab) {
      case CreationSubTab.image:
        return _entryDisplayFormat(entry) == 'image';
      case CreationSubTab.video:
        return _entryDisplayFormat(entry) == 'video';
      case CreationSubTab.article:
        return _entryDisplayFormat(entry) == 'note';
      case CreationSubTab.all:
        return true;
    }
  }

  bool _entryIsArticle(CircleHubFeedPostEntry entry) {
    final d = entry.dto;
    if (d != null) return d.type == 'article';
    return _rawIsArticle(entry.raw);
  }

  bool _entryIsVideo(CircleHubFeedPostEntry entry) {
    final d = entry.dto;
    if (d != null) return d.isVideoLike;
    return _rawIsVideo(entry.raw);
  }

  String _rawIdentity(Map<String, dynamic> item) {
    return (item['contentIdentity'] ??
            (item['type']?.toString() == 'micro' ? 'moment' : 'work'))
        .toString();
  }

  String _rawDisplayFormat(Map<String, dynamic> item) {
    final type = (item['type'] ?? '').toString();
    switch (type) {
      case 'image':
        return 'image';
      case 'video':
        return 'video';
      case 'article':
        return 'note';
      case 'micro':
        return 'micro';
      default:
        return type;
    }
  }

  String _entryIdentity(CircleHubFeedPostEntry entry) {
    final d = entry.dto;
    if (d != null) {
      if (d.identity == 'moment') return 'moment';
      return d.identity.isNotEmpty
          ? d.identity
          : (entry.raw['type']?.toString() == 'micro' ? 'moment' : 'work');
    }
    return _rawIdentity(entry.raw);
  }

  String _entryDisplayFormat(CircleHubFeedPostEntry entry) {
    final d = entry.dto;
    if (d != null) {
      switch (d.type) {
        case 'image':
          return 'image';
        case 'video':
          return 'video';
        case 'article':
          return 'note';
        case 'micro':
          return 'micro';
        default:
          return d.type;
      }
    }
    return _rawDisplayFormat(entry.raw);
  }

  String _entryArticleTemplate(CircleHubFeedPostEntry entry) {
    final rp = entry.tryReadPresentation();
    if (rp != null && rp.articleTemplate.isNotEmpty) return rp.articleTemplate;
    return (entry.raw['articleTemplate'] ?? '').toString();
  }

  String _entryCoverUrl(CircleHubFeedPostEntry entry) => entry.wireCoverUrl;

  String _entryHeadlineText(CircleHubFeedPostEntry entry) {
    final rp = entry.tryReadPresentation();
    if (rp != null && rp.title.isNotEmpty) return rp.title;
    return _rawHeadlineText(entry.raw);
  }

  String _entrySupportingText(CircleHubFeedPostEntry entry) {
    final rp = entry.tryReadPresentation();
    if (rp == null) return _rawSupportingText(entry.raw);
    final headline = rp.title.isNotEmpty ? rp.title : _entryTypeLabel(entry);
    final summary = rp.body.trim();
    if (_entryIsArticle(entry) && summary.isNotEmpty && summary != headline) {
      return summary;
    }
    return _rawSupportingText(entry.raw);
  }

  int _entryLikeCount(CircleHubFeedPostEntry entry) {
    final rp = entry.tryReadPresentation();
    if (rp != null) return rp.likeCount;
    return _rawLikeCount(entry.raw);
  }

  String _entryAuthorDisplayName(CircleHubFeedPostEntry entry) {
    return entry.wireAuthorDisplayName.trim();
  }

  String _entryId(CircleHubFeedPostEntry entry) {
    final rp = entry.tryReadPresentation();
    if (rp != null && rp.postId.isNotEmpty) return rp.postId;
    return entry.postIdForKey;
  }

  String _entryTypeLabel(CircleHubFeedPostEntry entry) {
    final identity = _entryIdentity(entry);
    if (identity == 'moment') {
      return UITextConstants.creationFilterMoment;
    }
    switch (_entryDisplayFormat(entry)) {
      case 'image':
        return UITextConstants.workFormatFilterImage;
      case 'video':
        return UITextConstants.workFormatFilterVideo;
      case 'note':
        return UITextConstants.creationSubText;
      default:
        return UITextConstants.homepageContentTypeDefault;
    }
  }

  Widget _entryArticleTemplateBadge(CircleHubFeedPostEntry entry) {
    return _rawArticleTemplateBadge(entry.raw);
  }

  String _entryArticleTemplateLabel(CircleHubFeedPostEntry entry) {
    final id = _entryArticleTemplate(entry);
    return articleTemplatePresetFromString(id.isNotEmpty ? id : null).label;
  }

  String _entryArticleRecommendationLabel(CircleHubFeedPostEntry entry) {
    return _rawArticleRecommendationLabel(entry.raw);
  }

  String _rawTypeLabel(Map<String, dynamic> item) {
    final identity = _rawIdentity(item);
    if (identity == 'moment') {
      return UITextConstants.creationFilterMoment;
    }
    switch (_rawDisplayFormat(item)) {
      case 'image':
        return UITextConstants.workFormatFilterImage;
      case 'video':
        return UITextConstants.workFormatFilterVideo;
      case 'note':
        return UITextConstants.creationSubText;
      default:
        return UITextConstants.homepageContentTypeDefault;
    }
  }

  Widget _buildSortControls(
    CircleState circleState,
    CircleStateNotifier circleCtrl,
    Color fg,
    Color fgSecondary,
  ) {
    final activeSortMode = circleState.sortMode;
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      physics: const BouncingScrollPhysics(),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: CreationSortMode.values.map((mode) {
          final selected = mode == activeSortMode;
          return Padding(
            padding: EdgeInsets.only(right: AppSpacing.sm),
            child: GestureDetector(
              onTap: () {
                circleCtrl.setSortMode(mode);
                _loadFeed();
              },
              child: Container(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.md,
                  vertical: AppSpacing.sm,
                ),
                decoration: BoxDecoration(
                  color: selected
                      ? (widget.isDark
                            ? AppColors.white.withValues(alpha: 0.1)
                            : AppColors.black.withValues(alpha: 0.06))
                      : null,
                  borderRadius: BorderRadius.circular(
                    AppSpacing.circularBorderRadius,
                  ),
                  border: Border.all(
                    color: widget.isDark
                        ? AppColors.white.withValues(alpha: 0.24)
                        : AppColors.black.withValues(alpha: 0.12),
                  ),
                ),
                child: Text(
                  _sortLabels[mode]!,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.extraBold,
                    color: selected ? fg : fgSecondary,
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildViewModeToggle(
    CircleState circleState,
    CircleStateNotifier circleCtrl, {
    required Color fgSecondary,
    required Color borderColor,
    required Color backgroundColor,
  }) {
    final activeMode = circleState.viewMode;
    return Align(
      alignment: Alignment.centerRight,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          _ViewModeButton(
            icon: CupertinoIcons.square_grid_2x2,
            tooltip: '网格视图',
            selected: activeMode == CreationViewMode.grid,
            fgSecondary: fgSecondary,
            borderColor: borderColor,
            backgroundColor: backgroundColor,
            onPressed: () => circleCtrl.setViewMode(CreationViewMode.grid),
          ),
          SizedBox(width: AppSpacing.xs),
          _ViewModeButton(
            icon: CupertinoIcons.rectangle_grid_1x2,
            tooltip: '列表视图',
            selected: activeMode == CreationViewMode.list,
            fgSecondary: fgSecondary,
            borderColor: borderColor,
            backgroundColor: backgroundColor,
            onPressed: () => circleCtrl.setViewMode(CreationViewMode.list),
          ),
        ],
      ),
    );
  }

  Future<void> _openMediaViewer(
    BuildContext context,
    CircleHubFeedPostEntry tapped,
    List<CircleHubFeedPostEntry> sourceItems,
  ) async {
    final tappedDto = _tryParsePost(tapped);
    if (tappedDto == null) return;
    if (!_supportsViewer(tappedDto)) return;

    final viewerEntries = sourceItems
        .where((e) {
          final d = _tryParsePost(e);
          return d != null && _supportsViewer(d);
        })
        .toList(growable: false);
    if (viewerEntries.isEmpty) return;

    final viewerDtos = viewerEntries
        .map((e) => _tryParsePost(e)!)
        .toList(growable: false);
    final initialIndex = viewerDtos
        .indexWhere((item) => item.id == tappedDto.id)
        .clamp(0, viewerDtos.length - 1);
    final rawPostsById = <String, MediaViewerPostWireRow>{
      for (final e in viewerEntries)
        _tryParsePost(e)!.id: MediaViewerPostWireRow.fromDynamicMap(
          Map<String, dynamic>.from(e.raw),
        ),
    };

    final interactionSnapshot = buildMediaViewerInteractionSnapshot(
      posts: viewerDtos,
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
        workId: tappedDto.id,
        filter: _isVideoPost(tappedDto)
            ? 'video'
            : (tappedDto.isArticleLike ? 'article' : 'image'),
        source: 'circle',
        index: '$initialIndex',
      ),
      extra: MediaViewerExtra(
        posts: viewerDtos
            .map(
              (dto) => ContentSurfaceViewMapper.fromDto(dto, wire: dto.toMap()),
            )
            .toList(growable: false),
        dtoPosts: viewerDtos,
        initialIndex: initialIndex,
        source: 'circle',
        circleId: widget.circleId,
        rawPostsById: rawPostsById,
        interactionSnapshot: interactionSnapshot,
        referralSource: ReferralSource.circlePost,
        feedRequestId: navFeedRequestId,
      ),
    );
    if (result is MediaViewerResult) {
      _applyViewerResult(result);
    }
  }

  PostBaseDto? _tryParsePost(CircleHubFeedPostEntry entry) =>
      entry.tryResolveDto();

  bool _supportsViewer(PostBaseDto post) {
    return post.supportsUnifiedViewer;
  }

  bool _isVideoPost(PostBaseDto post) {
    return post.isVideoLike;
  }

  void _applyViewerResult(MediaViewerResult result) {
    applyMediaViewerResultToInteractionState(ref, result);
    setState(() {
      CircleHubFeedPostEntry.applyResultToList(_feedEntries, result);
    });
  }

  Widget _buildGridItem(
    CircleHubFeedPostEntry entry,
    Color fgSecondary, {
    required VoidCallback onTap,
  }) {
    if (_entryIsArticle(entry)) {
      return _buildArticleGridItem(entry, fgSecondary, onTap: onTap);
    }
    // 统一记录卡范式：封面 + 唯一交集句 + 标题 + 作者 + 点赞。
    final dto = entry.tryResolveDto();
    if (dto != null) {
      return RecordPostCard(
        key: ValueKey<String>('circle-record-grid-${_entryId(entry)}'),
        post: dto,
        isDark: widget.isDark,
        onTap: onTap,
        // N5：圈子记录卡 → 交集句对象片段点击精确归因为圈子内容（非推荐流）。
        referralSource: ReferralSource.circlePost,
      );
    }
    final typeLabel = _entryTypeLabel(entry);
    return PostPreviewCard(
      isDark: widget.isDark,
      title: _entryHeadlineText(entry),
      supportingText: '',
      coverUrl: _entryCoverUrl(entry),
      mediaAspectRatio: _creationGridCoverAspectRatio,
      showVideoBadge: _entryIsVideo(entry),
      mediaOverlay: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.intraGroupXs,
        ),
        decoration: BoxDecoration(
          color: AppColors.black.withValues(alpha: 0.32),
          borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        ),
        child: Text(
          typeLabel,
          style: TextStyle(
            color: AppColors.white,
            fontSize: AppTypography.xs,
            fontWeight: AppTypography.semiBold,
          ),
        ),
      ),
      onTap: onTap,
      footer: Row(
        children: [
          PostCardMetric(
            icon: CupertinoIcons.heart_fill,
            label: '${_entryLikeCount(entry)}',
            color: fgSecondary,
            iconColor: AppColors.error.withValues(alpha: 0.9),
            textStyle: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildListItem(
    CircleHubFeedPostEntry entry,
    Color fgSecondary, {
    required VoidCallback onTap,
  }) {
    if (_entryIsArticle(entry)) {
      return _buildArticleListItem(entry, fgSecondary, onTap: onTap);
    }
    final typeLabel = _entryTypeLabel(entry);
    return PostPreviewListTile(
      isDark: widget.isDark,
      eyebrowText: typeLabel,
      title: _entryHeadlineText(entry),
      supportingText: _entrySupportingText(entry),
      coverUrl: _entryCoverUrl(entry),
      showVideoBadge: _entryIsVideo(entry),
      onTap: onTap,
      footer: Row(
        children: [
          PostCardMetric(
            icon: CupertinoIcons.heart_fill,
            label: '赞 ${_entryLikeCount(entry)}',
            color: fgSecondary,
            iconColor: AppColors.error.withValues(alpha: 0.9),
            textStyle: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
      ),
      trailing: Icon(
        CupertinoIcons.chevron_forward,
        size: AppSpacing.iconSmall,
        color: fgSecondary,
      ),
    );
  }

  Widget _buildArticleGridItem(
    CircleHubFeedPostEntry entry,
    Color fgSecondary, {
    required VoidCallback onTap,
  }) {
    final recommendationLabel = _entryArticleRecommendationLabel(entry);
    final authorName = _entryAuthorDisplayName(entry);
    return PostPreviewCard(
      key: ValueKey<String>('circle-article-grid-${_entryId(entry)}'),
      isDark: widget.isDark,
      title: _entryHeadlineText(entry),
      supportingText: _entrySupportingText(entry),
      supportingTextMaxLines:
          _circleArticleDistributionProfile.summaryLineLimit,
      coverUrl: _entryCoverUrl(entry),
      mediaAspectRatio: _creationGridCoverAspectRatio,
      mediaOverlay: _entryArticleTemplateBadge(entry),
      header: IntersectionReasonChip.fromReasons(
        entry.dto?.intersectionReasons,
        isDark: widget.isDark,
        // N5：圈子文章卡 → 交集句对象片段点击精确归因为圈子内容（非推荐流）。
        referralSource: ReferralSource.circlePost,
      ),
      onTap: onTap,
      footer: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (recommendationLabel.isNotEmpty) ...[
            Text(
              recommendationLabel,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.xs,
                color: AppColors.primaryColor,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs / 2),
          ],
          Row(
            children: [
              Expanded(
                child: Text(
                  authorName,
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
                icon: CupertinoIcons.heart_fill,
                label: '${_entryLikeCount(entry)}',
                color: fgSecondary,
                iconColor: AppColors.error.withValues(alpha: 0.9),
                textStyle: TextStyle(
                  fontSize: AppTypography.iosCaption1,
                  color: fgSecondary,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildArticleListItem(
    CircleHubFeedPostEntry entry,
    Color fgSecondary, {
    required VoidCallback onTap,
  }) {
    final recommendationLabel = _entryArticleRecommendationLabel(entry);
    final authorName = _entryAuthorDisplayName(entry);
    return PostPreviewListTile(
      key: ValueKey<String>('circle-article-list-${_entryId(entry)}'),
      isDark: widget.isDark,
      eyebrowText: recommendationLabel.isNotEmpty
          ? recommendationLabel
          : '笔记 · ${_entryArticleTemplateLabel(entry)}',
      eyebrowColor: AppColors.primaryColor,
      title: _entryHeadlineText(entry),
      supportingText: _entrySupportingText(entry),
      supportingTextMaxLines:
          _circleArticleDistributionProfile.summaryLineLimit,
      coverUrl: _entryCoverUrl(entry),
      hideThumbnailWhenNoCover: true,
      onTap: onTap,
      footer: Row(
        children: [
          Expanded(
            child: Text(
              authorName,
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
            icon: CupertinoIcons.heart_fill,
            label: '赞 ${_entryLikeCount(entry)}',
            color: fgSecondary,
            iconColor: AppColors.error.withValues(alpha: 0.9),
            textStyle: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
      ),
      trailing: Icon(
        CupertinoIcons.chevron_forward,
        size: AppSpacing.iconSmall,
        color: fgSecondary,
      ),
    );
  }

  bool _rawIsArticle(Map<String, dynamic> item) {
    return (item['contentType'] ?? item['type'] ?? '').toString() == 'article';
  }

  String _rawTitle(Map<String, dynamic> item) {
    final candidates = [
      item['title'],
      item['body'],
      item['caption'],
      item['summary'],
    ];
    for (final candidate in candidates) {
      final text = candidate?.toString().trim() ?? '';
      if (text.isNotEmpty) {
        return text;
      }
    }
    return _rawTypeLabel(item);
  }

  String _rawHeadlineText(Map<String, dynamic> item) {
    final title = _rawTitle(item);
    if (title.isNotEmpty) {
      return title;
    }
    return _rawTypeLabel(item);
  }

  String _rawSupportingText(Map<String, dynamic> item) {
    final headline = _rawHeadlineText(item);
    final summary = (item['summary'] ?? '').toString().trim();
    if (_rawIsArticle(item) && summary.isNotEmpty && summary != headline) {
      return summary;
    }
    final body =
        (item['body'] ??
                item['description'] ??
                item['content'] ??
                item['caption'] ??
                '')
            .toString()
            .trim();
    if (body.isEmpty || body == headline) {
      return '';
    }
    return body;
  }

  List<String> _recommendedArticleTemplatesForCircle() {
    final categoryId = (_circleCategoryId ?? '').trim();
    if (categoryId.isEmpty) {
      return const <String>[];
    }
    for (final recommendation
        in ContentUIConfig.articleTemplateRecommendations) {
      if (recommendation.categoryId == categoryId) {
        return recommendation.recommendedArticleTemplates;
      }
    }
    return const <String>[];
  }

  String _rawArticleRecommendationLabel(Map<String, dynamic> item) {
    final recommended = _recommendedArticleTemplatesForCircle();
    if (recommended.isEmpty) {
      return '';
    }
    final templateId = (item['articleTemplate'] ?? '').toString().trim();
    if (templateId.isNotEmpty && recommended.contains(templateId)) {
      return '讨论推荐 · ${articleTemplatePresetFromString(templateId).label}';
    }
    final labels = recommended
        .take(2)
        .map((value) => articleTemplatePresetFromString(value).label)
        .join(' / ');
    if (labels.isEmpty) {
      return '';
    }
    return '讨论推荐 · $labels';
  }

  int _rawLikeCount(Map<String, dynamic> item) {
    return (item['likeCount'] as num?)?.toInt() ??
        (item['likes'] as num?)?.toInt() ??
        0;
  }

  bool _rawIsVideo(Map<String, dynamic> item) {
    return (item['type'] ?? '').toString() == 'video' ||
        (item['videoUrl']?.toString().trim() ?? '').isNotEmpty;
  }

  Widget _buildErrorCard() {
    return AppSectionErrorCard(
      semantic: _errorSemantic!,
      margin: EdgeInsets.zero,
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await _loadFeed();
        }
      },
    );
  }

  Widget _buildSurface({
    required Widget child,
    required Color backgroundColor,
    required Color borderColor,
    EdgeInsetsGeometry padding = const EdgeInsets.symmetric(
      vertical: AppSpacing.containerSm,
    ),
  }) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(color: borderColor.withValues(alpha: 0.12)),
        boxShadow: [
          BoxShadow(
            color: AppColors.black.withValues(
              alpha: widget.isDark ? 0.16 : 0.05,
            ),
            blurRadius: AppSpacing.md,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: child,
    );
  }
}
