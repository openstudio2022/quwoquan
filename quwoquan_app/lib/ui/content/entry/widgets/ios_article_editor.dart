import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/article_editor_accessory_panels.dart';
import 'package:quwoquan_app/ui/content/widgets/article_content_block_renderer.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

enum _ArticleTitleLevel { h1, h2, h3 }

class ArticleEditor extends StatefulWidget {
  const ArticleEditor({
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
    required this.onActiveBlockChanged,
    required this.onUpdateTextBlock,
    required this.onInsertTextBlock,
    required this.onUpdateTextBlockType,
    required this.onRemoveTextBlock,
    required this.onCoverChanged,
    required this.onTemplateChanged,
    required this.onFontPresetChanged,
    this.immersive = false,
  });

  final CreateEditorStateV2 state;
  final TextEditingController titleController;
  final FocusNode titleFocusNode;
  final ValueChanged<String> onTitleChanged;
  final void Function(ArticlePageData page, String value) onUpdatePageText;
  final Future<void> Function(ArticlePageData page) onEditPageImage;
  final void Function(ArticlePageData page, String imageLayout)
  onUpdatePageImageLayout;
  final void Function(ArticlePageData page) onRemovePage;
  final ValueChanged<String?> onActivePageChanged;
  final ValueChanged<String?> onActiveBlockChanged;
  final void Function(String blockId, String value) onUpdateTextBlock;
  final String Function(String? afterBlockId, CreateTextBlockType type)
  onInsertTextBlock;
  final void Function(String blockId, CreateTextBlockType type)
  onUpdateTextBlockType;
  final void Function(String blockId) onRemoveTextBlock;
  final ValueChanged<String?> onCoverChanged;
  final ValueChanged<ArticleTemplatePreset> onTemplateChanged;
  final ValueChanged<ArticleFontPreset> onFontPresetChanged;
  final bool immersive;

  @override
  State<ArticleEditor> createState() => _ArticleEditorState();
}

class _ArticleEditorState extends State<ArticleEditor> {
  final Map<String, TextEditingController> _pageControllers =
      <String, TextEditingController>{};
  final Map<String, FocusNode> _pageFocusNodes = <String, FocusNode>{};
  final Map<String, TextEditingController> _semanticControllers =
      <String, TextEditingController>{};
  final Map<String, FocusNode> _semanticFocusNodes = <String, FocusNode>{};
  List<ArticlePageData> _renderedPages = const <ArticlePageData>[];
  late final PageController _pageController;
  ArticleEditorAccessoryPanelType _surface =
      ArticleEditorAccessoryPanelType.none;
  ArticleEditorStructureAction? _activeStructureAction;
  _ArticleTitleLevel _titleLevel = _ArticleTitleLevel.h1;
  FocusNode? _lastFocusedNode;
  String? _focusedSemanticBlockId;
  double _keyboardHeightSnapshot = SettingsSemanticConstants.emojiPanelHeight;
  bool _keyboardRestoring = false;

  int _activeIndexForPages(List<ArticlePageData> pages) {
    final index = pages.indexWhere(
      (page) => page.id == widget.state.activeArticlePageId,
    );
    return index < 0 ? 0 : index;
  }

  @override
  void initState() {
    super.initState();
    _pageController = PageController(initialPage: 0);
    widget.titleFocusNode.addListener(_handleTitleFocusChanged);
  }

  @override
  void didUpdateWidget(covariant ArticleEditor oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.titleFocusNode != widget.titleFocusNode) {
      oldWidget.titleFocusNode.removeListener(_handleTitleFocusChanged);
      widget.titleFocusNode.addListener(_handleTitleFocusChanged);
    }
  }

  @override
  void dispose() {
    widget.titleFocusNode.removeListener(_handleTitleFocusChanged);
    _pageController.dispose();
    for (final controller in _pageControllers.values) {
      controller.dispose();
    }
    for (final focusNode in _pageFocusNodes.values) {
      focusNode.dispose();
    }
    for (final controller in _semanticControllers.values) {
      controller.dispose();
    }
    for (final focusNode in _semanticFocusNodes.values) {
      focusNode.dispose();
    }
    super.dispose();
  }

  void _syncControllers(List<ArticlePageData> pages) {
    final pageIds = pages.map((page) => page.id).toSet();
    final removed = _pageControllers.keys
        .where((id) => !pageIds.contains(id))
        .toList(growable: false);
    for (final id in removed) {
      _pageControllers.remove(id)?.dispose();
    }
    for (final page in pages) {
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

  void _syncFocusNodes(List<ArticlePageData> pages) {
    final pageIds = pages.map((page) => page.id).toSet();
    final removed = _pageFocusNodes.keys
        .where((id) => !pageIds.contains(id))
        .toList(growable: false);
    for (final id in removed) {
      _pageFocusNodes.remove(id)?.dispose();
    }
    for (final page in pages) {
      _pageFocusNodes.putIfAbsent(page.id, () {
        final focusNode = FocusNode(debugLabel: 'article_page_${page.id}');
        focusNode.addListener(
          () => _handlePageFocusChanged(page.id, focusNode),
        );
        return focusNode;
      });
    }
  }

  Iterable<ArticleDocumentBlock> _semanticBlocksForPages(
    List<ArticlePageData> pages,
  ) {
    return pages.expand(
      (page) => page.contentBlocks.where(
        (block) =>
            block.type == ArticleDocumentBlockType.heading2 ||
            block.type == ArticleDocumentBlockType.heading3 ||
            block.type == ArticleDocumentBlockType.sectionTitle,
      ),
    );
  }

  String? _pageIdForSemanticBlock(String blockId) {
    for (final page in _renderedPages) {
      for (final block in page.contentBlocks) {
        if (block.id == blockId) {
          return page.id;
        }
      }
    }
    return null;
  }

  void _syncSemanticControllers(List<ArticlePageData> pages) {
    final blockIds = _semanticBlocksForPages(
      pages,
    ).map((block) => block.id).toSet();
    final removed = _semanticControllers.keys
        .where((id) => !blockIds.contains(id))
        .toList(growable: false);
    for (final id in removed) {
      _semanticControllers.remove(id)?.dispose();
    }
    for (final block in _semanticBlocksForPages(pages)) {
      final controller = _semanticControllers.putIfAbsent(
        block.id,
        () => TextEditingController(text: block.text),
      );
      if (controller.text != block.text) {
        controller.value = TextEditingValue(
          text: block.text,
          selection: TextSelection.collapsed(
            offset: controller.selection.baseOffset.clamp(0, block.text.length),
          ),
        );
      }
    }
  }

  void _syncSemanticFocusNodes(List<ArticlePageData> pages) {
    final blockIds = _semanticBlocksForPages(
      pages,
    ).map((block) => block.id).toSet();
    final removed = _semanticFocusNodes.keys
        .where((id) => !blockIds.contains(id))
        .toList(growable: false);
    for (final id in removed) {
      _semanticFocusNodes.remove(id)?.dispose();
    }
    for (final page in pages) {
      for (final block in page.contentBlocks) {
        if (block.type != ArticleDocumentBlockType.heading2 &&
            block.type != ArticleDocumentBlockType.heading3 &&
            block.type != ArticleDocumentBlockType.sectionTitle) {
          continue;
        }
        _semanticFocusNodes.putIfAbsent(block.id, () {
          final focusNode = FocusNode(debugLabel: 'article_block_${block.id}');
          focusNode.addListener(
            () => _handleSemanticBlockFocusChanged(
              _pageIdForSemanticBlock(block.id) ?? page.id,
              block.id,
              focusNode,
            ),
          );
          return focusNode;
        });
      }
    }
  }

  void _handleTitleFocusChanged() {
    if (widget.titleFocusNode.hasFocus) {
      _lastFocusedNode = widget.titleFocusNode;
      _focusedSemanticBlockId = null;
      if (_surface != ArticleEditorAccessoryPanelType.none ||
          _keyboardRestoring) {
        setState(() {
          _surface = ArticleEditorAccessoryPanelType.none;
          _keyboardRestoring = false;
        });
      }
    }
  }

  void _handlePageFocusChanged(String pageId, FocusNode focusNode) {
    if (!focusNode.hasFocus) {
      return;
    }
    _lastFocusedNode = focusNode;
    _focusedSemanticBlockId = null;
    widget.onActivePageChanged(pageId);
    if (_surface != ArticleEditorAccessoryPanelType.none ||
        _keyboardRestoring) {
      setState(() {
        _surface = ArticleEditorAccessoryPanelType.none;
        _keyboardRestoring = false;
      });
    }
  }

  void _handleSemanticBlockFocusChanged(
    String pageId,
    String blockId,
    FocusNode focusNode,
  ) {
    if (!focusNode.hasFocus) {
      return;
    }
    _lastFocusedNode = focusNode;
    _focusedSemanticBlockId = blockId;
    widget.onActivePageChanged(pageId);
    widget.onActiveBlockChanged(blockId);
    if (_surface != ArticleEditorAccessoryPanelType.none ||
        _keyboardRestoring) {
      setState(() {
        _surface = ArticleEditorAccessoryPanelType.none;
        _keyboardRestoring = false;
      });
    }
  }

  FocusNode? _activePageFocusNode() {
    final activeBlockId = widget.state.activeArticleBlockId;
    if (activeBlockId != null &&
        _semanticFocusNodes.containsKey(activeBlockId)) {
      return _semanticFocusNodes[activeBlockId];
    }
    return _pageFocusNodes[_activePage()?.id];
  }

  ArticlePageData? _activePage() {
    if (_renderedPages.isEmpty) {
      return null;
    }
    final currentId = widget.state.activeArticlePageId;
    for (final page in _renderedPages) {
      if (page.id == currentId) {
        return page;
      }
    }
    return _renderedPages.first;
  }

  ArticleDocumentBlock? _activeSemanticBlock() {
    final activeBlockId = _focusedSemanticBlockId;
    if (activeBlockId == null) {
      return null;
    }
    for (final page in _renderedPages) {
      for (final block in page.contentBlocks) {
        if (block.id == activeBlockId) {
          return block;
        }
      }
    }
    return null;
  }

  void _rememberKeyboardHeight() {
    final liveKeyboardInset = MediaQuery.viewInsetsOf(context).bottom;
    if (liveKeyboardInset > 0) {
      _keyboardHeightSnapshot = liveKeyboardInset;
    }
  }

  double _resolvedKeyboardPanelHeight(BuildContext context) {
    final fallback = AppSpacing.responsiveValue(
      context,
      compact: 256,
      regular: SettingsSemanticConstants.emojiPanelHeight,
      expanded: 336,
    );
    final maxHeight = math.max(
      fallback,
      MediaQuery.sizeOf(context).height * 0.48,
    );
    final candidate = _keyboardHeightSnapshot > 0
        ? _keyboardHeightSnapshot
        : fallback;
    return candidate.clamp(fallback, maxHeight);
  }

  void _insertEmoji(String emoji) {
    final semanticBlock = _activeSemanticBlock();
    if (semanticBlock != null) {
      final controller = _semanticControllers[semanticBlock.id];
      if (controller == null) {
        return;
      }
      final selection = controller.selection;
      final start = selection.isValid
          ? selection.start
          : controller.text.length;
      final end = selection.isValid ? selection.end : controller.text.length;
      final safeStart = start.clamp(0, controller.text.length);
      final safeEnd = end.clamp(0, controller.text.length);
      final nextText = controller.text.replaceRange(safeStart, safeEnd, emoji);
      controller.value = TextEditingValue(
        text: nextText,
        selection: TextSelection.collapsed(offset: safeStart + emoji.length),
      );
      widget.onUpdateTextBlock(semanticBlock.id, nextText);
      return;
    }
    final page = _activePage();
    if (page == null) {
      return;
    }
    final controller = _pageControllers[page.id];
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
    widget.onUpdatePageText(page, nextText);
  }

  void _insertBulletPrefix() {
    final page = _activePage();
    if (page == null) {
      return;
    }
    final controller = _pageControllers[page.id];
    if (controller == null) {
      return;
    }
    final cursor = controller.selection.baseOffset.clamp(
      0,
      controller.text.length,
    );
    final before = controller.text.substring(0, cursor);
    final after = controller.text.substring(cursor);
    final prefix = before.isEmpty || before.endsWith('\n') ? '• ' : '\n• ';
    final nextText = '$before$prefix$after';
    controller.value = TextEditingValue(
      text: nextText,
      selection: TextSelection.collapsed(offset: (before + prefix).length),
    );
    widget.onUpdatePageText(page, nextText);
  }

  void _insertOrderedPrefix() {
    final page = _activePage();
    if (page == null) {
      return;
    }
    final controller = _pageControllers[page.id];
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
    widget.onUpdatePageText(page, nextText);
  }

  void _togglePanel(ArticleEditorAccessoryPanelType panel) {
    if (_surface == panel) {
      _restoreKeyboard();
      return;
    }
    _rememberKeyboardHeight();
    FocusScope.of(context).unfocus();
    setState(() {
      _keyboardRestoring = false;
      _surface = panel;
    });
  }

  void _restoreKeyboard({FocusNode? focusNode}) {
    _rememberKeyboardHeight();
    final targetFocusNode =
        focusNode ?? _lastFocusedNode ?? _activePageFocusNode();
    if (targetFocusNode == null) {
      setState(() {
        _surface = ArticleEditorAccessoryPanelType.none;
        _keyboardRestoring = false;
      });
      return;
    }
    setState(() {
      _surface = ArticleEditorAccessoryPanelType.none;
      _keyboardRestoring = true;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      targetFocusNode.requestFocus();
    });
  }

  void _applyStructureAction(ArticleEditorStructureAction action) {
    CreateTextBlockType? semanticTypeForAction() {
      return switch (action) {
        ArticleEditorStructureAction.heading2 => CreateTextBlockType.heading2,
        ArticleEditorStructureAction.heading3 => CreateTextBlockType.heading3,
        ArticleEditorStructureAction.sectionTitle =>
          CreateTextBlockType.sectionTitle,
        _ => null,
      };
    }

    void focusSemanticBlockAfterBuild(String blockId) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        widget.onActiveBlockChanged(blockId);
        final focusNode = _semanticFocusNodes[blockId];
        if (focusNode != null) {
          _restoreKeyboard(focusNode: focusNode);
        } else {
          _restoreKeyboard();
        }
      });
    }

    switch (action) {
      case ArticleEditorStructureAction.heading1:
        setState(() {
          _titleLevel = _ArticleTitleLevel.h1;
          _activeStructureAction = action;
        });
        _restoreKeyboard(focusNode: widget.titleFocusNode);
        break;
      case ArticleEditorStructureAction.heading2:
      case ArticleEditorStructureAction.heading3:
      case ArticleEditorStructureAction.sectionTitle:
        final semanticType = semanticTypeForAction();
        setState(() => _activeStructureAction = action);
        final activeSemanticBlock = _activeSemanticBlock();
        if (semanticType != null &&
            activeSemanticBlock != null &&
            (_semanticControllers[activeSemanticBlock.id]?.text
                    .trim()
                    .isEmpty ??
                activeSemanticBlock.text.trim().isEmpty)) {
          widget.onUpdateTextBlockType(activeSemanticBlock.id, semanticType);
          focusSemanticBlockAfterBuild(activeSemanticBlock.id);
          break;
        }
        final newBlockId = widget.onInsertTextBlock(
          widget.state.activeArticleBlockId,
          semanticType ?? CreateTextBlockType.heading2,
        );
        focusSemanticBlockAfterBuild(newBlockId);
        break;
      case ArticleEditorStructureAction.orderedList:
        setState(() => _activeStructureAction = action);
        _insertOrderedPrefix();
        _restoreKeyboard(focusNode: _activePageFocusNode());
        break;
      case ArticleEditorStructureAction.bulletList:
        setState(() => _activeStructureAction = action);
        _insertBulletPrefix();
        _restoreKeyboard(focusNode: _activePageFocusNode());
        break;
    }
  }

  TextStyle _resolveTitleStyle(ArticleTypographySpec typography) {
    final titleStyle = typography.titleStyle;
    final bodyStyle = typography.bodyStyle;
    final titleFontSize = titleStyle.fontSize ?? 28;
    final bodyFontSize = bodyStyle.fontSize ?? 17;
    return switch (_titleLevel) {
      _ArticleTitleLevel.h1 => titleStyle,
      _ArticleTitleLevel.h2 => titleStyle.copyWith(
        fontSize: titleFontSize * 0.84,
        fontWeight: AppTypography.semiBold,
      ),
      _ArticleTitleLevel.h3 => bodyStyle.copyWith(
        fontSize: math.max(bodyFontSize * 1.12, 18),
        fontWeight: AppTypography.semiBold,
      ),
    };
  }

  String _titlePlaceholder() {
    return switch (_titleLevel) {
      _ArticleTitleLevel.h1 => '输入 H1 标题（可选）',
      _ArticleTitleLevel.h2 => '输入 H2 标题（可选）',
      _ArticleTitleLevel.h3 => '输入 H3 标题（可选）',
    };
  }

  TextStyle _semanticBlockStyle(
    ArticleDocumentBlock block,
    ArticleTypographySpec typography,
  ) {
    final titleFont = typography.titleStyle.fontSize ?? AppTypography.xl;
    final bodyFont = typography.bodyStyle.fontSize ?? AppTypography.base;
    return switch (block.type) {
      ArticleDocumentBlockType.heading2 => typography.titleStyle.copyWith(
        fontSize: titleFont * 0.82,
        fontWeight: AppTypography.semiBold,
      ),
      ArticleDocumentBlockType.heading3 => typography.bodyStyle.copyWith(
        fontSize: math.max(bodyFont * 1.14, 18),
        fontWeight: AppTypography.semiBold,
      ),
      ArticleDocumentBlockType.sectionTitle => typography.titleStyle.copyWith(
        fontSize: math.max(bodyFont * 1.28, 20),
        fontWeight: AppTypography.bold,
        letterSpacing: 0.18,
      ),
      _ => typography.bodyStyle,
    };
  }

  String _semanticPlaceholder(ArticleDocumentBlockType type) {
    return switch (type) {
      ArticleDocumentBlockType.heading2 => '输入正文 H2 标题',
      ArticleDocumentBlockType.heading3 => '输入正文 H3 标题',
      ArticleDocumentBlockType.sectionTitle => '输入分节标题',
      _ => '输入正文',
    };
  }

  Widget _buildSemanticTextField(
    BuildContext context,
    ArticlePageData page,
    ArticleDocumentBlock block,
    ArticleTypographySpec typography,
  ) {
    final controller = _semanticControllers[block.id];
    final focusNode = _semanticFocusNodes[block.id];
    if (controller == null || focusNode == null) {
      return const SizedBox.shrink();
    }
    final style = _semanticBlockStyle(block, typography);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Expanded(
          child: CupertinoTextField(
            controller: controller,
            focusNode: focusNode,
            padding: EdgeInsets.zero,
            decoration: const BoxDecoration(),
            placeholder: _semanticPlaceholder(block.type),
            style: style,
            placeholderStyle: typography.placeholderStyle.copyWith(
              fontSize: style.fontSize,
              fontWeight: style.fontWeight,
            ),
            onTap: () {
              widget.onActivePageChanged(page.id);
              widget.onActiveBlockChanged(block.id);
            },
            onChanged: (value) => widget.onUpdateTextBlock(block.id, value),
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        CupertinoButton(
          padding: EdgeInsets.zero,
          minimumSize: const Size.square(28),
          onPressed: () => widget.onRemoveTextBlock(block.id),
          child: Icon(
            CupertinoIcons.minus_circle,
            size: AppSpacing.iconMedium,
            color: CupertinoColors.tertiaryLabel.resolveFrom(context),
          ),
        ),
      ],
    );
  }

  Future<void> _handleImageTap() async {
    final page = _activePage();
    if (page == null) {
      return;
    }
    setState(() {
      _surface = ArticleEditorAccessoryPanelType.none;
      _keyboardRestoring = false;
    });
    await widget.onEditPageImage(page);
  }

  double _resolveUnboundedPagerHeight(
    BuildContext context,
    BoxConstraints constraints,
    double aspectRatio,
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
    return pageWidth / aspectRatio;
  }

  @override
  Widget build(BuildContext context) {
    final keyboardInset = MediaQuery.viewInsetsOf(context).bottom;
    final safeBottom = MediaQuery.viewPaddingOf(context).bottom;
    if (keyboardInset > 0) {
      _keyboardHeightSnapshot = keyboardInset;
      _keyboardRestoring = false;
    }
    final panelHeight = _resolvedKeyboardPanelHeight(context);
    final toolbarHeight = SettingsSemanticConstants.toolbarHeightOverKeyboard;
    final accessoryBottomOffset =
        _surface == ArticleEditorAccessoryPanelType.none
        ? keyboardInset > 0
              ? keyboardInset
              : _keyboardRestoring
              ? panelHeight
              : safeBottom
        : 0.0;
    final contentBottomInset =
        toolbarHeight +
        (_surface == ArticleEditorAccessoryPanelType.none
            ? accessoryBottomOffset
            : panelHeight) +
        AppSpacing.interGroupSm;

    return LayoutBuilder(
      builder: (context, constraints) {
        final metrics = resolveArticleCanvasMetrics(
          context,
          constraints,
          variant: ArticleCanvasVariant.editor,
        );
        final pages = resolvePaginatedArticlePages(
          context: context,
          constraints: constraints,
          document: widget.state.articleDocument,
          template: widget.state.articleTemplate,
          fontPreset: widget.state.articleFontPreset,
          variant: ArticleCanvasVariant.editor,
        );
        _renderedPages = pages;
        _syncControllers(pages);
        _syncFocusNodes(pages);
        _syncSemanticControllers(pages);
        _syncSemanticFocusNodes(pages);
        final activeIndex = _activeIndexForPages(pages);
        if (_pageController.hasClients &&
            (_pageController.page?.round() ?? 0) != activeIndex) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (!mounted || !_pageController.hasClients) {
              return;
            }
            _pageController.jumpToPage(activeIndex);
          });
        }
        final pageView = PageView.builder(
          controller: _pageController,
          itemCount: pages.length,
          onPageChanged: (index) {
            widget.onActivePageChanged(pages[index].id);
          },
          itemBuilder: (context, index) {
            final page = pages[index];
            final typography = resolveArticleTypography(
              context,
              widget.state.articleTemplate,
              widget.state.articleFontPreset,
            );
            final titleStyle = _resolveTitleStyle(typography);
            return Padding(
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
              child: ArticlePageShell(
                template: widget.state.articleTemplate,
                fontPreset: widget.state.articleFontPreset,
                pageIndex: index,
                totalPages: pages.length,
                aspectRatio: metrics.aspectRatio,
                contentPadding: metrics.contentPadding,
                child: LayoutBuilder(
                  builder: (context, contentConstraints) {
                    const coverTitleLineHeight = 1.15;
                    final coverHeight =
                        index == 0 &&
                            widget.state.articleCoverImagePath.trim().isNotEmpty
                        ? math.min(
                            140.0,
                            math.max(0.0, contentConstraints.maxHeight * 0.22),
                          )
                        : 0.0;
                    final coverTitleStyle = titleStyle.copyWith(
                      color: AppColors.white,
                      height: coverTitleLineHeight,
                      shadows: <Shadow>[
                        Shadow(
                          color: AppColors.black.withValues(alpha: 0.4),
                          blurRadius: 18,
                          offset: const Offset(0, 4),
                        ),
                      ],
                    );
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        if (coverHeight > 0) ...<Widget>[
                          ClipRRect(
                            borderRadius: BorderRadius.circular(
                              AppSpacing.radiusTwenty,
                            ),
                            child: SizedBox(
                              height: coverHeight,
                              width: double.infinity,
                              child: Stack(
                                fit: StackFit.expand,
                                children: <Widget>[
                                  ArticleAdaptiveImage(
                                    key: const ValueKey<String>(
                                      'article-editor-frontispiece-image',
                                    ),
                                    imageUrl:
                                        widget.state.articleCoverImagePath,
                                  ),
                                  Positioned.fill(
                                    child: DecoratedBox(
                                      decoration: BoxDecoration(
                                        gradient: LinearGradient(
                                          begin: Alignment.topCenter,
                                          end: Alignment.bottomCenter,
                                          colors: <Color>[
                                            AppColors.black.withValues(
                                              alpha: 0.04,
                                            ),
                                            AppColors.black.withValues(
                                              alpha: 0.18,
                                            ),
                                            AppColors.black.withValues(
                                              alpha: 0.74,
                                            ),
                                          ],
                                          stops: const <double>[0.0, 0.48, 1.0],
                                        ),
                                      ),
                                    ),
                                  ),
                                  Positioned(
                                    left: AppSpacing.containerSm,
                                    right: AppSpacing.containerSm,
                                    bottom: AppSpacing.containerSm,
                                    child: CupertinoTextField(
                                      controller: widget.titleController,
                                      focusNode: widget.titleFocusNode,
                                      padding: EdgeInsets.zero,
                                      decoration: const BoxDecoration(),
                                      placeholder: _titlePlaceholder(),
                                      style: coverTitleStyle,
                                      placeholderStyle: coverTitleStyle
                                          .copyWith(
                                            color: AppColors.white.withValues(
                                              alpha: 0.72,
                                            ),
                                          ),
                                      maxLines: 3,
                                      onChanged: widget.onTitleChanged,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                          SizedBox(height: AppSpacing.interGroupSm),
                        ],
                        if (index == 0 && coverHeight <= 0) ...<Widget>[
                          CupertinoTextField(
                            controller: widget.titleController,
                            focusNode: widget.titleFocusNode,
                            padding: EdgeInsets.zero,
                            decoration: const BoxDecoration(),
                            placeholder: _titlePlaceholder(),
                            style: titleStyle,
                            placeholderStyle: typography.placeholderStyle
                                .copyWith(
                                  fontSize: titleStyle.fontSize,
                                  fontWeight: titleStyle.fontWeight,
                                ),
                            onChanged: widget.onTitleChanged,
                          ),
                          SizedBox(height: AppSpacing.interGroupSm),
                        ],
                        if (page.contentBlocks.isNotEmpty) ...<Widget>[
                          ...page.contentBlocks.map(
                            (block) => Padding(
                              padding: EdgeInsets.only(
                                bottom: AppSpacing.intraGroupSm,
                              ),
                              child: _buildSemanticTextField(
                                context,
                                page,
                                block,
                                typography,
                              ),
                            ),
                          ),
                        ],
                        if (page.imageUrl.trim().isNotEmpty) ...<Widget>[
                          GestureDetector(
                            onTap: () => widget.onEditPageImage(page),
                            child: ClipRRect(
                              borderRadius: BorderRadius.circular(
                                AppSpacing.radiusTwenty,
                              ),
                              child: AspectRatio(
                                aspectRatio: page.usesWrappedLayout
                                    ? 1
                                    : metrics.fullWidthImageAspectRatio,
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
                                widget.onUpdatePageImageLayout(page, value);
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
                              focusNode: _pageFocusNodes[page.id],
                              maxLines: null,
                              minLines: page.usesWrappedLayout ? 8 : 12,
                              padding: EdgeInsets.zero,
                              decoration: const BoxDecoration(),
                              placeholder: '继续写内容，支持 emoji、图片、序号和模板',
                              style: typography.bodyStyle,
                              placeholderStyle: typography.placeholderStyle,
                              onTap: () => widget.onActivePageChanged(page.id),
                              onChanged: (value) =>
                                  widget.onUpdatePageText(page, value),
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
                              onPressed: () => widget.onRemovePage(page),
                              child: Icon(
                                CupertinoIcons.minus_circle,
                                size: AppSpacing.iconMedium,
                                color: CupertinoColors.tertiaryLabel
                                    .resolveFrom(context),
                              ),
                            ),
                          ),
                        ],
                      ],
                    );
                  },
                ),
              ),
            );
          },
        );
        final pagerHeight = constraints.hasBoundedHeight
            ? null
            : _resolveUnboundedPagerHeight(
                context,
                constraints,
                metrics.aspectRatio,
              );
        final pageViewport = constraints.hasBoundedHeight
            ? pageView
            : SizedBox(height: pagerHeight, child: pageView);

        final content = Stack(
          children: <Widget>[
            Positioned.fill(
              child: Padding(
                padding: EdgeInsets.only(bottom: contentBottomInset),
                child: pageViewport,
              ),
            ),
            Positioned(
              left: 0,
              right: 0,
              bottom: accessoryBottomOffset,
              child: ArticleEditorAccessoryHost(
                panelType: _surface,
                panelHeight: panelHeight,
                template: widget.state.articleTemplate,
                fontPreset: widget.state.articleFontPreset,
                coverImagePaths: widget.state.imagePaths,
                selectedCoverPath: widget.state.articleCoverImagePath,
                emojiUsesKeyboardGlyph:
                    _surface == ArticleEditorAccessoryPanelType.emoji,
                activeStructureAction: _activeStructureAction,
                onImageTap: _handleImageTap,
                onEmojiTap: () =>
                    _togglePanel(ArticleEditorAccessoryPanelType.emoji),
                onStructureTap: () =>
                    _togglePanel(ArticleEditorAccessoryPanelType.structure),
                onTemplateTap: () =>
                    _togglePanel(ArticleEditorAccessoryPanelType.template),
                onFontTap: () =>
                    _togglePanel(ArticleEditorAccessoryPanelType.font),
                onEmojiSelected: _insertEmoji,
                onStructureActionSelected: _applyStructureAction,
                onCoverSelected: widget.onCoverChanged,
                onTemplateSelected: widget.onTemplateChanged,
                onFontSelected: widget.onFontPresetChanged,
              ),
            ),
          ],
        );

        if (constraints.hasBoundedHeight) {
          return content;
        }
        return SizedBox(
          height: (pagerHeight ?? 0) + contentBottomInset,
          child: content,
        );
      },
    );
  }
}
