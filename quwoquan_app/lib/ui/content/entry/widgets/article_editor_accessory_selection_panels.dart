part of 'article_editor_accessory_panels.dart';

/// 列表、排版、模板与字体选择面板。
///
/// 这些组件只投影调用方传入的选择值并转发动作，不持有编辑器业务状态。
class ArticleEditorListPanel extends StatelessWidget {
  const ArticleEditorListPanel({
    super.key,
    required this.onStructureSelected,
    this.activeAction,
  });

  final ValueChanged<ArticleEditorStructureAction> onStructureSelected;
  final ArticleEditorStructureAction? activeAction;

  @override
  Widget build(BuildContext context) {
    return ListView(
      key: const ValueKey<String>('article_editor_list_panel'),
      physics: const BouncingScrollPhysics(),
      children: <Widget>[
        _AccessorySectionLabel(label: CreatePageText.listSection),
        SizedBox(height: AppSpacing.intraGroupSm),
        Wrap(
          spacing: AppSpacing.intraGroupSm,
          runSpacing: AppSpacing.intraGroupSm,
          children: <Widget>[
            _StructureChip(
              label: CreatePageText.numberedList,
              selected:
                  activeAction == ArticleEditorStructureAction.orderedList,
              onTap: () =>
                  onStructureSelected(ArticleEditorStructureAction.orderedList),
            ),
            _StructureChip(
              label: CreatePageText.bulletedList,
              selected: activeAction == ArticleEditorStructureAction.bulletList,
              onTap: () =>
                  onStructureSelected(ArticleEditorStructureAction.bulletList),
            ),
          ],
        ),
      ],
    );
  }
}

/// 排版：纸张质感 + 字体
class ArticleEditorTypographyPanel extends StatefulWidget {
  const ArticleEditorTypographyPanel({
    super.key,
    required this.paperTexture,
    required this.fontPreset,
    required this.onPaperTextureSelected,
    required this.onFontSelected,
  });

  final ArticlePaperTexture paperTexture;
  final ArticleFontPreset fontPreset;
  final ValueChanged<ArticlePaperTexture> onPaperTextureSelected;
  final ValueChanged<ArticleFontPreset> onFontSelected;

  @override
  State<ArticleEditorTypographyPanel> createState() =>
      _ArticleEditorTypographyPanelState();
}

class _ArticleEditorTypographyPanelState
    extends State<ArticleEditorTypographyPanel> {
  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        // 纸张质感选择器
        _AccessorySectionLabel(label: CreatePageText.paper),
        SizedBox(
          height: AppSpacing.avatarRailHeight,
          child: _PaperTextureSelector(
            selected: widget.paperTexture,
            onSelected: widget.onPaperTextureSelected,
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        // 字体选择器
        _AccessorySectionLabel(label: CreatePageText.font),
        SizedBox(
          height: AppSpacing.bottomNavHeight,
          child: _FontPresetSelector(
            selected: widget.fontPreset,
            onSelected: widget.onFontSelected,
          ),
        ),
      ],
    );
  }
}

class ArticleEditorStructurePanel extends StatelessWidget {
  const ArticleEditorStructurePanel({
    super.key,
    required this.onSelected,
    this.activeAction,
  });

  final ValueChanged<ArticleEditorStructureAction> onSelected;
  final ArticleEditorStructureAction? activeAction;

  @override
  Widget build(BuildContext context) {
    return ArticleEditorStylePanel(
      onStructureSelected: onSelected,
      activeAction: activeAction,
    );
  }
}

class _StructureChip extends StatelessWidget {
  const _StructureChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      minimumSize: const Size(44, AppSpacing.buttonHeightSm),
      color: selected
          ? AppColors.primaryColor.withValues(alpha: 0.14)
          : CupertinoColors.secondarySystemFill.resolveFrom(context),
      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      onPressed: onTap,
      child: Text(
        label,
        style: TextStyle(
          color: selected
              ? AppColors.primaryColor
              : CupertinoColors.label.resolveFrom(context),
          fontSize: AppTypography.sm,
          fontWeight: selected ? AppTypography.semiBold : AppTypography.medium,
        ),
      ),
    );
  }
}

class ArticleEditorTemplatePanel extends StatelessWidget {
  const ArticleEditorTemplatePanel({
    super.key,
    required this.selectedTemplate,
    required this.selectedFontPreset,
    required this.coverImagePaths,
    required this.selectedCoverPath,
    required this.onCoverSelected,
    required this.onSelected,
  });

  final ArticleTemplatePreset selectedTemplate;
  final ArticleFontPreset selectedFontPreset;
  final List<String> coverImagePaths;
  final String selectedCoverPath;
  final ValueChanged<String?> onCoverSelected;
  final ValueChanged<ArticleTemplatePreset> onSelected;

  @override
  Widget build(BuildContext context) {
    final coverCandidates = <String>[
      if (selectedCoverPath.trim().isNotEmpty &&
          !coverImagePaths.contains(selectedCoverPath.trim()))
        selectedCoverPath.trim(),
      ...coverImagePaths.where((path) => path.trim().isNotEmpty),
    ];
    return ListView(
      key: TestKeys.createTemplatePanel,
      physics: const BouncingScrollPhysics(),
      children: <Widget>[
        _AccessorySectionLabel(label: CreatePageText.cover),
        SizedBox(height: AppSpacing.intraGroupSm),
        _ArticleCoverPicker(
          imagePaths: coverCandidates,
          selectedCoverPath: selectedCoverPath,
          onSelected: onCoverSelected,
        ),
        if (coverCandidates.isEmpty) ...<Widget>[
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            CreatePageText.coverEmptyHint,
            style: TextStyle(
              color: CupertinoColors.secondaryLabel.resolveFrom(context),
              fontSize: AppTypography.xsPlus,
            ),
          ),
        ],
        SizedBox(height: AppSpacing.interGroupSm),
        _AccessorySectionLabel(label: CreatePageText.template),
        SizedBox(height: AppSpacing.intraGroupSm),
        Wrap(
          spacing: AppSpacing.containerSm,
          runSpacing: AppSpacing.containerSm,
          children: ArticleTemplatePreset.values
              .map((template) {
                return _AccessoryTemplateThumbnail(
                  template: template,
                  fontPreset: selectedFontPreset,
                  label: template.label,
                  selected: template == selectedTemplate,
                  onTap: () => onSelected(template),
                );
              })
              .toList(growable: false),
        ),
      ],
    );
  }
}

class _AccessoryTemplateThumbnail extends StatelessWidget {
  const _AccessoryTemplateThumbnail({
    required this.template,
    required this.fontPreset,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final palette = resolveArticleTemplatePalette(context, template);
    final typography = resolveArticleTypography(context, template, fontPreset);
    final borderColor = selected
        ? AppColors.primaryColor
        : CupertinoColors.separator.resolveFrom(context);
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          AnimatedContainer(
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOutCubic,
            width: AppSpacing.avatarUserXl,
            height: AppSpacing.oneHundred + AppSpacing.xs,
            padding: const EdgeInsets.all(AppSpacing.xs),
            decoration: BoxDecoration(
              color: palette.paperColor,
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              border: Border.all(color: borderColor, width: selected ? 2 : 1),
              boxShadow: <BoxShadow>[
                BoxShadow(
                  color: palette.shadowColor.withValues(alpha: 0.12),
                  blurRadius: AppSpacing.md,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Container(
                  height: AppSpacing.two,
                  decoration: BoxDecoration(
                    color: palette.accentColor.withValues(alpha: 0.28),
                    borderRadius: BorderRadius.circular(AppSpacing.radiusTwo),
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
                Container(
                  height: AppSpacing.six,
                  decoration: BoxDecoration(
                    color: palette.textColor.withValues(alpha: 0.88),
                    borderRadius: BorderRadius.circular(AppSpacing.radiusTwo),
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: typography.captionStyle.copyWith(
                    color: palette.textColor,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs),
                Container(
                  height: AppSpacing.two,
                  decoration: BoxDecoration(
                    color: palette.secondaryTextColor.withValues(alpha: 0.4),
                    borderRadius: BorderRadius.circular(AppSpacing.radiusTwo),
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs),
                Container(
                  height: AppSpacing.two,
                  decoration: BoxDecoration(
                    color: palette.secondaryTextColor.withValues(alpha: 0.26),
                    borderRadius: BorderRadius.circular(AppSpacing.radiusTwo),
                  ),
                ),
                const Spacer(),
                Align(
                  alignment: Alignment.centerLeft,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.intraGroupXs,
                      vertical: AppSpacing.two,
                    ),
                    decoration: BoxDecoration(
                      color: palette.badgeBackground,
                      borderRadius: BorderRadius.circular(
                        AppSpacing.radiusNinetyNine,
                      ),
                    ),
                    child: Text(label, style: typography.badgeStyle),
                  ),
                ),
              ],
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            label,
            style: TextStyle(
              color: CupertinoColors.label.resolveFrom(context),
              fontSize: AppTypography.sm,
              fontWeight: selected
                  ? AppTypography.semiBold
                  : AppTypography.medium,
            ),
          ),
        ],
      ),
    );
  }
}

class _ArticleCoverPicker extends StatelessWidget {
  const _ArticleCoverPicker({
    required this.imagePaths,
    required this.selectedCoverPath,
    required this.onSelected,
  });

  final List<String> imagePaths;
  final String selectedCoverPath;
  final ValueChanged<String?> onSelected;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      key: const ValueKey<String>('article_cover_picker'),
      scrollDirection: Axis.horizontal,
      child: Row(
        children: <Widget>[
          _ArticleCoverOption(
            key: TestKeys.createArticleCoverNoneOption,
            label: CreatePageText.noCover,
            selected: selectedCoverPath.trim().isEmpty,
            onTap: () => onSelected(null),
          ),
          for (var index = 0; index < imagePaths.length; index += 1)
            Padding(
              padding: EdgeInsets.only(left: AppSpacing.containerSm),
              child: _ArticleCoverOption(
                key: ValueKey<String>('create_article_cover_option_$index'),
                label: CreatePageText.coverLabel(index + 1),
                imagePath: imagePaths[index],
                selected: imagePaths[index] == selectedCoverPath,
                onTap: () => onSelected(imagePaths[index]),
              ),
            ),
        ],
      ),
    );
  }
}

class _ArticleCoverOption extends StatelessWidget {
  const _ArticleCoverOption({
    super.key,
    required this.label,
    required this.selected,
    required this.onTap,
    this.imagePath,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;
  final String? imagePath;

  @override
  Widget build(BuildContext context) {
    const coverThumbnailExtent = 92.0;
    final borderColor = selected
        ? AppColors.primaryColor
        : CupertinoColors.separator
              .resolveFrom(context)
              .withValues(alpha: 0.28);
    final background = selected
        ? AppColors.primaryColor.withValues(alpha: 0.08)
        : CupertinoColors.secondarySystemBackground.resolveFrom(context);
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOutCubic,
        width: coverThumbnailExtent,
        padding: EdgeInsets.all(AppSpacing.intraGroupXs),
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(color: borderColor, width: selected ? 1.5 : 1),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            ClipRRect(
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              child: SizedBox(
                height: coverThumbnailExtent,
                width: double.infinity,
                child: imagePath == null || imagePath!.trim().isEmpty
                    ? DecoratedBox(
                        decoration: BoxDecoration(
                          color: CupertinoColors.systemFill.resolveFrom(
                            context,
                          ),
                        ),
                        child: Center(
                          child: Icon(
                            CupertinoIcons.book,
                            color: CupertinoColors.secondaryLabel.resolveFrom(
                              context,
                            ),
                            size: AppSpacing.iconMedium,
                          ),
                        ),
                      )
                    : ArticleAdaptiveImage(imageUrl: imagePath!),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: CupertinoColors.label.resolveFrom(context),
                fontSize: AppTypography.xsPlus,
                fontWeight: selected
                    ? AppTypography.semiBold
                    : AppTypography.medium,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ArticleEditorFontPanel extends StatelessWidget {
  const ArticleEditorFontPanel({
    super.key,
    required this.selectedTemplate,
    required this.selectedFontPreset,
    required this.onSelected,
  });

  final ArticleTemplatePreset selectedTemplate;
  final ArticleFontPreset selectedFontPreset;
  final ValueChanged<ArticleFontPreset> onSelected;

  @override
  Widget build(BuildContext context) {
    return ListView(
      key: TestKeys.createFontPanel,
      physics: const BouncingScrollPhysics(),
      children: <Widget>[
        _AccessorySectionLabel(label: CreatePageText.font),
        SizedBox(height: AppSpacing.intraGroupSm),
        Wrap(
          spacing: AppSpacing.containerSm,
          runSpacing: AppSpacing.containerSm,
          children: ArticleFontPreset.values
              .map((preset) {
                return _FontPreviewCard(
                  preset: preset,
                  template: selectedTemplate,
                  selected: preset == selectedFontPreset,
                  onTap: () => onSelected(preset),
                );
              })
              .toList(growable: false),
        ),
      ],
    );
  }
}

class _FontPreviewCard extends StatelessWidget {
  const _FontPreviewCard({
    required this.preset,
    required this.template,
    required this.selected,
    required this.onTap,
  });

  final ArticleFontPreset preset;
  final ArticleTemplatePreset template;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    const fontPreviewCardWidth = 148.0;
    final typography = resolveArticleTypography(context, template, preset);
    final divider = CupertinoColors.separator.resolveFrom(context);
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOutCubic,
        width: fontPreviewCardWidth,
        padding: EdgeInsets.all(AppSpacing.containerSm),
        decoration: BoxDecoration(
          color: selected
              ? AppColors.primaryColor.withValues(alpha: 0.08)
              : CupertinoColors.secondarySystemBackground.resolveFrom(context),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(
            color: selected
                ? AppColors.primaryColor
                : divider.withValues(alpha: 0.28),
            width: selected ? 1.5 : AppSpacing.hairline,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              preset.label,
              style: TextStyle(
                color: CupertinoColors.label.resolveFrom(context),
                fontSize: AppTypography.sm,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              CreatePageText.typographyQualityTitle,
              maxLines: 2,
              style: typography.bodyStyle,
            ),
          ],
        ),
      ),
    );
  }
}

class _AccessorySectionLabel extends StatelessWidget {
  const _AccessorySectionLabel({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      style: TextStyle(
        color: CupertinoColors.secondaryLabel.resolveFrom(context),
        fontSize: AppTypography.xs,
        fontWeight: AppTypography.semiBold,
        letterSpacing: 0.1,
      ),
    );
  }
}
