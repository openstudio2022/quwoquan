part of 'homepage_detail_shell.dart';

extension _HomepageBuilders on _HomepageDetailShellState {
  /// 「我的交集」区块：与圈子/用户主页直接消费同一 [ObjectIntersectionSection]。
  Widget _buildIntersectionCard(bool isDark) {
    final objectId = (_reference?.id ?? '').trim();
    if (objectId.isEmpty) {
      return const SizedBox.shrink();
    }
    return Consumer(
      builder: (context, ref, _) {
        final query = ObjectIntersectionQuery(
          objectAId: ref.watch(currentUserIdProvider),
          objectAType: 'user',
          objectBId: objectId,
          objectBType: 'homepage',
        );
        if (!query.isResolvable) {
          return const SizedBox.shrink();
        }
        return ObjectIntersectionSection(
          key: const ValueKey<String>('homepage-my-intersection-card'),
          query: query,
          title: ObjectHomepageText.objectMyIntersectionsTitle,
          isDark: isDark,
          emptyText: ObjectHomepageText.objectIntersectionEmptyEntity,
          emptyKey: const ValueKey<String>('homepage-my-intersection-empty'),
        );
      },
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
      title: ObjectHomepageText.objectImpactTitleEntity,
      enumerableHint: ObjectHomepageText.impactEnumerableHintEntity,
      cardKey: const ValueKey<String>('homepage-impact-card'),
      topDivider: false,
    );
  }

  /// 身份头像内容（封面缩略 / Logo）；为空返回 null，由 [ObjectIdentityAvatar]
  /// 回退到类型占位图标，避免空白方块。
  String _resolvedHeroImageUrl() {
    final candidates = <String?>[
      _reference?.coverUrl,
      widget.objectPageBundle?.coverUrl,
      widget.detail?.coverUrl,
      widget.initialSummary?.coverUrl,
      for (final item in _contentPreview) item.coverUrl,
    ];
    for (final candidate in candidates) {
      final value = (candidate ?? '').trim();
      if (value.isNotEmpty) {
        return value;
      }
    }
    return '';
  }

  Widget? _buildIdentityMedia(BuildContext context, String? coverUrl) {
    final source = (coverUrl ?? '').trim();
    if (source.isEmpty) {
      return null;
    }
    return AppMediaImage(
      key: const ValueKey<String>('homepage-identity-media'),
      imageSource: source,
      fit: BoxFit.cover,
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
                  // 分享走真实统一分享面板；未发布/下线主页提示不可分享。
                  onShare: _canShare
                      ? widget.onShare
                      : () => AppToast.show(
                          context,
                          ObjectHomepageText.homepageShareUnavailable,
                        ),
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
    final coverUrl = _resolvedHeroImageUrl();
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
    final coverUrl = _resolvedHeroImageUrl();
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
    );

    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        if (coverUrl.isEmpty)
          fallback
        else
          AppMediaImage(
            key: const ValueKey<String>('homepage-background-media'),
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
    final typeLabel = homepageTypeLabel(reference?.homepageType ?? '');
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
          label: FoundationText.follow,
        ),
      if (recordCount > 0)
        ObjectStatItem(
          value: formatCompactActionCount(recordCount),
          label: ObjectHomepageText.objectTabRecord,
        ),
      if (discussionCount > 0)
        ObjectStatItem(
          value: formatCompactActionCount(discussionCount),
          label: ObjectHomepageText.objectTabDiscussion,
        ),
    ];

    final identityCard = Container(
      key: const ValueKey<String>('homepage-summary-identity-card'),
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
          0,
          AppSpacing.feedContentHorizontal(context),
          AppSpacing.containerLg,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            ObjectIdentityHeader(
              title:
                  reference?.title ??
                  ObjectHomepageText.objectHomepageDefaultTitle,
              media: ObjectIdentityAvatar(
                kind: ObjectIdentityKind.entity,
                child: _buildIdentityMedia(context, _resolvedHeroImageUrl()),
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
              // WP3 统一打标：实体主页展示数据工程标签（类型 + 地理，叶子名），
              // 与摘要卡 [ObjectMetaChip] 同款胶囊 token。
              if (_displayTagLabels.isNotEmpty) ...<Widget>[
                SizedBox(height: AppSpacing.containerSm),
                Wrap(
                  key: const ValueKey<String>('homepage-tag-refs-wrap'),
                  spacing: AppSpacing.intraGroupXs,
                  runSpacing: AppSpacing.intraGroupXs,
                  children: _displayTagLabels
                      .map((label) => ObjectMetaChip(label: label))
                      .toList(growable: false),
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

  /// 实体首屏 CTA：可到访地点主动作=想去，其余主页主动作=关注；次动作=发记录。
  /// 真相源下沉到共享 [ObjectActionBar]，主/次按钮 token 与用户主页 `ProfileActionBar` 同源。
  Widget _buildEntityActionBar(bool isDark) {
    final separator = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.14);
    final neutralFill = AppColors.iosProfileSurface(context);
    final neutralForeground = AppColors.iosLabel(context);
    final usesWishlistIntent = widget.wishlistState != null;
    final primaryIntentSelected = usesWishlistIntent
        ? widget.wishlistState!
        : (widget.detail?.viewerFollowsHomepage ?? false);
    final primaryIntentLabel = usesWishlistIntent
        ? (primaryIntentSelected
              ? ObjectHomepageText.homepageWishlistedAction
              : ObjectHomepageText.homepageWishlistAction)
        : (primaryIntentSelected
              ? FoundationText.following
              : FoundationText.follow);
    final reference = _reference;
    return ObjectActionBar(
      actions: <ObjectAction>[
        primaryIntentSelected
            ? ObjectAction(
                label: primaryIntentLabel,
                icon: CupertinoIcons.check_mark,
                onPressed: widget.onToggleFollow,
                style: ProfileIosActionStyle.outlined,
                backgroundColor: neutralFill,
                foregroundColor: neutralForeground,
                borderColor: separator,
              )
            : ObjectAction(
                label: primaryIntentLabel,
                icon: usesWishlistIntent
                    ? CupertinoIcons.location
                    : CupertinoIcons.add,
                onPressed: widget.onToggleFollow,
                style: ProfileIosActionStyle.filled,
              ),
        ObjectAction(
          label: ObjectHomepageText.entityActionPublishRecord,
          icon: CupertinoIcons.pencil,
          onPressed: reference == null
              ? null
              : () => widget.onCreateContent(reference),
          style: ProfileIosActionStyle.outlined,
          backgroundColor: neutralFill,
          foregroundColor: neutralForeground,
          borderColor: separator,
        ),
        if (_canMessageOwner)
          ObjectAction(
            label: ProfileText.profileDirectMessage,
            icon: CupertinoIcons.chat_bubble,
            onPressed: widget.onMessageOwner,
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
      title: title ?? ContentText.homepageInfoUnavailableTitle,
      child: ProfileIosSectionCard(child: child),
    );
  }

  Widget _buildOverviewTab(BuildContext context) {
    final detail = widget.detail;
    if (detail == null) {
      if (widget.isLoading) {
        return _buildMessageCard(
          context,
          title: FoundationText.loading,
          child: AppRequestFeedback.section(),
        );
      }
      return _buildMessageCard(
        context,
        title: ContentText.homepageInfoUnavailableTitle,
        child: Text(
          widget.errorText ?? FoundationText.contentLoadSoftFailed,
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
            if (_displayTagLabels.isNotEmpty)
              ProfileIosGroupedCell(
                title: HomepageDetailText.categoryInfoTitle,
                subtitle: _displayTagLabels.join(' · '),
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
