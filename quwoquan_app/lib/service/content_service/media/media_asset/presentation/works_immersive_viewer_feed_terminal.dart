part of 'works_immersive_viewer.dart';

enum _WorksInternalFeedTerminal {
  loading,
  content,
  canonicalEmpty,
  blockingError,
}

final class _WorksInternalFeedAggregate {
  const _WorksInternalFeedAggregate({
    required this.terminal,
    required this.posts,
    this.blockingError,
    this.emptyReason,
  });

  final _WorksInternalFeedTerminal terminal;
  final List<ContentPostViewData> posts;
  final Object? blockingError;
  final ContentFeedEmptyReason? emptyReason;
}

extension _WorksImmersiveViewerFeedTerminal on _WorksImmersiveViewerState {
  Widget _buildInternalFeedTerminal(
    BuildContext context,
    _WorksInternalFeedAggregate feed,
  ) {
    switch (feed.terminal) {
      case _WorksInternalFeedTerminal.loading:
        return ColoredBox(
          key: const ValueKey<String>('works-internal-feed-loading'),
          color: AppColors.black,
          child: AppRequestFeedback.page(),
        );
      case _WorksInternalFeedTerminal.canonicalEmpty:
        final reason = feed.emptyReason!;
        return ColoredBox(
          key: ValueKey<String>('works-internal-feed-empty-${reason.wireName}'),
          color: AppColors.black,
          child: Center(
            child: Padding(
              padding: EdgeInsets.all(AppSpacing.containerLg),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    DiscoveryText.webPcFeedEmpty,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: AppColors.white,
                      fontSize: AppTypography.iosTitle3,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupSm),
                  Text(
                    DiscoveryFeedText.contentLoadingCompleted,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: AppColors.white.withValues(alpha: 0.72),
                      fontSize: AppTypography.iosSubheadline,
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      case _WorksInternalFeedTerminal.blockingError:
        final semantic = runtime_error_display.ensureRetryUiErrorSemantic(
          runtime_error_display.runtimeErrorSemantic(
            context,
            error: feed.blockingError!,
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
            presentation: UiErrorPresentation.emptyPage,
            appearanceMode: UiErrorAppearanceMode.dark,
            sourceRouteId: AppUiSurfaces.workBrowser.routeId,
            sourceSurfaceId: AppUiSurfaces.workBrowser.id,
            sourceOperationId: AppCloudOperationIds.contentPostGetFeed,
          ),
          retryLabel: SearchText.reload,
        );
        return AppPageErrorState(
          key: const ValueKey<String>('works-internal-feed-error'),
          semantic: semantic,
          onRecovery: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              return _retryTrackedFeeds();
            }
            if (action.type == UiErrorActionType.dismiss) {
              _dismissViewer();
              return UiRecoveryOutcome.handedOff;
            }
            return UiRecoveryOutcome.cancelled;
          },
        );
      case _WorksInternalFeedTerminal.content:
        return const SizedBox.shrink();
    }
  }

  void _applyFilterSelection(Set<String> selectedIds) {
    final nextIds = selectedIds.isEmpty || selectedIds.contains('all')
        ? <String>{'all'}
        : selectedIds;
    _setMountedState(() {
      _selectedWorkFilterIds = nextIds;
      _currentPage = 0;
      _invalidateVideoViewport();
      _pageController.jumpToPage(0);
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _retainPostLocalStateAround(_buildFeed(), _currentPage);
    });
  }

  _WorksInternalFeedAggregate _buildInternalFeedAggregate() {
    final channelIds = _trackedFeedTabIds;
    final feedStates = <String, AsyncValue<WorksViewerFeedSnapshot>>{
      for (final channelId in channelIds)
        channelId: ref.watch(worksViewerFeedProvider(channelId)),
    };
    final snapshots = <String, WorksViewerFeedSnapshot>{
      for (final entry in feedStates.entries) entry.key: ?entry.value.value,
    };
    final posts = _buildInternalFeedPosts(snapshots);
    if (posts.isNotEmpty) {
      return _WorksInternalFeedAggregate(
        terminal: _WorksInternalFeedTerminal.content,
        posts: posts,
      );
    }

    for (final entry in feedStates.entries) {
      final state = entry.value;
      final error = state.hasError ? state.error : state.value?.blockingError;
      if (error != null) {
        return _WorksInternalFeedAggregate(
          terminal: _WorksInternalFeedTerminal.blockingError,
          posts: posts,
          blockingError: error,
        );
      }
    }

    if (feedStates.values.any(
      (state) => state.isLoading || (state.value?.isLoading ?? false),
    )) {
      return _WorksInternalFeedAggregate(
        terminal: _WorksInternalFeedTerminal.loading,
        posts: posts,
      );
    }

    final emptyReasons = <ContentFeedEmptyReason>[
      for (final channelId in channelIds) ?snapshots[channelId]?.emptyReason,
    ];
    if (channelIds.isNotEmpty && emptyReasons.length == channelIds.length) {
      final reason =
          emptyReasons.contains(ContentFeedEmptyReason.noActiveRelease)
          ? ContentFeedEmptyReason.noActiveRelease
          : emptyReasons.first;
      return _WorksInternalFeedAggregate(
        terminal: _WorksInternalFeedTerminal.canonicalEmpty,
        posts: posts,
        emptyReason: reason,
      );
    }

    return _WorksInternalFeedAggregate(
      terminal: _WorksInternalFeedTerminal.blockingError,
      posts: posts,
      blockingError: StateError(
        'Works feed completed without content or a canonical empty reason.',
      ),
    );
  }

  Widget _buildLoadMoreSentinel({
    required bool isLoading,
    required Object? error,
    required VoidCallback onRetry,
  }) {
    final hasError = error != null;
    return ColoredBox(
      key: TestKeys.worksLoadMoreSentinel,
      color: AppColors.black,
      child: Center(
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (hasError)
                AppListAppendErrorFooter(
                  key: const ValueKey<String>('works-load-more-retry'),
                  semantic: runtime_error_display.runtimeErrorSemantic(
                    context,
                    error: error,
                    category: UiErrorCategory.listAppend,
                    scope: UiErrorScope.section,
                    presentation: UiErrorPresentation.appendFooter,
                  ),
                  onAction: isLoading
                      ? null
                      : (action) async {
                          if (action.type == UiErrorActionType.retry ||
                              action.type == UiErrorActionType.resubmit) {
                            onRetry();
                          }
                        },
                )
              else ...[
                AppRequestFeedback.inline(),
                SizedBox(height: AppSpacing.containerSm),
                Text(
                  DiscoveryText.worksVideoBookLoadingTitle,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: AppTypography.body,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
                Text(
                  DiscoveryText.worksVideoBookLoadingSubtitle,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.white.withValues(alpha: 0.72),
                    fontSize: AppTypography.iosSubheadline,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
