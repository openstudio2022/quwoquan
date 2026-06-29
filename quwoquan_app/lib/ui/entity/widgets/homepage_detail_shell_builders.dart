part of 'homepage_detail_shell.dart';

extension _HomepageBuilders on _HomepageDetailShellState {
  /// 「我的交集」预览卡：与圈子/用户主页同构，消费 [ObjectIntersectionPreviewCard]。
  Widget _buildIntersectionCard(bool isDark) {
    final objectId = (_reference?.id ?? '').trim();
    if (objectId.isEmpty) {
      return const SizedBox.shrink();
    }
    return ObjectIntersectionPreviewCard(
      objectId: objectId,
      objectType: 'homepage',
      title: UITextConstants.objectMyIntersectionsTitle,
      emptyText: UITextConstants.objectIntersectionEmptyEntity,
      referralSource: ReferralSource.entityPage,
      cardKey: const ValueKey<String>('homepage-my-intersection-card'),
      emptyKey: const ValueKey<String>('homepage-my-intersection-empty'),
    );
  }

  Widget _buildEntityImpactCard(bool isDark) {
    final objectId = (_reference?.id ?? '').trim();
    if (objectId.isEmpty) {
      return const SizedBox.shrink();
    }
    return ObjectImpactPreviewCard(
      objectId: objectId,
      target: ObjectImpactTarget.homepage,
      referralSource: ReferralSource.entityPage,
      enumerableHint: UITextConstants.impactEnumerableHintEntity,
      cardKey: const ValueKey<String>('homepage-impact-card'),
    );
  }

  Widget _buildIdentityMedia(BuildContext context, String? coverUrl) {
    final source = (coverUrl ?? '').trim();
    if (source.isEmpty) {
      return const SizedBox.shrink();
    }
    return AppMediaImage(
      imageSource: source,
      fit: BoxFit.cover,
      placeholder: const SizedBox.shrink(),
      errorWidget: const SizedBox.shrink(),
    );
  }

  Widget _buildToolbar(BuildContext context, double progress) {
    final safeTop = AppSpacing.appChromeTopSafeInset(
      MediaQuery.viewPaddingOf(context).top,
      context,
    );
    final toolbarFill = AppColors.iosSystemBackground(
      context,
    ).withValues(alpha: progress * 0.92);
    final toolbarBorder = AppColors.iosSeparator(
      context,
    ).withValues(alpha: progress * 0.14);
    final buttonForeground =
        Color.lerp(
          CupertinoColors.white,
          AppColors.iosLabel(context),
          progress,
        ) ??
        AppColors.iosLabel(context);
    final buttonBackground =
        Color.lerp(
          AppColors.black.withValues(alpha: 0.18),
          AppColors.iosFill(context).withValues(alpha: 0.94),
          progress,
        ) ??
        AppColors.iosFill(context);

    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Container(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          safeTop + AppSpacing.appChromeToolbarVerticalPadding(context),
          AppSpacing.containerMd,
          AppSpacing.appChromeToolbarVerticalPadding(context),
        ),
        decoration: BoxDecoration(
          color: toolbarFill,
          border: Border(
            bottom: BorderSide(
              color: toolbarBorder,
              width: AppSpacing.hairline,
            ),
          ),
        ),
        child: Row(
          children: <Widget>[
            ProfileIosIconButton(
              icon: widget.selectionMode
                  ? CupertinoIcons.xmark
                  : CupertinoIcons.chevron_back,
              onPressed: widget.onBack,
              backgroundColor: buttonBackground,
              foregroundColor: buttonForeground,
            ),
            Expanded(
              child: IgnorePointer(
                child: Opacity(
                  opacity: progress,
                  child: Text(
                    _reference?.title ?? '',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: AppTypography.iosNavTitle,
                      fontWeight: AppTypography.semiBold,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                ),
              ),
            ),
            if (_hasMoreActions)
              ProfileIosIconButton(
                key: const ValueKey<String>('homepage-detail-more-button'),
                icon: CupertinoIcons.slider_horizontal_3,
                onPressed: () => _showMoreActions(context),
                backgroundColor: buttonBackground,
                foregroundColor: buttonForeground,
              )
            else
              const SizedBox(width: AppSpacing.minInteractiveSize),
          ],
        ),
      ),
    );
  }

  Widget _buildBackgroundLayer(BuildContext context) {
    final coverUrl = (_reference?.coverUrl ?? '').trim();
    final pageBackground = AppColors.iosPageBackground(context);
    final fallback = DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[
            AppColors.primaryColor.withValues(alpha: 0.22),
            AppColors.primaryColor.withValues(alpha: 0.08),
            pageBackground,
          ],
        ),
      ),
      child: Center(
        child: Icon(
          CupertinoIcons.photo_fill_on_rectangle_fill,
          size: AppSpacing.iconLarge,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
    );

    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        if (coverUrl.isEmpty)
          fallback
        else
          AppMediaImage(
            imageSource: coverUrl,
            fit: BoxFit.cover,
            placeholder: fallback,
            errorWidget: fallback,
          ),
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: <Color>[
                AppColors.black.withValues(alpha: 0.12),
                AppColors.black.withValues(alpha: 0.06),
                pageBackground.withValues(alpha: 0.96),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSummaryCard(BuildContext context) {
    final detail = widget.detail;
    final reference = _reference;
    final summarySurface = AppColors.iosProfileSurface(context);
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final summaryBorder = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.08);
    final summaryShadow = isDark
        ? AppColors.black.withValues(alpha: 0.18)
        : AppColors.black.withValues(alpha: 0.05);
    final locationLine = <String>[
      if ((detail?.city ?? widget.initialSummary?.city ?? '').trim().isNotEmpty)
        (detail?.city ?? widget.initialSummary?.city ?? '').trim(),
      if ((detail?.address ?? widget.initialSummary?.address ?? '')
          .trim()
          .isNotEmpty)
        (detail?.address ?? widget.initialSummary?.address ?? '').trim(),
    ].join(' · ');
    final typeLabel = _typeLabel(reference?.homepageType ?? '');
    final identitySubtitle = <String>[
      if (typeLabel.trim().isNotEmpty) typeLabel.trim(),
      if (locationLine.trim().isNotEmpty) locationLine.trim(),
    ].join(' · ');
    final followerCount = detail?.followerCount ?? 0;
    final recordCount = _contentPreview.length;
    final discussionCount = _questionPreview.length;
    final statsLine = <String>[
      if (followerCount > 0)
        UITextConstants.entityFollowerCountLabel(
          formatCompactActionCount(followerCount),
        ),
      if (recordCount > 0)
        '${formatCompactActionCount(recordCount)} ${UITextConstants.objectTabRecord}',
      if (discussionCount > 0)
        '${formatCompactActionCount(discussionCount)} ${UITextConstants.objectTabDiscussion}',
    ].join(' · ');
    final referenceSubtitle = (reference?.subtitle ?? '').trim();
    final identityMetaLine = statsLine.isNotEmpty
        ? statsLine
        : referenceSubtitle;
    final identityBadges = <String>[
      if (detail?.verified == true) UITextConstants.entityVerifiedBadge,
    ];

    return Container(
      decoration: BoxDecoration(
        color: summarySurface,
        borderRadius: BorderRadius.circular(
          _HomepageDetailShellState._cardRadius,
        ),
        border: Border.all(color: summaryBorder, width: AppSpacing.hairline),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: summaryShadow,
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.feedContentHorizontal(context),
          AppSpacing.containerLg,
          AppSpacing.feedContentHorizontal(context),
          AppSpacing.containerLg,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            ObjectIdentityHeader(
              kind: ObjectIdentityKind.entity,
              title:
                  reference?.title ??
                  UITextConstants.objectHomepageDefaultTitle,
              subtitle: identitySubtitle,
              metaLine: identityMetaLine,
              badges: identityBadges,
              media: _buildIdentityMedia(context, reference?.coverUrl),
              trailing: _hasMoreActions
                  ? ProfileIosIconButton(
                      key: const ValueKey<String>(
                        'homepage-summary-settings-button',
                      ),
                      icon: CupertinoIcons.slider_horizontal_3,
                      onPressed: () => _showMoreActions(context),
                      style: ProfileIosIconButtonStyle.tinted,
                    )
                  : null,
            ),
            SizedBox(height: AppSpacing.containerSm),
            if (!widget.selectionMode) ...<Widget>[
              SizedBox(height: AppSpacing.containerSm),
              if (_entityIntroLine().trim().isNotEmpty) ...<Widget>[
                ProfileSloganCard(
                  isDark: isDark,
                  bio: _entityIntroLine(),
                  onTap: widget.onOpenIntroduction,
                ),
                SizedBox(height: AppSpacing.containerSm),
              ],
              _HomepageActionBar(
                isFollowing: widget.detail?.viewerFollowsHomepage ?? false,
                onToggleFollow: widget.onToggleFollow,
                onPublishRecord: _reference == null
                    ? null
                    : () => widget.onCreateContent(_reference!),
              ),
            ],
            SizedBox(height: AppSpacing.containerSm),
            _buildIntersectionCard(isDark),
            _buildEntityImpactCard(isDark),
          ],
        ),
      ),
    );
  }

  String _entityIntroLine() {
    final introductionSummary = (widget.introductionSummary ?? '').trim();
    if (introductionSummary.isNotEmpty) {
      return introductionSummary;
    }
    return (_reference?.subtitle ?? '').trim();
  }

  Widget _buildPrimaryTabBar(BuildContext context) {
    final tabs = _HomepageDetailShellState._tabs
        .map((tab) => TabItem(id: tab.id, label: tab.label))
        .toList(growable: false);
    return Container(
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: AppColors.iosSeparator(context).withValues(alpha: 0.1),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: SizedBox(
        height: AppSpacing.tabNavigationHeight,
        child: CenteredScrollableTabBar(
          tabs: tabs,
          activeTab: _activeTabId,
          onTabChange: _changeActiveTab,
          transparentBackground: true,
          iosProfileStyle: true,
        ),
      ),
    );
  }

  Widget _buildSectionBlock({
    required BuildContext context,
    required String title,
    required Widget child,
  }) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.interGroupMd),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          ProfileIosSectionHeader(
            title: title,
            padding: EdgeInsets.only(
              left: AppSpacing.containerXs,
              right: AppSpacing.containerXs,
              bottom: AppSpacing.intraGroupSm,
            ),
          ),
          child,
        ],
      ),
    );
  }

  Widget _buildMessageCard(
    BuildContext context, {
    String? title,
    required Widget child,
  }) {
    return _buildSectionBlock(
      context: context,
      title: title ?? '说明',
      child: ProfileIosSectionCard(child: child),
    );
  }

  Widget _buildOverviewTab(BuildContext context) {
    final detail = widget.detail;
    if (detail == null) {
      if (widget.isLoading) {
        return _buildMessageCard(
          context,
          title: '加载中',
          child: const Center(child: CupertinoActivityIndicator()),
        );
      }
      return _buildMessageCard(
        context,
        title: '暂时不可用',
        child: Text(
          widget.errorText ?? '主页详情暂时不可用，请稍后重试',
          style: TextStyle(
            fontSize: AppTypography.iosBody,
            color: AppColors.iosSecondaryLabel(context),
            height: AppSpacing.textLineHeightBody,
          ),
        ),
      );
    }

    final sections = <Widget>[];
    if (_reviewSummary != null ||
        detail.averageRating != null ||
        widget.initialSummary?.averageRating != null) {
      sections.add(
        _buildSectionBlock(
          context: context,
          title: HomepageDetailText.reviewSummaryTitle,
          child: _HomepageReviewCard(
            summary: _reviewSummary,
            fallbackAverageRating:
                detail.averageRating ?? widget.initialSummary?.averageRating,
            fallbackRatingCount: detail.ratingCount,
          ),
        ),
      );
    }

    sections.add(
      _buildSectionBlock(
        context: context,
        title: HomepageDetailText.basicInfoSectionTitle,
        child: ProfileIosGroupedSection(
          margin: EdgeInsets.zero,
          children: <Widget>[
            if ((detail.city ?? '').trim().isNotEmpty ||
                (detail.address ?? '').trim().isNotEmpty)
              ProfileIosGroupedCell(
                title: HomepageDetailText.locationInfoTitle,
                subtitle: <String>[
                  if ((detail.city ?? '').trim().isNotEmpty)
                    detail.city!.trim(),
                  if ((detail.address ?? '').trim().isNotEmpty)
                    detail.address!.trim(),
                ].join(' · '),
                showChevron: false,
              ),
            if (detail.categoryTags.isNotEmpty)
              ProfileIosGroupedCell(
                title: HomepageDetailText.categoryInfoTitle,
                subtitle: detail.categoryTags.join(' · '),
                showChevron: false,
              ),
            if (detail.establishedYear != null && detail.establishedYear! > 0)
              ProfileIosGroupedCell(
                title: HomepageDetailText.establishedInfoTitle,
                subtitle: UITextConstants.entityEstablishedYearLabel(
                  detail.establishedYear!,
                ),
                showChevron: false,
              ),
          ],
        ),
      ),
    );

    if (detail.status == 'offline' || detail.offlineAt != null) {
      sections.add(
        _buildSectionBlock(
          context: context,
          title: HomepageDetailText.offlineNoticeTitle,
          child: ProfileIosSectionCard(
            child: Text(
              HomepageDetailText.offlineNoticeMessage,
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                color: AppColors.iosSecondaryLabel(context),
                height: AppSpacing.textLineHeightBody,
              ),
            ),
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: sections,
    );
  }
}
