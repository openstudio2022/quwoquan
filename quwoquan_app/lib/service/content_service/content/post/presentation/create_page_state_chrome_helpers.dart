part of 'create_page.dart';

/// 创作页普通/沉浸模式共用的页面壳与主操作栏。
///
/// 本扩展不持有状态，所有状态读写仍通过唯一的 [_CreatePageState] 与
/// [createEditorProvider] 完成。
extension _CreatePageStateChromeHelpers on _CreatePageState {
  Widget _buildImmersiveArticlePage(CreateEditorState state) {
    final background = CupertinoColors.systemBackground.resolveFrom(context);
    final brightness =
        CupertinoTheme.of(context).brightness ?? Brightness.light;
    SystemChrome.setSystemUIOverlayStyle(
      SystemUiOverlayStyle(
        statusBarBrightness: brightness,
        statusBarIconBrightness: brightness == Brightness.dark
            ? Brightness.light
            : Brightness.dark,
      ),
    );

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (!didPop) {
          await _onCloseRequest();
        }
      },
      child: CupertinoPageScaffold(
        backgroundColor: background,
        // Same transparent Material host as main create route (see [AppScaffold]).
        child: Material(
          type: MaterialType.transparency,
          child: KeyedSubtree(
            key: TestKeys.createPage,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeOutCubic,
              color: background,
              child: SafeArea(
                top: false,
                bottom: false,
                child: Column(
                  children: <Widget>[
                    _buildImmersiveArticleTopBar(state: state),
                    Expanded(
                      child: Padding(
                        padding: EdgeInsets.only(top: AppSpacing.containerSm),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: <Widget>[
                            if (!_unifiedCreateEditorEnabled) ...<Widget>[
                              Padding(
                                padding: EdgeInsets.symmetric(
                                  horizontal: AppSpacing.containerMd,
                                ),
                                child: _buildRollbackBanner(
                                  CupertinoColors.secondaryLabel.resolveFrom(
                                    context,
                                  ),
                                ),
                              ),
                              SizedBox(height: AppSpacing.interGroupSm),
                            ],
                            Expanded(child: _buildTextEditor(state)),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildImmersiveArticleTopBar({required CreateEditorState state}) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final onAccentLabel = AppColorsFunctional.getColor(
      isDark,
      ColorType.badgeForeground,
    );
    final title = _pageTitleForState(state);
    final titleColor = AppNavigationSemanticConstants.barTitleColor(isDark);

    return _buildCreateTopChromeBar(
      collapseProgress: 1,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          KeyedSubtree(
            key: TestKeys.createCloseButton,
            child: AppNavigationBarIconButton(
              icon: CupertinoIcons.back,
              onPressed: _onCloseRequest,
            ),
          ),
          Expanded(
            child: Center(
              child: Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: titleColor,
                  fontSize: AppTypography.iosNavTitle,
                  fontWeight: AppTypography.regular,
                ),
              ),
            ),
          ),
          _buildDraftToolbarAction(immersiveDark: true),
          SizedBox(width: AppSpacing.intraGroupSm),
          CupertinoButton(
            key: TestKeys.createPublishButton,
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
            minimumSize: const Size.square(AppSpacing.buttonHeightSm),
            color: AppColors.iosAccentLight,
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
            onPressed: _isPublishing
                ? (_publicationCancellationSignal == null
                      ? null
                      : _cancelPublicationUpload)
                : _publish,
            child: _buildPublishActionLabel(onAccentLabel),
          ),
        ],
      ),
    );
  }

  Widget _buildHeader({
    required CreateEditorState state,
    required double collapseProgress,
  }) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final onAccentLabel = AppColorsFunctional.getColor(
      isDark,
      ColorType.badgeForeground,
    );
    final title = _pageTitleForState(state);
    final titleColor = AppNavigationSemanticConstants.barTitleColor(isDark);
    return _buildCreateTopChromeBar(
      collapseProgress: collapseProgress,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          KeyedSubtree(
            key: TestKeys.createCloseButton,
            child: AppNavigationBarIconButton(
              icon: CupertinoIcons.back,
              onPressed: _onCloseRequest,
            ),
          ),
          Expanded(
            child: Center(
              child: Opacity(
                opacity: _isPhotoCreateFlow(state)
                    ? 1
                    : lerpDouble(0.34, 1, collapseProgress)!,
                child: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: titleColor,
                    fontSize: AppTypography.iosNavTitle,
                    fontWeight: AppTypography.regular,
                  ),
                ),
              ),
            ),
          ),
          _buildDraftToolbarAction(),
          SizedBox(width: AppSpacing.intraGroupSm),
          CupertinoButton(
            key: TestKeys.createPublishButton,
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
            minimumSize: const Size.square(AppSpacing.buttonHeightSm),
            color: AppColors.iosAccentLight,
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
            onPressed: _isPublishing
                ? (_publicationCancellationSignal == null
                      ? null
                      : _cancelPublicationUpload)
                : _publish,
            child: _buildPublishActionLabel(onAccentLabel),
          ),
        ],
      ),
    );
  }

  /// 共同经历回流上下文条：从行动入口进入创作时展示，作者可移除关联。
  /// 关联是否最终写入由 PublishSettings.gatheringRef 唯一决定。
  Widget _buildGatheringContextBar(CreateEditorState state) {
    final gatheringRef = state.settings.gatheringRef.trim();
    if (gatheringRef.isEmpty) {
      return const SizedBox.shrink();
    }
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final title = state.settings.gatheringTitle.trim().isEmpty
        ? CreatePageText.gatheringContextFallbackTitle
        : state.settings.gatheringTitle.trim();
    return Container(
      key: TestKeys.createGatheringContextBar,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.intraGroupSm,
      ),
      child: Row(
        children: <Widget>[
          Icon(
            CupertinoIcons.person_2,
            size: AppTypography.base,
            color: AppColors.primaryColor,
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(
            child: Text(
              '${CreatePageText.gatheringContextPrefix}$title'
              '${CreatePageText.gatheringContextSuffix}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(color: foreground, fontSize: AppTypography.sm),
            ),
          ),
          CupertinoButton(
            key: TestKeys.createGatheringContextRemove,
            padding: EdgeInsets.zero,
            minimumSize: const Size.square(AppSpacing.buttonHeightSm),
            onPressed: () {
              final notifier = ref.read(createEditorProvider.notifier);
              notifier.setSettings(
                ref
                    .read(createEditorProvider)
                    .settings
                    .copyWith(clearGatheringRef: true),
              );
            },
            child: Text(
              CreatePageText.gatheringContextRemove,
              style: TextStyle(
                color: foreground,
                fontSize: AppTypography.sm,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPublishActionLabel(Color onAccentLabel) {
    if (_isPublishing && _publicationCancellationSignal == null) {
      return AppRequestFeedback.inline(indicatorColor: onAccentLabel);
    }
    final cancellation = _publicationCancellationSignal;
    final progress = _publishUploadProgress;
    final label = cancellation == null || progress == null
        ? MediaText.mediaPickerNextStep
        : cancellation.isCancelled
        ? CreatePageText.uploadCancelling
        : '${(progress * 100).round()}% · ${CreatePageText.cancelUpload}';
    return Text(
      label,
      style: TextStyle(
        color: onAccentLabel,
        fontSize: AppTypography.base,
        fontWeight: AppTypography.semiBold,
      ),
    );
  }
}
