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
      topPadding: false,
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
      topDivider: false,
    );
  }

  /// 身份头像内容（封面缩略 / Logo）；为空返回 null，由 [ObjectIdentityAvatar]
  /// 回退到类型占位图标，避免空白方块。
  Widget? _buildIdentityMedia(BuildContext context, String? coverUrl) {
    final source = (coverUrl ?? '').trim();
    if (source.isEmpty) {
      return null;
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
    final isPinned = progress > 0.12;
    final toolbarFill = isPinned
        ? AppColors.iosSystemBackground(context)
        : AppColors.transparent;
    final toolbarBorder = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isPinned ? 0.14 : 0);
    final buttonForeground = isPinned
        ? AppColors.iosLabel(context)
        : CupertinoColors.white;
    const buttonBackground = AppColors.transparent;

    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: AnnotatedRegion<SystemUiOverlayStyle>(
        value: SystemUiOverlayStyle(
          statusBarColor: AppColors.transparent,
          statusBarIconBrightness: isPinned
              ? (CupertinoTheme.of(context).brightness == Brightness.dark
                    ? Brightness.light
                    : Brightness.dark)
              : Brightness.light,
          statusBarBrightness: isPinned
              ? (CupertinoTheme.of(context).brightness == Brightness.dark
                    ? Brightness.dark
                    : Brightness.light)
              : Brightness.dark,
        ),
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
              SizedBox(
                width: AppSpacing.appChromeActionButtonSize,
                height: AppSpacing.appChromeActionButtonSize,
                child: Center(
                  child: widget.selectionMode || !isPinned
                      ? ProfileIosIconButton(
                          key: const ValueKey<String>(
                            'homepage-detail-back-button',
                          ),
                          icon: widget.selectionMode
                              ? CupertinoIcons.xmark
                              : CupertinoIcons.chevron_back,
                          onPressed: widget.onBack,
                          backgroundColor: buttonBackground,
                          foregroundColor: buttonForeground,
                        )
                      : _buildCompactToolbarAvatar(context),
                ),
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
              if (widget.selectionMode)
                const SizedBox(width: AppSpacing.minInteractiveSize)
              else
                // 高保顶栏右侧四图标：搜索 / AI / 分享 / 更多（⚙︎=对象操作面板）。
                ObjectChromeActions(
                  foregroundColor: buttonForeground,
                  backgroundColor: buttonBackground,
                  onSearch: () => GlobalSearchLauncher.open(
                    context,
                    initialScope: GlobalSearchScope.all.searchScope,
                  ),
                  onAssistant: (ref) =>
                      GlobalAssistantLauncher.open(context, ref),
                  onShare: () => AppToast.show(context, UITextConstants.share),
                  onMore: _hasMoreActions
                      ? () => _showMoreActions(context)
                      : null,
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCompactToolbarAvatar(BuildContext context) {
    final coverUrl = (_reference?.coverUrl ?? '').trim();
    final fallback = DecoratedBox(
      decoration: BoxDecoration(color: AppColors.iosSecondaryFill(context)),
      child: Center(
        child: Icon(
          CupertinoIcons.photo_fill_on_rectangle_fill,
          size: AppSpacing.iconSmall,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
    );
    return ClipOval(
      key: const ValueKey<String>('homepage-detail-compact-avatar'),
      child: SizedBox(
        width: AppSpacing.avatarUserSm,
        height: AppSpacing.avatarUserSm,
        child: coverUrl.isEmpty
            ? fallback
            : AppMediaImage(
                imageSource: coverUrl,
                fit: BoxFit.cover,
                placeholder: fallback,
                errorWidget: fallback,
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
    // 轻统计行：主统计「关注」，弱展示「记录 / 讨论」（高保口径 #5：实体用关注，
    // 不用粉丝）。下沉到共享 [ObjectStatsRow]，与用户主页同款值/标签 token。
    final statItems = <ObjectStatItem>[
      if (followerCount > 0)
        ObjectStatItem(
          value: formatCompactActionCount(followerCount),
          label: UITextConstants.follow,
        ),
      if (recordCount > 0)
        ObjectStatItem(
          value: formatCompactActionCount(recordCount),
          label: UITextConstants.objectTabRecord,
        ),
      if (discussionCount > 0)
        ObjectStatItem(
          value: formatCompactActionCount(discussionCount),
          label: UITextConstants.objectTabDiscussion,
        ),
    ];

    final identityCard = Container(
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
              title:
                  reference?.title ??
                  UITextConstants.objectHomepageDefaultTitle,
              media: ObjectIdentityAvatar(
                kind: ObjectIdentityKind.entity,
                child: _buildIdentityMedia(context, reference?.coverUrl),
              ),
              titleTrailing: (detail?.verified ?? false)
                  ? Icon(
                      key: const ValueKey<String>(
                        'homepage-summary-verified-badge',
                      ),
                      CupertinoIcons.checkmark_seal_fill,
                      size: AppSpacing.iconSmall,
                      color: AppColors.iosAccent(context),
                    )
                  : null,
              subtitle: identitySubtitle,
            ),
            if (!widget.selectionMode) ...<Widget>[
              if (_entityIntroLine().trim().isNotEmpty) ...<Widget>[
                SizedBox(height: AppSpacing.containerSm),
                ObjectSloganCard(
                  isDark: isDark,
                  bio: _entityIntroLine(),
                  onTap: widget.onOpenIntroduction,
                  cardKey: const ValueKey<String>('homepage-intro-slogan-card'),
                ),
              ],
              if (statItems.isNotEmpty) ...<Widget>[
                SizedBox(height: AppSpacing.containerSm),
                ObjectStatsRow(
                  isDark: isDark,
                  items: statItems,
                  rowKey: const ValueKey<String>('homepage-stats-inline-row'),
                ),
              ],
              SizedBox(height: AppSpacing.containerMd),
              _buildEntityActionBar(isDark),
            ],
          ],
        ),
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        identityCard,
        if (!widget.selectionMode) ...<Widget>[
          SizedBox(height: AppSpacing.containerSm),
          _buildIntersectionCard(isDark),
          SizedBox(height: AppSpacing.containerSm),
          _buildEntityImpactCard(isDark),
        ],
      ],
    );
  }

  String _entityIntroLine() {
    final introductionSummary = (widget.introductionSummary ?? '').trim();
    if (introductionSummary.isNotEmpty) {
      return introductionSummary;
    }
    return (_reference?.subtitle ?? '').trim();
  }

  /// 实体首屏 CTA：主=关注/已关注，次=发记录（高保口径 #3 实体主动作是关注）。
  /// 真相源下沉到共享 [ObjectActionBar]，主/次按钮 token 与用户主页 `ProfileActionBar` 同源。
  Widget _buildEntityActionBar(bool isDark) {
    final separator = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.14);
    final neutralFill = AppColors.iosProfileSurface(context);
    final neutralForeground = AppColors.iosLabel(context);
    final isFollowing = widget.detail?.viewerFollowsHomepage ?? false;
    final reference = _reference;
    return ObjectActionBar(
      actions: <ObjectAction>[
        isFollowing
            ? ObjectAction(
                label: UITextConstants.following,
                icon: CupertinoIcons.check_mark,
                onPressed: widget.onToggleFollow,
                style: ProfileIosActionStyle.outlined,
                backgroundColor: neutralFill,
                foregroundColor: neutralForeground,
                borderColor: separator,
              )
            : ObjectAction(
                label: UITextConstants.follow,
                icon: CupertinoIcons.add,
                onPressed: widget.onToggleFollow,
                style: ProfileIosActionStyle.filled,
              ),
        ObjectAction(
          label: UITextConstants.entityActionPublishRecord,
          icon: CupertinoIcons.pencil,
          onPressed: reference == null
              ? null
              : () => widget.onCreateContent(reference),
          style: ProfileIosActionStyle.outlined,
          backgroundColor: neutralFill,
          foregroundColor: neutralForeground,
          borderColor: separator,
        ),
      ],
    );
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
      title: title ?? UITextConstants.homepageInfoUnavailableTitle,
      child: ProfileIosSectionCard(child: child),
    );
  }

  Widget _buildOverviewTab(BuildContext context) {
    final detail = widget.detail;
    if (detail == null) {
      if (widget.isLoading) {
        return _buildMessageCard(
          context,
          title: UITextConstants.loading,
          child: const Center(child: CupertinoActivityIndicator()),
        );
      }
      return _buildMessageCard(
        context,
        title: UITextConstants.homepageInfoUnavailableTitle,
        child: Text(
          widget.errorText ?? UITextConstants.contentLoadSoftFailed,
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
