import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart'
    show Icons, TextDirection, TextPainter, TextSpan, TextStyle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/constants/create_page_text_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/emoji/emoji_catalog.dart';
import 'package:quwoquan_app/core/emoji/emoji_providers.dart';
import 'package:quwoquan_app/core/platform/app_font_families.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/models/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/models/article_theme.dart';
import 'package:quwoquan_app/ui/content/widgets/article_content_block_renderer.dart';

part 'article_editor_accessory_style_panels.dart';
part 'article_editor_accessory_selection_panels.dart';
part 'article_editor_accessory_controls.dart';

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
}

class ArticleEditorAccessoryHost extends StatelessWidget {
  const ArticleEditorAccessoryHost({
    super.key,
    required this.panelType,
    required this.panelHeight,
    required this.onImageTap,
    required this.onEmojiTap,
    required this.onStyleTap,
    this.onMentionTap,
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
  final VoidCallback? onMentionTap;
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
                // 工具栏：固定 6 个 44 触控区 + 竖线；剩余宽度均分为 8 段（左缘、6 处
                // 相邻间隔、右缘），与下方样式面板同宽（feedMaxContentWidth），左右对称。
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    const fixedToolbarWidth =
                        6 * AppSpacing.minInteractiveSize + AppSpacing.hairline;
                    final maxW = constraints.maxWidth;
                    final gap = maxW > fixedToolbarWidth
                        ? (maxW - fixedToolbarWidth) / 8.0
                        : 0.0;
                    Widget gapBox() => SizedBox(width: gap);
                    return Row(
                      children: <Widget>[
                        gapBox(),
                        ArticleEditorAccessoryButton(
                          buttonKey: TestKeys.createMediaAddButton,
                          glyph: ArticleEditorAccessoryGlyph.image,
                          semanticLabel: CreatePageText.image,
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
                          selected:
                              panelType ==
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
                          selected:
                              panelType ==
                              ArticleEditorAccessoryPanelType.emoji,
                        ),
                        gapBox(),
                        ArticleEditorAccessoryButton(
                          buttonKey: TestKeys.createAccessoryMentionButton,
                          glyph: ArticleEditorAccessoryGlyph.at,
                          semanticLabel: CreatePageText.mentionObject,
                          onPressed: onMentionTap ?? () {},
                        ),
                        gapBox(),
                        SizedBox(
                          height: AppSpacing.iconMedium,
                          width: AppSpacing.hairline,
                          child: ColoredBox(color: divider),
                        ),
                        gapBox(),
                        _AccessoryIconButton(
                          icon: CupertinoIcons.arrow_uturn_left,
                          semanticLabel: CreatePageText.undo,
                          onPressed: canUndo ? onUndo : null,
                        ),
                        gapBox(),
                        _AccessoryIconButton(
                          icon: CupertinoIcons.arrow_uturn_right,
                          semanticLabel: CreatePageText.redo,
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
          if (panelType == ArticleEditorAccessoryPanelType.none &&
              bottomInset > 0)
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
