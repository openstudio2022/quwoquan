import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/widgets/article_content_block_renderer.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

enum ArticleEditorAccessoryPanelType { none, emoji, style, list, typography }

enum ArticleEditorStructureAction {
  titleNone,
  titleMajor,
  titleMinor,
  orderedList,
  bulletList,
}

class ArticleEditorAccessoryHost extends StatelessWidget {
  const ArticleEditorAccessoryHost({
    super.key,
    required this.panelType,
    required this.panelHeight,
    required this.template,
    required this.paperTexture,
    required this.fontPreset,
    required this.coverImagePaths,
    required this.selectedCoverPath,
    required this.onImageTap,
    required this.onEmojiTap,
    required this.onStyleTap,
    required this.onListTap,
    required this.onTypographyTap,
    required this.onUndo,
    required this.onRedo,
    required this.canUndo,
    required this.canRedo,
    required this.onEmojiSelected,
    required this.onStructureActionSelected,
    required this.onCoverSelected,
    required this.onTemplateSelected,
    required this.onPaperTextureSelected,
    required this.onFontSelected,
    this.activeStructureAction,
    this.showTopHairline = true,
  });

  final ArticleEditorAccessoryPanelType panelType;
  final double panelHeight;
  final ArticleTemplatePreset template;
  final ArticlePaperTexture paperTexture;
  final ArticleFontPreset fontPreset;
  final List<String> coverImagePaths;
  final String selectedCoverPath;
  final VoidCallback onImageTap;
  final VoidCallback onEmojiTap;
  final VoidCallback onStyleTap;
  final VoidCallback onListTap;
  final VoidCallback onTypographyTap;
  final VoidCallback onUndo;
  final VoidCallback onRedo;
  final bool canUndo;
  final bool canRedo;
  final ValueChanged<String> onEmojiSelected;
  final ValueChanged<ArticleEditorStructureAction> onStructureActionSelected;
  final ValueChanged<String?> onCoverSelected;
  final ValueChanged<ArticleTemplatePreset> onTemplateSelected;
  final ValueChanged<ArticlePaperTexture> onPaperTextureSelected;
  final ValueChanged<ArticleFontPreset> onFontSelected;
  final ArticleEditorStructureAction? activeStructureAction;
  /// 为 `false` 时不画上边框，便于与紧贴在上方的条（如文内图工具栏）共用一条分割线。
  final bool showTopHairline;

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
        border: showTopHairline
            ? Border(
                top: BorderSide(color: divider, width: AppSpacing.hairline),
              )
            : null,
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
                        glyph: panelType == ArticleEditorAccessoryPanelType.emoji
                            ? ArticleEditorAccessoryGlyph.keyboard
                            : ArticleEditorAccessoryGlyph.emoji,
                        semanticLabel:
                            panelType == ArticleEditorAccessoryPanelType.emoji
                            ? '键盘'
                            : '表情',
                        onPressed: onEmojiTap,
                        selected:
                            panelType == ArticleEditorAccessoryPanelType.emoji,
                      ),
                      ArticleEditorAccessoryButton(
                        buttonKey: TestKeys.createAccessoryStructureButton,
                        glyph: panelType == ArticleEditorAccessoryPanelType.style
                            ? ArticleEditorAccessoryGlyph.keyboard
                            : ArticleEditorAccessoryGlyph.style,
                        semanticLabel:
                            panelType == ArticleEditorAccessoryPanelType.style
                            ? '键盘'
                            : '样式',
                        onPressed: onStyleTap,
                        selected:
                            panelType == ArticleEditorAccessoryPanelType.style,
                      ),
                      ArticleEditorAccessoryButton(
                        buttonKey: TestKeys.createAccessoryTemplateButton,
                        glyph: panelType == ArticleEditorAccessoryPanelType.list
                            ? ArticleEditorAccessoryGlyph.keyboard
                            : ArticleEditorAccessoryGlyph.list,
                        semanticLabel:
                            panelType == ArticleEditorAccessoryPanelType.list
                            ? '键盘'
                            : '序号',
                        onPressed: onListTap,
                        selected:
                            panelType == ArticleEditorAccessoryPanelType.list,
                      ),
                      ArticleEditorAccessoryButton(
                        buttonKey: TestKeys.createAccessoryFontButton,
                        glyph: panelType ==
                                ArticleEditorAccessoryPanelType.typography
                            ? ArticleEditorAccessoryGlyph.keyboard
                            : ArticleEditorAccessoryGlyph.typography,
                        semanticLabel: panelType ==
                                ArticleEditorAccessoryPanelType.typography
                            ? '键盘'
                            : '排版',
                        onPressed: onTypographyTap,
                        selected: panelType ==
                            ArticleEditorAccessoryPanelType.typography,
                      ),
                      Padding(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.intraGroupXs,
                        ),
                        child: SizedBox(
                          height: AppSpacing.iconMedium,
                          width: AppSpacing.hairline,
                          child: ColoredBox(
                            color: divider,
                          ),
                        ),
                      ),
                      _AccessoryIconButton(
                        icon: CupertinoIcons.arrow_uturn_left,
                        semanticLabel: '撤销',
                        onPressed: canUndo ? onUndo : null,
                      ),
                      _AccessoryIconButton(
                        icon: CupertinoIcons.arrow_uturn_right,
                        semanticLabel: '重做',
                        onPressed: canRedo ? onRedo : null,
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
                      paperTexture: paperTexture,
                      fontPreset: fontPreset,
                      coverImagePaths: coverImagePaths,
                      selectedCoverPath: selectedCoverPath,
                      onEmojiSelected: onEmojiSelected,
                      onStructureActionSelected: onStructureActionSelected,
                      onCoverSelected: onCoverSelected,
                      onTemplateSelected: onTemplateSelected,
                      onPaperTextureSelected: onPaperTextureSelected,
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
    required this.paperTexture,
    required this.fontPreset,
    required this.coverImagePaths,
    required this.selectedCoverPath,
    required this.onEmojiSelected,
    required this.onStructureActionSelected,
    required this.onCoverSelected,
    required this.onTemplateSelected,
    required this.onPaperTextureSelected,
    required this.onFontSelected,
    this.activeStructureAction,
  });

  final ArticleEditorAccessoryPanelType panelType;
  final ArticleTemplatePreset template;
  final ArticlePaperTexture paperTexture;
  final ArticleFontPreset fontPreset;
  final List<String> coverImagePaths;
  final String selectedCoverPath;
  final ValueChanged<String> onEmojiSelected;
  final ValueChanged<ArticleEditorStructureAction> onStructureActionSelected;
  final ValueChanged<String?> onCoverSelected;
  final ValueChanged<ArticleTemplatePreset> onTemplateSelected;
  final ValueChanged<ArticlePaperTexture> onPaperTextureSelected;
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
        ArticleEditorAccessoryPanelType.style => ArticleEditorStylePanel(
          key: const ValueKey<String>('style_panel'),
          activeAction: activeStructureAction,
          onStructureSelected: onStructureActionSelected,
        ),
        ArticleEditorAccessoryPanelType.list => ArticleEditorListPanel(
          key: const ValueKey<String>('list_panel'),
          onStructureSelected: onStructureActionSelected,
          activeAction: activeStructureAction,
        ),
        ArticleEditorAccessoryPanelType.typography =>
          ArticleEditorTypographyPanel(
            key: const ValueKey<String>('typography_panel'),
            template: template,
            paperTexture: paperTexture,
            fontPreset: fontPreset,
            coverImagePaths: coverImagePaths,
            selectedCoverPath: selectedCoverPath,
            onCoverSelected: onCoverSelected,
            onTemplateSelected: onTemplateSelected,
            onPaperTextureSelected: onPaperTextureSelected,
            onFontSelected: onFontSelected,
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

/// 样式面板：标题层级 + 行内样式入口（粗斜体等于后续富文本接入）
class ArticleEditorStylePanel extends StatelessWidget {
  const ArticleEditorStylePanel({
    super.key,
    required this.onStructureSelected,
    this.activeAction,
  });

  final ValueChanged<ArticleEditorStructureAction> onStructureSelected;
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
              label: '无标题',
              selected: activeAction == ArticleEditorStructureAction.titleNone,
              onTap: () =>
                  onStructureSelected(ArticleEditorStructureAction.titleNone),
            ),
            _StructureChip(
              label: '大标题',
              selected: activeAction == ArticleEditorStructureAction.titleMajor,
              onTap: () =>
                  onStructureSelected(ArticleEditorStructureAction.titleMajor),
            ),
            _StructureChip(
              label: '小标题',
              selected: activeAction == ArticleEditorStructureAction.titleMinor,
              onTap: () =>
                  onStructureSelected(ArticleEditorStructureAction.titleMinor),
            ),
          ],
        ),
        SizedBox(height: AppSpacing.interGroupMd),
        _AccessorySectionLabel(label: '字样式'),
        SizedBox(height: AppSpacing.intraGroupSm),
        Wrap(
          spacing: AppSpacing.intraGroupSm,
          runSpacing: AppSpacing.intraGroupSm,
          children: <Widget>[
            _StructureChip(label: 'B', selected: false, onTap: () {}),
            _StructureChip(label: 'I', selected: false, onTap: () {}),
            _StructureChip(label: 'U', selected: false, onTap: () {}),
            _StructureChip(label: 'S', selected: false, onTap: () {}),
          ],
        ),
        SizedBox(height: AppSpacing.interGroupMd),
        _AccessorySectionLabel(label: '对齐'),
        SizedBox(height: AppSpacing.intraGroupSm),
        Wrap(
          spacing: AppSpacing.intraGroupSm,
          runSpacing: AppSpacing.intraGroupSm,
          children: <Widget>[
            _StructureChip(label: '左', selected: false, onTap: () {}),
            _StructureChip(label: '中', selected: false, onTap: () {}),
            _StructureChip(label: '右', selected: false, onTap: () {}),
            _StructureChip(label: '两端', selected: false, onTap: () {}),
          ],
        ),
      ],
    );
  }
}

/// 序号与列表层级（≤3）
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
              onTap: () =>
                  onStructureSelected(ArticleEditorStructureAction.orderedList),
            ),
            _StructureChip(
              label: '• 圆点序号',
              selected: activeAction == ArticleEditorStructureAction.bulletList,
              onTap: () =>
                  onStructureSelected(ArticleEditorStructureAction.bulletList),
            ),
          ],
        ),
        SizedBox(height: AppSpacing.interGroupMd),
        _AccessorySectionLabel(label: '层级'),
        SizedBox(height: AppSpacing.intraGroupSm),
        Wrap(
          spacing: AppSpacing.intraGroupSm,
          runSpacing: AppSpacing.intraGroupSm,
          children: <Widget>[
            _StructureChip(label: '1 级', selected: true, onTap: () {}),
            _StructureChip(label: '2 级', selected: false, onTap: () {}),
            _StructureChip(label: '3 级', selected: false, onTap: () {}),
          ],
        ),
      ],
    );
  }
}

/// 排版：模版 Tab + 字号 Tab
class ArticleEditorTypographyPanel extends StatefulWidget {
  const ArticleEditorTypographyPanel({
    super.key,
    required this.template,
    required this.paperTexture,
    required this.fontPreset,
    required this.coverImagePaths,
    required this.selectedCoverPath,
    required this.onCoverSelected,
    required this.onTemplateSelected,
    required this.onPaperTextureSelected,
    required this.onFontSelected,
  });

  final ArticleTemplatePreset template;
  final ArticlePaperTexture paperTexture;
  final ArticleFontPreset fontPreset;
  final List<String> coverImagePaths;
  final String selectedCoverPath;
  final ValueChanged<String?> onCoverSelected;
  final ValueChanged<ArticleTemplatePreset> onTemplateSelected;
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
        _AccessorySectionLabel(label: '纸张'),
        SizedBox(
          height: AppSpacing.avatarRailHeight,
          child: _PaperTextureSelector(
            selected: widget.paperTexture,
            onSelected: widget.onPaperTextureSelected,
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        // 字体选择器
        _AccessorySectionLabel(label: '字体'),
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

class _AccessoryIconButton extends StatelessWidget {
  const _AccessoryIconButton({
    required this.icon,
    required this.semanticLabel,
    required this.onPressed,
  });

  final IconData icon;
  final String semanticLabel;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    final color = enabled
        ? CupertinoColors.label.resolveFrom(context)
        : CupertinoColors.tertiaryLabel.resolveFrom(context);
    return SizedBox(
      width: AppSpacing.minInteractiveSize,
      child: Semantics(
        button: true,
        label: semanticLabel,
        enabled: enabled,
        child: CupertinoButton(
          padding: EdgeInsets.zero,
          minimumSize: const Size.square(AppSpacing.iconButtonMinSizeSm),
          onPressed: onPressed,
          child: Icon(icon, size: AppSpacing.iconMedium, color: color),
        ),
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
  style,
  list,
  typography,
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
      case ArticleEditorAccessoryGlyph.style:
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
      case ArticleEditorAccessoryGlyph.list:
        for (var row = 0; row < 3; row += 1) {
          final y = size.height * (0.28 + row * 0.2);
          canvas.drawCircle(
            Offset(size.width * 0.18, y),
            size.width * 0.03,
            fill,
          );
          canvas.drawLine(
            Offset(size.width * 0.28, y),
            Offset(size.width * 0.84, y),
            stroke,
          );
        }
      case ArticleEditorAccessoryGlyph.typography:
        final rect = RRect.fromRectAndRadius(
          Rect.fromLTWH(
            size.width * 0.12,
            size.height * 0.12,
            size.width * 0.76,
            size.height * 0.76,
          ),
          Radius.circular(size.width * 0.12),
        );
        canvas.drawRRect(rect, stroke);
        canvas.drawLine(
          Offset(size.width * 0.5, size.height * 0.18),
          Offset(size.width * 0.5, size.height * 0.82),
          stroke,
        );
        final path = Path()
          ..moveTo(size.width * 0.58, size.height * 0.72)
          ..lineTo(size.width * 0.78, size.height * 0.22)
          ..lineTo(size.width * 0.88, size.height * 0.72);
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

// ── 纸张质感滤镜式横滑选择器 ──

class _PaperTextureSelector extends StatelessWidget {
  const _PaperTextureSelector({
    required this.selected,
    required this.onSelected,
  });

  final ArticlePaperTexture selected;
  final ValueChanged<ArticlePaperTexture> onSelected;

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      scrollDirection: Axis.horizontal,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      itemCount: ArticlePaperTexture.values.length,
      separatorBuilder: (_, __) =>
          SizedBox(width: AppSpacing.filterTemplateItemGap),
      itemBuilder: (context, index) {
        final texture = ArticlePaperTexture.values[index];
        final isSelected = texture == selected;
        final palette = resolveArticlePaperPalette(context, texture);
        final labelColor =
            CupertinoColors.secondaryLabel.resolveFrom(context);
        return GestureDetector(
          onTap: () => onSelected(texture),
          child: SizedBox(
            width: AppSpacing.largeAvatarSize,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  curve: Curves.easeOutCubic,
                  width: AppSpacing.avatarCircleLg,
                  height: AppSpacing.avatarCircleLg,
                  decoration: BoxDecoration(
                    color: palette.paperColor,
                    borderRadius:
                        BorderRadius.circular(AppSpacing.borderRadius),
                    border: Border.all(
                      color: isSelected
                          ? CupertinoColors.activeBlue.resolveFrom(context)
                          : palette.paperBorderColor,
                      width: isSelected ? 2.5 : 1,
                    ),
                  ),
                  child: Center(
                    child: Text(
                      '文',
                      style: TextStyle(
                        fontSize: AppTypography.lg,
                        fontWeight: AppTypography.medium,
                        color: palette.textColor,
                      ),
                    ),
                  ),
                ),
                SizedBox(height: AppSpacing.xs),
                Text(
                  texture.label,
                  style: TextStyle(
                    fontSize: AppTypography.xxs,
                    fontWeight:
                        isSelected ? AppTypography.semiBold : AppTypography.regular,
                    color: isSelected
                        ? CupertinoColors.label.resolveFrom(context)
                        : labelColor,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _FontPresetSelector extends StatelessWidget {
  const _FontPresetSelector({
    required this.selected,
    required this.onSelected,
  });

  final ArticleFontPreset selected;
  final ValueChanged<ArticleFontPreset> onSelected;

  @override
  Widget build(BuildContext context) {
    final labelColor = CupertinoColors.secondaryLabel.resolveFrom(context);
    return ListView.separated(
      scrollDirection: Axis.horizontal,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      itemCount: ArticleFontPreset.values.length,
      separatorBuilder: (_, __) =>
          SizedBox(width: AppSpacing.filterTemplateItemGap),
      itemBuilder: (context, index) {
        final preset = ArticleFontPreset.values[index];
        final isSelected = preset == selected;
        final fontFamily = switch (preset) {
          ArticleFontPreset.classic => 'Songti SC',
          ArticleFontPreset.handwritten => 'Kaiti SC',
          ArticleFontPreset.rounded => 'SF Pro Rounded',
          ArticleFontPreset.mono => 'Menlo',
          ArticleFontPreset.clean => null,
        };
        return GestureDetector(
          onTap: () => onSelected(preset),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOutCubic,
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.containerSm,
              vertical: AppSpacing.sm,
            ),
            decoration: BoxDecoration(
              color: isSelected
                  ? CupertinoColors.tertiarySystemFill.resolveFrom(context)
                  : CupertinoColors.systemBackground
                      .resolveFrom(context)
                      .withValues(alpha: 0),
              borderRadius:
                  BorderRadius.circular(AppSpacing.borderRadius),
              border: Border.all(
                color: isSelected
                    ? CupertinoColors.activeBlue.resolveFrom(context)
                    : CupertinoColors.separator.resolveFrom(context),
                width: isSelected ? 2 : 0.5,
              ),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                Text(
                  '春江',
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontFamily: fontFamily,
                    fontFamilyFallback: const <String>['PingFang SC'],
                    color: CupertinoColors.label.resolveFrom(context),
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  preset.label,
                  style: TextStyle(
                    fontSize: AppTypography.xxs,
                    fontWeight: isSelected
                        ? AppTypography.semiBold
                        : AppTypography.regular,
                    color: isSelected
                        ? CupertinoColors.label.resolveFrom(context)
                        : labelColor,
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
