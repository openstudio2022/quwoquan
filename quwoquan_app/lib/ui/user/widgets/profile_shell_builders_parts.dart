part of 'profile_shell.dart';

extension _ProfileShellBuilders on _ProfileShellState {
  /// 交集卡「我与TA的交集」：与我的主页同源预览卡。
  /// 仅 other 模式展示；无交集时展示稳定空态，避免首屏 IA 断层。
  Widget _buildIntersectionCard() {
    if (widget.mode != ProfileMode.other) {
      return const SizedBox.shrink();
    }
    return OtherProfileIntersectionCard(userId: widget.userId);
  }

  /// 打动摘要模块（他人主页 / 我的主页双视角）。
  ///
  /// async 三态：loading / error 不占位；data 由 [AuthorImpactCard] 决定
  /// （other 无事实收起，mine 空态展示鼓励发布文案）。
  Widget _buildAuthorImpactCard(bool isDark) {
    final impact = ref.watch(authorImpactProvider(widget.userId));
    return impact.when(
      data: (summary) => AuthorImpactCard(
        summary: summary,
        isDark: isDark,
        isMine: widget.mode == ProfileMode.mine,
      ),
      loading: () => const SizedBox.shrink(),
      error: (_, _) => const SizedBox.shrink(),
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

  /// 私信：创建或复用正式 1v1 会话后再进入聊天详情。
  Future<void> _gatedOpenMessage(
    BuildContext context,
    ProfileNotifier notifier,
  ) async {
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      try {
        final created = await notifier.openOrCreateDirectConversation();
        if (!context.mounted || created.conversationId.isEmpty) {
          return;
        }
        context.push(AppRoutePaths.chatDetail(id: created.conversationId));
      } catch (error) {
        if (!context.mounted) {
          return;
        }
        final resolved = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        );
        await AppActionErrorFeedback.show(context, semantic: resolved);
      }
      return;
    }
    ref
        .read(authContinuationProvider.notifier)
        .set(OpenDirectConversationContinuation(subAccountId: widget.userId));
    await requireLogin(
      ref,
      context,
      AuthGateReason.sendMessage,
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

  void maybeResumeDirectMessageContinuation(
    BuildContext context,
    ProfileNotifier notifier,
  ) {
    final direct = ref
        .read(authContinuationProvider.notifier)
        .take<OpenDirectConversationContinuation>();
    if (direct != null) {
      if (direct.subAccountId != widget.userId) {
        ref.read(authContinuationProvider.notifier).set(direct);
      } else {
        unawaited(_gatedOpenMessage(context, notifier));
      }
    }
  }

  Widget _buildSummarySection(
    BuildContext context, {
    required bool isDark,
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
    final isMine = widget.mode == ProfileMode.mine;
    final displayCapability = state.displayCapability;
    final resolvedAvatarUrl = isLocalFileImageSource(avatarUrl)
        ? (avatarUrl ?? '')
        : resolveAvatarImageUrl(avatarUrl);
    final effectiveIdentityTags =
        state.profile?.identityTags ?? const <String>[];
    final hasIdentityTags = effectiveIdentityTags
        .map((tag) => tag.trim())
        .any((tag) => tag.isNotEmpty);
    final hasAvatar = resolvedAvatarUrl.isNotEmpty;
    final hasBio = (bio ?? '').trim().isNotEmpty;
    final isProfileComplete = hasIdentityTags && hasAvatar && hasBio;
    final summaryShadow = isDark
        ? AppColors.black.withValues(alpha: 0.10)
        : AppColors.black.withValues(alpha: 0.025);
    return DecoratedBox(
      decoration: const BoxDecoration(color: AppColors.transparent),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            key: const ValueKey<String>('profile-shell-profile-card'),
            decoration: BoxDecoration(
              color: summarySurface,
              borderRadius: BorderRadius.circular(
                _ProfileShellState._profileCardRadius,
              ),
              border: Border.all(
                color: summaryBorder.withValues(alpha: isDark ? 0.75 : 0.55),
                width: AppSpacing.hairline,
              ),
              boxShadow: <BoxShadow>[
                BoxShadow(
                  color: summaryShadow,
                  blurRadius: AppSpacing.fourteen,
                  offset: const Offset(0, 6),
                ),
              ],
            ),
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerMd,
                0,
                AppSpacing.containerMd,
                AppSpacing.containerMd,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  ProfileHeader(
                    isDark: isDark,
                    avatarUrl: avatarUrl,
                    displayName: displayName,
                    identityTags: effectiveIdentityTags,
                    verified: state.profile?.verified ?? false,
                    onEdit: () => context.push(AppRoutePaths.profileEdit),
                    showQrCode: isMine,
                    onQrCode: () => context.push(AppRoutePaths.myQrCode),
                    showUploadAvatarPrompt: isMine && !hasAvatar,
                    showIdentityTagPrompt: isMine && !hasIdentityTags,
                  ),
                  if (widget.mode == ProfileMode.mine ||
                      (bio != null && bio.trim().isNotEmpty)) ...[
                    SizedBox(height: AppSpacing.interGroupSm),
                    ProfileSloganCard(
                      isDark: isDark,
                      bio: bio,
                      showEmptyPrompt: widget.mode == ProfileMode.mine,
                      onTap: widget.mode == ProfileMode.mine
                          ? () => context.push(AppRoutePaths.profileEdit)
                          : null,
                    ),
                  ],
                  if (widget.mode == ProfileMode.mine &&
                      (state.profile?.profileCompleteness ?? 100) < 100) ...[
                    SizedBox(height: AppSpacing.intraGroupMd),
                    ProfileCompletenessCard(
                      percent: state.profile?.profileCompleteness ?? 100,
                      missingItems:
                          state.profile?.profileCompletenessMissingItems ??
                          const <String>[],
                      onTap: () => context.push(AppRoutePaths.profileEdit),
                    ),
                  ],
                  SizedBox(height: AppSpacing.interGroupSm),
                  ProfileStatsRow(
                    isDark: isDark,
                    profile: state.profile,
                    onStatTap: (type) =>
                        _handleProfileStatTap(context, type, state),
                  ),
                  if (widget.mode == ProfileMode.mine) ...[
                    SizedBox(height: AppSpacing.interGroupSm),
                    ProfileActionBar(
                      mode: widget.mode,
                      isDark: isDark,
                      isFollowing: state.isFollowing,
                      profileComplete: isProfileComplete,
                      onManagePersonas:
                          ref.watch(personaManagementFeatureFlagProvider)
                          ? () => context.push(AppRoutePaths.profilePersonas)
                          : null,
                      onEditProfile: () =>
                          context.push(AppRoutePaths.profileEdit),
                    ),
                  ] else ...[
                    SizedBox(height: AppSpacing.interGroupSm),
                    ProfileActionBar(
                      mode: widget.mode,
                      isDark: isDark,
                      isFollowing:
                          displayCapability?.viewerFollowsTarget ??
                          state.isFollowing,
                      capability: displayCapability,
                      onEditProfile: () =>
                          context.push(AppRoutePaths.profileEdit),
                      onShareProfile: () => AppToast.show(
                        context,
                        UITextConstants.shareComingSoon,
                      ),
                      onFollow: () => _gatedToggleFollow(context, notifier),
                      onMessage: () =>
                          unawaited(_gatedOpenMessage(context, notifier)),
                    ),
                  ],
                ],
              ),
            ),
          ),
          if (widget.mode == ProfileMode.mine) ...[
            MyIntersectionInboxCard(isDark: isDark),
          ] else ...[
            _buildIntersectionCard(),
          ],
          _buildAuthorImpactCard(isDark),
          SizedBox(height: AppSpacing.interGroupSm),
        ],
      ),
    );
  }

  /// 「添加封面」按钮顶部锚点：toolbar 底部，避免遮住顶部工具栏。
  double _coverPromptTop(BuildContext context) => _toolbarExtent(context);

  /// 「添加封面」按钮可用高度：非拉伸态封面可见区（base 封面高 − toolbar 区），
  /// 不含下拉拉伸增量，确保拉伸时按钮锚点不下沉。
  double _coverPromptVisibleHeight(BuildContext context) {
    final baseHeight =
        MediaQuery.sizeOf(context).height *
        AppSpacing.adaptiveProfileHeaderBaseHeightRatio(context);
    final visible = baseHeight - _toolbarExtent(context);
    return visible > 0 ? visible : 0.0;
  }

  Widget _buildBackgroundLayer(
    BuildContext context, {
    required String? backgroundUrl,
    required Color backgroundColor,
    required bool showCoverPrompt,
    required VoidCallback onCoverPrompt,
  }) {
    final isDark = ref.watch(isDarkProvider);
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Positioned(
          left: 0,
          right: 0,
          top: 0,
          bottom: -_ProfileShellState._profileSurfaceBridge,
          child: backgroundUrl != null && backgroundUrl.isNotEmpty
              ? (isLocalFileImageSource(backgroundUrl)
                    // 本地选取（未上传）封面经 FileImage 直显（alpha 保存后即时回显）。
                    ? AppMediaImage(
                        imageSource: backgroundUrl,
                        fit: BoxFit.cover,
                        errorWidget: _buildProfileBackgroundFallback(
                          backgroundColor: backgroundColor,
                        ),
                      )
                    : AppCachedNetworkImage(
                        imageUrl: backgroundUrl,
                        fit: BoxFit.cover,
                        errorWidget: _buildProfileBackgroundFallback(
                          backgroundColor: backgroundColor,
                        ),
                      ))
              : _buildProfileBackgroundFallback(
                  backgroundColor: backgroundColor,
                ),
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
        if (showCoverPrompt)
          // 「添加封面」按钮锚定在「非拉伸态封面可见区」的垂直居中点：
          //  - 顶部从 toolbar 底部起算，避免遮住顶部工具栏；
          //  - 高度只取 base 封面高度（不含下拉拉伸增量），故下拉拉伸时按钮不下沉；
          //  - 背景层整体随内容上卷（top = -scrollOffset），故上滑时按钮随封面上移。
          Positioned(
            left: 0,
            right: 0,
            top: _coverPromptTop(context),
            height: _coverPromptVisibleHeight(context),
            child: Align(
              alignment: Alignment.center,
              child: CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                onPressed: onCoverPrompt,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColors.iosSystemBackground(
                      context,
                    ).withValues(alpha: isDark ? 0.22 : 0.82),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.radiusNinetyNine,
                    ),
                    border: Border.all(
                      color: AppColors.iosSeparator(
                        context,
                      ).withValues(alpha: isDark ? 0.24 : 0.18),
                      width: AppSpacing.hairline,
                    ),
                  ),
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerMd,
                      vertical: AppSpacing.intraGroupSm,
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        Icon(
                          CupertinoIcons.photo,
                          size: AppSpacing.iconSmall,
                          color: AppColors.iosSecondaryLabel(context),
                        ),
                        SizedBox(width: AppSpacing.intraGroupXs),
                        Text(
                          UITextConstants.profileUploadCover,
                          style: TextStyle(
                            fontSize: AppTypography.iosFootnote,
                            color: AppColors.iosSecondaryLabel(context),
                            fontWeight: AppTypography.regular,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildProfileBackgroundFallback({required Color backgroundColor}) {
    final isDark = ref.watch(isDarkProvider);
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: <Color>[
            isDark
                ? backgroundColor.withValues(alpha: 0.86)
                : AppColors.brandBlue100.withValues(alpha: 0.96),
            isDark
                ? AppColors.iosProfileSurface(context).withValues(alpha: 0.76)
                : AppColors.brandBlue50.withValues(alpha: 0.92),
            backgroundColor.withValues(alpha: isDark ? 0.96 : 0.88),
          ],
        ),
      ),
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
    required bool contentForegroundIsDark,
  }) {
    final topPadding = AppSpacing.appChromeTopSafeInset(
      MediaQuery.viewPaddingOf(context).top,
      context,
    );
    final hasLeadingAction =
        widget.mode == ProfileMode.other || widget.onBack != null;
    final sideSlotWidth =
        AppSpacing.appChromeActionButtonSize + AppSpacing.containerXs;
    final leadingSlotWidth = hasLeadingAction ? sideSlotWidth : 0.0;
    final trailingSlotWidth = widget.mode == ProfileMode.mine
        ? AppSpacing.appChromeActionButtonSize * 4 +
              AppSpacing.intraGroupXs * 3 +
              AppSpacing.containerXs
        : sideSlotWidth;
    final resolvedOpacity = backgroundOpacity.clamp(0.0, 1.0);
    final chromeVisible = resolvedOpacity > 0.12;
    // chrome 不透明：随主题（浅色=深字，深色=浅字）。chrome 透明（贴在封面上）：
    // 随封面亮度自适应，默认浅色封面下不再用不可见的白色前景。
    final compactForeground = chromeVisible
        ? fg
        : (contentForegroundIsDark
              ? AppColors.iosLabel(context)
              : CupertinoColors.white);
    final toolbarChrome = Color.lerp(
      AppColors.transparent,
      AppColors.iosSystemBackground(context),
      resolvedOpacity,
    )!;
    final toolbarShadowColor = AppColors.black.withValues(
      alpha: isDark ? 0.18 : 0.07,
    );
    final actionBackground =
        AppNavigationSemanticConstants.chromeActionBackground(
          surface: AppChromeSurface.overlay,
        );
    // 状态栏图标深浅与 toolbar 前景同源：chrome 不透明随主题，透明随封面亮度。
    final useDarkStatusIcons = chromeVisible
        ? !isDark
        : contentForegroundIsDark;
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: AnnotatedRegion<SystemUiOverlayStyle>(
        value: SystemUiOverlayStyle(
          statusBarColor: AppColors.transparent,
          statusBarIconBrightness: useDarkStatusIcons
              ? Brightness.dark
              : Brightness.light,
          statusBarBrightness: useDarkStatusIcons
              ? Brightness.light
              : Brightness.dark,
        ),
        child: Container(
          padding: EdgeInsets.only(top: topPadding),
          decoration: BoxDecoration(
            color: toolbarChrome,
            border: resolvedOpacity > 0.02
                ? Border(bottom: _profileSeparatorSide(border))
                : null,
            boxShadow: resolvedOpacity > 0.18
                ? <BoxShadow>[
                    BoxShadow(
                      color: toolbarShadowColor,
                      blurRadius: AppSpacing.containerSm,
                      offset: const Offset(0, AppSpacing.one),
                    ),
                  ]
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
                        if (hasLeadingAction)
                          SizedBox(
                            width: leadingSlotWidth,
                            child: Align(
                              alignment: Alignment.centerLeft,
                              child: ProfileIosIconButton(
                                icon: CupertinoIcons.back,
                                onPressed: widget.onBack ?? () => context.pop(),
                                backgroundColor: actionBackground,
                                foregroundColor: compactForeground,
                              ),
                            ),
                          ),
                        Expanded(
                          child: Opacity(
                            opacity: opacity,
                            child: LayoutBuilder(
                              builder: (context, constraints) {
                                return Align(
                                  alignment: Alignment.centerLeft,
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
                                        ClipOval(
                                          child: SizedBox(
                                            width: AppSpacing.avatarUserSm,
                                            height: AppSpacing.avatarUserSm,
                                            child:
                                                avatarUrl != null &&
                                                    avatarUrl.isNotEmpty
                                                ? (isLocalFileImageSource(
                                                        avatarUrl,
                                                      )
                                                      ? AppMediaImage(
                                                          key:
                                                              const ValueKey<
                                                                String
                                                              >(
                                                                'profile-shell-compact-avatar-image',
                                                              ),
                                                          imageSource:
                                                              avatarUrl,
                                                          fit: BoxFit.cover,
                                                          errorWidget: ColoredBox(
                                                            color:
                                                                actionBackground,
                                                            child: Icon(
                                                              CupertinoIcons
                                                                  .person_crop_circle_fill,
                                                              size: AppSpacing
                                                                  .iconMedium,
                                                              color:
                                                                  compactForeground,
                                                            ),
                                                          ),
                                                        )
                                                      : AppCachedNetworkImage(
                                                          key:
                                                              const ValueKey<
                                                                String
                                                              >(
                                                                'profile-shell-compact-avatar-image',
                                                              ),
                                                          imageUrl: avatarUrl,
                                                          fit: BoxFit.cover,
                                                          errorWidget: ColoredBox(
                                                            color:
                                                                actionBackground,
                                                            child: Icon(
                                                              CupertinoIcons
                                                                  .person_crop_circle_fill,
                                                              size: AppSpacing
                                                                  .iconMedium,
                                                              color:
                                                                  compactForeground,
                                                            ),
                                                          ),
                                                        ))
                                                : ColoredBox(
                                                    color: actionBackground,
                                                    child: Icon(
                                                      CupertinoIcons
                                                          .person_crop_circle_fill,
                                                      size:
                                                          AppSpacing.iconMedium,
                                                      color: compactForeground,
                                                    ),
                                                  ),
                                          ),
                                        ),
                                        SizedBox(width: AppSpacing.containerSm),
                                        Flexible(
                                          child: Text(
                                            displayName,
                                            maxLines: 1,
                                            overflow: TextOverflow.ellipsis,
                                            textAlign: TextAlign.start,
                                            style: TextStyle(
                                              fontSize:
                                                  AppTypography.iosNavTitle,
                                              fontWeight: AppTypography.regular,
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
                                      GlobalTopActions(
                                        showQuickAction: false,
                                        surface: AppChromeSurface.overlay,
                                        foregroundColor: compactForeground,
                                      ),
                                      SizedBox(width: AppSpacing.intraGroupXs),
                                      ProfileIosIconButton(
                                        icon: CupertinoIcons
                                            .arrowshape_turn_up_right,
                                        onPressed: () => AppToast.show(
                                          context,
                                          UITextConstants.shareComingSoon,
                                        ),
                                        backgroundColor: actionBackground,
                                        foregroundColor: compactForeground,
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
    required bool pinned,
    double opacity = 1.0,
  }) {
    final tabDivider = SettingsSemanticConstants.conversationSheetDividerColor(
      CupertinoTheme.brightnessOf(context) == Brightness.dark,
    );
    final tabs = UserProfileUIConfig.profileTabs
        .where((tab) => tab.visibleInMode(widget.mode.name))
        .map(
          (tab) => TabItem(id: tab.id, label: _profileObjectTabLabel(tab.id)),
        )
        .toList(growable: false);
    final state = ref.watch(profileNotifierProvider(widget.userId));
    final showInteractionDirectionSwitch =
        widget.mode == ProfileMode.mine && _activeTabId == 'interaction';
    final directionSwitch = showInteractionDirectionSwitch
        ? ProfileInteractionDirectionSwitch(
            isDark: CupertinoTheme.brightnessOf(context) == Brightness.dark,
            current: state.interactionDirection,
            onSelected: (direction) {
              ref
                  .read(profileNotifierProvider(widget.userId).notifier)
                  .setInteractionDirection(direction);
            },
          )
        : null;
    final surface = Container(
      key: pinned
          ? const ValueKey<String>('profile-shell-primary-tabs-pinned')
          : const ValueKey<String>('profile-shell-primary-tabs-inline'),
      clipBehavior: pinned ? Clip.none : Clip.antiAlias,
      decoration: BoxDecoration(
        color: bg,
        border: pinned ? Border(top: _profileSeparatorSide(tabDivider)) : null,
      ),
      child: SizedBox(
        height: _primaryTabBarHeight(context),
        child: Stack(
          alignment: Alignment.center,
          children: <Widget>[
            CenteredScrollableTabBar(
              tabs: tabs,
              activeTab: _activeTabId,
              onTabChange: _onPrimaryTabChange,
              onHorizontalDragEnd: _handleTabSwipeDragEnd,
              transparentBackground: true,
              selectedLabelColor: AppColors.iosAccent(context),
            ),
            if (directionSwitch != null)
              PositionedDirectional(
                end: AppSpacing.containerMd,
                child: directionSwitch,
              ),
          ],
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
    return profileTabLabelForId(tabId);
  }

  void _handleProfileStatTap(
    BuildContext context,
    String type,
    ProfileState state,
  ) {
    final subjectUserId = state.profile?.subAccountId.trim().isNotEmpty == true
        ? state.profile!.subAccountId
        : widget.userId;
    switch (type) {
      case 'fans':
      case 'following':
      case 'circles':
        context.push(
          AppRoutePaths.profileStats(type: type, userId: subjectUserId),
        );
      case 'likes':
        ref
            .read(profileNotifierProvider(widget.userId).notifier)
            .setInteractionSubTab(InteractionSubTab.likes);
        _onPrimaryTabChange('interaction');
      default:
        break;
    }
  }

  /// 首屏聚合失败错误态：结构化 [UiErrorSemantic] + 重试（重新 loadProfile）。
  /// 仅在无可展示档案时渲染，保持壳层几何稳定、错误对用户可见。
  Widget _buildFirstScreenError(BuildContext context, ProfileState state) {
    return AppPageErrorState(
      semantic: _profileBlockingErrorSemantic(context, state.rawError!),
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await ref
              .read(profileNotifierProvider(widget.userId).notifier)
              .loadProfile();
        }
      },
    );
  }

  Widget _buildInlineTabContent(BuildContext context, bool isDark) {
    final content = switch (_activeTabId) {
      'interaction' => ProfileInteractionTab(
        mode: widget.mode,
        userId: widget.userId,
        isDark: isDark,
        inlineScroll: true,
        secondaryTabBarKey: _interactionSecondaryTabKey,
        onSecondaryHorizontalDragEnd: _handleTabSwipeDragEnd,
      ),
      // 足迹=浏览历史，隐私门控仅本人主页可见（ui_config modes: [mine]）；body 复用既有
      // ProfileFootprintTab（myFootprintListProvider，scope 限 mine），不新建第二取数路径。
      'footprint' => ProfileFootprintTab(
        isDark: isDark,
        onSecondaryHorizontalDragEnd: _handleTabSwipeDragEnd,
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
    final body = KeyedSubtree(
      key: ValueKey<String>('profile-tab-body-$_activeTabId'),
      child: content,
    );
    final fallbackError = ref
        .watch(profileNotifierProvider(widget.userId))
        .rawError;
    if (fallbackError == null) {
      return body;
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        AppTransientErrorNotice(
          semantic: _profileCacheFallbackSemantic(context, fallbackError),
        ),
        body,
      ],
    );
  }

  UiErrorSemantic _profileBlockingErrorSemantic(
    BuildContext context,
    Object error,
  ) {
    final base = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
    return UiErrorSemantic(
      category: base.category,
      scope: base.scope,
      title: UITextConstants.homepageLoadFailedTitle,
      message: UITextConstants.pageLoadFailedMessage,
      secondaryMessage: base.secondaryMessage,
      primaryAction: base.primaryAction,
      secondaryAction: base.secondaryAction,
      dismissible: base.dismissible,
      sourceCode: base.sourceCode,
      failureKind: base.failureKind,
      copyKey: 'homepageLoadFailedTitle',
      recoveryAction: base.recoveryAction,
      presentation: base.presentation,
      tone: base.tone,
    );
  }

  UiErrorSemantic _profileCacheFallbackSemantic(
    BuildContext context,
    Object error,
  ) {
    final base = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.backgroundAction,
      scope: UiErrorScope.section,
      allowRetry: false,
      presentation: UiErrorPresentation.transientNotice,
    );
    return UiErrorSemantic(
      category: base.category,
      scope: base.scope,
      title: UITextConstants.homepageLoadFailedTitle,
      message: UITextConstants.profileCacheFallback,
      secondaryMessage: base.secondaryMessage,
      primaryAction: base.primaryAction,
      secondaryAction: base.secondaryAction,
      dismissible: base.dismissible,
      sourceCode: base.sourceCode,
      failureKind: base.failureKind,
      copyKey: 'profileCacheFallback',
      recoveryAction: base.recoveryAction,
      presentation: base.presentation,
      tone: UiErrorTone.caution,
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
              label: UITextConstants.share,
              icon: CupertinoIcons.arrowshape_turn_up_right,
            ),
          ],
        ),
        AppActionSheetSection<_ProfileMoreAction>(
          items: [
            AppActionSheetItem<_ProfileMoreAction>(
              value: _ProfileMoreAction.block,
              label: UITextConstants.profileBlockUser,
              icon: CupertinoIcons.person_crop_circle_badge_xmark,
            ),
            AppActionSheetItem<_ProfileMoreAction>(
              value: _ProfileMoreAction.report,
              label: UITextConstants.report,
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
        AppToast.show(context, UITextConstants.shareComingSoon);
      case _ProfileMoreAction.block:
        _gatedBlockUser(context);
      case _ProfileMoreAction.report:
        _gatedReportUser(context);
    }
  }

  /// 拉黑用户：登录门保障 + 二次确认，经 [blockRepositoryProvider] 走 Remote。
  void _gatedBlockUser(BuildContext context) {
    runWhenLoggedIn(ref, context, AuthGateReason.report, () async {
      final confirmed = await showAppActionSheet<bool>(
        context,
        title: UITextConstants.profileBlockConfirmTitle,
        message: UITextConstants.profileBlockConfirmMessage,
        sections: const [
          AppActionSheetSection<bool>(
            items: [
              AppActionSheetItem<bool>(
                value: true,
                label: UITextConstants.profileBlockUser,
                icon: CupertinoIcons.person_crop_circle_badge_xmark,
                isDestructive: true,
              ),
            ],
          ),
        ],
      );
      if (confirmed != true || !context.mounted) return;
      try {
        await ref.read(blockRepositoryProvider).blockUser(widget.userId);
        if (context.mounted) {
          AppToast.show(context, UITextConstants.profileBlockSuccess);
        }
      } catch (error) {
        if (!context.mounted) {
          return;
        }
        final resolved = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        );
        await AppActionErrorFeedback.show(context, semantic: resolved);
      }
    });
  }
}
