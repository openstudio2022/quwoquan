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
    return entry.isArticle;
  }

  bool _entryIsVideo(CircleHubFeedPostEntry entry) {
    return entry.isVideo;
  }

  String _entryIdentity(CircleHubFeedPostEntry entry) {
    return entry.contentIdentity;
  }

  String _entryDisplayFormat(CircleHubFeedPostEntry entry) {
    return entry.displayFormat;
  }

  String _entryArticleTemplate(CircleHubFeedPostEntry entry) {
    return entry.articleTemplate;
  }

  String _entryCoverUrl(CircleHubFeedPostEntry entry) => entry.coverUrl;

  String _entryHeadlineText(CircleHubFeedPostEntry entry) {
    if (entry.title.isNotEmpty) {
      return entry.title;
    }
    if (entry.bodyText.isNotEmpty) {
      return entry.bodyText;
    }
    return _entryTypeLabel(entry);
  }

  String _entrySupportingText(CircleHubFeedPostEntry entry) {
    final body = entry.bodyText;
    if (body.isEmpty || body == _entryHeadlineText(entry)) {
      return '';
    }
    return body;
  }

  int _entryLikeCount(CircleHubFeedPostEntry entry) {
    return entry.likeCount;
  }

  String _entryAuthorDisplayName(CircleHubFeedPostEntry entry) {
    return entry.authorDisplayName;
  }

  String _entryId(CircleHubFeedPostEntry entry) {
    return entry.postId;
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
    return _articleTemplateBadge(entry.articleTemplate);
  }

  String _entryArticleTemplateLabel(CircleHubFeedPostEntry entry) {
    final id = _entryArticleTemplate(entry);
    return articleTemplatePresetFromString(id.isNotEmpty ? id : null).label;
  }

  String _entryArticleRecommendationLabel(CircleHubFeedPostEntry entry) {
    return _articleRecommendationLabel(entry.articleTemplate);
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
    final tappedDto = tapped.post;
    if (!_supportsViewer(tappedDto)) return;

    final viewerEntries = sourceItems
        .where((entry) => _supportsViewer(entry.post))
        .toList(growable: false);
    if (viewerEntries.isEmpty) return;

    final viewerDtos = viewerEntries
        .map((entry) => entry.post)
        .toList(growable: false);
    final initialIndex = viewerDtos
        .indexWhere((item) => item.id == tappedDto.id)
        .clamp(0, viewerDtos.length - 1);
    final rawPostsById = <String, MediaViewerPostWireRow>{
      for (final entry in viewerEntries)
        entry.postId: entry.toMediaViewerWireRow(),
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
            .map(ContentSurfaceViewMapper.fromDto)
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

  List<String> _presentationLabels(CircleHubFeedPostEntry entry) => [
    if (entry.pinned) UITextConstants.circlePostPinnedBadge,
    if (entry.featured) UITextConstants.circlePostFeaturedBadge,
  ];

  String _presentationEyebrow(
    CircleHubFeedPostEntry entry,
    String fallback,
  ) {
    final labels = _presentationLabels(entry);
    if (labels.isEmpty) {
      return fallback;
    }
    return [...labels, fallback].where((value) => value.isNotEmpty).join(' · ');
  }

  Widget _managedEntrySurface(
    CircleHubFeedPostEntry entry, {
    required Widget child,
    required bool showOverlay,
  }) {
    final labels = _presentationLabels(entry);
    final surface = showOverlay && labels.isNotEmpty
        ? Stack(
            clipBehavior: Clip.none,
            children: [
              child,
              Positioned.directional(
                textDirection: Directionality.of(context),
                top: AppSpacing.sm,
                end: AppSpacing.sm,
                child: IgnorePointer(
                  child: Wrap(
                    spacing: AppSpacing.intraGroupXs,
                    children: labels
                        .map(
                          (label) => Container(
                            key: ValueKey<String>(
                              'circle-post-presentation-${entry.postId}-$label',
                            ),
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.sm,
                              vertical: AppSpacing.intraGroupXs,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.primaryColor.withValues(
                                alpha: 0.92,
                              ),
                              borderRadius: BorderRadius.circular(
                                AppSpacing.circularBorderRadius,
                              ),
                            ),
                            child: Text(
                              label,
                              style: TextStyle(
                                color: AppColors.white,
                                fontSize: AppTypography.xs,
                                fontWeight: AppTypography.bold,
                              ),
                            ),
                          ),
                        )
                        .toList(growable: false),
                  ),
                ),
              ),
            ],
          )
        : child;
    return GestureDetector(
      behavior: HitTestBehavior.deferToChild,
      onLongPress:
          _isAdminOrOwner && entry.placementId.trim().isNotEmpty
          ? () => _showPostManagement(entry)
          : null,
      child: surface,
    );
  }

  Future<void> _showPostManagement(CircleHubFeedPostEntry entry) async {
    final action = await showAppActionSheet<_CirclePostManagementAction>(
      context,
      title: UITextConstants.circlePostManagementTitle,
      sections: [
        AppActionSheetSection<_CirclePostManagementAction>(
          items: [
            AppActionSheetItem<_CirclePostManagementAction>(
              value: _CirclePostManagementAction.pin,
              label: entry.pinned
                  ? UITextConstants.circlePostUnpinAction
                  : UITextConstants.circlePostPinAction,
              icon: entry.pinned
                  ? CupertinoIcons.pin_slash
                  : CupertinoIcons.pin,
            ),
            AppActionSheetItem<_CirclePostManagementAction>(
              value: _CirclePostManagementAction.feature,
              label: entry.featured
                  ? UITextConstants.circlePostUnfeatureAction
                  : UITextConstants.circlePostFeatureAction,
              icon: entry.featured
                  ? CupertinoIcons.star_slash
                  : CupertinoIcons.star,
            ),
          ],
        ),
        const AppActionSheetSection<_CirclePostManagementAction>(
          items: [
            AppActionSheetItem<_CirclePostManagementAction>(
              value: _CirclePostManagementAction.remove,
              label: UITextConstants.circlePostRemoveAction,
              icon: CupertinoIcons.delete,
              isDestructive: true,
            ),
          ],
        ),
      ],
    );
    if (!mounted || action == null) {
      return;
    }
    if (action == _CirclePostManagementAction.remove) {
      final confirmed = await showCupertinoDialog<bool>(
        context: context,
        builder: (dialogContext) => CupertinoAlertDialog(
          title: const Text(UITextConstants.circlePostRemoveConfirmTitle),
          content: const Text(UITextConstants.circlePostRemoveConfirmMessage),
          actions: [
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text(UITextConstants.cancel),
            ),
            CupertinoDialogAction(
              isDestructiveAction: true,
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text(UITextConstants.circlePostRemoveAction),
            ),
          ],
        ),
      );
      if (confirmed != true || !mounted) {
        return;
      }
    }
    try {
      final writer = ref.read(circleDetailPostPlacementCommandWriterProvider);
      final message = switch (action) {
        _CirclePostManagementAction.pin => () async {
          await writer.setPinned(
            PinCirclePostCommand(
              circleId: widget.circleId,
              placementId: entry.placementId,
              enabled: !entry.pinned,
            ),
          );
          return UITextConstants.circlePostPinUpdated;
        }(),
        _CirclePostManagementAction.feature => () async {
          await writer.setFeatured(
            FeatureCirclePostCommand(
              circleId: widget.circleId,
              placementId: entry.placementId,
              enabled: !entry.featured,
            ),
          );
          return UITextConstants.circlePostFeatureUpdated;
        }(),
        _CirclePostManagementAction.remove => () async {
          await writer.removePost(
            RemoveCirclePostCommand(
              circleId: widget.circleId,
              placementId: entry.placementId,
            ),
          );
          return UITextConstants.circlePostRemoved;
        }(),
      };
      final resolvedMessage = await message;
      await _loadFeed();
      if (mounted) {
        AppToast.show(context, resolvedMessage);
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      final semantic = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.section,
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: semantic,
        onAction: (errorAction) async {
          if (errorAction.type == UiErrorActionType.retry ||
              errorAction.type == UiErrorActionType.resubmit) {
            await _showPostManagement(entry);
          }
        },
      );
    }
  }

  Widget _buildGridItem(
    CircleHubFeedPostEntry entry,
    Color fgSecondary, {
    required VoidCallback onTap,
  }) {
    if (_entryIsArticle(entry)) {
      return _managedEntrySurface(
        entry,
        showOverlay: true,
        child: _buildArticleGridItem(entry, fgSecondary, onTap: onTap),
      );
    }
    // 统一记录卡范式：封面 + 唯一交集句 + 标题 + 作者 + 点赞。
    return _managedEntrySurface(
      entry,
      showOverlay: true,
      child: RecordPostCard(
        key: ValueKey<String>('circle-record-grid-${_entryId(entry)}'),
        post: entry.post,
        isDark: widget.isDark,
        onTap: onTap,
        // N5：圈子记录卡 → 交集句对象片段点击精确归因为圈子内容（非推荐流）。
        referralSource: ReferralSource.circlePost,
      ),
    );
  }

  Widget _buildListItem(
    CircleHubFeedPostEntry entry,
    Color fgSecondary, {
    required VoidCallback onTap,
  }) {
    if (_entryIsArticle(entry)) {
      return _managedEntrySurface(
        entry,
        showOverlay: false,
        child: _buildArticleListItem(entry, fgSecondary, onTap: onTap),
      );
    }
    final typeLabel = _entryTypeLabel(entry);
    return _managedEntrySurface(
      entry,
      showOverlay: false,
      child: PostPreviewListTile(
        isDark: widget.isDark,
        eyebrowText: _presentationEyebrow(entry, typeLabel),
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
        entry.post.intersectionReasons,
        isDark: widget.isDark,
        // N5：圈子文章卡 → 交集句对象片段点击精确归因为圈子内容（非推荐流）。
        referralSource: ReferralSource.circlePost,
        contextObjectName: _entryHeadlineText(entry).trim().isNotEmpty
            ? _entryHeadlineText(entry).trim()
            : _entrySupportingText(entry).trim(),
        contextObjectTarget: IntersectionTarget(
          objectType: 'post',
          objectId: entry.postId,
          objectKind: 'content',
          routeId: 'workBrowser',
        ),
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
      eyebrowText: _presentationEyebrow(
        entry,
        recommendationLabel.isNotEmpty
            ? recommendationLabel
            : '笔记 · ${_entryArticleTemplateLabel(entry)}',
      ),
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

  String _articleRecommendationLabel(String articleTemplate) {
    final recommended = _recommendedArticleTemplatesForCircle();
    if (recommended.isEmpty) {
      return '';
    }
    final templateId = articleTemplate.trim();
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
