part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerEngagementActions on _WorksImmersiveViewerState {
  void _openCommentFor(String postId) {
    _setMountedState(() {
      _commentSplitPostId = postId;
      _invalidateVideoViewport(resetDurationWindow: false);
    });
  }

  Widget _buildCommentSplitContent(PostBaseDto post) {
    return ColoredBox(
      color: AppColors.worksBackground,
      child: _buildPostCanvas(
        post,
        enableArticlePageCurl: _enableArticlePageCurl,
        isVisible: true,
        videoViewportEpoch: _videoViewportEpoch,
      ),
    );
  }

  PostBaseDto? _postById(List<PostBaseDto> posts, String postId) {
    for (final post in posts) {
      if (post.id == postId) {
        return post;
      }
    }
    return null;
  }

  void _sharePost(
    BuildContext ctx,
    PostBaseDto post, {
    required bool enableIdentityTemplate,
  }) {
    runWhenLoggedIn(ref, context, AuthGateReason.share, () {
      final template = _buildShareTemplate(
        post: post,
        enableIdentityTemplate: enableIdentityTemplate,
      );
      ContentShareSheet.show(
        ctx,
        template: template,
        circlePostPlacementWriter: ref.read(
          workBrowserCirclePostPlacementWriterProvider,
        ),
        circleMembershipQuery: ref.read(
          workBrowserCircleMembershipQueryProvider,
        ),
        outboundShareWriter: ref.read(
          workBrowserContentOutboundShareWriterProvider,
        ),
        onActionCompleted: (result) async {
          await _recordShare(post.id, result.actionId);
        },
      );
    });
  }

  Future<void> _copyLink(
    BuildContext context,
    PostBaseDto post, {
    required bool enableIdentityTemplate,
  }) async {
    final result = await const DefaultContentShareActionHandler().execute(
      context,
      _buildShareTemplate(
        post: post,
        enableIdentityTemplate: enableIdentityTemplate,
      ),
      ContentShareAction(id: 'copy_link', label: UITextConstants.copyLink),
    );
    if (result.success) {
      await _recordShare(post.id, result.actionId);
    }
  }

  ContentShareTemplate _buildShareTemplate({
    required PostBaseDto post,
    required bool enableIdentityTemplate,
  }) {
    final raw = _rawPostById(post.id);
    final visibility =
        raw?[ContentPostImmersiveWireKeys.visibility]?.toString() ?? 'public';
    final surfaceView = ContentSurfaceViewMapper.fromDto(post, wire: raw);
    return ContentShareTemplateBuilder.build(
      surfaceView: surfaceView,
      enableIdentityTemplate: enableIdentityTemplate,
      visibility: visibility,
    );
  }

  Future<void> _recordShare(String postId, String actionId) async {
    ref
        .read(contentBehaviorTrackerProvider)
        .trackShare(postId, tags: <String>[actionId]);
  }

  MediaViewerResult _buildResult() {
    final posts = _buildFeed();
    final postsById = <String, PostBaseDto>{
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
    PostBaseDto post,
    ActivePersonaContextViewData? activePersonaContext,
  ) {
    final postSubAccountId = post.subAccountId.trim();
    if (postSubAccountId.isEmpty) {
      return false;
    }
    final personaSubAccountId = activePersonaContext?.subAccountId.trim() ?? '';
    if (personaSubAccountId.isNotEmpty) {
      return personaSubAccountId == postSubAccountId;
    }
    final sessionSubAccountId = ref
        .read(authSessionControllerProvider)
        .activeSubAccountId
        .trim();
    if (sessionSubAccountId.isNotEmpty) {
      return sessionSubAccountId == postSubAccountId;
    }
    final currentUserId = ref.read(currentUserIdProvider).trim();
    return currentUserId.isNotEmpty && currentUserId == postSubAccountId;
  }

  Future<void> _deleteCurrentPost(
    BuildContext context,
    PostBaseDto post,
  ) async {
    runWhenLoggedIn(ref, context, AuthGateReason.deletePost, () async {
      final displayName = post.displayName.trim().isNotEmpty
          ? post.displayName.trim()
          : post.title.trim().isNotEmpty
          ? post.title.trim()
          : UITextConstants.contentUnavailable;
      final confirmed = await showAppActionSheet<bool>(
        context,
        title: ChatText.messageActionDelete,
        message: UITextConstants.profileSubAccountDeleteConfirmTemplate
            .replaceFirst('%s', displayName),
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
            .read(contentWriteRepositoryProvider)
            .deletePost(
              postId: post.id,
              idempotencyKey: contentPostDeleteIdempotencyKey(post.id),
            );
        ref.read(discoveryFeedMapProvider.notifier).removePostLocally(post.id);
        if (context.mounted) {
          AppToast.show(context, UITextConstants.contentDeleteSuccess);
        }
        if (!mounted) {
          return;
        }
        _setMountedState(() {
          _commentSplitPostId = null;
          _hydratedRawPostsById.remove(post.id);
          _workItemCache.remove(post.id);
          _failedArticleHydrationIds.remove(post.id);
          _failedArticleHydrationErrorsById.remove(post.id);
          _hydratingArticleIds.remove(post.id);
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

  Future<void> _requestPostReport(PostBaseDto post) async {
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
    PostBaseDto post,
    ContentReportReason reason,
  ) async {
    final journeyTracker = ref.read(journeyEventTrackerProvider);
    final startedAt = DateTime.now();
    try {
      await ref
          .read(workBrowserContentReportCommandWriterProvider)
          .createReport(
            CreateContentReportCommand(
              targetId: post.id,
              targetType: ContentReportTargetType.post,
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
      AppToast.show(context, UITextConstants.reportSubmittedViewProgress);
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

  void _requestOriginalImageAccess(PostBaseDto post) {
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
    required PostBaseDto post,
    required String mediaId,
    required int imageIndex,
  }) async {
    if (!_requestingOriginalMediaIds.add(mediaId)) {
      return;
    }
    try {
      final grant = await ref
          .read(workBrowserContentMediaFacetProvider)
          .requestOriginalAccess(
            RequestContentMediaOriginalAccessCommand(mediaId: mediaId),
          );
      if (grant.mediaId != mediaId) {
        throw StateError('original access grant media id mismatch');
      }
      if (!mounted) {
        return;
      }
      _setMountedState(() {
        (_originalImageUrlsByPostId[post.id] ??= <int, String>{})[imageIndex] =
            grant.originalUrl.toString();
      });
      AppToast.show(context, UITextConstants.imageOriginalLoaded);
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
    for (final filter in ContentUIConfig.workFormatFilters) {
      if (_effectiveFilterIds.contains(filter.id) &&
          filter.contentType != null) {
        types.add(filter.contentType!);
      }
    }
    return types;
  }

  Future<void> _requestBlockAuthor(PostBaseDto post) async {
    final confirmed = await showAppActionSheet<bool>(
      context,
      title: UITextConstants.profileBlockConfirmTitle,
      message: UITextConstants.profileBlockConfirmMessage,
      sections: const <AppActionSheetSection<bool>>[
        AppActionSheetSection<bool>(
          items: <AppActionSheetItem<bool>>[
            AppActionSheetItem<bool>(
              value: true,
              label: UITextConstants.blockAuthor,
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

  Future<void> _applyBlockAuthor(PostBaseDto post) async {
    try {
      await ref
          .read(
            personaRelationshipBlockWriterProvider(AppUiSurfaces.workBrowser),
          )
          .blockUser(BlockUserCommand(targetSubAccountId: post.authorId));
      final feedSession = ref.read(feedSessionProvider.notifier);
      ref
          .read(contentBehaviorTrackerProvider)
          .trackHideAuthor(
            post.id,
            authorId: post.authorId,
            contentType: post.type,
            referralSource: widget.referralSource,
            feedRequestId: _effectiveFeedRequestId(),
            channelId: _immersiveChannelId(),
            rankingVersion: feedSession.currentRankingVersion,
            reasonVersion: feedSession.currentReasonVersion,
            recallPath: post.recallPath,
            contentVertical: post.contentVertical,
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

  Future<void> _requestBlockKeyword(PostBaseDto post) async {
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

  Future<void> _applyBlockKeyword(PostBaseDto post, String keyword) async {
    try {
      await ref.read(blockedKeywordWriterProvider).add(keyword);
      final feedSession = ref.read(feedSessionProvider.notifier);
      ref
          .read(contentBehaviorTrackerProvider)
          .trackHideContentType(
            post.id,
            contentType: post.type,
            authorId: post.authorId,
            referralSource: widget.referralSource,
            feedRequestId: _effectiveFeedRequestId(),
            channelId: _immersiveChannelId(),
            rankingVersion: feedSession.currentRankingVersion,
            reasonVersion: feedSession.currentReasonVersion,
            recallPath: post.recallPath,
            contentVertical: post.contentVertical,
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
  /// Work Browser V1.0：媒体筛选入口在「更多」菜单内（全部作品/图片/视频/文章）。
  void _showWorksMoreSheet(BuildContext context) {
    final posts = _buildFeed();
    final post = posts.isEmpty
        ? null
        : posts[_currentPage.clamp(0, posts.length - 1)] as PostBaseDto?;
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
    final filterOptions = <MoreActionFilterOption>[
      for (final filter in ContentUIConfig.workFormatFilters)
        MoreActionFilterOption(
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
        ? <MoreActionReadingOption>[
            for (final option in ContentUIConfig.articlePaperThemeOptions)
              MoreActionReadingOption(
                id: option.id,
                label: UITextConstants.contentLabelForKey(option.labelKey),
              ),
          ]
        : const <MoreActionReadingOption>[];
    MoreActionPopup.show(
      context: context,
      config: MediaPostMoreActionConfig(
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
          final feedSession = ref.read(feedSessionProvider.notifier);
          final previousPage = _currentPage;
          ref
              .read(contentBehaviorTrackerProvider)
              .trackDislike(
                post.id,
                contentType: post.type,
                authorId: post.authorId,
                referralSource: widget.referralSource,
                feedRequestId: _effectiveFeedRequestId(),
                channelId: _immersiveChannelId(),
                rankingVersion: feedSession.currentRankingVersion,
                reasonVersion: feedSession.currentReasonVersion,
                recallPath: post.recallPath,
                contentVertical: post.contentVertical,
                supplySource: post.supplySource,
              );
          _advanceAfterNegativeFeedback(post);
          AppToast.show(
            context,
            DiscoveryFeedText.feedNegativeFeedbackNotInterested,
            actionLabel: UITextConstants.undo,
            onAction: () {
              ref
                  .read(contentBehaviorTrackerProvider)
                  .trackUndoDislike(
                    post.id,
                    contentType: post.type,
                    authorId: post.authorId,
                    referralSource: widget.referralSource,
                    feedRequestId: _effectiveFeedRequestId(),
                    channelId: _immersiveChannelId(),
                    rankingVersion: feedSession.currentRankingVersion,
                    reasonVersion: feedSession.currentReasonVersion,
                    recallPath: post.recallPath,
                    contentVertical: post.contentVertical,
                    supplySource: post.supplySource,
                  );
              if (_pageController.hasClients) {
                _pageController.jumpToPage(previousPage);
              }
              AppToast.show(context, UITextConstants.notInterestedUndone);
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

  void _advanceAfterNegativeFeedback(PostBaseDto post) {
    final posts = _buildFeed();
    final index = posts.indexWhere((candidate) => candidate.id == post.id);
    if (index >= 0 && index + 1 < posts.length && _pageController.hasClients) {
      _pageController.jumpToPage(index + 1);
    }
  }
}
