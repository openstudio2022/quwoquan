part of 'homepage_detail_shell.dart';

extension _HomepageBuilders on _HomepageDetailShellState {
  /// 「为什么推荐这里」交集卡：与圈子/用户主页同构，切 [ObjectIntersectionSection]
  /// 单一真相源（provider 驱动 loading/data/error 三态 + §7.3 高亮 + 归因上报）。
  /// 不再页面内自造交集渲染；无可解析交集则组件自行收起（G2 不占位）。
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
        return ObjectIntersectionSection(
          query: query,
          title: UITextConstants.entityWhyRecommendTitle,
          isDark: isDark,
          bottomPadding: AppSpacing.containerSm,
          onReasonTap: widget.onIntersectionReasonTap,
        );
      },
    );
  }

  Widget _buildIdentityMedia(BuildContext context, String? coverUrl) {
    final source = (coverUrl ?? '').trim();
    if (source.isEmpty) {
      return const SizedBox.shrink();
    }
    return CircleMediaImage(
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
          CircleMediaImage(
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
    final establishedYear = detail?.establishedYear;
    final followerCount = detail?.followerCount ?? 0;
    final statsLine = <String>[
      if (establishedYear != null && establishedYear > 0)
        UITextConstants.entityEstablishedYearLabel(establishedYear),
      if (followerCount > 0)
        UITextConstants.entityFollowerCountLabel(
          formatCompactActionCount(followerCount),
        ),
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
              _HomepageActionBar(
                isFollowing: widget.detail?.viewerFollowsHomepage ?? false,
                onToggleFollow: widget.onToggleFollow,
                onMessageOwner: widget.onMessageOwner,
              ),
            ],
            SizedBox(height: AppSpacing.containerSm),
            _buildIntersectionCard(isDark),
            _buildEntityIntroCard(context),
          ],
        ),
      ),
    );
  }

  /// 「关于这里」介绍卡：标题 + 2~4 行简介 + 右侧缩略图。
  /// 去「认识XX」泛词，统一结论导向标题；缩略图来自封面，无封面则只排文字。
  Widget _buildEntityIntroCard(BuildContext context) {
    final introductionSummary = (widget.introductionSummary ?? '').trim();
    final fallbackIntro = <String>[
      if ((_reference?.subtitle ?? '').trim().isNotEmpty)
        _reference!.subtitle!.trim(),
      if ((widget.detail?.categoryTags ?? const <String>[]).isNotEmpty)
        widget.detail!.categoryTags.take(3).join(' · '),
      if ((widget.detail?.city ?? '').trim().isNotEmpty)
        widget.detail!.city!.trim(),
    ].join(' · ');
    final intro = introductionSummary.isNotEmpty
        ? introductionSummary
        : fallbackIntro;
    final canOpenIntroduction = introductionSummary.isNotEmpty;
    if (intro.isEmpty) {
      return const SizedBox.shrink();
    }
    final thumbnailUrl = (_reference?.coverUrl ?? '').trim();
    final introText = Text(
      intro,
      maxLines: 4,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(
        fontSize: AppTypography.iosFootnote,
        color: AppColors.iosSecondaryLabel(context),
        height: AppSpacing.textLineHeightBody,
      ),
    );
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.containerSm),
      child: CupertinoButton(
        key: const ValueKey<String>('homepage-introduction-entry-button'),
        padding: EdgeInsets.zero,
        onPressed: canOpenIntroduction ? widget.onOpenIntroduction : null,
        child: ProfileIosSectionCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Expanded(
                    child: Text(
                      UITextConstants.entityAboutTitle,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.semiBold,
                        color: AppColors.iosLabel(context),
                      ),
                    ),
                  ),
                  if (canOpenIntroduction) ...<Widget>[
                    Text(
                      UITextConstants.objectIntroMoreLabel,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: AppColors.iosAccent(context),
                      ),
                    ),
                    SizedBox(width: AppSpacing.two),
                    Icon(
                      CupertinoIcons.chevron_forward,
                      size: AppSpacing.iconXSmall,
                      color: AppColors.iosTertiaryLabel(context),
                    ),
                  ],
                ],
              ),
              SizedBox(height: AppSpacing.intraGroupSm),
              if (thumbnailUrl.isEmpty)
                introText
              else
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Expanded(child: introText),
                    SizedBox(width: AppSpacing.containerSm),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(
                        AppSpacing.radiusTen,
                      ),
                      child: SizedBox(
                        width: AppSpacing.avatarUserXl,
                        height: AppSpacing.avatarUserXl,
                        child: CircleMediaImage(
                          imageSource: thumbnailUrl,
                          fit: BoxFit.cover,
                          placeholder: const SizedBox.shrink(),
                          errorWidget: const SizedBox.shrink(),
                        ),
                      ),
                    ),
                  ],
                ),
            ],
          ),
        ),
      ),
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
          title: '口碑摘要',
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
        title: '基础信息',
        child: ProfileIosGroupedSection(
          margin: EdgeInsets.zero,
          children: <Widget>[
            if ((widget.objectPageBundle?.canonicalEntityId ?? '')
                .trim()
                .isNotEmpty)
              ProfileIosGroupedCell(
                title: '统一对象键',
                subtitle: widget.objectPageBundle!.canonicalEntityId,
                showChevron: false,
              ),
            if ((widget.objectPageBundle?.objectPageTemplate ?? '')
                .trim()
                .isNotEmpty)
              ProfileIosGroupedCell(
                title: '对象页模板',
                subtitle: widget.objectPageBundle!.objectPageTemplate,
                showChevron: false,
              ),
            ProfileIosGroupedCell(
              title: '主页状态',
              subtitle: _statusLabel(detail.status),
              showChevron: false,
            ),
            if ((detail.sourceType ?? '').trim().isNotEmpty)
              ProfileIosGroupedCell(
                title: '来源',
                subtitle: _sourceLabel(detail.sourceType),
                showChevron: false,
              ),
            if ((detail.claimStatus ?? '').trim().isNotEmpty)
              ProfileIosGroupedCell(
                title: '认领状态',
                subtitle: _claimLabel(detail.claimStatus),
                showChevron: false,
              ),
            if ((detail.city ?? '').trim().isNotEmpty ||
                (detail.address ?? '').trim().isNotEmpty)
              ProfileIosGroupedCell(
                title: '位置',
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
                title: '分类标签',
                subtitle: detail.categoryTags.join(' · '),
                showChevron: false,
              ),
            if ((widget.objectPageBundle?.rolloutContext?.cohort ?? '')
                .trim()
                .isNotEmpty)
              ProfileIosGroupedCell(
                title: '灰度 cohort',
                subtitle: widget.objectPageBundle!.rolloutContext!.cohort,
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
          title: '记录状态',
          child: ProfileIosSectionCard(
            child: Text(
              '该主页已下线，记录口碑、关联内容与讨论摘要会继续保留，方便用户回看与迁移判断。',
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

    if (_isOwnerLike || _canClaim || _isClaimPending) {
      final managementChildren = <Widget>[];
      if (_isOwnerLike) {
        managementChildren.add(
          ProfileIosGroupedCell(
            title: '维护主页',
            subtitle: '更新标题、简介、位置与分类标签等基础资料',
            onTap: widget.onMaintain,
          ),
        );
      } else if (_canClaim) {
        managementChildren.add(
          ProfileIosGroupedCell(
            title: '认领主页',
            subtitle: '提交营业执照、联系电话等材料进入审核',
            onTap: widget.onClaim,
          ),
        );
      } else if (_isClaimPending) {
        managementChildren.add(
          const ProfileIosGroupedCell(
            title: '认领审核中',
            subtitle: '审核通过后即可维护主页资料与状态',
            showChevron: false,
          ),
        );
      }
      if (_isOwnerLike || _canReport) {
        managementChildren.add(
          ProfileIosGroupedCell(
            title: '状态上报',
            subtitle: '主页停业、重复或关键信息失效时发起上报',
            onTap: widget.onReport,
            isDestructive: !_isOwnerLike,
          ),
        );
      }
      sections.add(
        _buildSectionBlock(
          context: context,
          title: '主页管理',
          child: ProfileIosGroupedSection(
            margin: EdgeInsets.zero,
            children: managementChildren,
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
