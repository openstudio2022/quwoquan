part of 'circle_shell.dart';

extension _CircleShellBuilders on _CircleShellState {
  Widget _buildSummaryCard(
    BuildContext context, {
    required bool isDark,
    required CircleState state,
    required CircleStateNotifier notifier,
    required String circleName,
    required String? coverUrl,
  }) {
    final circle = state.circleData;
    final hasConversation = (circle?.conversationId ?? '').trim().isNotEmpty;
    final summarySurface = AppColors.iosProfileSurface(context);
    final summaryBorder = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.24 : 0.08);
    final summaryShadow = isDark
        ? AppColors.black.withValues(alpha: 0.18)
        : AppColors.black.withValues(alpha: 0.05);

    return Container(
      decoration: BoxDecoration(
        color: summarySurface,
        borderRadius: BorderRadius.circular(_CircleShellState._cardRadius),
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
          children: [
            CircleHeader(
              isDark: isDark,
              avatarUrl: coverUrl,
              name: circleName,
              description: circle?.description,
              tags: circle?.tags ?? const [],
              badgeLabel: _badgeLabel(state),
              metaLine: _metaLine(state),
              onTagTap: (tag) {
                ref
                    .read(contentEngagementTrackerProvider)
                    .trackTagClick(tag, fromContentId: widget.circleId);
              },
            ),
            SizedBox(height: AppSpacing.md),
            Wrap(
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: _metaChips(state)
                  .map(
                    (chip) => _CircleMetaChip(
                      label: chip.label,
                      icon: chip.icon,
                      accent: chip.accent,
                    ),
                  )
                  .toList(growable: false),
            ),
            SizedBox(height: AppSpacing.sm),
            CircleStatsRow(
              isDark: isDark,
              stats: state.circleStats.forDetailRow(circle),
            ),
            SizedBox(height: AppSpacing.sm),
            CircleActionBar(
              isDark: isDark,
              role: state.role,
              joinStatus: state.joinStatus,
              isFollowed: state.isFollowed,
              joinPolicy: circle?.joinPolicy ?? 'open',
              hasConversation: hasConversation,
              onEditCircle: () => _openEditor(
                context,
                state: state,
                initialTab: CircleEditSettingsTab.info,
              ),
              onManageCenter: () => _openEditor(
                context,
                state: state,
                initialTab: CircleEditSettingsTab.settings,
              ),
              onFollow: notifier.toggleFollow,
              onJoinCircle:
                  _isMemberLike(state) || state.joinStatus == 'pending'
                  ? null
                  : notifier.joinCircle,
              onOpenChat: hasConversation
                  ? () => _openChat(context, circle!.conversationId!)
                  : null,
            ),
            if (state.error != null && state.error!.trim().isNotEmpty) ...[
              SizedBox(height: AppSpacing.sm),
              Container(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                  vertical: AppSpacing.containerSm,
                ),
                decoration: BoxDecoration(
                  color: AppColors.error.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius,
                  ),
                ),
                child: Row(
                  children: [
                    Icon(
                      CupertinoIcons.exclamationmark_triangle_fill,
                      size: AppSpacing.iconSmall,
                      color: AppColors.error,
                    ),
                    SizedBox(width: AppSpacing.intraGroupSm),
                    Expanded(
                      child: Text(
                        UITextConstants.loadFailed,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: AppColors.iosSecondaryLabel(context),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildBackgroundLayer({required Color bg, required String? coverUrl}) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          bottom: -_CircleShellState._surfaceBridge,
          child: coverUrl != null && coverUrl.isNotEmpty
              ? Image.network(
                  coverUrl,
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) =>
                      ColoredBox(color: bg),
                )
              : ColoredBox(color: bg.withValues(alpha: 0.75)),
        ),
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          bottom: -_CircleShellState._surfaceBridge,
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  AppColors.black.withValues(alpha: 0.08),
                  AppColors.black.withValues(alpha: 0.04),
                  bg.withValues(alpha: 0.12),
                ],
                stops: const [0.0, 0.56, 1.0],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildToolbar(
    BuildContext context, {
    required bool isDark,
    required Color fg,
    required Color border,
    required String circleName,
    required String? avatarUrl,
    required double identityOpacity,
    required double backgroundOpacity,
  }) {
    final topPadding = AppSpacing.appChromeTopSafeInset(
      MediaQuery.viewPaddingOf(context).top,
      context,
    );
    final slotWidth =
        AppSpacing.appChromeActionButtonSize + AppSpacing.containerXs;
    final chrome = Color.lerp(
      AppColors.transparent,
      AppColors.iosSystemBackground(context),
      backgroundOpacity.clamp(0.0, 1.0),
    )!;
    final compactForeground = backgroundOpacity > 0.12
        ? fg
        : CupertinoColors.white;
    final actionBackground =
        AppNavigationSemanticConstants.chromeActionBackground(
          surface: AppChromeSurface.overlay,
        );

    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: AnnotatedRegion<SystemUiOverlayStyle>(
        value: SystemUiOverlayStyle(
          statusBarColor: AppColors.transparent,
          statusBarIconBrightness: backgroundOpacity > 0.12
              ? (isDark ? Brightness.light : Brightness.dark)
              : Brightness.light,
          statusBarBrightness: backgroundOpacity > 0.12
              ? (isDark ? Brightness.dark : Brightness.light)
              : Brightness.dark,
        ),
        child: Container(
          padding: EdgeInsets.only(top: topPadding),
          decoration: BoxDecoration(
            color: chrome,
            border: backgroundOpacity > 0.02
                ? Border(
                    bottom: BorderSide(
                      color: border.withValues(alpha: 0.16),
                      width: AppSpacing.hairline,
                    ),
                  )
                : null,
          ),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final maxWidth = AppSpacing.adaptiveFeedMaxContentWidth(
                constraints.maxWidth,
              );
              return Align(
                alignment: Alignment.topCenter,
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: maxWidth),
                  child: SizedBox(
                    height: AppSpacing.appChromeTopBarHeight(context),
                    child: Row(
                      children: [
                        SizedBox(
                          width: slotWidth,
                          child: Align(
                            alignment: Alignment.centerLeft,
                            child: _CircleToolbarButton(
                              icon: CupertinoIcons.back,
                              onPressed:
                                  widget.onBack ??
                                  () {
                                    Navigator.of(context).maybePop();
                                  },
                              backgroundColor: actionBackground,
                              foregroundColor: compactForeground,
                            ),
                          ),
                        ),
                        Expanded(
                          child: Opacity(
                            opacity: identityOpacity,
                            child: Row(
                              key: const ValueKey<String>(
                                'circle-shell-compact-identity',
                              ),
                              mainAxisAlignment: MainAxisAlignment.center,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                CircleAvatar(
                                  radius: AppSpacing.avatarUserSm / 2,
                                  backgroundColor: actionBackground,
                                  backgroundImage:
                                      avatarUrl != null && avatarUrl.isNotEmpty
                                      ? NetworkImage(avatarUrl)
                                      : null,
                                  child: avatarUrl == null || avatarUrl.isEmpty
                                      ? Icon(
                                          CupertinoIcons.person_3_fill,
                                          size: AppSpacing.iconMedium,
                                          color: compactForeground,
                                        )
                                      : null,
                                ),
                                SizedBox(width: AppSpacing.containerSm),
                                Flexible(
                                  child: Text(
                                    circleName,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: AppTypography.iosNavTitle,
                                      fontWeight: AppTypography.medium,
                                      color: compactForeground,
                                      letterSpacing: -0.24,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        SizedBox(
                          width: slotWidth,
                          child: Align(
                            alignment: Alignment.centerRight,
                            child: _CircleToolbarButton(
                              icon: CupertinoIcons.ellipsis,
                              onPressed: () => _showMoreOptions(
                                context,
                                circleName: circleName,
                              ),
                              backgroundColor: actionBackground,
                              foregroundColor: compactForeground,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }

  Widget _buildPrimaryTabBar(
    BuildContext context, {
    required Color bg,
    required Color border,
    required bool pinned,
    double opacity = 1.0,
  }) {
    final tabs = _resolvedTabs
        .map((tab) => TabItem(id: tab.type, label: tab.label))
        .toList(growable: false);
    final surface = Container(
      key: pinned
          ? const ValueKey<String>('circle-shell-primary-tabs-pinned')
          : const ValueKey<String>('circle-shell-primary-tabs-inline'),
      decoration: BoxDecoration(
        color: bg,
        border: Border(
          bottom: BorderSide(
            color: border.withValues(alpha: 0.1),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: SizedBox(
        height: AppSpacing.tabNavigationHeight,
        child: CenteredScrollableTabBar(
          tabs: tabs,
          activeTab: _activeTabId,
          onTabChange: _changeTab,
          onHorizontalDragEnd: _handleTabSwipeDragEnd,
          transparentBackground: true,
        ),
      ),
    );
    if (pinned) return surface;
    return IgnorePointer(
      ignoring: opacity <= 0.02,
      child: Opacity(opacity: opacity, child: surface),
    );
  }

  Widget _buildInlineTabBody(
    BuildContext context, {
    required bool isDark,
    required CircleState state,
  }) {
    final circle = state.circleData;
    final contentLocked = !_canAccessPrimaryContent(state);
    final memberLocked = !_canAccessMemberSpaces(state);

    final child = switch (_activeTabId) {
      'content' =>
        contentLocked
            ? _buildGateCard(
                context,
                title: UITextConstants.visibilityPrivate,
                description: UITextConstants.circleVisibilityMembersDescription,
                keySuffix: 'content',
              )
            : SectionCreations(
                circleId: widget.circleId,
                isDark: isDark,
                role: state.role,
                inlineScroll: true,
              ),
      'discussion' =>
        contentLocked
            ? _buildGateCard(
                context,
                title: UITextConstants.visibilityPrivate,
                description: UITextConstants.circleVisibilityMembersDescription,
                keySuffix: 'discussion',
              )
            : Padding(
                padding: EdgeInsets.fromLTRB(
                  AppSpacing.containerMd,
                  AppSpacing.containerSm,
                  AppSpacing.containerMd,
                  0,
                ),
                child: _SectionSurface(
                  isDark: isDark,
                  child: SectionInteraction(
                    circleId: widget.circleId,
                    isDark: isDark,
                  ),
                ),
              ),
      'assets' =>
        memberLocked
            ? _buildGateCard(
                context,
                title: UITextConstants.visibilityMembers,
                description: circle?.joinPolicy == 'approval'
                    ? UITextConstants.circleJoinApprovalDescription
                    : UITextConstants.circleJoinOpenDescription,
                keySuffix: 'assets',
              )
            : Padding(
                padding: EdgeInsets.fromLTRB(
                  AppSpacing.containerMd,
                  AppSpacing.containerSm,
                  AppSpacing.containerMd,
                  0,
                ),
                child: Column(
                  children: [
                    _SectionSurface(
                      isDark: isDark,
                      child: SectionChat(
                        circleId: widget.circleId,
                        conversationId: circle?.conversationId,
                        isDark: isDark,
                      ),
                    ),
                    SizedBox(height: AppSpacing.md),
                    _SectionSurface(
                      isDark: isDark,
                      child: SectionStorage(
                        circleId: widget.circleId,
                        isDark: isDark,
                        storageUsedBytes: circle?.storageUsedBytes ?? 0,
                        storageQuotaBytes:
                            circle?.storageQuotaBytes ?? 1073741824,
                      ),
                    ),
                  ],
                ),
              ),
      _ => const SizedBox.shrink(),
    };

    return KeyedSubtree(
      key: ValueKey<String>('circle-tab-body-$_activeTabId'),
      child: child,
    );
  }

}
