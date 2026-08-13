// ignore_for_file: invalid_use_of_protected_member

part of 'section_creations.dart';

extension _SectionCreationsStateHelpers on _SectionCreationsState {
  Future<void> _loadFeed() async {
    setState(() {
      _isLoading = true;
      _errorSemantic = null;
      _nextCursor = null;
      _isLoadingMore = false;
      _loadMoreErrorSemantic = null;
    });
    try {
      final circleState = ref.read(circleStateProvider(widget.circleId));
      final query = _feedQueryForState(circleState);
      final page = await widget.participantSlots.loadFeed(
        ref,
        CircleFeedQuery(
          circleId: widget.circleId,
          identity: query.identity,
          type: query.type,
          sort: circleState.sortMode.name,
        ),
      );
      final nextCursor = page.cursor?.trim();
      final entries = page.items
          .map(
            (projection) =>
                CircleHubFeedPostEntry.fromProjection(projection: projection),
          )
          .toList(growable: false);
      var circleCategoryId = circleState.circleData?.category;
      if (circleCategoryId == null || circleCategoryId.trim().isEmpty) {
        try {
          final circleDetail = await widget.participantSlots.loadCircle(
            ref,
            CircleDetailQuery(circleId: widget.circleId),
          );
          circleCategoryId = circleDetail.category;
        } on Object {
          // 推荐标签是增强信息；详情暂不可用时仍应展示强类型作品流。
          circleCategoryId = null;
        }
      }
      if (mounted) {
        setState(() {
          _feedEntries = entries;
          _circleCategoryId = circleCategoryId;
          _nextCursor = (nextCursor == null || nextCursor.isEmpty)
              ? null
              : nextCursor;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _errorSemantic = runtimeErrorSemantic(
            context,
            error: e,
            category: UiErrorCategory.sectionLoad,
            scope: UiErrorScope.section,
          );
        });
      }
    }
  }

  /// 追加加载下一页：cursor 只由服务端裁定，端侧按 postId 去重后只追加，
  /// 失败保留已加载内容并给出 canonical 可重试反馈（不产生伪成功）。
  Future<void> _loadMoreFeed() async {
    final cursor = _nextCursor;
    if (cursor == null || _isLoadingMore || _isLoading) {
      return;
    }
    setState(() {
      _isLoadingMore = true;
      _loadMoreErrorSemantic = null;
    });
    try {
      final circleState = ref.read(circleStateProvider(widget.circleId));
      final query = _feedQueryForState(circleState);
      final page = await widget.participantSlots.loadFeed(
        ref,
        CircleFeedQuery(
          circleId: widget.circleId,
          identity: query.identity,
          type: query.type,
          sort: circleState.sortMode.name,
          cursor: cursor,
        ),
      );
      final nextCursor = page.cursor?.trim();
      final knownPostIds = _feedEntries.map((entry) => entry.postId).toSet();
      final appended = page.items
          .map(
            (projection) =>
                CircleHubFeedPostEntry.fromProjection(projection: projection),
          )
          .where((entry) => !knownPostIds.contains(entry.postId))
          .toList(growable: false);
      if (mounted) {
        setState(() {
          _feedEntries = List<CircleHubFeedPostEntry>.unmodifiable(
            <CircleHubFeedPostEntry>[..._feedEntries, ...appended],
          );
          _nextCursor = (nextCursor == null || nextCursor.isEmpty)
              ? null
              : nextCursor;
          _isLoadingMore = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoadingMore = false;
          _loadMoreErrorSemantic = runtimeErrorSemantic(
            context,
            error: e,
            category: UiErrorCategory.sectionLoad,
            scope: UiErrorScope.section,
          );
        });
      }
    }
  }

  bool _handleFeedScroll(ScrollNotification notification) {
    if (_nextCursor == null ||
        _isLoadingMore ||
        _loadMoreErrorSemantic != null) {
      return false;
    }
    final metrics = notification.metrics;
    if (metrics.axis == Axis.vertical &&
        metrics.extentAfter < AppSpacing.threeHundredTwenty) {
      _loadMoreFeed();
    }
    return false;
  }

  /// 分页 footer：加载中/失败重试/手动加载更多（inline 模式无法监听外层
  /// 滚动，入口常驻；非 inline 模式作为触底自动加载的兜底）。
  Widget? _buildLoadMoreFooter(Color fgSecondary) {
    if (_nextCursor == null && _loadMoreErrorSemantic == null) {
      return null;
    }
    final Widget child;
    if (_isLoadingMore) {
      child = const CupertinoActivityIndicator();
    } else if (_loadMoreErrorSemantic != null) {
      child = Text(
        CommunityText.circleCreationsLoadMoreFailed,
        style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary),
      );
    } else {
      child = Text(
        CommunityText.circleCreationsLoadMore,
        style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary),
      );
    }
    return CupertinoButton(
      key: const ValueKey<String>('circle-creations-load-more'),
      padding: EdgeInsets.symmetric(vertical: AppSpacing.containerSm),
      onPressed: _isLoadingMore ? null : _loadMoreFeed,
      child: Center(child: child),
    );
  }

  Widget _buildContent(CircleState circleState, Color fgSecondary) {
    if (_isLoading) {
      return AppRequestFeedback.section();
    }
    if (_errorSemantic != null) {
      return _buildErrorCard();
    }

    final activeSubTab = circleState.activeSubTab;
    final filtered = _feedEntries
        .where((entry) => _matchesIdentityFilter(entry, activeSubTab))
        .toList(growable: true);

    if (activeSubTab == CircleCreationSubTab.article) {
      filtered.sort((left, right) {
        final leftHasTemplate = _entryArticleTemplate(left).trim().isNotEmpty;
        final rightHasTemplate = _entryArticleTemplate(right).trim().isNotEmpty;
        if (leftHasTemplate != rightHasTemplate) {
          return leftHasTemplate ? -1 : 1;
        }
        final leftHasCover = _entryCoverUrl(left).isNotEmpty;
        final rightHasCover = _entryCoverUrl(right).isNotEmpty;
        if (leftHasCover != rightHasCover) {
          return leftHasCover ? -1 : 1;
        }
        return 0;
      });
    }

    if (filtered.isEmpty) {
      return _buildEmpty(fgSecondary);
    }

    if (circleState.viewMode == CreationViewMode.list) {
      return _wrapWithPagination(
        fgSecondary: fgSecondary,
        child: ListView.separated(
          physics: widget.inlineScroll
              ? const NeverScrollableScrollPhysics()
              : const BouncingScrollPhysics(),
          shrinkWrap: widget.inlineScroll,
          padding: EdgeInsets.fromLTRB(
            AppSpacing.postPreviewGridSpacing,
            AppSpacing.postPreviewGridSpacing,
            AppSpacing.postPreviewGridSpacing,
            AppSpacing.postPreviewSectionPadding,
          ),
          itemCount: filtered.length,
          separatorBuilder: (_, _) =>
              SizedBox(height: AppSpacing.postPreviewGridSpacing),
          itemBuilder: (context, index) {
            final entry = filtered[index];
            return _buildListItem(
              entry,
              fgSecondary,
              onTap: () => _openMediaViewer(context, entry, filtered),
            );
          },
        ),
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = AppSpacing.responsiveGridColumns(
          context,
          availableWidth: constraints.maxWidth,
        );
        // 双列瀑布：与用户主页记录流同一范式，卡片高度随内容自适应。
        if (widget.inlineScroll) {
          return _wrapWithPagination(
            fgSecondary: fgSecondary,
            child: GridView.builder(
              physics: const NeverScrollableScrollPhysics(),
              shrinkWrap: true,
              primary: false,
              padding: EdgeInsets.fromLTRB(
                AppSpacing.postPreviewGridSpacing,
                AppSpacing.postPreviewGridSpacing,
                AppSpacing.postPreviewGridSpacing,
                AppSpacing.postPreviewSectionPadding,
              ),
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: columns,
                mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
                crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
                mainAxisExtent: _inlineGridMainAxisExtent(columns),
              ),
              itemCount: filtered.length,
              itemBuilder: (context, index) {
                final entry = filtered[index];
                return _buildGridItem(
                  entry,
                  fgSecondary,
                  onTap: () => _openMediaViewer(context, entry, filtered),
                );
              },
            ),
          );
        }
        return _wrapWithPagination(
          fgSecondary: fgSecondary,
          child: MasonryGridView.count(
            physics: const BouncingScrollPhysics(),
            shrinkWrap: false,
            primary: false,
            padding: EdgeInsets.fromLTRB(
              AppSpacing.postPreviewGridSpacing,
              AppSpacing.postPreviewGridSpacing,
              AppSpacing.postPreviewGridSpacing,
              AppSpacing.postPreviewSectionPadding,
            ),
            crossAxisCount: columns,
            mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
            crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
            itemCount: filtered.length,
            itemBuilder: (context, index) {
              final entry = filtered[index];
              return _buildGridItem(
                entry,
                fgSecondary,
                onTap: () => _openMediaViewer(context, entry, filtered),
              );
            },
          ),
        );
      },
    );
  }

  /// 统一分页包装：有 cursor 即常驻手动入口（首屏不满一屏时触底通知不会
  /// 发生，入口必须可达）；非 inline 模式叠加触底自动加载增强。
  Widget _wrapWithPagination({
    required Widget child,
    required Color fgSecondary,
  }) {
    final footer = _buildLoadMoreFooter(fgSecondary);
    if (widget.inlineScroll) {
      if (footer == null) {
        return child;
      }
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[child, footer],
      );
    }
    return NotificationListener<ScrollNotification>(
      onNotification: _handleFeedScroll,
      child: footer == null
          ? child
          : Column(
              children: <Widget>[
                Expanded(child: child),
                footer,
              ],
            ),
    );
  }

  double _inlineGridMainAxisExtent(int columns) {
    if (columns <= 1) {
      return AppSpacing.threeHundredTwenty + AppSpacing.twoHundredTwenty;
    }
    return AppSpacing.threeHundredTwenty + AppSpacing.buttonHeight * 2;
  }

  Widget _articleTemplateBadge(String articleTemplate) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: AppColors.black.withValues(alpha: 0.32),
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      ),
      child: Text(
        articleTemplatePresetFromString(articleTemplate).label,
        style: TextStyle(
          color: AppColors.white,
          fontSize: AppTypography.xs,
          fontWeight: AppTypography.semiBold,
        ),
      ),
    );
  }

  Widget _buildEmpty(Color fgSecondary) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final ultraCompact = constraints.maxHeight < AppSpacing.buttonHeight;
        final compact = !ultraCompact && constraints.maxHeight < 220;
        final horizontalPadding = compact
            ? AppSpacing.containerSm
            : AppSpacing.containerMd;
        final verticalPadding = ultraCompact
            ? 0.0
            : compact
            ? AppSpacing.containerSm
            : AppSpacing.containerMd;
        final iconContainerSize = compact
            ? AppSpacing.buttonHeightLg
            : AppSpacing.xl * 2;
        final iconSize = compact ? AppSpacing.iconMedium : AppSpacing.xl;
        final textStyle = TextStyle(
          fontSize: compact ? AppTypography.base : AppTypography.md,
          color: fgSecondary,
        );
        final text = Text(
          CommunityText.circleNoCreations,
          style: textStyle,
          maxLines: ultraCompact ? 1 : 2,
          overflow: TextOverflow.ellipsis,
          textAlign: TextAlign.center,
        );

        if (ultraCompact) {
          return Center(
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: horizontalPadding),
              child: text,
            ),
          );
        }

        final iconBubble = Container(
          width: iconContainerSize,
          height: iconContainerSize,
          decoration: BoxDecoration(
            color: fgSecondary.withValues(alpha: 0.08),
            shape: BoxShape.circle,
          ),
          child: Icon(
            CupertinoIcons.photo_on_rectangle,
            size: iconSize,
            color: fgSecondary,
          ),
        );

        if (compact) {
          final compactContentWidth =
              (constraints.maxWidth - (horizontalPadding * 2))
                  .clamp(0.0, double.infinity)
                  .toDouble();
          return Center(
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: horizontalPadding,
                vertical: verticalPadding,
              ),
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: compactContentWidth),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    iconBubble,
                    SizedBox(width: AppSpacing.sm),
                    Flexible(child: text),
                  ],
                ),
              ),
            ),
          );
        }

        return Center(
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: horizontalPadding,
              vertical: verticalPadding,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                iconBubble,
                SizedBox(height: AppSpacing.md),
                text,
              ],
            ),
          ),
        );
      },
    );
  }
}
