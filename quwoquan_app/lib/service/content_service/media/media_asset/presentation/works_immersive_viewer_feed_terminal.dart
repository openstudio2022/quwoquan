part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerFeedTerminal on _WorksImmersiveViewerState {
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
