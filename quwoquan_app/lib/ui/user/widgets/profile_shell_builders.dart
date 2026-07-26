part of 'profile_shell.dart';

extension _ProfileShellTabBuilders on _ProfileShellState {
  /// 首屏聚合失败错误态：结构化 [UiErrorSemantic] + 重试。
  Widget _buildFirstScreenError(BuildContext context, ProfileState state) {
    return AppPageErrorState(
      semantic: _profileBlockingErrorSemantic(context, state.failure!),
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
        onDirectionSelected: _selectInteractionDirection,
      ),
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
        .failure;
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
      primaryAction:
          base.primaryAction ??
          const UiErrorAction(
            type: UiErrorActionType.retry,
            label: UITextConstants.tryAgain,
          ),
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
}
