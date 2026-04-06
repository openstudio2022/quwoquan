import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Icons, TextDirection, TextPainter, TextSpan, TextStyle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/article_theme.dart';
import 'package:quwoquan_app/ui/content/widgets/article_content_block_renderer.dart';

enum ArticleEditorAccessoryPanelType { none, emoji, style }

enum ArticleEditorStructureAction {
  titleNone,
  titleMajor,
  titleMinor,
  headingMajor,
  headingMinor,
  paragraph,
  orderedList,
  bulletList,
  blockquote,
}

class ArticleEditorAccessoryHost extends StatelessWidget {
  const ArticleEditorAccessoryHost({
    super.key,
    required this.panelType,
    required this.panelHeight,
    required this.onImageTap,
    required this.onEmojiTap,
    required this.onStyleTap,
    required this.onUndo,
    required this.onRedo,
    required this.canUndo,
    required this.canRedo,
    required this.onEmojiSelected,
    required this.onStructureActionSelected,
    this.activeStructureAction,
    this.showTopHairline = true,
    this.onToggleBold,
    this.onToggleItalic,
    this.onToggleUnderline,
    this.isBoldActive = false,
    this.isItalicActive = false,
    this.isUnderlineActive = false,
    this.activeAlignment = 'left',
    this.onAlignmentSelected,
  });

  final ArticleEditorAccessoryPanelType panelType;
  final double panelHeight;
  final VoidCallback onImageTap;
  final VoidCallback onEmojiTap;
  final VoidCallback onStyleTap;
  final VoidCallback onUndo;
  final VoidCallback onRedo;
  final bool canUndo;
  final bool canRedo;
  final ValueChanged<String> onEmojiSelected;
  final ValueChanged<ArticleEditorStructureAction> onStructureActionSelected;
  final ArticleEditorStructureAction? activeStructureAction;
  /// 为 `false` 时不画上边框，便于与紧贴在上方的条（如文内图工具栏）共用一条分割线。
  final bool showTopHairline;
  final VoidCallback? onToggleBold;
  final VoidCallback? onToggleItalic;
  final VoidCallback? onToggleUnderline;
  final bool isBoldActive;
  final bool isItalicActive;
  final bool isUnderlineActive;
  final String activeAlignment;
  final ValueChanged<String>? onAlignmentSelected;

  @override
  Widget build(BuildContext context) {
    final background = CupertinoColors.systemBackground
        .resolveFrom(context)
        .withValues(alpha: 0.98);
    final divider = CupertinoColors.separator
        .resolveFrom(context)
        .withValues(alpha: 0.3);
    // 键盘弹起时 viewInsets.bottom > 0，此时系统已处理安全区；
    // 面板展开或键盘收起时需要手动补底部安全区（同底部导航栏处理方式）。
    final keyboardVisible = MediaQuery.viewInsetsOf(context).bottom > 0;
    final bottomInset = keyboardVisible
        ? 0.0
        : MediaQuery.viewPaddingOf(context).bottom;

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
                // 工具栏：固定 5 个 44 触控区 + 竖线；剩余宽度均分为 7 段（左缘、5 处
                // 相邻间隔、右缘），与下方样式面板同宽（feedMaxContentWidth），左右对称。
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    const fixedToolbarWidth =
                        5 * AppSpacing.minInteractiveSize + AppSpacing.hairline;
                    final maxW = constraints.maxWidth;
                    final gap = maxW > fixedToolbarWidth
                        ? (maxW - fixedToolbarWidth) / 7.0
                        : 0.0;
                    Widget gapBox() => SizedBox(width: gap);
                    return Row(
                      children: <Widget>[
                        gapBox(),
                        ArticleEditorAccessoryButton(
                          buttonKey: TestKeys.createMediaAddButton,
                          glyph: ArticleEditorAccessoryGlyph.image,
                          semanticLabel: '图片',
                          onPressed: onImageTap,
                        ),
                        gapBox(),
                        ArticleEditorAccessoryButton(
                          buttonKey: TestKeys.createAccessoryStructureButton,
                          glyph:
                              panelType == ArticleEditorAccessoryPanelType.style
                              ? ArticleEditorAccessoryGlyph.keyboard
                              : ArticleEditorAccessoryGlyph.style,
                          semanticLabel:
                              panelType == ArticleEditorAccessoryPanelType.style
                              ? '键盘'
                              : '样式',
                          onPressed: onStyleTap,
                          selected: panelType ==
                              ArticleEditorAccessoryPanelType.style,
                        ),
                        gapBox(),
                        ArticleEditorAccessoryButton(
                          buttonKey: TestKeys.createAccessoryEmojiButton,
                          glyph:
                              panelType == ArticleEditorAccessoryPanelType.emoji
                              ? ArticleEditorAccessoryGlyph.keyboard
                              : ArticleEditorAccessoryGlyph.emoji,
                          semanticLabel:
                              panelType == ArticleEditorAccessoryPanelType.emoji
                              ? '键盘'
                              : '表情',
                          onPressed: onEmojiTap,
                          selected: panelType ==
                              ArticleEditorAccessoryPanelType.emoji,
                        ),
                        gapBox(),
                        SizedBox(
                          height: AppSpacing.iconMedium,
                          width: AppSpacing.hairline,
                          child: ColoredBox(
                            color: divider,
                          ),
                        ),
                        gapBox(),
                        _AccessoryIconButton(
                          icon: CupertinoIcons.arrow_uturn_left,
                          semanticLabel: '撤销',
                          onPressed: canUndo ? onUndo : null,
                        ),
                        gapBox(),
                        _AccessoryIconButton(
                          icon: CupertinoIcons.arrow_uturn_right,
                          semanticLabel: '重做',
                          onPressed: canRedo ? onRedo : null,
                        ),
                        gapBox(),
                      ],
                    );
                  },
                ),
              ),
            ),
          ),
          if (panelType != ArticleEditorAccessoryPanelType.none)
            SizedBox(
              key: TestKeys.createAccessoryPanel,
              height: panelHeight + bottomInset,
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
                      AppSpacing.containerMd + bottomInset,
                    ),
                    child: _AccessoryPanelSwitcher(
                      panelType: panelType,
                      onEmojiSelected: onEmojiSelected,
                      onStructureActionSelected: onStructureActionSelected,
                      activeStructureAction: activeStructureAction,
                      onToggleBold: onToggleBold,
                      onToggleItalic: onToggleItalic,
                      onToggleUnderline: onToggleUnderline,
                      isBoldActive: isBoldActive,
                      isItalicActive: isItalicActive,
                      isUnderlineActive: isUnderlineActive,
                      activeAlignment: activeAlignment,
                      onAlignmentSelected: onAlignmentSelected,
                    ),
                  ),
                ),
              ),
            ),
          // 键盘收起且无面板时，补底部安全区占位
          if (panelType == ArticleEditorAccessoryPanelType.none && bottomInset > 0)
            SizedBox(height: bottomInset),
        ],
      ),
    );
  }
}

class _AccessoryPanelSwitcher extends StatelessWidget {
  const _AccessoryPanelSwitcher({
    required this.panelType,
    required this.onEmojiSelected,
    required this.onStructureActionSelected,
    this.activeStructureAction,
    this.onToggleBold,
    this.onToggleItalic,
    this.onToggleUnderline,
    this.isBoldActive = false,
    this.isItalicActive = false,
    this.isUnderlineActive = false,
    this.activeAlignment = 'left',
    this.onAlignmentSelected,
  });

  final ArticleEditorAccessoryPanelType panelType;
  final ValueChanged<String> onEmojiSelected;
  final ValueChanged<ArticleEditorStructureAction> onStructureActionSelected;
  final ArticleEditorStructureAction? activeStructureAction;
  final VoidCallback? onToggleBold;
  final VoidCallback? onToggleItalic;
  final VoidCallback? onToggleUnderline;
  final bool isBoldActive;
  final bool isItalicActive;
  final bool isUnderlineActive;
  final String activeAlignment;
  final ValueChanged<String>? onAlignmentSelected;

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
          onToggleBold: onToggleBold,
          onToggleItalic: onToggleItalic,
          onToggleUnderline: onToggleUnderline,
          isBoldActive: isBoldActive,
          isItalicActive: isItalicActive,
          isUnderlineActive: isUnderlineActive,
          activeAlignment: activeAlignment,
          onAlignmentSelected: onAlignmentSelected,
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

/// 样式面板：标题层级 + 正文结构 + 行内样式
class ArticleEditorStylePanel extends StatelessWidget {
  const ArticleEditorStylePanel({
    super.key,
    required this.onStructureSelected,
    this.activeAction,
    this.onToggleBold,
    this.onToggleItalic,
    this.onToggleUnderline,
    this.isBoldActive = false,
    this.isItalicActive = false,
    this.isUnderlineActive = false,
    this.activeAlignment = 'left',
    this.onAlignmentSelected,
  });

  final ValueChanged<ArticleEditorStructureAction> onStructureSelected;
  final ArticleEditorStructureAction? activeAction;
  final VoidCallback? onToggleBold;
  final VoidCallback? onToggleItalic;
  final VoidCallback? onToggleUnderline;
  final bool isBoldActive;
  final bool isItalicActive;
  final bool isUnderlineActive;
  final String activeAlignment;
  final ValueChanged<String>? onAlignmentSelected;

  /// 三选一行：选中再点取消（回到 paragraph）。
  void _onExclusiveTap(ArticleEditorStructureAction action) {
    if (activeAction == action) {
      onStructureSelected(ArticleEditorStructureAction.paragraph);
    } else {
      onStructureSelected(action);
    }
  }

  @override
  Widget build(BuildContext context) {
    final labelColor = CupertinoColors.label.resolveFrom(context);
    const rowSpacing = 8.0;
    const cellSpacing = 6.0;

    return Column(
      key: TestKeys.createStructurePanel,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        // ── 第一行：大标题 / 小标题 / 引用 ──
        _StyleRow(
          spacing: cellSpacing,
          children: <Widget>[
            _StyleCell(
              child: Text(
                '大标题',
                style: TextStyle(
                  color: labelColor,
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
              selected: activeAction == ArticleEditorStructureAction.headingMajor,
              onTap: () => _onExclusiveTap(ArticleEditorStructureAction.headingMajor),
            ),
            _StyleCell(
              child: Text(
                '小标题',
                style: TextStyle(
                  color: labelColor,
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.medium,
                ),
              ),
              selected: activeAction == ArticleEditorStructureAction.headingMinor,
              onTap: () => _onExclusiveTap(ArticleEditorStructureAction.headingMinor),
            ),
            _StyleCell(
              child: Text(
                '引用',
                style: TextStyle(
                  color: labelColor,
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.regular,
                ),
              ),
              selected: activeAction == ArticleEditorStructureAction.blockquote,
              onTap: () => _onExclusiveTap(ArticleEditorStructureAction.blockquote),
            ),
          ],
        ),
        SizedBox(height: rowSpacing),
        // ── 第二行：无序 / 数字序号 / 中文数字序号（三选一，再点取消）──
        _StyleRow(
          spacing: cellSpacing,
          children: <Widget>[
            _StyleCell(
              child: Icon(
                CupertinoIcons.list_bullet,
                size: AppSpacing.iconMedium,
                color: labelColor,
              ),
              selected: activeAction == ArticleEditorStructureAction.bulletList,
              onTap: () => _onExclusiveTap(ArticleEditorStructureAction.bulletList),
            ),
            _StyleCell(
              child: Icon(
                CupertinoIcons.list_number,
                size: AppSpacing.iconMedium,
                color: labelColor,
              ),
              selected: activeAction == ArticleEditorStructureAction.orderedList,
              onTap: () => _onExclusiveTap(ArticleEditorStructureAction.orderedList),
            ),
            _StyleCell(
              child: _CnListIcon(color: labelColor),
              selected: false, // 占位：中文数字序号暂不支持
              onTap: () {},
            ),
          ],
        ),
        SizedBox(height: rowSpacing),
        // ── 第三行：左对齐 / 居中 / 右对齐 ──
        _StyleRow(
          spacing: cellSpacing,
          children: <Widget>[
            _StyleCell(
              child: Icon(
                CupertinoIcons.text_alignleft,
                size: AppSpacing.twenty,
                color: labelColor,
              ),
              selected: activeAlignment == 'left',
              onTap: () => onAlignmentSelected?.call(
                activeAlignment == 'left' ? '' : 'left',
              ),
            ),
            _StyleCell(
              child: Icon(
                CupertinoIcons.text_aligncenter,
                size: AppSpacing.twenty,
                color: labelColor,
              ),
              selected: activeAlignment == 'center',
              onTap: () => onAlignmentSelected?.call(
                activeAlignment == 'center' ? 'left' : 'center',
              ),
            ),
            _StyleCell(
              child: Icon(
                CupertinoIcons.text_alignright,
                size: AppSpacing.twenty,
                color: labelColor,
              ),
              selected: activeAlignment == 'right',
              onTap: () => onAlignmentSelected?.call(
                activeAlignment == 'right' ? 'left' : 'right',
              ),
            ),
          ],
        ),
        SizedBox(height: rowSpacing),
        // ── 第四行：加粗 / 斜体 / 下划线 ──
        _StyleRow(
          spacing: cellSpacing,
          children: <Widget>[
            _StyleCell(
              child: Text(
                '加粗',
                style: TextStyle(
                  color: labelColor,
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.bold,
                ),
              ),
              selected: isBoldActive,
              onTap: onToggleBold ?? () {},
            ),
            _StyleCell(
              child: Text(
                '斜体',
                style: TextStyle(
                  color: labelColor,
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.regular,
                  fontStyle: FontStyle.italic,
                ),
              ),
              selected: isItalicActive,
              onTap: onToggleItalic ?? () {},
            ),
            _StyleCell(
              child: Text(
                '下划线',
                style: TextStyle(
                  color: labelColor,
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.regular,
                  decoration: TextDecoration.underline,
                ),
              ),
              selected: isUnderlineActive,
              onTap: onToggleUnderline ?? () {},
            ),
          ],
        ),
      ],
    );
  }
}

/// 面板中一行，子项均分宽度。
class _StyleRow extends StatelessWidget {
  const _StyleRow({required this.children, this.spacing = 6.0});
  final List<Widget> children;
  final double spacing;

  @override
  Widget build(BuildContext context) {
    final items = <Widget>[];
    for (var i = 0; i < children.length; i++) {
      if (i > 0) items.add(SizedBox(width: spacing));
      items.add(Expanded(child: children[i]));
    }
    return Row(children: items);
  }
}

/// 面板中一个可点击格子（iOS 风格）。
///
/// 未选中：`CupertinoColors.tertiarySystemFill`（浅灰，深色/浅色自适应，有可见轮廓）
/// 选中：`CupertinoColors.activeBlue` 12% 不透明度背景 + 蓝色边框
class _StyleCell extends StatelessWidget {
  const _StyleCell({
    required this.child,
    required this.selected,
    required this.onTap,
  });
  final Widget child;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final accentColor = CupertinoColors.activeBlue.resolveFrom(context);
    final normalBg =
        CupertinoColors.tertiarySystemFill.resolveFrom(context);
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 160),
        height: AppSpacing.minInteractiveSize,
        decoration: BoxDecoration(
          color: selected
              ? accentColor.withValues(alpha: 0.12)
              : normalBg,
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          border: selected
              ? Border.all(color: accentColor, width: AppSpacing.oneHalf)
              : Border.all(
                  color: AppColors.transparent,
                  width: AppSpacing.oneHalf,
                ),
        ),
        alignment: Alignment.center,
        child: child,
      ),
    );
  }
}

/// 中文数字序号列表图标：水平显示「一二三」。
class _CnListIcon extends StatelessWidget {
  const _CnListIcon({required this.color});
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Text(
      '一二三',
      style: TextStyle(
        color: color,
        fontSize: AppTypography.iosFootnote,
        fontWeight: AppTypography.semiBold,
        height: AppSpacing.textLineHeightSingle,
        letterSpacing: -AppSpacing.one,
      ),
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
                  style: typography.captionStyle.copyWith(color: palette.textColor),
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

    // emoji 使用 Material Icon（与聊天页底部工具栏一致）
    final Widget glyphWidget;
    if (glyph == ArticleEditorAccessoryGlyph.emoji) {
      glyphWidget = Icon(
        Icons.sentiment_satisfied_alt,
        size: iconSize + 2,
        color: color,
      );
    } else {
      glyphWidget = SizedBox(
        width: iconSize,
        height: iconSize,
        child: CustomPaint(
          painter: _AccessoryGlyphPainter(
            glyph: glyph,
            color: color,
            strokeWidth: strokeWidth,
          ),
        ),
      );
    }

    return SizedBox(
      width: AppSpacing.minInteractiveSize,
      child: Semantics(
        button: true,
        label: semanticLabel,
        child: CupertinoButton(
          key: buttonKey,
          padding: EdgeInsets.zero,
          minimumSize: const Size.square(AppSpacing.iconButtonMinSizeSm),
          onPressed: onPressed,
          child: Center(child: glyphWidget),
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
        // 图片图标：圆角矩形框 + 右上角实心小圆点太阳 + 山峰折线（参考图一）
        final rect = RRect.fromRectAndRadius(
          Rect.fromLTWH(
            size.width * 0.06,
            size.height * 0.06,
            size.width * 0.88,
            size.height * 0.88,
          ),
          Radius.circular(size.width * 0.14),
        );
        canvas.drawRRect(rect, stroke);
        // 太阳：实心小圆点
        canvas.drawCircle(
          Offset(size.width * 0.72, size.height * 0.3),
          size.width * 0.06,
          fill,
        );
        // 山峰折线
        final mountainPath = Path()
          ..moveTo(size.width * 0.12, size.height * 0.78)
          ..lineTo(size.width * 0.36, size.height * 0.48)
          ..lineTo(size.width * 0.52, size.height * 0.6)
          ..lineTo(size.width * 0.72, size.height * 0.42)
          ..lineTo(size.width * 0.88, size.height * 0.64);
        canvas.drawPath(mountainPath, stroke);
      case ArticleEditorAccessoryGlyph.emoji:
        // emoji 由 ArticleEditorAccessoryButton 直接用 Icon 渲染
        break;
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
      case ArticleEditorAccessoryGlyph.style:
        // "Aa" 样式图标：在 iconSize×iconSize 画布内绘制，视觉居中
        final bigA = TextPainter(
          text: TextSpan(
            text: 'A',
            style: TextStyle(
              color: color,
              fontSize: size.height * 0.88,
              fontWeight: AppTypography.semiBold,
              height: AppSpacing.textLineHeightSingle,
            ),
          ),
          textDirection: TextDirection.ltr,
        )..layout();
        final smallA = TextPainter(
          text: TextSpan(
            text: 'a',
            style: TextStyle(
              color: color,
              fontSize: size.height * 0.62,
              fontWeight: AppTypography.regular,
              height: AppSpacing.textLineHeightSingle,
            ),
          ),
          textDirection: TextDirection.ltr,
        )..layout();
        // 整体水平居中
        final totalWidth = bigA.width + smallA.width - size.width * 0.06;
        final startX = (size.width - totalWidth) / 2;
        // 略低于几何中心，与描边类图标（山峰在下方）视觉重心对齐
        final baselineY = size.height * 0.88;
        // 大 A
        bigA.paint(canvas, Offset(startX, baselineY - bigA.height));
        // 小 a 底部对齐大 A
        smallA.paint(
          canvas,
          Offset(startX + bigA.width - size.width * 0.06, baselineY - smallA.height),
        );
      // 以下 glyph 不再在工具栏使用，保留以避免编译错误
      case ArticleEditorAccessoryGlyph.structure:
      case ArticleEditorAccessoryGlyph.template:
      case ArticleEditorAccessoryGlyph.font:
      case ArticleEditorAccessoryGlyph.list:
      case ArticleEditorAccessoryGlyph.typography:
        break;
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
