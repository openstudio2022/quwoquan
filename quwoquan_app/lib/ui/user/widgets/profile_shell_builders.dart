part of 'profile_shell.dart';

extension _ProfileShellBuilders on _ProfileShellState {
  /// 交集卡「你们的连接」：tag-service shared-tags 对象对直打（当前用户 × 被看用户）。
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
    // 统一 async 三态（loading 骨架 / data 卡 / error 收起）+ §7.3 旅程高亮。
    // 证据组点击归因（B3）由 ObjectIntersectionSection 内部统一上报（三主页一致）。
    return ObjectIntersectionSection(
      query: query,
      title: UITextConstants.profileMutualIntersectionTitle,
      isDark: isDark,
      bottomPadding: AppSpacing.md,
    );
  }

  /// 影响力摘要模块（他人主页 / 我的主页双视角）。
  ///
  /// async 三态：loading / error 不占位；data 由 [AuthorImpactCard] 决定
  /// （other 无事实收起，mine 空态展示鼓励发布文案）。
  Widget _buildAuthorImpactCard(bool isDark) {
    final impact = ref.watch(authorImpactProvider(widget.userId));
    return impact.when(
      data: (summary) => Padding(
        padding: EdgeInsets.only(bottom: AppSpacing.md),
        child: AuthorImpactCard(
          summary: summary,
          isDark: isDark,
          isMine: widget.mode == ProfileMode.mine,
        ),
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
              identityTags: state.profile?.identityTags ?? const <String>[],
            ),
            SizedBox(height: AppSpacing.md),
            ProfileActionBar(
              mode: widget.mode,
              isDark: isDark,
              isFollowing:
                  displayCapability?.viewerFollowsTarget ?? state.isFollowing,
              capability: displayCapability,
              onEditProfile: () => context.push(AppRoutePaths.profileEdit),
              onShareProfile: () =>
                  AppToast.show(context, UITextConstants.shareComingSoon),
              onFollow: () => _gatedToggleFollow(context, notifier),
              onMessage: () => unawaited(_gatedOpenMessage(context, notifier)),
            ),
            SizedBox(height: AppSpacing.md),
            if (widget.mode == ProfileMode.mine) ...[
              MyIntersectionInboxCard(isDark: isDark),
              SizedBox(height: AppSpacing.md),
            ] else ...[
              _buildIntersectionCard(isDark),
            ],
            _buildAuthorImpactCard(isDark),
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
              ? AppCachedNetworkImage(
                  imageUrl: backgroundUrl,
                  fit: BoxFit.cover,
                  errorWidget: ColoredBox(color: backgroundColor),
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
                                                        CupertinoIcons
                                                            .person_crop_circle_fill,
                                                        size: AppSpacing
                                                            .iconMedium,
                                                        color:
                                                            compactForeground,
                                                      ),
                                                    ),
                                                  )
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
    return profileTabLabelForId(tabId);
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
              label: UITextConstants.share,
              icon: CupertinoIcons.share,
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

  /// 举报用户：登录门保障 + 原因选择，经 [reportRepositoryProvider] 走 Remote。
  void _gatedReportUser(BuildContext context) {
    runWhenLoggedIn(ref, context, AuthGateReason.report, () async {
      final reason = await showAppActionSheet<_ProfileReportReason>(
        context,
        title: UITextConstants.profileReportReasonTitle,
        sections: [
          AppActionSheetSection<_ProfileReportReason>(
            items: _ProfileReportReason.values
                .map(
                  (r) => AppActionSheetItem<_ProfileReportReason>(
                    value: r,
                    label: r.label,
                  ),
                )
                .toList(growable: false),
          ),
        ],
      );
      if (reason == null || !context.mounted) return;
      try {
        await ref
            .read(reportRepositoryProvider)
            .createReport(
              targetId: widget.userId,
              targetType: 'user',
              reason: reason.code,
            );
        if (context.mounted) {
          AppToast.show(context, UITextConstants.commentReportSubmitted);
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
