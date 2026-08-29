part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerEngagementActions on _WorksImmersiveViewerState {
  void _openCommentFor(String postId) {
    _setMountedState(() {
      _commentSplitPostId = postId;
      _invalidateVideoViewport(resetDurationWindow: false);
    });
  }

  Widget _buildCommentSplitContent(
    ContentPostViewData post, {
    required bool enableArticlePageCurl,
  }) {
    return ColoredBox(
      color: AppColors.worksBackground,
      child: _buildPostCanvas(
        post,
        enableArticlePageCurl: enableArticlePageCurl,
        isVisible: true,
        videoViewportEpoch: _videoViewportEpoch,
      ),
    );
  }

  ContentPostViewData? _postById(
    List<ContentPostViewData> posts,
    String postId,
  ) {
    for (final post in posts) {
      if (post.id == postId) {
        return post;
      }
    }
    return null;
  }

  void _sharePost(
    BuildContext ctx,
    ContentPostViewData post, {
    required bool enableIdentityTemplate,
  }) {
    runWhenLoggedIn(ref, context, AuthGateReason.share, () {
      final raw = _rawPostById(post.id);
      final visibility =
          raw?[ContentMediaPostProjectionKeys.visibility]?.toString() ??
          'public';
      WorksViewerContentActionsComposition.showShareSheet(
        ctx,
        surfaceView: ContentSurfaceViewMapper.fromDto(post, wire: raw),
        enableIdentityTemplate: enableIdentityTemplate,
        visibility: visibility,
        circlePostPlacementWriter: ref.read(
          workBrowserCirclePostPlacementWriterProvider,
        ),
        circleMembershipQuery: ref.read(
          workBrowserCircleMembershipQueryProvider,
        ),
        outboundShareWriter: ref.read(
          workBrowserContentOutboundShareWriterProvider,
        ),
        onActionCompleted: (actionId) => _recordShare(post.id, actionId),
      );
    });
  }

  Future<void> _copyLink(
    BuildContext context,
    ContentPostViewData post, {
    required bool enableIdentityTemplate,
  }) async {
    final raw = _rawPostById(post.id);
    final result = await WorksViewerContentActionsComposition.copyLink(
      context,
      surfaceView: ContentSurfaceViewMapper.fromDto(post, wire: raw),
      enableIdentityTemplate: enableIdentityTemplate,
      visibility:
          raw?[ContentMediaPostProjectionKeys.visibility]?.toString() ??
          'public',
    );
    if (result.success) {
      await _recordShare(post.id, result.actionId);
    }
  }

  Future<void> _recordShare(String postId, String actionId) async {
    ref
        .read(contentBehaviorTrackerProvider)
        .trackShare(postId, tags: <String>[actionId]);
  }

  MediaViewerResult _buildResult() {
    final posts = _buildFeed();
    final postsById = <String, ContentPostViewData>{
      for (final post in posts) post.id: post,
    };
    final scopePostIds =
        widget.initialInteractionSnapshot.effectiveScopePostIds;
    final scopeProfileIds =
        widget.initialInteractionSnapshot.effectiveScopeProfileIds;
    final postInteractionState = ref.read(postInteractionStateProvider);
    final relationshipState = ref.read(userRelationshipStateProvider);
    return MediaViewerResult(
      scopePostIds: Set<String>.from(scopePostIds),
      scopeProfileIds: Set<String>.from(scopeProfileIds),
      followingUsers: {
        for (final profileId in scopeProfileIds)
          if (relationshipState.isFollowing(profileId)) profileId,
      },
      likedPosts: {
        for (final postId in scopePostIds)
          if (postInteractionState.isLiked(postId)) postId,
      },
      postLikesCount: {
        for (final postId in scopePostIds)
          postId: postInteractionState.likeCountFor(
            postId,
            fallback: postsById[postId]?.likeCount ?? 0,
          ),
      },
      postSharesCount: {
        for (final postId in scopePostIds)
          postId: postInteractionState.shareCountFor(
            postId,
            fallback: postsById[postId]?.shareCount ?? 0,
          ),
      },
      postCommentCount: {
        for (final postId in scopePostIds)
          postId: postInteractionState.commentCountFor(
            postId,
            fallback: postsById[postId]?.commentCount ?? 0,
          ),
      },
    );
  }

  void _dismissViewer() {
    final result = _buildResult();
    if (widget.onDismissed != null) {
      widget.onDismissed!(result);
      return;
    }
    widget.onTapBack?.call();
  }

  bool _canDeletePost(
    ContentPostViewData post,
    ActivePersonaContextViewData? activePersonaContext,
  ) {
    final postPersonaId = post.personaId.trim();
    if (postPersonaId.isEmpty) {
      return false;
    }
    final personaPersonaId = activePersonaContext?.personaId.trim() ?? '';
    if (personaPersonaId.isNotEmpty) {
      return personaPersonaId == postPersonaId;
    }
    final sessionPersonaId = ref
        .read(authSessionControllerProvider)
        .activePersonaId
        .trim();
    if (sessionPersonaId.isNotEmpty) {
      return sessionPersonaId == postPersonaId;
    }
    final currentUserId = ref.read(currentUserIdProvider).trim();
    return currentUserId.isNotEmpty && currentUserId == postPersonaId;
  }

  Future<void> _deleteCurrentPost(
    BuildContext context,
    ContentPostViewData post,
  ) async {
    runWhenLoggedIn(ref, context, AuthGateReason.deletePost, () async {
      final displayName = post.displayName.trim().isNotEmpty
          ? post.displayName.trim()
          : post.title.trim().isNotEmpty
          ? post.title.trim()
          : ContentText.contentUnavailable;
      final confirmed = await showAppActionSheet<bool>(
        context,
        title: ChatText.messageActionDelete,
        message: ProfileText.profilePersonaDeleteConfirmTemplate.replaceFirst(
          '%s',
          displayName,
        ),
        sections: const [
          AppActionSheetSection<bool>(
            items: [
              AppActionSheetItem<bool>(
                value: true,
                label: ChatText.messageActionDelete,
                icon: CupertinoIcons.delete,
                isDestructive: true,
              ),
            ],
          ),
        ],
      );
      if (confirmed != true || !context.mounted) {
        return;
      }
      try {
        await ref
            .read(contentPostDeleteCommandWriterProvider)
            .deletePost(
              postId: post.id,
              idempotencyKey: contentPostDeleteIdempotencyKey(post.id),
            );
        ref.read(worksViewerFeedCommandsProvider).removePostLocally(post.id);
        if (context.mounted) {
          AppToast.show(context, ProfileText.contentDeleteSuccess);
        }
        if (!mounted) {
          return;
        }
        _setMountedState(() {
          _commentSplitPostId = null;
          _postStateWindow.remove(post.id);
          _articleHydrationAdmission.cancelPost(post.id);
        });
        _dismissViewer();
      } catch (error) {
        if (!context.mounted) {
          return;
        }
        final semantic = runtime_error_display.runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        );
        await AppActionErrorFeedback.show(context, semantic: semantic);
      }
    });
  }

  Future<void> _requestPostReport(ContentPostViewData post) async {
    final reason = await showContentReportReasonSheet(context);
    if (reason == null || !mounted) {
      return;
    }
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      await _submitPostReport(post, reason);
      return;
    }
    final accepted = ref
        .read(authContinuationProvider.notifier)
        .set(
          SubmitContentReportContinuation(
            postId: post.id,
            surface: ContentReportContinuationSurface.workBrowser,
            reason: reason,
          ),
          ownerToken: 'work-browser-report:${post.id}',
        );
    if (!accepted) {
      return;
    }
    unawaited(
      requireLogin(
        ref,
        context,
        AuthGateReason.report,
        dismissFallback: AppRoutePaths.home,
        dismissPolicy: LoginDismissPolicy.safeFallback,
      ),
    );
  }

  Future<void> _submitPostReport(
    ContentPostViewData post,
    ReportReason reason,
  ) async {
    final journeyTracker = ref.read(journeyEventTrackerProvider);
    final startedAt = DateTime.now();
    try {
      await ref
          .read(workBrowserContentReportCommandWriterProvider)
          .createReport(
            CreateContentReportCommand(
              targetId: post.id,
              targetType: ReportTargetType.post,
              reason: reason,
            ),
          );
      await journeyTracker.trackAction(
        journey: 'content_report',
        action: 'submit_report',
        pageName: 'works_immersive_viewer',
        payload: <String, Object?>{
          'result': 'success',
          'durationMs': DateTime.now().difference(startedAt).inMilliseconds,
        },
      );
      if (!mounted) return;
      AppToast.show(context, ContentText.reportSubmittedViewProgress);
    } catch (error) {
      await journeyTracker.trackAction(
        journey: 'content_report',
        action: 'submit_report',
        pageName: 'works_immersive_viewer',
        error: error,
        payload: <String, Object?>{
          'result': 'failure',
          'failReasonCode': error is CloudException
              ? (error.code ?? error.type.name)
              : error.runtimeType.toString(),
          'durationMs': DateTime.now().difference(startedAt).inMilliseconds,
        },
      );
      if (!mounted) return;
      await AppActionErrorFeedback.show(
        context,
        semantic: runtime_error_display.runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _submitPostReport(post, reason);
          }
        },
      );
    }
  }

  void _requestOriginalImageAccess(ContentPostViewData post) {
    final imageIndex =
        (_photoInnerIndex[post.id] ?? _defaultImageIndexFor(post))
            .clamp(0, max(0, _imageUrlsForPost(post).length - 1))
            .toInt();
    final mediaId = _originalMediaIdFor(post, imageIndex);
    if (mediaId == null) {
      return;
    }
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      unawaited(
        _loadOriginalImage(
          post: post,
          mediaId: mediaId,
          imageIndex: imageIndex,
        ),
      );
      return;
    }
    final accepted = ref
        .read(authContinuationProvider.notifier)
        .set(
          RequestOriginalImageAccessContinuation(
            postId: post.id,
            mediaId: mediaId,
            imageIndex: imageIndex,
          ),
          ownerToken: 'work-browser-original:$mediaId',
        );
    if (!accepted) {
      return;
    }
    unawaited(
      requireLogin(
        ref,
        context,
        AuthGateReason.generic,
        dismissFallback: AppRoutePaths.home,
        dismissPolicy: LoginDismissPolicy.safeFallback,
      ),
    );
  }

  Future<void> _loadOriginalImage({
    required ContentPostViewData post,
    required String mediaId,
    required int imageIndex,
  }) async {
    if (!_requestingOriginalMediaIds.add(mediaId)) {
      return;
    }
    try {
      // grant 兑换、校验、缓存、单飞与换签只存在于 coordinator 一处（DEC-033）；
      // 「查看原图」不再自建一条 facet 直调，否则同一资产会有两套授权路径。
      final lease = await ref
          .read(signedMediaDeliveryCoordinatorProvider)
          .resolve(
            assetId: mediaId,
            kind: MediaDeliveryKind.image,
            accessMode: MediaDeliveryAccessMode.signedGrant,
          );
      final access = WorksViewerOriginalImageAccess(
        url: lease.deliveryUri.toString(),
        expiresAt: lease.expiresAt,
      );
      if (!access.isUsableAt(DateTime.now())) {
        throw StateError('original access grant already expired');
      }
      if (!mounted || !_postStateWindow.contains(post.id)) {
        return;
      }
      _setMountedState(() {
        _rememberPostLocalState(post.id);
        final entries = _originalImageUrlsByPostId[post.id] ??=
            <int, WorksViewerOriginalImageAccess>{};
        entries.remove(imageIndex);
        entries[imageIndex] = access;
        while (entries.length >
            _WorksImmersiveViewerState._maxOriginalImageAccessEntriesPerPost) {
          entries.remove(entries.keys.first);
        }
      });
      AppToast.show(context, MediaText.imageOriginalLoaded);
    } catch (error) {
      _requestingOriginalMediaIds.remove(mediaId);
      if (!mounted) {
        return;
      }
      await AppActionErrorFeedback.show(
        context,
        semantic: runtime_error_display.runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _loadOriginalImage(
              post: post,
              mediaId: mediaId,
              imageIndex: imageIndex,
            );
          }
        },
      );
    } finally {
      _requestingOriginalMediaIds.remove(mediaId);
    }
  }

  Set<String> get _effectiveFilterIds {
    if (_selectedWorkFilterIds.isEmpty ||
        _selectedWorkFilterIds.contains('all')) {
      return <String>{'all'};
    }
    return _selectedWorkFilterIds;
  }

  Set<String> get _effectiveFilterContentTypes {
    final types = <String>{};
    for (final filter in _contentMediaViewerPolicy.workFormatFilters) {
      if (_effectiveFilterIds.contains(filter.id) &&
          filter.contentType != null) {
        types.add(filter.contentType!);
      }
    }
    return types;
  }

  Future<void> _requestBlockAuthor(ContentPostViewData post) async {
    final confirmed = await showAppActionSheet<bool>(
      context,
      title: ContentText.profileBlockConfirmTitle,
      message: ContentText.profileBlockConfirmMessage,
      sections: const <AppActionSheetSection<bool>>[
        AppActionSheetSection<bool>(
          items: <AppActionSheetItem<bool>>[
            AppActionSheetItem<bool>(
              value: true,
              label: ContentText.blockAuthor,
              icon: CupertinoIcons.person_crop_circle_badge_xmark,
              isDestructive: true,
            ),
          ],
        ),
      ],
    );
    if (confirmed != true || !mounted) return;
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      await _applyBlockAuthor(post);
      return;
    }
    final accepted = ref
        .read(authContinuationProvider.notifier)
        .set(
          ContentModerationContinuation(
            postId: post.id,
            surface: ContentModerationContinuationSurface.workBrowser,
            action: ContentModerationContinuationAction.blockAuthor,
            authorId: post.authorId,
          ),
          ownerToken: 'work-browser-block-author:${post.id}',
        );
    if (!accepted) return;
    unawaited(
      requireLogin(
        ref,
        context,
        AuthGateReason.blockUser,
        dismissFallback: AppRoutePaths.home,
        dismissPolicy: LoginDismissPolicy.safeFallback,
      ),
    );
  }

  Future<void> _applyBlockAuthor(ContentPostViewData post) async {
    try {
      await ref
          .read(
            personaRelationshipBlockWriterProvider(AppUiSurfaces.workBrowser),
          )
          .blockUser(BlockUserCommand(targetPersonaId: post.authorId));
      final attribution = _feedAttributionForPost(post);
      ref
          .read(contentBehaviorTrackerProvider)
          .trackHideAuthor(
            post.id,
            authorId: post.authorId,
            contentType: post.type,
            referralSource: widget.referralSource,
            feedRequestId: attribution.feedRequestId,
            channelId: _immersiveChannelId(),
            policyDigest: attribution.policyDigest,
            recallPath: post.recallPath,
            supplySource: post.supplySource,
          );
      _advanceAfterNegativeFeedback(post);
    } catch (error) {
      if (!mounted) return;
      await AppActionErrorFeedback.show(
        context,
        semantic: runtime_error_display.runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _applyBlockAuthor(post);
          }
        },
      );
    }
  }

  Future<void> _requestBlockKeyword(ContentPostViewData post) async {
    final suggested = suggestContentBlockedKeyword(<String>[
      post.title,
      post.normalizedBody,
    ]);
    final keyword = await showBlockedKeywordConfirmationSheet(
      context,
      suggestedKeyword: suggested,
    );
    if (keyword == null || !mounted) return;
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      await _applyBlockKeyword(post, keyword);
      return;
    }
    final accepted = ref
        .read(authContinuationProvider.notifier)
        .set(
          ContentModerationContinuation(
            postId: post.id,
            surface: ContentModerationContinuationSurface.workBrowser,
            action: ContentModerationContinuationAction.blockKeyword,
            keyword: keyword,
          ),
          ownerToken: 'work-browser-block-keyword:${post.id}',
        );
    if (!accepted) return;
    unawaited(
      requireLogin(
        ref,
        context,
        AuthGateReason.settingsAccount,
        dismissFallback: AppRoutePaths.home,
        dismissPolicy: LoginDismissPolicy.safeFallback,
      ),
    );
  }

  Future<void> _applyBlockKeyword(
    ContentPostViewData post,
    String keyword,
  ) async {
    try {
      await ref.read(blockedKeywordWriterProvider).add(keyword);
      final attribution = _feedAttributionForPost(post);
      ref
          .read(contentBehaviorTrackerProvider)
          .trackHideContentType(
            post.id,
            contentType: post.type,
            authorId: post.authorId,
            referralSource: widget.referralSource,
            feedRequestId: attribution.feedRequestId,
            channelId: _immersiveChannelId(),
            policyDigest: attribution.policyDigest,
            recallPath: post.recallPath,
            supplySource: post.supplySource,
          );
      _advanceAfterNegativeFeedback(post);
    } catch (error) {
      if (!mounted) return;
      await AppActionErrorFeedback.show(
        context,
        semantic: runtime_error_display.runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _applyBlockKeyword(post, keyword);
          }
        },
      );
    }
  }

  /// Opens the post-level more-options sheet for the currently visible post.
  ///
  /// 作品浏览器：媒体筛选入口在「更多」菜单内（全部作品/图片/视频/文章）。
  void _showWorksMoreSheet(BuildContext context) {
    final posts = _buildFeed();
    final post = posts.isEmpty
        ? null
        : posts[_currentPage.clamp(0, posts.length - 1)]
              as ContentPostViewData?;
    if (post == null) return;
    final journeyTracker = ref.read(journeyEventTrackerProvider);
    unawaited(
      journeyTracker.trackAction(
        journey: 'content_more_actions',
        action: 'open',
        pageName: 'works_immersive_viewer',
        targetType: 'post',
        targetKey: post.id,
      ),
    );
    final enableIdentityTemplate = ref.read(
      contentFeatureFlagProvider('enable_identity_share_template'),
    );
    final activePersonaContext = ref
        .read(activePersonaContextProvider)
        .asData
        ?.value;
    final canDelete = _canDeletePost(post, activePersonaContext);
    final filterOptions = <WorksViewerMoreActionOption>[
      for (final filter in _contentMediaViewerPolicy.workFormatFilters)
        WorksViewerMoreActionOption(
          id: filter.id,
          label: UITextConstants.contentLabelForKey(filter.labelKey),
        ),
    ];
    final isArticle = _isArticleLikePost(post);
    final currentImageIndex =
        (_photoInnerIndex[post.id] ?? _defaultImageIndexFor(post))
            .clamp(0, max(0, _imageUrlsForPost(post).length - 1))
            .toInt();
    final originalMediaId = _isImageLikePost(post)
        ? _originalMediaIdFor(post, currentImageIndex)
        : null;
    final readingOptions = isArticle
        ? <WorksViewerMoreActionOption>[
            for (final option
                in _contentMediaViewerPolicy.articlePaperThemeOptions)
              WorksViewerMoreActionOption(
                id: option.id,
                label: UITextConstants.contentLabelForKey(option.labelKey),
              ),
          ]
        : const <WorksViewerMoreActionOption>[];
    WorksViewerContentActionsComposition.showMoreActions(
      context,
      config: WorksViewerMoreActionsConfig(
        onActionInvoked: (actionId) => unawaited(
          journeyTracker.trackAction(
            journey: 'content_more_actions',
            action: 'invoke',
            pageName: 'works_immersive_viewer',
            targetType: 'post',
            targetKey: post.id,
            payload: <String, Object?>{'actionId': actionId},
          ),
        ),
        showShareAction: true,
        showViewOriginalAction: originalMediaId != null,
        onViewOriginal: originalMediaId == null
            ? null
            : () => _requestOriginalImageAccess(post),
        filterOptions: filterOptions,
        selectedFilterIds: _effectiveFilterIds.toList(growable: false),
        onFilterSelectionChanged: _applyFilterSelection,
        readingOptions: readingOptions,
        selectedReadingOptionId: isArticle
            ? (_articlePaperThemeOverrides[post.id] ?? 'system')
            : null,
        onReadingOptionChanged: isArticle
            ? (id) => _setMountedState(() {
                _rememberPostLocalState(post.id);
                if (id == 'system') {
                  _articlePaperThemeOverrides.remove(post.id);
                } else {
                  _articlePaperThemeOverrides[post.id] = id;
                }
              })
            : null,
        forceDarkAppearance: true,
        onCopyLink: () => _copyLink(
          context,
          post,
          enableIdentityTemplate: enableIdentityTemplate,
        ),
        onShare: () => _sharePost(
          context,
          post,
          enableIdentityTemplate: enableIdentityTemplate,
        ),
        onNotInterested: () {
          final attribution = _feedAttributionForPost(post);
          final previousPage = _currentPage;
          ref
              .read(contentBehaviorTrackerProvider)
              .trackDislike(
                post.id,
                contentType: post.type,
                authorId: post.authorId,
                referralSource: widget.referralSource,
                feedRequestId: attribution.feedRequestId,
                channelId: _immersiveChannelId(),
                policyDigest: attribution.policyDigest,
                recallPath: post.recallPath,
                supplySource: post.supplySource,
              );
          _advanceAfterNegativeFeedback(post);
          AppToast.show(
            context,
            DiscoveryFeedText.feedNegativeFeedbackNotInterested,
            actionLabel: ContentText.undo,
            onAction: () {
              ref
                  .read(contentBehaviorTrackerProvider)
                  .trackUndoDislike(
                    post.id,
                    contentType: post.type,
                    authorId: post.authorId,
                    referralSource: widget.referralSource,
                    feedRequestId: attribution.feedRequestId,
                    channelId: _immersiveChannelId(),
                    policyDigest: attribution.policyDigest,
                    recallPath: post.recallPath,
                    supplySource: post.supplySource,
                  );
              if (_pageController.hasClients) {
                _pageController.jumpToPage(previousPage);
              }
              AppToast.show(context, ContentText.notInterestedUndone);
            },
          );
        },
        onBlockUser: () => unawaited(_requestBlockAuthor(post)),
        onBlockWords: () => unawaited(_requestBlockKeyword(post)),
        onReport: () => _requestPostReport(post),
        showDeleteAction: canDelete,
        onDelete: canDelete ? () => _deleteCurrentPost(context, post) : null,
      ),
    );
  }

  void _advanceAfterNegativeFeedback(ContentPostViewData post) {
    final posts = _buildFeed();
    final index = posts.indexWhere((candidate) => candidate.id == post.id);
    if (index >= 0 && index + 1 < posts.length && _pageController.hasClients) {
      _pageController.jumpToPage(index + 1);
    }
  }

  /// 想去锚点：作品经 primaryHomepageId 绑定到支持想去的实体主页时才存在。
  /// 真相源是 list/detail wire 的 primaryHomepageId/Type + codegen 类型门；
  /// 锚点缺失时不渲染想去按钮，不做本地推断。
  ({String homepageId, String displayName})? _wishlistAnchorForPost(
    ContentPostViewData post,
  ) {
    final raw = _effectiveRawPostById(post.id);
    if (raw == null) {
      return null;
    }
    final homepageId = raw['primaryHomepageId']?.toString().trim() ?? '';
    final homepageType = raw['primaryHomepageType']?.toString().trim() ?? '';
    if (homepageId.isEmpty ||
        !HomepageUIConfig.wishlistHomepageTypes.contains(homepageType)) {
      return null;
    }
    final snapshot = raw['primaryHomepageSnapshot'];
    final displayName = snapshot is Map
        ? (snapshot['title']?.toString().trim() ?? '')
        : '';
    return (homepageId: homepageId, displayName: displayName);
  }

  /// 按需读取 wishlist 服务端状态；未登录默认 false（登录后经续接刷新）。
  void _ensureWishlistStateLoaded(String homepageId) {
    if (_wishlistStateByHomepageId.containsKey(homepageId) ||
        !_loadingWishlistHomepageIds.add(homepageId)) {
      return;
    }
    if (!ref.read(authSessionControllerProvider).isAuthenticated) {
      // build 期间可被调用：默认未想去与 UI 缺省一致，直接记录、不触发重建。
      _loadingWishlistHomepageIds.remove(homepageId);
      _wishlistStateByHomepageId[homepageId] = false;
      return;
    }
    unawaited(() async {
      // 本函数可在 build 期被调用；先让出一拍，保证包括 provider 装配
      // 同步抛错在内的全部路径都在 build 之外执行（catch 里有 setState）。
      await null;
      try {
        final state = await ref
            .read(workBrowserEntityWishlistStateReaderProvider)
            .getEntityWishlistState(
              objectId: homepageId,
              objectKind: FollowSubjectKind.homepage.wireName,
            );
        if (!mounted) return;
        _setMountedState(
          () => _wishlistStateByHomepageId[homepageId] = state.wishlisted,
        );
      } catch (error, stackTrace) {
        unawaited(
          ref
              .read(exceptionTelemetryPortProvider)
              .recordHandledException(
                source: 'content.works_viewer.load_wishlist_state',
                error: error,
                stackTrace: stackTrace,
              ),
        );
        if (!mounted) return;
        _setMountedState(() => _wishlistStateByHomepageId[homepageId] = false);
      } finally {
        _loadingWishlistHomepageIds.remove(homepageId);
      }
    }());
  }

  void _toggleWishlistForPost(ContentPostViewData post) {
    final anchor = _wishlistAnchorForPost(post);
    if (anchor == null) {
      return;
    }
    if (!ref.read(authSessionControllerProvider).isAuthenticated) {
      // 双目标契约：关闭登录回安全态（首页），登录成功经续接完成想去。
      ref
          .read(authContinuationProvider.notifier)
          .set(
            WishlistHomepageContinuation(homepageId: anchor.homepageId),
            ownerToken: 'work-browser-wishlist:${anchor.homepageId}',
          );
      unawaited(
        requireLogin(
          ref,
          context,
          AuthGateReason.wishlist,
          dismissFallback: AppRoutePaths.home,
          dismissPolicy: LoginDismissPolicy.safeFallback,
        ),
      );
      return;
    }
    final wishlisted = _wishlistStateByHomepageId[anchor.homepageId] ?? false;
    unawaited(
      _applyWishlist(
        post: post,
        homepageId: anchor.homepageId,
        displayName: anchor.displayName,
        wishlisted: !wishlisted,
      ),
    );
  }

  Future<void> _applyWishlist({
    required ContentPostViewData post,
    required String homepageId,
    required String displayName,
    required bool wishlisted,
  }) async {
    final tracker = ref.read(contentBehaviorTrackerProvider);
    final attribution = _feedAttributionForPost(post);
    if (wishlisted) {
      tracker.trackWishlistAdd(
        homepageId,
        objectKind: FollowSubjectKind.homepage.wireName,
        displayName: displayName.isEmpty ? null : displayName,
        sourceSurface: AppUiSurfaces.workBrowser.id,
        feedRequestId: attribution.feedRequestId,
        referralSource: widget.referralSource,
      );
    } else {
      tracker.trackWishlistRemove(
        homepageId,
        objectKind: FollowSubjectKind.homepage.wireName,
        sourceSurface: AppUiSurfaces.workBrowser.id,
        feedRequestId: attribution.feedRequestId,
        referralSource: widget.referralSource,
      );
    }
    await tracker.flush();
    if (!mounted) {
      return;
    }
    _setMountedState(() => _wishlistStateByHomepageId[homepageId] = wishlisted);
    if (!wishlisted) {
      AppToast.show(context, ObjectHomepageText.wishlistRemovedFeedback);
      return;
    }
    await _showWishlistIntersectionFeedback(homepageId);
  }

  /// Aha 时刻（诚实两态）：想去成功后立刻回答「谁也想去」。
  /// 有对象交集 → 点名共同人数并给查看入口；无 → 只确认动作，不伪造。
  Future<void> _showWishlistIntersectionFeedback(String homepageId) async {
    final personaId = ref
        .read(authSessionControllerProvider)
        .activePersonaId
        .trim();
    List<IntersectionReason> reasons = const <IntersectionReason>[];
    try {
      reasons = await ref.read(
        objectSharedReasonsProvider(
          ObjectIntersectionQuery(
            objectAId: personaId,
            objectAType: 'person',
            objectBId: homepageId,
            objectBType: 'homepage',
          ),
        ).future,
      );
    } catch (error, stackTrace) {
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'content.works_viewer.wishlist_intersection_feedback',
              error: error,
              stackTrace: stackTrace,
            ),
      );
    }
    if (!mounted) {
      return;
    }
    final wishReason = reasons.isEmpty
        ? null
        : reasons.firstWhere(
            (reason) => reason.kind == 'coWishlistedEntity',
            orElse: () => reasons.first,
          );
    final mutualCount = wishReason == null
        ? 0
        : intersectionMutualCountOf(wishReason);
    if (wishReason == null || mutualCount <= 0) {
      AppToast.show(context, ObjectHomepageText.wishlistAddedFeedback);
      return;
    }
    AppToast.show(
      context,
      ObjectHomepageText.wishlistSharedFeedback(mutualCount),
      actionLabel: ObjectHomepageText.wishlistSharedFeedbackViewAction,
      onAction: () {
        if (!mounted) return;
        context.push(AppRoutePaths.homepageDetail(id: homepageId));
      },
    );
  }
}
