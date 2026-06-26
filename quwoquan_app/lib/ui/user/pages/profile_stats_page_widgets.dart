part of 'profile_stats_page.dart';

extension _ProfileStatsPageWidgets on _ProfileStatsPageState {
  Widget _buildBody(BuildContext context, bool isDark) {
    if (_bundleError != null && _bundle == null) {
      return _buildBlockingState(
        context,
        isDark: isDark,
        title: UITextConstants.loadFailed,
        message: runtimeErrorDisplayMessage(_bundleError!),
        actionLabel: UITextConstants.tryAgain,
        onAction: _loadBundleAndActiveTab,
      );
    }
    if (_bundle != null && !_bundle!.viewerContext.canViewFullProfile) {
      return _buildPermissionState(isDark);
    }
    final memory = _activeMemory;
    return CustomScrollView(
      controller: memory.scrollController,
      physics: const BouncingScrollPhysics(
        parent: AlwaysScrollableScrollPhysics(),
      ),
      slivers: <Widget>[
        CupertinoSliverRefreshControl(onRefresh: _refreshActiveTab),
        SliverToBoxAdapter(child: _buildSearchBar(isDark)),
        if (_isBundleLoading || (memory.isLoading && !memory.hasLoaded))
          _buildSkeletonSliver(isDark)
        else if (memory.loadError != null && memory.items.isEmpty)
          SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerMd,
                AppSpacing.containerSm,
                AppSpacing.containerMd,
                AppSpacing.containerLg,
              ),
              child: _buildStatusCard(
                isDark: isDark,
                title: UITextConstants.loadFailed,
                message: runtimeErrorDisplayMessage(memory.loadError!),
                actionLabel: UITextConstants.tryAgain,
                onAction: () => _loadTab(_activeTab),
              ),
            ),
          )
        else if (memory.items.isEmpty)
          SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerMd,
                AppSpacing.containerSm,
                AppSpacing.containerMd,
                AppSpacing.containerLg,
              ),
              child: _buildEmptyCard(isDark, _activeTab),
            ),
          )
        else
          ..._buildListSlivers(isDark, memory),
      ],
    );
  }

  Widget _buildSegmentedControl(BuildContext context) {
    final availableWidth =
        (MediaQuery.sizeOf(context).width -
                AppSpacing.appChromeActionButtonSize * 2)
            .clamp(
              AppSpacing.minInteractiveSize * _ProfileStatsTab.values.length,
              AppSpacing.minInteractiveSize *
                  _ProfileStatsTab.values.length *
                  2,
            )
            .toDouble();
    return SizedBox(
      width: availableWidth,
      child: AppSegmentedChoiceBar<_ProfileStatsTab>(
        items: <AppSegmentedChoiceItem<_ProfileStatsTab>>[
          for (final tab in _ProfileStatsTab.values)
            AppSegmentedChoiceItem<_ProfileStatsTab>(
              value: tab,
              label: tab.label,
            ),
        ],
        selectedValue: _activeTab,
        onChanged: (value) => _selectTab(value, trackEvent: true),
      ),
    );
  }

  Widget _buildSearchBar(bool isDark) {
    return EmbeddedMemberSearchBarPlain(
      isDark: isDark,
      controller: _activeMemory.searchController,
      placeholder: _activeTab.searchHint,
      onChanged: (_) {},
    );
  }

  Widget _buildBlockingState(
    BuildContext context, {
    required bool isDark,
    required String title,
    required String message,
    required String actionLabel,
    required Future<void> Function() onAction,
  }) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: _buildStatusCard(
          isDark: isDark,
          title: title,
          message: message,
          actionLabel: actionLabel,
          onAction: onAction,
        ),
      ),
    );
  }

  Widget _buildPermissionState(bool isDark) {
    final blocked = _isBlockedProfile;
    final title = blocked
        ? UITextConstants.profileStatsBlockedTitle
        : UITextConstants.profileStatsPrivateTitle;
    final message = blocked
        ? UITextConstants.profileStatsBlockedBody
        : UITextConstants.profileStatsPrivateBody;
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: _buildStatusCard(isDark: isDark, title: title, message: message),
      ),
    );
  }

  List<Widget> _buildListSlivers(bool isDark, _ProfileStatsTabMemory memory) {
    return <Widget>[
      SliverPadding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerSm,
          AppSpacing.containerMd,
          AppSpacing.containerLg,
        ),
        sliver: _buildSeparatedSliverList(
          itemCount: memory.items.length,
          itemBuilder: (context, index) {
            final item = memory.items[index];
            return switch (_activeTab) {
              _ProfileStatsTab.circles => _buildCircleRow(
                context,
                item as CircleDto,
                isDark,
              ),
              _ProfileStatsTab.fans ||
              _ProfileStatsTab.following => _buildRelationRow(
                context,
                item as ProfileSocialRelationRowViewData,
                isDark,
              ),
            };
          },
        ),
      ),
      if (memory.isAppending)
        SliverToBoxAdapter(
          child: Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.containerLg),
            child: Center(child: CupertinoActivityIndicator()),
          ),
        ),
      if (memory.appendError != null)
        SliverToBoxAdapter(
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              0,
              AppSpacing.containerMd,
              AppSpacing.containerLg,
            ),
            child: _buildStatusCard(
              isDark: isDark,
              title: UITextConstants.loadFailed,
              message: runtimeErrorDisplayMessage(memory.appendError!),
              actionLabel: UITextConstants.tryAgain,
              onAction: () => _appendTab(_activeTab),
            ),
          ),
        ),
    ];
  }

  Widget _buildCircleRow(BuildContext context, CircleDto circle, bool isDark) {
    final titleColor = SettingsSemanticConstants.labelColor(isDark);
    final subtitleColor = SettingsSemanticConstants.secondaryColor(isDark);
    final visibilityText = _circleVisibilityText(circle.visibility);
    return _buildCard(
      isDark: isDark,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: () => _openCircle(circle),
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerSm),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                child: SizedBox(
                  width: AppSpacing.profileStatsRowAvatarSize,
                  height: AppSpacing.profileStatsRowAvatarSize,
                  child: circle.coverUrl?.isNotEmpty == true
                      ? AppCachedNetworkImage(
                          imageUrl: circle.coverUrl!,
                          fit: BoxFit.cover,
                          cdnPreset: CdnImagePreset.cover,
                        )
                      : ColoredBox(
                          color: CupertinoDynamicColor.resolve(
                            CupertinoColors.systemGrey5,
                            context,
                          ),
                          child: Icon(
                            CupertinoIcons.group,
                            color: subtitleColor,
                          ),
                        ),
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      circle.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.semiBold,
                        color: titleColor,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Wrap(
                      spacing: AppSpacing.intraGroupXs,
                      runSpacing: AppSpacing.intraGroupXs,
                      children: [
                        Text(
                          '${circle.memberCount} ${UITextConstants.profileStatsCircleMembersUnit}',
                          style: TextStyle(
                            fontSize: AppTypography.iosFootnote,
                            color: subtitleColor,
                          ),
                        ),
                        Text(
                          '·',
                          style: TextStyle(
                            fontSize: AppTypography.iosFootnote,
                            color: subtitleColor,
                          ),
                        ),
                        Text(
                          '${circle.postCount} ${UITextConstants.profileStatsCircleCreationsUnit}',
                          style: TextStyle(
                            fontSize: AppTypography.iosFootnote,
                            color: subtitleColor,
                          ),
                        ),
                        if (visibilityText.isNotEmpty) ...[
                          Text(
                            '·',
                            style: TextStyle(
                              fontSize: AppTypography.iosFootnote,
                              color: subtitleColor,
                            ),
                          ),
                          Text(
                            visibilityText,
                            style: TextStyle(
                              fontSize: AppTypography.iosFootnote,
                              color: subtitleColor,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupXs),
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.listTrailingChevronSize,
                color: subtitleColor,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildRelationRow(
    BuildContext context,
    ProfileSocialRelationRowViewData row,
    bool isDark,
  ) {
    final capability = _resolvedCapability(row);
    final titleColor = SettingsSemanticConstants.labelColor(isDark);
    final subtitleColor = SettingsSemanticConstants.secondaryColor(isDark);
    final button = _buildFollowButton(context, row, capability, isDark);
    return _buildCard(
      isDark: isDark,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: () => _openUserProfile(row),
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerSm),
          child: Row(
            children: [
              ClipOval(
                child: SizedBox(
                  width: AppSpacing.profileStatsRowAvatarSize,
                  height: AppSpacing.profileStatsRowAvatarSize,
                  child: row.avatarUrl.isNotEmpty
                      ? AppAvatarImage(
                          imageUrl: row.avatarUrl,
                          size: AppSpacing.profileStatsRowAvatarSize,
                        )
                      : ColoredBox(
                          color: CupertinoDynamicColor.resolve(
                            CupertinoColors.systemGrey5,
                            context,
                          ),
                          child: Icon(
                            CupertinoIcons.person_solid,
                            color: subtitleColor,
                          ),
                        ),
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      row.displayName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.semiBold,
                        color: titleColor,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      '@${row.userHandle}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: subtitleColor,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      _relationSecondaryText(row, capability),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: subtitleColor,
                      ),
                    ),
                  ],
                ),
              ),
              if (button != null) ...[
                SizedBox(width: AppSpacing.containerSm),
                button,
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget? _buildFollowButton(
    BuildContext context,
    ProfileSocialRelationRowViewData row,
    RelationshipCapabilityDto capability,
    bool isDark,
  ) {
    if (capability.isSelf || capability.isBlocked || capability.isBlockedBy) {
      return null;
    }
    final (label, isPrimary, onPressed) = switch (capability.relationState) {
      'followed_by' => (
        UITextConstants.followBack,
        true,
        () => _handleFollowAction(row),
      ),
      'following' => (
        UITextConstants.following,
        false,
        () => _showFollowingActionSheet(row),
      ),
      'mutual' => (
        UITextConstants.profileStatsMutual,
        false,
        () => _showFollowingActionSheet(row),
      ),
      _ => (UITextConstants.follow, true, () => _handleFollowAction(row)),
    };
    final fillColor = isPrimary
        ? AppColors.iosAccent(context).withValues(alpha: 0.12)
        : CupertinoDynamicColor.resolve(CupertinoColors.systemGrey5, context);
    final textColor = isPrimary
        ? AppColors.iosAccent(context)
        : SettingsSemanticConstants.secondaryColor(isDark);
    final borderColor = isPrimary
        ? AppColors.iosAccent(context).withValues(alpha: 0.18)
        : SettingsSemanticConstants.insetFormSectionDividerColor(isDark);
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      color: fillColor,
      onPressed: onPressed,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(color: borderColor, width: AppSpacing.hairline),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerXs,
            vertical: AppSpacing.intraGroupXs,
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              fontWeight: AppTypography.medium,
              color: textColor,
            ),
          ),
        ),
      ),
    );
  }

  String _relationSecondaryText(
    ProfileSocialRelationRowViewData row,
    RelationshipCapabilityDto capability,
  ) {
    final segments = <String>[];
    if (capability.relationState == 'mutual') {
      segments.add(UITextConstants.relatedMutualFollow);
    } else if (capability.relationState == 'followed_by') {
      segments.add(UITextConstants.profileStatsFollowedBy);
    } else if (capability.relationState == 'following') {
      segments.add(UITextConstants.following);
    }
    final visibility = _profileVisibilityText(row.profileVisibility);
    if (visibility.isNotEmpty) {
      segments.add(visibility);
    }
    if (segments.isEmpty) {
      return UITextConstants.visibilityPublic;
    }
    return segments.join(' · ');
  }

  String _profileVisibilityText(String raw) {
    switch (raw) {
      case 'contacts':
      case 'followers':
      case 'semi':
        return UITextConstants.profileStatsVisibilityContacts;
      case 'private':
        return UITextConstants.profileStatsVisibilitySelfOnly;
      case 'blocked':
      case 'restricted':
        return UITextConstants.profileStatsVisibilityBlocked;
      case 'public':
      default:
        return UITextConstants.visibilityPublic;
    }
  }

  String _circleVisibilityText(String raw) {
    switch (raw) {
      case 'members':
        return UITextConstants.visibilityMembers;
      case 'private':
        return UITextConstants.profileStatsVisibilitySelfOnly;
      case 'public':
      default:
        return UITextConstants.visibilityPublic;
    }
  }

  Widget _buildEmptyCard(bool isDark, _ProfileStatsTab tab) {
    final title = switch (tab) {
      _ProfileStatsTab.fans =>
        (_bundle?.viewerContext.isOwner ?? false)
            ? UITextConstants.profileStatsEmptyFansMineTitle
            : UITextConstants.profileStatsEmptyFansOtherTitle,
      _ProfileStatsTab.following =>
        (_bundle?.viewerContext.isOwner ?? false)
            ? UITextConstants.profileStatsEmptyFollowingMineTitle
            : UITextConstants.profileStatsEmptyFollowingOtherTitle,
      _ProfileStatsTab.circles =>
        (_bundle?.viewerContext.isOwner ?? false)
            ? UITextConstants.profileStatsEmptyCirclesMineTitle
            : UITextConstants.profileStatsEmptyCirclesOtherTitle,
    };
    final message = switch (tab) {
      _ProfileStatsTab.fans =>
        (_bundle?.viewerContext.isOwner ?? false)
            ? UITextConstants.profileStatsEmptyFansMineBody
            : UITextConstants.profileStatsEmptyFansOtherBody,
      _ProfileStatsTab.following =>
        (_bundle?.viewerContext.isOwner ?? false)
            ? UITextConstants.profileStatsEmptyFollowingMineBody
            : UITextConstants.profileStatsEmptyFollowingOtherBody,
      _ProfileStatsTab.circles =>
        (_bundle?.viewerContext.isOwner ?? false)
            ? UITextConstants.profileStatsEmptyCirclesMineBody
            : UITextConstants.profileStatsEmptyCirclesOtherBody,
    };
    final showCirclesCta =
        tab == _ProfileStatsTab.circles &&
        (_bundle?.viewerContext.isOwner ?? false);
    return _buildStatusCard(
      isDark: isDark,
      title: title,
      message: message,
      actionLabel: showCirclesCta
          ? UITextConstants.profileStatsDiscoverCircles
          : null,
      onAction: showCirclesCta
          ? () async {
              if (!mounted) {
                return;
              }
              context.go(AppRoutePaths.circles);
            }
          : null,
    );
  }

  Widget _buildSkeletonSliver(bool isDark) {
    return SliverPadding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerSm,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
      ),
      sliver: _buildSeparatedSliverList(
        itemCount: 6,
        itemBuilder: (_, _) => _buildSkeletonRow(isDark),
      ),
    );
  }

  SliverList _buildSeparatedSliverList({
    required int itemCount,
    required Widget Function(BuildContext context, int index) itemBuilder,
  }) {
    return SliverList(
      delegate: SliverChildBuilderDelegate((context, index) {
        final itemIndex = index ~/ 2;
        if (index.isOdd) {
          return SizedBox(height: AppSpacing.sm);
        }
        return itemBuilder(context, itemIndex);
      }, childCount: itemCount == 0 ? 0 : itemCount * 2 - 1),
    );
  }

  Widget _buildSkeletonRow(bool isDark) {
    final surface = SettingsSemanticConstants.insetFormSectionSurface(isDark);
    final shimmer = CupertinoDynamicColor.resolve(
      CupertinoColors.systemGrey5,
      context,
    );
    return ClipRRect(
      borderRadius: BorderRadius.circular(
        SettingsSemanticConstants.insetFormSectionCornerRadius,
      ),
      child: ColoredBox(
        color: surface,
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerSm),
          child: Row(
            children: [
              Container(
                width: AppSpacing.profileStatsRowAvatarSize,
                height: AppSpacing.profileStatsRowAvatarSize,
                decoration: BoxDecoration(
                  color: shimmer,
                  shape: BoxShape.circle,
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _skeletonLine(widthFactor: 0.54, color: shimmer),
                    SizedBox(height: AppSpacing.intraGroupXs),
                    _skeletonLine(widthFactor: 0.34, color: shimmer),
                    SizedBox(height: AppSpacing.intraGroupXs),
                    _skeletonLine(widthFactor: 0.46, color: shimmer),
                  ],
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              Container(
                width: AppSpacing.profileStatsFollowSkeletonWidth,
                height: AppSpacing.profileStatsFollowSkeletonHeight,
                decoration: BoxDecoration(
                  color: shimmer,
                  borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _skeletonLine({required double widthFactor, required Color color}) {
    return FractionallySizedBox(
      widthFactor: widthFactor,
      child: Container(
        height: AppSpacing.ten,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        ),
      ),
    );
  }

  Widget _buildCard({required bool isDark, required Widget child}) {
    return AppListSurface(child: child);
  }

  Widget _buildStatusCard({
    required bool isDark,
    required String title,
    required String message,
    String? actionLabel,
    Future<void> Function()? onAction,
  }) {
    final titleColor = SettingsSemanticConstants.labelColor(isDark);
    final subtitleColor = SettingsSemanticConstants.secondaryColor(isDark);
    return _buildCard(
      isDark: isDark,
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              title,
              style: TextStyle(
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
                color: titleColor,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              message,
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                color: subtitleColor,
                height: AppTypography.lineHeightRelaxed,
              ),
            ),
            if (actionLabel != null && onAction != null) ...[
              SizedBox(height: AppSpacing.containerSm),
              CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: () => unawaited(onAction()),
                child: Text(actionLabel),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
