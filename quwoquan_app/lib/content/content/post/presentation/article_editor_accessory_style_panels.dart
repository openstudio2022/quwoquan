part of 'article_editor_accessory_panels.dart';

/// 表情与结构样式面板。
///
/// 面板选择状态仍由 [ArticleEditorAccessoryHost] 的调用方持有，本文件只渲染
/// 当前面板并转发用户动作。
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
          _AccessorySectionLabel(label: CreatePageText.recentEmoji),
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
        _AccessorySectionLabel(label: CreatePageText.allEmoji),
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
          CreatePageText.emojiPanelKeyboardHint,
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
    const rowSpacing = AppSpacing.intraGroupMd;
    const cellSpacing = AppSpacing.intraGroupSm;

    return Column(
      key: TestKeys.createStructurePanel,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        // ── 第一行：大标题 / 小标题 ──
        _StyleRow(
          spacing: cellSpacing,
          children: <Widget>[
            _StyleCell(
              selected:
                  activeAction == ArticleEditorStructureAction.headingMajor,
              onTap: () =>
                  _onExclusiveTap(ArticleEditorStructureAction.headingMajor),
              child: Text(
                CreatePageText.headingLarge,
                style: TextStyle(
                  color: labelColor,
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
            _StyleCell(
              selected:
                  activeAction == ArticleEditorStructureAction.headingMinor,
              onTap: () =>
                  _onExclusiveTap(ArticleEditorStructureAction.headingMinor),
              child: Text(
                CreatePageText.headingSmall,
                style: TextStyle(
                  color: labelColor,
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.medium,
                ),
              ),
            ),
          ],
        ),
        SizedBox(height: rowSpacing),
        // ── 第二行：无序 / 数字序号（二选一，再点取消）──
        _StyleRow(
          spacing: cellSpacing,
          children: <Widget>[
            _StyleCell(
              selected: activeAction == ArticleEditorStructureAction.bulletList,
              onTap: () =>
                  _onExclusiveTap(ArticleEditorStructureAction.bulletList),
              child: Icon(
                CupertinoIcons.list_bullet,
                size: AppSpacing.iconMedium,
                color: labelColor,
              ),
            ),
            _StyleCell(
              selected:
                  activeAction == ArticleEditorStructureAction.orderedList,
              onTap: () =>
                  _onExclusiveTap(ArticleEditorStructureAction.orderedList),
              child: Icon(
                CupertinoIcons.list_number,
                size: AppSpacing.iconMedium,
                color: labelColor,
              ),
            ),
          ],
        ),
        SizedBox(height: rowSpacing),
        // ── 第三行：左对齐 / 居中 / 右对齐 ──
        _StyleRow(
          spacing: cellSpacing,
          children: <Widget>[
            _StyleCell(
              selected: activeAlignment == 'left',
              onTap: () => onAlignmentSelected?.call(
                activeAlignment == 'left' ? '' : 'left',
              ),
              child: Icon(
                CupertinoIcons.text_alignleft,
                size: AppSpacing.twenty,
                color: labelColor,
              ),
            ),
            _StyleCell(
              selected: activeAlignment == 'center',
              onTap: () => onAlignmentSelected?.call(
                activeAlignment == 'center' ? 'left' : 'center',
              ),
              child: Icon(
                CupertinoIcons.text_aligncenter,
                size: AppSpacing.twenty,
                color: labelColor,
              ),
            ),
            _StyleCell(
              selected: activeAlignment == 'right',
              onTap: () => onAlignmentSelected?.call(
                activeAlignment == 'right' ? 'left' : 'right',
              ),
              child: Icon(
                CupertinoIcons.text_alignright,
                size: AppSpacing.twenty,
                color: labelColor,
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
              selected: isBoldActive,
              onTap: onToggleBold ?? () {},
              child: Text(
                CreatePageText.bold,
                style: TextStyle(
                  color: labelColor,
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.bold,
                ),
              ),
            ),
            _StyleCell(
              selected: isItalicActive,
              onTap: onToggleItalic ?? () {},
              child: Text(
                CreatePageText.italic,
                style: TextStyle(
                  color: labelColor,
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.regular,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ),
            _StyleCell(
              selected: isUnderlineActive,
              onTap: onToggleUnderline ?? () {},
              child: Text(
                CreatePageText.underline,
                style: TextStyle(
                  color: labelColor,
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.regular,
                  decoration: TextDecoration.underline,
                ),
              ),
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
/// 选中：品牌蓝 12% 不透明度背景 + 蓝色边框
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
    final accentColor = AppColors.iosAccent(context);
    final normalBg = CupertinoColors.tertiarySystemFill.resolveFrom(context);
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 160),
        height: AppSpacing.minInteractiveSize,
        decoration: BoxDecoration(
          color: selected ? accentColor.withValues(alpha: 0.12) : normalBg,
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
