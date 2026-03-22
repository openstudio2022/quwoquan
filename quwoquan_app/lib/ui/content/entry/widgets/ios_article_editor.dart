import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/widgets/article_content_block_renderer.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

const double _kArticleEditorPageAspectRatio = 0.72;

class IosArticleEditor extends StatefulWidget {
  const IosArticleEditor({
    super.key,
    required this.state,
    required this.titleController,
    required this.titleFocusNode,
    required this.onTitleChanged,
    required this.onUpdatePageText,
    required this.onEditPageImage,
    required this.onUpdatePageImageLayout,
    required this.onRemovePage,
    required this.onActivePageChanged,
    required this.onTemplateChanged,
    required this.onFontPresetChanged,
    this.immersive = false,
  });

  final CreateEditorStateV2 state;
  final TextEditingController titleController;
  final FocusNode titleFocusNode;
  final ValueChanged<String> onTitleChanged;
  final void Function(String pageId, String value) onUpdatePageText;
  final Future<void> Function(String pageId) onEditPageImage;
  final void Function(String pageId, String imageLayout)
  onUpdatePageImageLayout;
  final void Function(String pageId) onRemovePage;
  final ValueChanged<String?> onActivePageChanged;
  final ValueChanged<ArticleTemplatePreset> onTemplateChanged;
  final ValueChanged<ArticleFontPreset> onFontPresetChanged;
  final bool immersive;

  @override
  State<IosArticleEditor> createState() => _IosArticleEditorState();
}

class _IosArticleEditorState extends State<IosArticleEditor> {
  final Map<String, TextEditingController> _pageControllers =
      <String, TextEditingController>{};
  late final PageController _pageController;
  bool _showEmojiPanel = false;

  int get _activeIndex {
    final index = widget.state.articlePages.indexWhere(
      (page) => page.id == widget.state.activeArticlePageId,
    );
    return index < 0 ? 0 : index;
  }

  @override
  void initState() {
    super.initState();
    _pageController = PageController(initialPage: _activeIndex);
    _syncControllers();
  }

  @override
  void didUpdateWidget(covariant IosArticleEditor oldWidget) {
    super.didUpdateWidget(oldWidget);
    _syncControllers();
    if (_pageController.hasClients &&
        (_pageController.page?.round() ?? 0) != _activeIndex) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _pageController.hasClients) {
          _pageController.animateToPage(
            _activeIndex,
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOutCubic,
          );
        }
      });
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    for (final controller in _pageControllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  void _syncControllers() {
    final pageIds = widget.state.articlePages.map((page) => page.id).toSet();
    final removed = _pageControllers.keys
        .where((id) => !pageIds.contains(id))
        .toList(growable: false);
    for (final id in removed) {
      _pageControllers.remove(id)?.dispose();
    }
    for (final page in widget.state.articlePages) {
      final controller = _pageControllers.putIfAbsent(
        page.id,
        () => TextEditingController(text: page.body),
      );
      if (controller.text != page.body) {
        controller.value = TextEditingValue(
          text: page.body,
          selection: TextSelection.collapsed(
            offset: controller.selection.baseOffset.clamp(0, page.body.length),
          ),
        );
      }
    }
  }

  void _insertEmoji(String emoji) {
    final pageId =
        widget.state.activeArticlePageId ?? widget.state.articlePages.first.id;
    final controller = _pageControllers[pageId];
    if (controller == null) {
      return;
    }
    final selection = controller.selection;
    final start = selection.isValid ? selection.start : controller.text.length;
    final end = selection.isValid ? selection.end : controller.text.length;
    final safeStart = start.clamp(0, controller.text.length);
    final safeEnd = end.clamp(0, controller.text.length);
    final nextText = controller.text.replaceRange(safeStart, safeEnd, emoji);
    controller.value = TextEditingValue(
      text: nextText,
      selection: TextSelection.collapsed(offset: safeStart + emoji.length),
    );
    widget.onUpdatePageText(pageId, nextText);
  }

  void _insertOrderedPrefix() {
    final pageId =
        widget.state.activeArticlePageId ?? widget.state.articlePages.first.id;
    final controller = _pageControllers[pageId];
    if (controller == null) {
      return;
    }
    final before = controller.text.substring(
      0,
      controller.selection.baseOffset.clamp(0, controller.text.length),
    );
    final after = controller.text.substring(
      controller.selection.baseOffset.clamp(0, controller.text.length),
    );
    final count = before
        .split('\n')
        .where((line) => RegExp(r'^\s*\d+\.\s+').hasMatch(line.trim()))
        .length;
    final prefix = before.isEmpty || before.endsWith('\n')
        ? '${count + 1}. '
        : '\n${count + 1}. ';
    final nextText = '$before$prefix$after';
    controller.value = TextEditingValue(
      text: nextText,
      selection: TextSelection.collapsed(offset: (before + prefix).length),
    );
    widget.onUpdatePageText(pageId, nextText);
  }

  Future<void> _showTemplateSheet() async {
    await showCupertinoModalPopup<void>(
      context: context,
      barrierColor: Colors.transparent,
      builder: (context) => _TemplateSheet(
        selected: widget.state.articleTemplate,
        fontPreset: widget.state.articleFontPreset,
        onSelected: (value) {
          widget.onTemplateChanged(value);
          Navigator.of(context).pop();
        },
      ),
    );
  }

  Future<void> _showFontSheet() async {
    await showCupertinoModalPopup<void>(
      context: context,
      barrierColor: Colors.transparent,
      builder: (context) => _FontSheet(
        selected: widget.state.articleFontPreset,
        onSelected: (value) {
          widget.onFontPresetChanged(value);
          Navigator.of(context).pop();
        },
      ),
    );
  }

  double _resolveUnboundedPagerHeight(
    BuildContext context,
    BoxConstraints constraints,
  ) {
    final viewportWidth = constraints.maxWidth.isFinite
        ? constraints.maxWidth
        : MediaQuery.sizeOf(context).width;
    if (viewportWidth <= 0) {
      return MediaQuery.sizeOf(context).height * 0.6;
    }
    final pageWidth = viewportWidth > AppSpacing.containerMd * 2
        ? viewportWidth - (AppSpacing.containerMd * 2)
        : viewportWidth;
    return pageWidth / _kArticleEditorPageAspectRatio;
  }

  @override
  Widget build(BuildContext context) {
    final pages = widget.state.articlePages;
    return LayoutBuilder(
      builder: (context, constraints) {
        final pageView = PageView.builder(
          controller: _pageController,
          itemCount: pages.length,
          onPageChanged: (index) {
            widget.onActivePageChanged(pages[index].id);
            if (_showEmojiPanel) {
              setState(() => _showEmojiPanel = false);
            }
          },
          itemBuilder: (context, index) {
            final page = pages[index];
            final typography = resolveArticleTypography(
              context,
              widget.state.articleTemplate,
              widget.state.articleFontPreset,
            );
            return Padding(
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
              child: ArticlePageShell(
                template: widget.state.articleTemplate,
                fontPreset: widget.state.articleFontPreset,
                pageIndex: index,
                totalPages: pages.length,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    if (index == 0) ...<Widget>[
                      CupertinoTextField(
                        controller: widget.titleController,
                        focusNode: widget.titleFocusNode,
                        padding: EdgeInsets.zero,
                        decoration: const BoxDecoration(),
                        placeholder: '输入标题（可选）',
                        style: typography.titleStyle,
                        placeholderStyle: typography.placeholderStyle.copyWith(
                          fontSize: typography.titleStyle.fontSize,
                          fontWeight: typography.titleStyle.fontWeight,
                        ),
                        onChanged: widget.onTitleChanged,
                      ),
                      SizedBox(height: AppSpacing.interGroupSm),
                    ],
                    if (page.imageUrl.trim().isNotEmpty) ...<Widget>[
                      GestureDetector(
                        onTap: () => widget.onEditPageImage(page.id),
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(
                            AppSpacing.radiusTwenty,
                          ),
                          child: AspectRatio(
                            aspectRatio: page.usesWrappedLayout ? 1 : 4 / 3,
                            child: ArticleAdaptiveImage(
                              imageUrl: page.imageUrl.trim(),
                            ),
                          ),
                        ),
                      ),
                      SizedBox(height: AppSpacing.intraGroupSm),
                      CupertinoSlidingSegmentedControl<String>(
                        groupValue: page.imageLayout,
                        children: const <String, Widget>{
                          'fullWidth': Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 4,
                            ),
                            child: Text('通栏'),
                          ),
                          'wrapLeft': Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 4,
                            ),
                            child: Text('左环绕'),
                          ),
                          'wrapRight': Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 4,
                            ),
                            child: Text('右环绕'),
                          ),
                        },
                        onValueChanged: (value) {
                          if (value != null) {
                            widget.onUpdatePageImageLayout(page.id, value);
                          }
                        },
                      ),
                      SizedBox(height: AppSpacing.intraGroupSm),
                    ],
                    Expanded(
                      child: SingleChildScrollView(
                        physics: const BouncingScrollPhysics(),
                        child: CupertinoTextField(
                          key: page.id == widget.state.activeArticlePageId
                              ? TestKeys.createMomentInput
                              : null,
                          controller: _pageControllers[page.id],
                          maxLines: null,
                          minLines: page.usesWrappedLayout ? 8 : 12,
                          padding: EdgeInsets.zero,
                          decoration: const BoxDecoration(),
                          placeholder: '继续写内容，支持 emoji、图片、序号和模板',
                          style: typography.bodyStyle,
                          placeholderStyle: typography.placeholderStyle,
                          onTap: () => widget.onActivePageChanged(page.id),
                          onChanged: (value) =>
                              widget.onUpdatePageText(page.id, value),
                        ),
                      ),
                    ),
                    if (pages.length > 1) ...<Widget>[
                      SizedBox(height: AppSpacing.intraGroupSm),
                      Align(
                        alignment: Alignment.centerRight,
                        child: CupertinoButton(
                          padding: EdgeInsets.zero,
                          minimumSize: const Size.square(28),
                          onPressed: () => widget.onRemovePage(page.id),
                          child: Icon(
                            CupertinoIcons.minus_circle,
                            size: AppSpacing.iconMedium,
                            color: CupertinoColors.tertiaryLabel.resolveFrom(
                              context,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            );
          },
        );
        final pageViewport = constraints.hasBoundedHeight
            ? Expanded(child: pageView)
            : SizedBox(
                height: _resolveUnboundedPagerHeight(context, constraints),
                child: pageView,
              );

        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            pageViewport,
            SizedBox(height: AppSpacing.interGroupSm),
            Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              decoration: BoxDecoration(
                color: CupertinoColors.secondarySystemGroupedBackground
                    .resolveFrom(context),
                borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              ),
              child: Row(
                children: <Widget>[
                  _ToolButton(
                    icon: CupertinoIcons.photo_on_rectangle,
                    label: '图片',
                    onTap: () => widget.onEditPageImage(
                      widget.state.activeArticlePageId ?? pages.first.id,
                    ),
                    iconKey: TestKeys.createMediaAddButton,
                  ),
                  _ToolButton(
                    icon: _showEmojiPanel
                        ? CupertinoIcons.keyboard
                        : CupertinoIcons.smiley,
                    label: '表情',
                    onTap: () =>
                        setState(() => _showEmojiPanel = !_showEmojiPanel),
                    selected: _showEmojiPanel,
                  ),
                  _ToolButton(
                    icon: CupertinoIcons.list_number,
                    label: '序号',
                    onTap: _insertOrderedPrefix,
                  ),
                  _ToolButton(
                    icon: CupertinoIcons.square_grid_2x2,
                    label: '模版',
                    onTap: _showTemplateSheet,
                  ),
                  _ToolButton(
                    icon: CupertinoIcons.textformat_alt,
                    label: '字体',
                    onTap: _showFontSheet,
                  ),
                ],
              ),
            ),
            if (_showEmojiPanel) ...<Widget>[
              SizedBox(height: AppSpacing.intraGroupSm),
              ClipRRect(
                borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                child: UnifiedEmojiPicker(
                  onEmojiSelected: _insertEmoji,
                  showCloseButton: true,
                  onClose: () => setState(() => _showEmojiPanel = false),
                ),
              ),
            ],
          ],
        );
      },
    );
  }
}

class _ToolButton extends StatelessWidget {
  const _ToolButton({
    required this.icon,
    required this.label,
    required this.onTap,
    this.selected = false,
    this.iconKey,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool selected;
  final Key? iconKey;

  @override
  Widget build(BuildContext context) {
    final color = selected
        ? AppColors.primaryColor
        : CupertinoColors.label.resolveFrom(context);
    return Expanded(
      child: CupertinoButton(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
        onPressed: onTap,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(icon, key: iconKey, color: color, size: AppSpacing.iconMedium),
            SizedBox(height: AppSpacing.intraGroupXs / 2),
            Text(
              label,
              style: TextStyle(
                color: color,
                fontSize: AppTypography.xs,
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

class _TemplateSheet extends StatelessWidget {
  const _TemplateSheet({
    required this.selected,
    required this.fontPreset,
    required this.onSelected,
  });

  final ArticleTemplatePreset selected;
  final ArticleFontPreset fontPreset;
  final ValueChanged<ArticleTemplatePreset> onSelected;

  @override
  Widget build(BuildContext context) {
    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      contentPadding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        0,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
      ),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: ArticleTemplatePreset.values
              .map((template) {
                return Padding(
                  padding: EdgeInsets.only(right: AppSpacing.containerSm),
                  child: ArticleTemplateThumbnail(
                    template: template,
                    fontPreset: fontPreset,
                    label: template.label,
                    selected: template == selected,
                    onTap: () => onSelected(template),
                  ),
                );
              })
              .toList(growable: false),
        ),
      ),
    );
  }
}

class _FontSheet extends StatelessWidget {
  const _FontSheet({required this.selected, required this.onSelected});

  final ArticleFontPreset selected;
  final ValueChanged<ArticleFontPreset> onSelected;

  @override
  Widget build(BuildContext context) {
    return AppBottomModalSurface(
      onDismiss: () => Navigator.of(context).pop(),
      contentPadding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        0,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
      ),
      child: Wrap(
        spacing: AppSpacing.intraGroupSm,
        runSpacing: AppSpacing.intraGroupSm,
        children: ArticleFontPreset.values
            .map((preset) {
              final selectedChip = preset == selected;
              return CupertinoButton(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                  vertical: AppSpacing.intraGroupXs,
                ),
                color: selectedChip
                    ? AppColors.primaryColor.withValues(alpha: 0.12)
                    : CupertinoColors.systemGrey5.resolveFrom(context),
                borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                onPressed: () => onSelected(preset),
                child: Text(
                  preset.label,
                  style: TextStyle(
                    color: selectedChip
                        ? AppColors.primaryColor
                        : CupertinoColors.label.resolveFrom(context),
                    fontSize: AppTypography.sm,
                    fontWeight: selectedChip
                        ? AppTypography.semiBold
                        : AppTypography.medium,
                  ),
                ),
              );
            })
            .toList(growable: false),
      ),
    );
  }
}
