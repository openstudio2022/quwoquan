part of 'create_page.dart';

/// 创作页共享表面与局部组件。
///
/// 这里只承载无独立状态的视图构建逻辑；编辑、草稿与发布状态仍唯一归属
/// [_CreatePageState]。
extension _CreatePageStateSurfaceHelpers on _CreatePageState {
  Widget _buildRollbackBanner(Color secondary) {
    return Container(
      margin: EdgeInsets.only(bottom: AppSpacing.interGroupMd),
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: AppColors.primaryColor.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Text(
        CreatePageText.editorFallbackBanner,
        style: TextStyle(color: secondary, fontSize: AppTypography.sm),
      ),
    );
  }

  /// 创作/沉浸文章顶栏共用：毛玻璃 + 底部分割线，并向上延伸至状态栏区域使背景连续。
  Widget _buildCreateTopChromeBar({
    required double collapseProgress,
    required Widget child,
    bool immersiveDark = false,
  }) {
    final divider = immersiveDark
        ? AppColors.white.withValues(alpha: 0.12)
        : CupertinoColors.separator.resolveFrom(context);
    final chrome = immersiveDark
        ? AppColors.black
        : CupertinoColors.systemBackground
              .resolveFrom(context)
              .withValues(alpha: lerpDouble(0.78, 0.94, collapseProgress)!);
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: AppSpacing.sm, sigmaY: AppSpacing.sm),
        child: Container(
          padding: EdgeInsets.only(
            top: MediaQuery.viewPaddingOf(context).top,
            left: AppSpacing.containerSm,
            right: AppSpacing.containerSm,
          ),
          decoration: BoxDecoration(
            color: chrome,
            border: Border(
              bottom: BorderSide(
                color: divider.withValues(alpha: immersiveDark ? 0.12 : 0.45),
                width: AppSpacing.hairline,
              ),
            ),
          ),
          child: SizedBox(height: AppSpacing.toolbarHeight, child: child),
        ),
      ),
    );
  }

  Future<void> _insertEntityMentionFromSelection(
    String nodeId,
    int start,
    int end,
  ) async {
    final selection = await pickArticleEntityMentionHomepage(context);
    if (!mounted || selection == null) return;
    final canonical = selection.canonicalEntityId?.trim() ?? '';
    if (canonical.isEmpty) {
      return;
    }
    ref
        .read(createEditorProvider.notifier)
        .attachArticleEntityMention(
          nodeId,
          start,
          end,
          targetType: 'entity',
          targetId: canonical,
          displayText: selection.title,
        );
  }

  Widget _buildMediaComposerSection({
    required CreateEditorState state,
    required String title,
    required String trailing,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _buildSectionHeader(title: title, trailing: trailing),
        SizedBox(height: AppSpacing.intraGroupSm),
        _buildSurfacePanel(
          padding: EdgeInsets.all(AppSpacing.containerSm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              _buildMediaStrip(
                state: state,
                onAdd: state.hasVideo
                    ? _pickVideoForMedia
                    : _pickImagesForCurrentEditor,
                onTapImage: _editCurrentImage,
                onRemove: (index) {
                  if (state.mediaKind == CreateMediaKind.video) {
                    ref.read(createEditorProvider.notifier).clearVideo();
                  } else {
                    ref
                        .read(createEditorProvider.notifier)
                        .removeImageAt(index);
                  }
                },
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSectionHeader({required String title, String? trailing}) {
    return Row(
      children: <Widget>[
        if (title.trim().isNotEmpty)
          Text(
            title,
            style: TextStyle(
              color: CupertinoColors.secondaryLabel.resolveFrom(context),
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.semiBold,
              letterSpacing: 0.2,
            ),
          ),
        const Spacer(),
        if (trailing != null)
          Text(
            trailing,
            style: TextStyle(
              color: CupertinoColors.secondaryLabel.resolveFrom(context),
              fontSize: AppTypography.sm,
            ),
          ),
      ],
    );
  }

  Widget _buildSurfacePanel({required Widget child, EdgeInsets? padding}) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final panelBackground = CupertinoColors.secondarySystemGroupedBackground
        .resolveFrom(context);
    final separator = CupertinoColors.separator.resolveFrom(context);
    return Container(
      padding: padding ?? EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: panelBackground,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(
          color: separator.withValues(alpha: 0.18),
          width: AppSpacing.hairline,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.foregroundPrimary,
            ).withValues(alpha: isDark ? 0.2 : 0.04),
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: child,
    );
  }
}
