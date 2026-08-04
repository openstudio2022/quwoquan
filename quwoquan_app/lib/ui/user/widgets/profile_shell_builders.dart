part of 'profile_shell.dart';

extension _ProfileShellTabBuilders on _ProfileShellState {
  /// 首屏聚合失败错误态：结构化 [UiErrorSemantic] + 重试。
  Widget _buildFirstScreenError(BuildContext context, ProfileState state) {
    return AppPageErrorState(
      semantic: _profileBlockingErrorSemantic(context, state.identityFailure!),
      onRecovery: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await ref
              .read(profileNotifierProvider(widget.userId).notifier)
              .reloadIdentity();
          return ref
                      .read(profileNotifierProvider(widget.userId))
                      .identityFailure ==
                  null
              ? UiRecoveryOutcome.recovered
              : UiRecoveryOutcome.stillBlocked;
        } else if (action.type == UiErrorActionType.login) {
          await requireLogin(
            ref,
            context,
            AuthGateReason.generic,
            redirect: GoRouterState.of(context).uri.toString(),
            dismissFallback: AppRoutePaths.home,
          );
          return UiRecoveryOutcome.handedOff;
        } else if (action.type == UiErrorActionType.dismiss) {
          _leaveProfile(context);
          return UiRecoveryOutcome.handedOff;
        }
        return UiRecoveryOutcome.cancelled;
      },
    );
  }

  Widget _buildInlineTabContent(
    BuildContext context,
    bool isDark, {
    required AppPageLoadDecision loadDecision,
    required AuthorImpactRequest impactRequest,
  }) {
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
        suppressFailure: loadDecision.suppresses('works'),
      ),
    };
    final body = KeyedSubtree(
      key: ValueKey<String>('profile-tab-body-$_activeTabId'),
      child: content,
    );
    if (loadDecision.kind != AppPageLoadDecisionKind.contentWithNotice ||
        loadDecision.semantic == null) {
      return body;
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        AppTransientErrorNotice(
          semantic: loadDecision.semantic!,
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              final reloads = <Future<void>>[];
              final notifier = ref.read(
                profileNotifierProvider(widget.userId).notifier,
              );
              if (loadDecision.suppresses('identity')) {
                reloads.add(notifier.reloadIdentity());
              }
              if (loadDecision.suppresses('works')) {
                reloads.add(notifier.reloadWorks());
              }
              if (loadDecision.suppresses('impact')) {
                ref.invalidate(authorImpactProvider(impactRequest));
              }
              await Future.wait(reloads);
            } else if (action.type == UiErrorActionType.login) {
              await requireLogin(
                ref,
                context,
                AuthGateReason.generic,
                redirect: GoRouterState.of(context).uri.toString(),
                dismissFallback: AppRoutePaths.home,
              );
            } else if (action.type == UiErrorActionType.dismiss) {
              _leaveProfile(context);
            }
          },
        ),
        body,
      ],
    );
  }

  UiErrorSemantic _profileBlockingErrorSemantic(
    BuildContext context,
    Object error,
  ) {
    return runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
  }
}
