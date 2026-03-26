import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/widgets/article_content_block_renderer.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

enum ArticleEditorAccessoryPanelType { none, emoji, structure, template, font }

enum ArticleEditorStructureAction {
  heading1,
  heading2,
  heading3,
  sectionTitle,
  orderedList,
  bulletList,
}

class ArticleEditorAccessoryHost extends StatelessWidget {
  const ArticleEditorAccessoryHost({
    super.key,
    required this.panelType,
    required this.panelHeight,
    required this.template,
    required this.fontPreset,
    required this.coverImagePaths,
    required this.selectedCoverPath,
    required this.emojiUsesKeyboardGlyph,
    required this.onImageTap,
    required this.onEmojiTap,
    required this.onStructureTap,
    required this.onTemplateTap,
    required this.onFontTap,
    required this.onEmojiSelected,
    required this.onStructureActionSelected,
    required this.onCoverSelected,
    required this.onTemplateSelected,
    required this.onFontSelected,
    this.activeStructureAction,
  });

  final ArticleEditorAccessoryPanelType panelType;
  final double panelHeight;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final List<String> coverImagePaths;
  final String selectedCoverPath;
  final bool emojiUsesKeyboardGlyph;
  final VoidCallback onImageTap;
  final VoidCallback onEmojiTap;
  final VoidCallback onStructureTap;
  final VoidCallback onTemplateTap;
  final VoidCallback onFontTap;
  final ValueChanged<String> onEmojiSelected;
  final ValueChanged<ArticleEditorStructureAction> onStructureActionSelected;
  final ValueChanged<String?> onCoverSelected;
  final ValueChanged<ArticleTemplatePreset> onTemplateSelected;
  final ValueChanged<ArticleFontPreset> onFontSelected;
  final ArticleEditorStructureAction? activeStructureAction;

  @override
  Widget build(BuildContext context) {
    final background = CupertinoColors.systemBackground
        .resolveFrom(context)
        .withValues(alpha: 0.98);
    final divider = CupertinoColors.separator
        .resolveFrom(context)
        .withValues(alpha: 0.3);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        border: Border(
          top: BorderSide(color: divider, width: AppSpacing.hairline),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          SizedBox(
            key: TestKeys.createAccessoryBar,
            height: SettingsSemanticConstants.toolbarHeightOverKeyboard,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(
                  maxWidth: AppSpacing.feedMaxContentWidth,
                ),
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                  ),
                  child: Row(
                    children: <Widget>[
                      ArticleEditorAccessoryButton(
                        buttonKey: TestKeys.createMediaAddButton,
                        glyph: ArticleEditorAccessoryGlyph.image,
                        semanticLabel: '图片',
                        onPressed: onImageTap,
                      ),
                      ArticleEditorAccessoryButton(
                        buttonKey: TestKeys.createAccessoryEmojiButton,
                        glyph: emojiUsesKeyboardGlyph
                            ? ArticleEditorAccessoryGlyph.keyboard
                            : ArticleEditorAccessoryGlyph.emoji,
                        semanticLabel: emojiUsesKeyboardGlyph ? '键盘' : '表情',
                        onPressed: onEmojiTap,
                        selected:
                            panelType == ArticleEditorAccessoryPanelType.emoji,
                      ),
                      ArticleEditorAccessoryButton(
                        buttonKey: TestKeys.createAccessoryStructureButton,
                        glyph: ArticleEditorAccessoryGlyph.structure,
                        semanticLabel: '结构',
                        onPressed: onStructureTap,
                        selected:
                            panelType ==
                            ArticleEditorAccessoryPanelType.structure,
                      ),
                      ArticleEditorAccessoryButton(
                        buttonKey: TestKeys.createAccessoryTemplateButton,
                        glyph: ArticleEditorAccessoryGlyph.template,
                        semanticLabel: '模版',
                        onPressed: onTemplateTap,
                        selected:
                            panelType ==
                            ArticleEditorAccessoryPanelType.template,
                      ),
                      ArticleEditorAccessoryButton(
                        buttonKey: TestKeys.createAccessoryFontButton,
                        glyph: ArticleEditorAccessoryGlyph.font,
                        semanticLabel: '字体',
                        onPressed: onFontTap,
                        selected:
                            panelType == ArticleEditorAccessoryPanelType.font,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          if (panelType != ArticleEditorAccessoryPanelType.none)
            SizedBox(
              key: TestKeys.createAccessoryPanel,
              height: panelHeight,
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(
                    maxWidth: AppSpacing.feedMaxContentWidth,
                  ),
                  child: Padding(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      AppSpacing.intraGroupSm,
                      AppSpacing.containerMd,
                      AppSpacing.containerMd,
                    ),
                    child: _AccessoryPanelSwitcher(
                      panelType: panelType,
                      template: template,
                      fontPreset: fontPreset,
                      coverImagePaths: coverImagePaths,
                      selectedCoverPath: selectedCoverPath,
                      onEmojiSelected: onEmojiSelected,
                      onStructureActionSelected: onStructureActionSelected,
                      onCoverSelected: onCoverSelected,
                      onTemplateSelected: onTemplateSelected,
                      onFontSelected: onFontSelected,
                      activeStructureAction: activeStructureAction,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _AccessoryPanelSwitcher extends StatelessWidget {
  const _AccessoryPanelSwitcher({
    required this.panelType,
    required this.template,
    required this.fontPreset,
    required this.coverImagePaths,
    required this.selectedCoverPath,
    required this.onEmojiSelected,
    required this.onStructureActionSelected,
    required this.onCoverSelected,
    required this.onTemplateSelected,
    required this.onFontSelected,
    this.activeStructureAction,
  });

  final ArticleEditorAccessoryPanelType panelType;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final List<String> coverImagePaths;
  final String selectedCoverPath;
  final ValueChanged<String> onEmojiSelected;
  final ValueChanged<ArticleEditorStructureAction> onStructureActionSelected;
  final ValueChanged<String?> onCoverSelected;
  final ValueChanged<ArticleTemplatePreset> onTemplateSelected;
  final ValueChanged<ArticleFontPreset> onFontSelected;
  final ArticleEditorStructureAction? activeStructureAction;

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 220),
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeOutCubic,
      child: switch (panelType) {
        ArticleEditorAccessoryPanelType.emoji => ArticleEditorEmojiPanel(
          key: const ValueKey<String>('emoji_panel'),
          onEmojiSelected: onEmojiSelected,
        ),
        ArticleEditorAccessoryPanelType.structure =>
          ArticleEditorStructurePanel(
            key: const ValueKey<String>('structure_panel'),
            activeAction: activeStructureAction,
            onSelected: onStructureActionSelected,
          ),
        ArticleEditorAccessoryPanelType.template => ArticleEditorTemplatePanel(
          key: const ValueKey<String>('template_panel'),
          selectedTemplate: template,
          selectedFontPreset: fontPreset,
          coverImagePaths: coverImagePaths,
          selectedCoverPath: selectedCoverPath,
          onCoverSelected: onCoverSelected,
          onSelected: onTemplateSelected,
        ),
        ArticleEditorAccessoryPanelType.font => ArticleEditorFontPanel(
          key: const ValueKey<String>('font_panel'),
          selectedTemplate: template,
          selectedFontPreset: fontPreset,
          onSelected: onFontSelected,
        ),
        ArticleEditorAccessoryPanelType.none => const SizedBox.shrink(),
      },
    );
  }
}

class ArticleEditorEmojiPanel extends ConsumerWidget {
  const ArticleEditorEmojiPanel({super.key, required this.onEmojiSelected});

  final ValueChanged<String> onEmojiSelected;

  int _emojiColumnCount(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    if (width < AppSpacing.compactBreakpoint) {
      return 7;
    }
    if (width >= AppSpacing.expandedBreakpoint) {
      return 10;
    }
    return 8;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final repoAsync = ref.watch(emojiRepositoryProvider);
    final recentEntries = repoAsync.when(
      data: (repo) => repo.getRecentEntries(),
      loading: () => const <EmojiEntry>[],
      error: (error, stackTrace) => const <EmojiEntry>[],
    );
    final allEntries = EmojiCatalog.categoryIds
        .expand(EmojiCatalog.getByCategory)
        .toList(growable: false);
    final fgColor = CupertinoColors.label.resolveFrom(context);
    final secondary = CupertinoColors.secondaryLabel.resolveFrom(context);
    final crossAxisCount = _emojiColumnCount(context);
    final emojiSize = AppSpacing.responsiveValue(
      context,
      compact: 28,
      regular: SettingsSemanticConstants.emojiIconFontSize,
      expanded: 30,
    );

    return ListView(
      key: TestKeys.createEmojiPanel,
      physics: const BouncingScrollPhysics(),
      children: <Widget>[
        if (recentEntries.isNotEmpty) ...<Widget>[
          _AccessorySectionLabel(label: '最近使用'),
          SizedBox(height: AppSpacing.intraGroupSm),
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: crossAxisCount,
              mainAxisSpacing: AppSpacing.intraGroupSm,
              crossAxisSpacing: AppSpacing.intraGroupSm,
            ),
            itemCount: recentEntries.length,
            itemBuilder: (context, index) {
              final entry = recentEntries[index];
              return _EmojiCell(
                char: entry.char,
                fontSize: emojiSize,
                color: fgColor,
                onTap: () {
                  onEmojiSelected(entry.char);
                  ref
                      .read(emojiRepositoryProvider.future)
                      .then((repo) => repo.recordEmojiUsed(entry.char));
                },
              );
            },
          ),
          SizedBox(height: AppSpacing.interGroupMd),
        ],
        _AccessorySectionLabel(label: '全部表情'),
        SizedBox(height: AppSpacing.intraGroupSm),
        GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: crossAxisCount,
            mainAxisSpacing: AppSpacing.intraGroupSm,
            crossAxisSpacing: AppSpacing.intraGroupSm,
          ),
          itemCount: allEntries.length,
          itemBuilder: (context, index) {
            final entry = allEntries[index];
            return _EmojiCell(
              char: entry.char,
              fontSize: emojiSize,
              color: fgColor,
              onTap: () {
                onEmojiSelected(entry.char);
                ref
                    .read(emojiRepositoryProvider.future)
                    .then((repo) => repo.recordEmojiUsed(entry.char));
              },
            );
          },
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        Text(
          '表情面板与系统键盘共用同一高度，切换时不改变工具栏位置。',
          style: TextStyle(
            color: secondary,
            fontSize: AppTypography.xs,
            height: AppSpacing.textLineHeightHeadline,
          ),
        ),
      ],
    );
  }
}

class _EmojiCell extends StatelessWidget {
  const _EmojiCell({
    required this.char,
    required this.fontSize,
    required this.color,
    required this.onTap,
  });

  final String char;
  final double fontSize;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size.square(AppSpacing.iconButtonMinSizeSm),
      onPressed: onTap,
      child: Center(
        child: Text(
          char,
          style: TextStyle(fontSize: fontSize, color: color),
        ),
      ),
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
    return ListView(
      key: TestKeys.createStructurePanel,
      physics: const BouncingScrollPhysics(),
      children: <Widget>[
        _AccessorySectionLabel(label: '标题'),
        SizedBox(height: AppSpacing.intraGroupSm),
        Wrap(
          spacing: AppSpacing.intraGroupSm,
          runSpacing: AppSpacing.intraGroupSm,
          children: <Widget>[
            _StructureChip(
              label: 'H1',
              selected: activeAction == ArticleEditorStructureAction.heading1,
              onTap: () => onSelected(ArticleEditorStructureAction.heading1),
            ),
            _StructureChip(
              label: 'H2',
              selected: activeAction == ArticleEditorStructureAction.heading2,
              onTap: () => onSelected(ArticleEditorStructureAction.heading2),
            ),
            _StructureChip(
              label: 'H3',
              selected: activeAction == ArticleEditorStructureAction.heading3,
              onTap: () => onSelected(ArticleEditorStructureAction.heading3),
            ),
            _StructureChip(
              label: '分节标题',
              selected:
                  activeAction == ArticleEditorStructureAction.sectionTitle,
              onTap: () =>
                  onSelected(ArticleEditorStructureAction.sectionTitle),
            ),
          ],
        ),
        SizedBox(height: AppSpacing.interGroupMd),
        _AccessorySectionLabel(label: '序号'),
        SizedBox(height: AppSpacing.intraGroupSm),
        Wrap(
          spacing: AppSpacing.intraGroupSm,
          runSpacing: AppSpacing.intraGroupSm,
          children: <Widget>[
            _StructureChip(
              label: '1. 数字序号',
              selected:
                  activeAction == ArticleEditorStructureAction.orderedList,
              onTap: () => onSelected(ArticleEditorStructureAction.orderedList),
            ),
            _StructureChip(
              label: '• 圆点序号',
              selected: activeAction == ArticleEditorStructureAction.bulletList,
              onTap: () => onSelected(ArticleEditorStructureAction.bulletList),
            ),
          ],
        ),
      ],
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
        _AccessorySectionLabel(label: '封面'),
        SizedBox(height: AppSpacing.intraGroupSm),
        _ArticleCoverPicker(
          imagePaths: coverCandidates,
          selectedCoverPath: selectedCoverPath,
          onSelected: onCoverSelected,
        ),
        if (coverCandidates.isEmpty) ...<Widget>[
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            '插入图片后可把其中一张设为扉页封面',
            style: TextStyle(
              color: CupertinoColors.secondaryLabel.resolveFrom(context),
              fontSize: AppTypography.xsPlus,
            ),
          ),
        ],
        SizedBox(height: AppSpacing.interGroupSm),
        _AccessorySectionLabel(label: '模版'),
        SizedBox(height: AppSpacing.intraGroupSm),
        Wrap(
          spacing: AppSpacing.containerSm,
          runSpacing: AppSpacing.containerSm,
          children: ArticleTemplatePreset.values
              .map((template) {
                return ArticleTemplateThumbnail(
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
            label: '无封面',
            selected: selectedCoverPath.trim().isEmpty,
            onTap: () => onSelected(null),
          ),
          for (var index = 0; index < imagePaths.length; index += 1)
            Padding(
              padding: EdgeInsets.only(left: AppSpacing.containerSm),
              child: _ArticleCoverOption(
                key: ValueKey<String>('create_article_cover_option_$index'),
                label: '封面 ${index + 1}',
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
        _AccessorySectionLabel(label: '字体'),
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
            Text('高质量文字排版', maxLines: 2, style: typography.bodyStyle),
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

enum ArticleEditorAccessoryGlyph {
  image,
  emoji,
  keyboard,
  structure,
  template,
  font,
}

class ArticleEditorAccessoryButton extends StatelessWidget {
  const ArticleEditorAccessoryButton({
    super.key,
    required this.glyph,
    required this.semanticLabel,
    required this.onPressed,
    this.selected = false,
    this.buttonKey,
  });

  final ArticleEditorAccessoryGlyph glyph;
  final String semanticLabel;
  final VoidCallback onPressed;
  final bool selected;
  final Key? buttonKey;

  @override
  Widget build(BuildContext context) {
    final color = selected
        ? CupertinoColors.label.resolveFrom(context)
        : CupertinoColors.label.resolveFrom(context).withValues(alpha: 0.78);
    final iconSize = AppSpacing.responsiveValue(
      context,
      compact: 20,
      regular: 22,
      expanded: 23,
    );
    final strokeWidth = AppSpacing.responsiveValue(
      context,
      compact: 1.5,
      regular: 1.65,
      expanded: 1.8,
    );

    return Expanded(
      child: Semantics(
        button: true,
        label: semanticLabel,
        child: CupertinoButton(
          key: buttonKey,
          padding: EdgeInsets.zero,
          minimumSize: const Size.square(AppSpacing.iconButtonMinSizeSm),
          onPressed: onPressed,
          child: Center(
            child: SizedBox(
              width: iconSize,
              height: iconSize,
              child: CustomPaint(
                painter: _AccessoryGlyphPainter(
                  glyph: glyph,
                  color: color,
                  strokeWidth: strokeWidth,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _AccessoryGlyphPainter extends CustomPainter {
  const _AccessoryGlyphPainter({
    required this.glyph,
    required this.color,
    required this.strokeWidth,
  });

  final ArticleEditorAccessoryGlyph glyph;
  final Color color;
  final double strokeWidth;

  @override
  void paint(Canvas canvas, Size size) {
    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final fill = Paint()
      ..color = color
      ..style = PaintingStyle.fill;

    switch (glyph) {
      case ArticleEditorAccessoryGlyph.image:
        final rect = RRect.fromRectAndRadius(
          Rect.fromLTWH(
            size.width * 0.08,
            size.height * 0.08,
            size.width * 0.84,
            size.height * 0.84,
          ),
          Radius.circular(size.width * 0.16),
        );
        canvas.drawRRect(rect, stroke);
        canvas.drawCircle(
          Offset(size.width * 0.72, size.height * 0.32),
          size.width * 0.07,
          fill,
        );
        final path = Path()
          ..moveTo(size.width * 0.18, size.height * 0.72)
          ..lineTo(size.width * 0.4, size.height * 0.48)
          ..lineTo(size.width * 0.54, size.height * 0.62)
          ..lineTo(size.width * 0.76, size.height * 0.4);
        canvas.drawPath(path, stroke);
      case ArticleEditorAccessoryGlyph.emoji:
        canvas.drawCircle(
          Offset(size.width / 2, size.height / 2),
          size.width * 0.42,
          stroke,
        );
        canvas.drawCircle(
          Offset(size.width * 0.38, size.height * 0.42),
          size.width * 0.045,
          fill,
        );
        canvas.drawCircle(
          Offset(size.width * 0.62, size.height * 0.42),
          size.width * 0.045,
          fill,
        );
        canvas.drawArc(
          Rect.fromLTWH(
            size.width * 0.28,
            size.height * 0.42,
            size.width * 0.44,
            size.height * 0.28,
          ),
          0.15 * math.pi,
          0.7 * math.pi,
          false,
          stroke,
        );
      case ArticleEditorAccessoryGlyph.keyboard:
        final rect = RRect.fromRectAndRadius(
          Rect.fromLTWH(
            size.width * 0.08,
            size.height * 0.18,
            size.width * 0.84,
            size.height * 0.64,
          ),
          Radius.circular(size.width * 0.12),
        );
        canvas.drawRRect(rect, stroke);
        for (var row = 0; row < 2; row += 1) {
          final y = row == 0 ? size.height * 0.36 : size.height * 0.52;
          for (var column = 0; column < 4; column += 1) {
            final x = size.width * (0.24 + column * 0.16);
            canvas.drawCircle(Offset(x, y), size.width * 0.03, fill);
          }
        }
        canvas.drawLine(
          Offset(size.width * 0.28, size.height * 0.66),
          Offset(size.width * 0.72, size.height * 0.66),
          stroke,
        );
      case ArticleEditorAccessoryGlyph.structure:
        canvas.drawLine(
          Offset(size.width * 0.36, size.height * 0.12),
          Offset(size.width * 0.28, size.height * 0.88),
          stroke,
        );
        canvas.drawLine(
          Offset(size.width * 0.68, size.height * 0.12),
          Offset(size.width * 0.6, size.height * 0.88),
          stroke,
        );
        canvas.drawLine(
          Offset(size.width * 0.16, size.height * 0.38),
          Offset(size.width * 0.84, size.height * 0.32),
          stroke,
        );
        canvas.drawLine(
          Offset(size.width * 0.12, size.height * 0.64),
          Offset(size.width * 0.8, size.height * 0.58),
          stroke,
        );
      case ArticleEditorAccessoryGlyph.template:
        final rect = RRect.fromRectAndRadius(
          Rect.fromLTWH(
            size.width * 0.14,
            size.height * 0.12,
            size.width * 0.72,
            size.height * 0.76,
          ),
          Radius.circular(size.width * 0.14),
        );
        canvas.drawRRect(rect, stroke);
        canvas.drawLine(
          Offset(size.width * 0.5, size.height * 0.22),
          Offset(size.width * 0.5, size.height * 0.78),
          stroke,
        );
        canvas.drawLine(
          Offset(size.width * 0.24, size.height * 0.5),
          Offset(size.width * 0.76, size.height * 0.5),
          stroke,
        );
      case ArticleEditorAccessoryGlyph.font:
        final path = Path()
          ..moveTo(size.width * 0.18, size.height * 0.86)
          ..lineTo(size.width * 0.5, size.height * 0.14)
          ..lineTo(size.width * 0.82, size.height * 0.86)
          ..moveTo(size.width * 0.32, size.height * 0.56)
          ..lineTo(size.width * 0.68, size.height * 0.56);
        canvas.drawPath(path, stroke);
    }
  }

  @override
  bool shouldRepaint(covariant _AccessoryGlyphPainter oldDelegate) {
    return oldDelegate.glyph != glyph ||
        oldDelegate.color != color ||
        oldDelegate.strokeWidth != strokeWidth;
  }
}
