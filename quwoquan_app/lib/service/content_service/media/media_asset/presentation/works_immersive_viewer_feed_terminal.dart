part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerFeedTerminal on _WorksImmersiveViewerState {
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
