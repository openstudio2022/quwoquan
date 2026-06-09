part of 'homepage_detail_shell.dart';

extension _HomepageBuilders on _HomepageDetailShellState {
  /// 交集卡「你和这里的交集」：tag-service shared-tags 对象对直打（当前用户 × 实体主页）。
  /// bundle 直出优先；否则经统一 section（loading 骨架 / 空收起，G2 不造假）。
  Widget _buildIntersectionCard(bool isDark) {
    final bundleReasons = widget.objectPageBundle?.intersectionReasons;
    if (bundleReasons != null && bundleReasons.isNotEmpty) {
      final card = ObjectIntersectionCard.fromReasons(
        title: UITextConstants.homepageIntersectionTitle,
        reasons: bundleReasons,
        isDark: isDark,
        onReasonTap: widget.onIntersectionReasonTap,
      );
      if (card != null) {
        return Padding(
          padding: EdgeInsets.only(top: AppSpacing.containerSm),
          child: card,
        );
      }
    }
    final viewerId = widget.viewerOwnerUserId ?? '';
    final entityId =
        widget.objectPageBundle?.canonicalEntityId ??
        widget.detail?.id ??
        widget.initialSummary?.id ??
        '';
    if (viewerId.isEmpty || entityId.isEmpty) {
      return const SizedBox.shrink();
    }
    // 无 bundle 直出数据时：经统一 section（loading 骨架 / data 卡 / error 收起 + 旅程高亮）。
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.containerSm),
      child: ObjectIntersectionSection(
        query: ObjectIntersectionQuery(
          objectAId: viewerId,
          objectAType: 'user',
          objectBId: entityId,
          objectBType: 'entity',
        ),
        title: UITextConstants.homepageIntersectionTitle,
        isDark: isDark,
        onReasonTap: widget.onIntersectionReasonTap,
      ),
    );
  }

  Widget _buildRelationRibbon(bool isDark) {
    final edges = widget.objectPageBundle?.relationEdges;
    if (edges == null || edges.isEmpty) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.containerSm),
      child: ObjectRelationRibbon(edges: edges, isDark: isDark),
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
    final stats = _HomepageSummaryStats(
      averageRating:
          _reviewSummary?.averageRating ??
          detail?.averageRating ??
          widget.initialSummary?.averageRating,
      ratingCount:
          _reviewSummary?.ratingCount ??
          detail?.ratingCount ??
          widget.initialSummary?.ratingCount ??
          0,
      contentCount: _contentPreview.length + _questionPreview.length,
      relatedCount: _relatedGroups.length,
    );

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
              title: reference?.title ?? '主页',
              subtitle: (reference?.subtitle ?? '').trim(),
              metaLine: locationLine,
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
            Wrap(
              spacing: AppSpacing.intraGroupXs,
              runSpacing: AppSpacing.intraGroupXs,
              children: _summaryChips()
                  .map(
                    (chip) => _HomepageSummaryChipWidget(
                      label: chip.label,
                      accent: chip.accent,
                    ),
                  )
                  .toList(growable: false),
            ),
            SizedBox(height: AppSpacing.containerSm),
            _HomepageStatsRow(stats: stats),
            _buildIntersectionCard(isDark),
            _buildRelationRibbon(isDark),
            if (!widget.selectionMode) ...<Widget>[
              SizedBox(height: AppSpacing.containerSm),
              _HomepageActionBar(
                canCreate: _canCreateFromHomepage,
                canClaim: _canClaim,
                isClaimPending: _isClaimPending,
                isOwnerLike: _isOwnerLike,
                onClaim: widget.onClaim,
                onMaintain: widget.onMaintain,
                onCreateContent: _handlePrimaryAction,
              ),
            ],
          ],
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
              '该主页已下线，记录口碑、关联内容与群组摘要会继续保留，方便用户回看与迁移判断。',
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
