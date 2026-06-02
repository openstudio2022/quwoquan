part of 'profile_shell.dart';

extension _ProfileShellBuilders on _ProfileShellState {
  /// 交集卡「你们的交集」：tag-service shared-tags 对象对直打（当前用户 × 被看用户）。
  /// 仅 other 模式展示；无可解析交集（空/异步未就绪）则不占位（G2 不造假）。
  Widget _buildIntersectionCard(bool isDark) {
    if (widget.mode != ProfileMode.other) {
      return const SizedBox.shrink();
    }
    final query = ObjectIntersectionQuery(
      objectAId: ref.watch(currentUserIdProvider),
      objectAType: 'user',
      objectBId: widget.userId,
      objectBType: 'user',
    );
    if (!query.isResolvable) {
      return const SizedBox.shrink();
    }
    final reasons = ref.watch(objectSharedReasonsProvider(query)).asData?.value;
    final card = ObjectIntersectionCard.fromReasons(
      title: UITextConstants.profileMutualIntersectionTitle,
      reasons: reasons,
      isDark: isDark,
      onReasonTap: (reason) => _reportIntersectionReasonTap(reason),
    );
    if (card == null) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.md),
      child: card,
    );
  }

  /// 交集点点击 → 交集行动归因（B3）：把触发维度 + 路径制 tagRef 锚点回流到推荐管线。
  /// contentId 为被看对象（用户），来源标记为来自主页交集卡。仓库内部已做失败入队，无需本地 catch。
  void _reportIntersectionReasonTap(IntersectionReason reason) {
    final repo = ref.read(behaviorRepositoryProvider);
    unawaited(
      repo.reportEvents(
        events: <BehaviorEvent>[
          BehaviorEvent(
            contentId: widget.userId,
            action: BehaviorAction.tagClick,
            contentType: 'user',
            authorId: widget.userId,
            referralSource: ReferralSource.authorProfile,
            tags: reason.tagRefs,
            intersectionDimension: reason.dimension,
            intersectionTagRefs: reason.tagRefs,
          ),
        ],
      ),
    );
  }

  /// 关注：游客显示「未关注」，点击先登记续接再引导登录；已登录直接 toggle。
  void _gatedToggleFollow(BuildContext context, ProfileNotifier notifier) {
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      unawaited(notifier.toggleFollow());
      return;
    }
    ref
        .read(authContinuationProvider.notifier)
        .set(FollowProfileContinuation(subAccountId: widget.userId));
    unawaited(requireLogin(ref, context, AuthGateReason.follow));
  }

  /// 私信：经 `/chat/*` 路由门保障，按钮层显式带统一 reason，未登录引导登录后进入会话。
  void _gatedOpenMessage(BuildContext context) {
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      context.push(AppRoutePaths.chatDetail(id: widget.userId));
      return;
    }
    openLoginPage(
      context,
      reasonName: AuthGateReason.sendMessage.name,
      redirect: AppRoutePaths.chatDetail(id: widget.userId),
      dismissFallback: AppRoutePaths.home,
    );
  }

  /// 登录后续接关注：登录成功（auth 翻转为已认证）且续接对象与本主页一致、当前未关注时，
  /// 自动补完关注，避免游客「点关注→登录回来什么都没发生」。
  void maybeResumeFollowContinuation(ProfileNotifier notifier) {
    final pending = ref
        .read(authContinuationProvider.notifier)
        .take<FollowProfileContinuation>();
    if (pending == null) {
      return;
    }
    if (pending.subAccountId != widget.userId) {
      // 续接对象不是本主页：放回槽位交由对应主页消费。
      ref.read(authContinuationProvider.notifier).set(pending);
      return;
    }
    if (!ref.read(profileNotifierProvider(widget.userId)).isFollowing) {
      unawaited(notifier.toggleFollow());
    }
  }

  Widget _buildSummarySection(
    BuildContext context, {
    required bool isDark,
    required bool personaManagementEnabled,
    required String? avatarUrl,
    required String displayName,
    required String? bio,
    required ProfileState state,
    required ProfileNotifier notifier,
  }) {
    final summarySurface =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final summaryBorder =
        SettingsSemanticConstants.conversationSheetCardBorderColor(isDark);
    final displayCapability = state.displayCapability;
    final summaryShadow = isDark
        ? AppColors.black.withValues(alpha: 0.18)
        : AppColors.black.withValues(alpha: 0.05);
    return Container(
      decoration: BoxDecoration(
        color: summarySurface,
        borderRadius: BorderRadius.circular(
          _ProfileShellState._profileCardRadius,
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
          children: [
            ProfileHeader(
              isDark: isDark,
              avatarUrl: avatarUrl,
              displayName: displayName,
              bio: bio,
            ),
            SizedBox(height: AppSpacing.md),
            _buildIntersectionCard(isDark),
            if (widget.mode == ProfileMode.mine) ...[
              MyIntersectionInboxCard(isDark: isDark),
              SizedBox(height: AppSpacing.md),
            ],
            SizedBox(height: AppSpacing.md),
            ProfileStatsRow(
              isDark: isDark,
              profile: state.profile,
              onStatTap: (type) => context.push(
                '${AppRoutePaths.profileStats(type: type)}&userId=${Uri.encodeComponent(widget.userId)}',
              ),
            ),
            SizedBox(height: AppSpacing.sm),
            if (widget.mode == ProfileMode.other &&
                displayCapability == null) ...[
              SizedBox(height: AppSpacing.xl + AppSpacing.md),
            ] else ...[
              ProfileActionBar(
                mode: widget.mode,
                isDark: isDark,
                capability: displayCapability,
                onEditProfile: () => context.push(AppRoutePaths.profileEdit),
                onManagePersonas: personaManagementEnabled
                    ? () => context.push(AppRoutePaths.profilePersonas)
                    : null,
                onFollow: () => _gatedToggleFollow(context, notifier),
                onMessage: () => _gatedOpenMessage(context),
                onGreet: () => _showGreetDialog(context),
                onVoiceCall: () => _startCall(context, 'voice'),
                onVideoCall: () => _startCall(context, 'video'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildBackgroundLayer(
    BuildContext context, {
    required String? backgroundUrl,
    required Color backgroundColor,
  }) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          bottom: -_ProfileShellState._profileSurfaceBridge,
          child: backgroundUrl != null && backgroundUrl.isNotEmpty
              ? Image.network(
                  backgroundUrl,
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) =>
                      ColoredBox(color: backgroundColor),
                )
              : ColoredBox(color: backgroundColor.withValues(alpha: 0.75)),
        ),
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          bottom: -_ProfileShellState._profileSurfaceBridge,
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  AppColors.black.withValues(alpha: 0.08),
                  AppColors.black.withValues(alpha: 0.04),
                  backgroundColor.withValues(alpha: 0.12),
                ],
                stops: const [0.0, 0.56, 1.0],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildToolbarOverlay(
    BuildContext context, {
    required bool isDark,
    required Color fg,
    required Color border,
    required String displayName,
    required String? avatarUrl,
    required double opacity,
    required double backgroundOpacity,
  }) {
    final topPadding = AppSpacing.appChromeTopSafeInset(
      MediaQuery.viewPaddingOf(context).top,
      context,
    );
    final sideSlotWidth =
        AppSpacing.appChromeActionButtonSize + AppSpacing.containerXs;
    final trailingSlotWidth = widget.mode == ProfileMode.mine
        ? AppSpacing.appChromeActionButtonSize * 3 +
              AppSpacing.intraGroupXs * 2 +
              AppSpacing.containerXs
        : sideSlotWidth;
    final resolvedOpacity = backgroundOpacity.clamp(0.0, 1.0);
    final compactForeground = resolvedOpacity > 0.12
        ? fg
        : CupertinoColors.white;
    final toolbarChrome = Color.lerp(
      AppColors.transparent,
      AppColors.iosSystemBackground(context),
      resolvedOpacity,
    )!;
    final actionBackground =
        AppNavigationSemanticConstants.chromeActionBackground(
          surface: AppChromeSurface.overlay,
        );
    final statusIconsDark = resolvedOpacity > 0.12;
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: AnnotatedRegion<SystemUiOverlayStyle>(
        value: SystemUiOverlayStyle(
          statusBarColor: AppColors.transparent,
          statusBarIconBrightness: statusIconsDark
              ? (isDark ? Brightness.light : Brightness.dark)
              : Brightness.light,
          statusBarBrightness: statusIconsDark
              ? (isDark ? Brightness.dark : Brightness.light)
              : Brightness.dark,
        ),
        child: Container(
          padding: EdgeInsets.only(top: topPadding),
          decoration: BoxDecoration(
            color: toolbarChrome,
            border: resolvedOpacity > 0.02
                ? Border(bottom: _profileSeparatorSide(border))
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
                    height: _compactToolbarHeight(context),
                    child: Row(
                      children: [
                        SizedBox(
                          width: sideSlotWidth,
                          child: Align(
                            alignment: Alignment.centerLeft,
                            child:
                                (widget.mode == ProfileMode.other ||
                                    widget.onBack != null)
                                ? ProfileIosIconButton(
                                    icon: CupertinoIcons.back,
                                    onPressed:
                                        widget.onBack ?? () => context.pop(),
                                    backgroundColor: actionBackground,
                                    foregroundColor: compactForeground,
                                  )
                                : const SizedBox.shrink(),
                          ),
                        ),
                        Expanded(
                          child: Opacity(
                            opacity: opacity,
                            child: LayoutBuilder(
                              builder: (context, constraints) {
                                return Center(
                                  child: ConstrainedBox(
                                    constraints: BoxConstraints(
                                      maxWidth: constraints.maxWidth,
                                    ),
                                    child: Row(
                                      key: const ValueKey<String>(
                                        'profile-shell-compact-identity',
                                      ),
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        CircleAvatar(
                                          radius: AppSpacing.avatarUserSm / 2,
                                          backgroundColor: actionBackground,
                                          backgroundImage:
                                              avatarUrl != null &&
                                                  avatarUrl.isNotEmpty
                                              ? NetworkImage(avatarUrl)
                                              : null,
                                          child:
                                              avatarUrl == null ||
                                                  avatarUrl.isEmpty
                                              ? Icon(
                                                  CupertinoIcons
                                                      .person_crop_circle_fill,
                                                  size: AppSpacing.iconMedium,
                                                  color: compactForeground,
                                                )
                                              : null,
                                        ),
                                        SizedBox(width: AppSpacing.containerSm),
                                        Flexible(
                                          child: Text(
                                            displayName,
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                            textAlign: TextAlign.center,
                                            style: TextStyle(
                                              fontSize:
                                                  AppTypography.iosNavTitle,
                                              fontWeight: AppTypography.medium,
                                              color: compactForeground,
                                              letterSpacing: -0.24,
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                );
                              },
                            ),
                          ),
                        ),
                        SizedBox(
                          width: trailingSlotWidth,
                          child: Align(
                            alignment: Alignment.centerRight,
                            child: widget.mode == ProfileMode.mine
                                ? Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      const GlobalTopActions(
                                        showQuickAction: false,
                                        surface: AppChromeSurface.overlay,
                                      ),
                                      SizedBox(width: AppSpacing.intraGroupXs),
                                      ProfileIosIconButton(
                                        icon: AppNavigationSemanticConstants
                                            .settingsActionIcon,
                                        onPressed: () => context.push(
                                          AppRoutePaths.settings,
                                        ),
                                        backgroundColor: actionBackground,
                                        foregroundColor: compactForeground,
                                      ),
                                    ],
                                  )
                                : ProfileIosIconButton(
                                    icon: CupertinoIcons.ellipsis,
                                    onPressed: () => _showMoreOptions(context),
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

  Widget _buildPrimaryTabBarSurface({
    required Color bg,
    required Color border,
    required bool pinned,
    double opacity = 1.0,
  }) {
    final tabs = UserProfileUIConfig.profileTabs
        .map(
          (tab) => TabItem(id: tab.id, label: _profileObjectTabLabel(tab.id)),
        )
        .toList(growable: false);
    final surface = Container(
      key: pinned
          ? const ValueKey<String>('profile-shell-primary-tabs-pinned')
          : const ValueKey<String>('profile-shell-primary-tabs-inline'),
      clipBehavior: pinned ? Clip.none : Clip.antiAlias,
      decoration: BoxDecoration(
        color: bg,
        border: Border(bottom: _profileSeparatorSide(border, alpha: 0.1)),
      ),
      child: SizedBox(
        height: _primaryTabBarHeight(context),
        child: CenteredScrollableTabBar(
          tabs: tabs,
          activeTab: _activeTabId,
          onTabChange: _onPrimaryTabChange,
          onHorizontalDragEnd: _handleTabSwipeDragEnd,
          transparentBackground: true,
        ),
      ),
    );
    if (pinned) {
      return surface;
    }
    return IgnorePointer(
      ignoring: opacity <= 0.02,
      child: Opacity(opacity: opacity, child: surface),
    );
  }

  String _profileObjectTabLabel(String tabId) {
    return switch (tabId) {
      'creations' => '作品',
      'circles' => '圈子',
      'interaction' => '互动',
      'lifestyle' => '看点',
      _ => UITextConstants.contentLabelForKey(tabId),
    };
  }

  Widget _buildInlineTabContent(BuildContext context, bool isDark) {
    final content = switch (_activeTabId) {
      'circles' => ProfileCirclesTab(
        mode: widget.mode,
        userId: widget.userId,
        isDark: isDark,
        inlineScroll: true,
      ),
      'interaction' => ProfileInteractionTab(
        mode: widget.mode,
        userId: widget.userId,
        isDark: isDark,
        inlineScroll: true,
        secondaryTabBarKey: _interactionSecondaryTabKey,
        onSecondaryHorizontalDragEnd: _handleTabSwipeDragEnd,
      ),
      'lifestyle' => ProfileLifestyleTab(
        mode: widget.mode,
        userId: widget.userId,
        isDark: isDark,
        inlineScroll: true,
      ),
      _ => ProfileWorksTab(
        mode: widget.mode,
        userId: widget.userId,
        isDark: isDark,
        inlineScroll: true,
        secondaryTabBarKey: _worksSecondaryTabKey,
        onSecondaryHorizontalDragEnd: _handleTabSwipeDragEnd,
      ),
    };
    return KeyedSubtree(
      key: ValueKey<String>('profile-tab-body-$_activeTabId'),
      child: content,
    );
  }

  Future<void> _showMoreOptions(BuildContext context) async {
    final action = await showAppActionSheet<_ProfileMoreAction>(
      context,
      title: '更多操作',
      sections: const [
        AppActionSheetSection<_ProfileMoreAction>(
          items: [
            AppActionSheetItem<_ProfileMoreAction>(
              value: _ProfileMoreAction.share,
              label: '分享',
              icon: CupertinoIcons.share,
            ),
          ],
        ),
        AppActionSheetSection<_ProfileMoreAction>(
          items: [
            AppActionSheetItem<_ProfileMoreAction>(
              value: _ProfileMoreAction.block,
              label: '拉黑',
              icon: CupertinoIcons.person_crop_circle_badge_xmark,
            ),
            AppActionSheetItem<_ProfileMoreAction>(
              value: _ProfileMoreAction.report,
              label: '举报',
              icon: CupertinoIcons.flag,
              isDestructive: true,
            ),
          ],
        ),
      ],
    );
    if (!context.mounted || action == null) return;
    switch (action) {
      case _ProfileMoreAction.share:
        AppToast.show(context, '分享能力待接入');
      case _ProfileMoreAction.block:
        AppToast.show(context, '拉黑能力待接入');
      case _ProfileMoreAction.report:
        AppToast.show(context, '举报能力待接入');
    }
  }
}
