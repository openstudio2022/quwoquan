part of 'circle_shell.dart';

extension _CircleShellBuilders on _CircleShellState {
  /// 加入圈子：游客显示「未加入」，点击先登记续接再引导登录；登录成功后自动加入。
  void _gatedJoinCircle(BuildContext context, CircleStateNotifier notifier) {
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      unawaited(notifier.joinCircle());
      return;
    }
    ref
        .read(authContinuationProvider.notifier)
        .set(JoinCircleContinuation(circleId: widget.circleId));
    unawaited(requireLogin(ref, context, AuthGateReason.joinCircle));
  }

  /// 登录后续接加入圈子：登录成功且续接圈子与本页一致、尚未加入时自动补完加入。
  void maybeResumeJoinContinuation(CircleStateNotifier notifier) {
    final pending = ref
        .read(authContinuationProvider.notifier)
        .take<JoinCircleContinuation>();
    if (pending == null) {
      return;
    }
    if (pending.circleId != widget.circleId) {
      ref.read(authContinuationProvider.notifier).set(pending);
      return;
    }
    final state = ref.read(circleStateProvider(widget.circleId));
    if (!_isMemberLike(state) && state.joinStatus != 'pending') {
      unawaited(notifier.joinCircle());
    }
  }

  Widget _buildSummaryCard(
    BuildContext context, {
    required bool isDark,
    required CircleState state,
    required CircleStateNotifier notifier,
    required String circleName,
    required String? coverUrl,
  }) {
    final circle = state.circleData;
    final statItems = _circleStatItems(state);
    final summarySurface = AppColors.iosProfileSurface(context);
    final summaryBorder = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.24 : 0.08);
    final summaryShadow = isDark
        ? AppColors.black.withValues(alpha: 0.18)
        : AppColors.black.withValues(alpha: 0.05);

    final identityCard = Container(
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
              avatarUrl: circle?.iconUrl ?? coverUrl,
              name: circleName,
              identityTags: circle?.tags ?? const <String>[],
              verified: _isVerified(state),
            ),
            if ((circle?.description ?? '').trim().isNotEmpty) ...[
              SizedBox(height: AppSpacing.containerSm),
              ObjectSloganCard(
                isDark: isDark,
                bio: circle?.description,
                cardKey: const ValueKey<String>('circle-slogan-card'),
              ),
            ],
            if (statItems.isNotEmpty) ...[
              SizedBox(height: AppSpacing.containerSm),
              ObjectStatsRow(
                isDark: isDark,
                items: statItems,
                rowKey: const ValueKey<String>('circle-stats-inline-row'),
              ),
            ],
            SizedBox(height: AppSpacing.md),
            CircleActionBar(
              isDark: isDark,
              role: state.role,
              joinStatus: state.joinStatus,
              joinPolicy: circle?.joinPolicy ?? 'open',
              onJoinCircle:
                  _isMemberLike(state) || state.joinStatus == 'pending'
                  ? null
                  : () => _gatedJoinCircle(context, notifier),
              onEnterDiscussion: () => _changeTab('discussion'),
            ),
          ],
        ),
      ),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        identityCard,
        if (circle != null &&
            ((circle.rulesText ?? '').trim().isNotEmpty ||
                (_isMemberLike(state) &&
                    (circle.welcomeMessage ?? '').trim().isNotEmpty))) ...<
          Widget
        >[
          SizedBox(height: AppSpacing.containerSm),
          _buildGovernanceCard(state, isDark),
        ],
        if (circle != null) ...<Widget>[
          SizedBox(height: AppSpacing.containerSm),
          _buildIntersectionCard(isDark),
          SizedBox(height: AppSpacing.containerSm),
          _buildCircleImpactCard(isDark),
        ],
        if (circle != null && state.loadError != null) ...<Widget>[
          SizedBox(height: AppSpacing.containerSm),
          AppSectionErrorCard(
            semantic: runtimeErrorSemantic(
              context,
              error: state.loadError!,
              category: UiErrorCategory.sectionLoad,
              scope: UiErrorScope.section,
              appearanceMode: widget.sourceAppearanceMode,
            ),
            margin: EdgeInsets.zero,
            onAction: (action) async {
              if (action.type == UiErrorActionType.retry ||
                  action.type == UiErrorActionType.resubmit) {
                await notifier.loadCircle();
              }
            },
          ),
        ],
      ],
    );
  }

  /// 圈规对所有访客可见；欢迎语只在加入后出现，形成治理信息闭环。
  Widget _buildGovernanceCard(CircleState state, bool isDark) {
    final circle = state.circleData!;
    final rulesText = (circle.rulesText ?? '').trim();
    final welcomeMessage = (circle.welcomeMessage ?? '').trim();
    final sections = <Widget>[
      if (rulesText.isNotEmpty)
        _buildGovernanceSection(
          title: UITextConstants.circleRulesTitle,
          body: rulesText,
          key: const ValueKey<String>('circle-rules-section'),
        ),
      if (_isMemberLike(state) && welcomeMessage.isNotEmpty)
        _buildGovernanceSection(
          title: UITextConstants.circleWelcomeTitle,
          body: welcomeMessage,
          key: const ValueKey<String>('circle-welcome-section'),
        ),
    ];
    return Container(
      key: const ValueKey<String>('circle-governance-card'),
      padding: EdgeInsets.all(AppSpacing.containerLg),
      decoration: BoxDecoration(
        color: AppColors.iosProfileSurface(context),
        borderRadius: BorderRadius.circular(_CircleShellState._cardRadius),
        border: Border.all(
          color: AppColors.iosSeparator(
            context,
          ).withValues(alpha: isDark ? 0.24 : 0.08),
          width: AppSpacing.hairline,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          for (var index = 0; index < sections.length; index++) ...<Widget>[
            if (index > 0) SizedBox(height: AppSpacing.md),
            sections[index],
          ],
        ],
      ),
    );
  }

  Widget _buildGovernanceSection({
    required String title,
    required String body,
    required Key key,
  }) {
    return Semantics(
      key: key,
      container: true,
      label: title,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            title,
            style: TextStyle(
              color: AppColors.iosLabel(context),
              fontSize: AppTypography.base,
              fontWeight: AppTypography.semiBold,
            ),
          ),
          SizedBox(height: AppSpacing.xs),
          Text(
            body,
            style: TextStyle(
              color: AppColors.iosSecondaryLabel(context),
              fontSize: AppTypography.sm,
              height: AppTypography.lineHeightRelaxed,
            ),
          ),
        ],
      ),
    );
  }

  /// 「我的交集」预览卡：viewer × 圈子，与实体/用户主页同壳。
  Widget _buildIntersectionCard(bool isDark) {
    final query = ObjectIntersectionQuery(
      objectAId: ref.watch(currentUserIdProvider),
      objectAType: 'user',
      objectBId: widget.circleId,
      objectBType: 'circle',
    );
    if (!query.isResolvable) {
      return const SizedBox.shrink();
    }
    return ObjectIntersectionSection(
      key: const ValueKey<String>('circle-my-intersection-card'),
      query: query,
      title: UITextConstants.objectMyIntersectionsTitle,
      isDark: isDark,
      emptyText: UITextConstants.objectIntersectionEmptyCircle,
      emptyKey: const ValueKey<String>('circle-my-intersection-empty'),
    );
  }

  /// 「打动」预览卡：与实体主页 / 用户主页同语义 token。
  Widget _buildCircleImpactCard(bool isDark) {
    return ObjectImpactPreviewCard(
      objectId: widget.circleId,
      target: ObjectImpactTarget.circle,
      referralSource: ReferralSource.circlePost,
      title: UITextConstants.objectImpactTitleCircle,
      enumerableHint: UITextConstants.impactEnumerableHintCircle,
      cardKey: const ValueKey<String>('circle-impact-card'),
      topDivider: false,
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
              ? AppMediaImage(
                  imageSource: coverUrl,
                  fit: BoxFit.cover,
                  errorWidget: _buildCoverFallback(bg),
                )
              : _buildCoverFallback(bg),
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

  Widget _buildCoverFallback(Color bg) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            bg.withValues(alpha: 0.78),
            AppColors.iosAccent(context).withValues(alpha: 0.18),
            bg.withValues(alpha: 0.92),
          ],
          stops: const [0.0, 0.48, 1.0],
        ),
      ),
    );
  }

  Widget _buildToolbar(
    BuildContext context, {
    required bool isDark,
    required Color fg,
    required Color border,
    required String circleName,
    required CircleState state,
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
                                ClipOval(
                                  child: SizedBox(
                                    width: AppSpacing.avatarUserSm,
                                    height: AppSpacing.avatarUserSm,
                                    child:
                                        avatarUrl != null &&
                                            avatarUrl.isNotEmpty
                                        ? AppCachedNetworkImage(
                                            imageUrl: avatarUrl,
                                            fit: BoxFit.cover,
                                            errorWidget: ColoredBox(
                                              color: actionBackground,
                                              child: Icon(
                                                CupertinoIcons.person_3_fill,
                                                size: AppSpacing.iconMedium,
                                                color: compactForeground,
                                              ),
                                            ),
                                          )
                                        : ColoredBox(
                                            color: actionBackground,
                                            child: Icon(
                                              CupertinoIcons.person_3_fill,
                                              size: AppSpacing.iconMedium,
                                              color: compactForeground,
                                            ),
                                          ),
                                  ),
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
                        // 高保顶栏右侧四图标：搜索 / AI / 分享 / 更多（⚙︎=圈子操作面板）。
                        ObjectChromeActions(
                          foregroundColor: compactForeground,
                          backgroundColor: actionBackground,
                          onSearch: () => GlobalSearchLauncher.open(
                            context,
                            initialScope: GlobalSearchScope.circles.searchScope,
                          ),
                          onAssistant: (ref) =>
                              GlobalAssistantLauncher.open(context, ref),
                          onShare: () => unawaited(
                            _shareCircle(context, circleName: circleName),
                          ),
                          onMore: () => _showMoreOptions(
                            context,
                            circleName: circleName,
                            state: state,
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
    final bodySlot = circleTabById(_activeTabId)?.bodySlot ?? 'creations';

    final child = switch (bodySlot) {
      'creations' =>
        contentLocked
            ? _buildGateCard(
                context,
                title: UITextConstants.visibilityPrivate,
                description: UITextConstants.circleVisibilityMembersDescription,
                keySuffix: _activeTabId,
              )
            : SectionCreations(
                circleId: widget.circleId,
                isDark: isDark,
                role: state.role,
                inlineScroll: true,
              ),
      'discussion' =>
        memberLocked
            ? _buildGateCard(
                context,
                title: UITextConstants.visibilityMembers,
                description: circle?.joinPolicy == 'approval'
                    ? UITextConstants.circleJoinApprovalDescription
                    : UITextConstants.circleJoinOpenDescription,
                keySuffix: _activeTabId,
              )
            : _buildDiscussionBody(context, isDark: isDark, state: state),
      'members' =>
        memberLocked
            ? _buildGateCard(
                context,
                title: UITextConstants.visibilityMembers,
                description: circle?.joinPolicy == 'approval'
                    ? UITextConstants.circleJoinApprovalDescription
                    : UITextConstants.circleJoinOpenDescription,
                keySuffix: _activeTabId,
              )
            : Padding(
                padding: EdgeInsets.only(top: AppSpacing.containerSm),
                child: SectionMembers(
                  circleId: widget.circleId,
                  isDark: isDark,
                ),
              ),
      _ => const SizedBox.shrink(),
    };

    return KeyedSubtree(
      key: ValueKey<String>('circle-tab-body-$_activeTabId'),
      child: child,
    );
  }

  /// 讨论 tab 按 metadata sectionTypes `[chat, storage]` 组合两个成员板块：
  /// 群聊入口 + 圈子文件（容量来自 stats wire，缺失配额时不渲染文件板块）。
  Widget _buildDiscussionBody(
    BuildContext context, {
    required bool isDark,
    required CircleState state,
  }) {
    final stats = state.circleStats;
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.containerSm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SectionChat(
            circleId: widget.circleId,
            conversationId: state.defaultPublicGroup?.conversationId,
            isDark: isDark,
          ),
          if (stats.storageQuotaBytes > 0) ...[
            SizedBox(height: AppSpacing.containerSm),
            Padding(
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
              child: Text(
                UITextConstants.circleStorageSection,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            SectionStorage(
              circleId: widget.circleId,
              isDark: isDark,
              storageUsedBytes: stats.storageUsedBytes,
              storageQuotaBytes: stats.storageQuotaBytes,
            ),
          ],
        ],
      ),
    );
  }
}
