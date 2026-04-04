// 文章编辑器：纵向滚动模式，按 document.nodes 遍历渲染。
// 编辑态不分页，预览态由 ArticleReadOnlyBookDeck 独立分页渲染。
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_image_intrinsic_registry.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/article_editor_accessory_panels.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

class ArticleEditor extends StatefulWidget {
  const ArticleEditor({
    super.key,
    required this.state,
    required this.titleController,
    required this.titleFocusNode,
    required this.onTitleChanged,
    required this.onTitleStyleChanged,
    required this.onUpdateNodeText,
    required this.onUpdateNodeImageLayout,
    required this.onUpdateNodeCaption,
    required this.onEditNodeImage,
    required this.onRemoveNodeImage,
    required this.onInsertImageAfter,
    required this.onActiveBlockChanged,
    required this.onInsertTextNodeAfter,
    this.onArticleIntrinsicImageResolved,
    this.onPaperTextureSelected,
    this.onFontSelected,
    this.immersive = false,
    this.canUndo = false,
    this.canRedo = false,
    this.onUndo,
    this.onRedo,
  });

  final CreateEditorState state;
  final TextEditingController titleController;
  final FocusNode titleFocusNode;
  final ValueChanged<String> onTitleChanged;
  final ValueChanged<ArticleDocumentTitleStyle> onTitleStyleChanged;
  final void Function(String nodeId, String value) onUpdateNodeText;
  final void Function(String nodeId, String layout) onUpdateNodeImageLayout;
  final void Function(String nodeId, String caption) onUpdateNodeCaption;
  final Future<void> Function(String nodeId) onEditNodeImage;
  final void Function(String nodeId) onRemoveNodeImage;
  final Future<void> Function(String? afterNodeId) onInsertImageAfter;
  final ValueChanged<String?> onActiveBlockChanged;
  final String Function(String afterNodeId, {String initialText}) onInsertTextNodeAfter;
  final VoidCallback? onArticleIntrinsicImageResolved;
  final ValueChanged<ArticlePaperTexture>? onPaperTextureSelected;
  final ValueChanged<ArticleFontPreset>? onFontSelected;
  final bool immersive;
  final bool canUndo;
  final bool canRedo;
  final VoidCallback? onUndo;
  final VoidCallback? onRedo;

  @override
  State<ArticleEditor> createState() => _ArticleEditorState();
}

class _ArticleEditorState extends State<ArticleEditor> {
  final Map<String, TextEditingController> _nodeControllers =
      <String, TextEditingController>{};
  final Map<String, FocusNode> _nodeFocusNodes =
      <String, FocusNode>{};
  final Map<String, TextEditingController> _captionControllers =
      <String, TextEditingController>{};

  ArticleEditorAccessoryPanelType _panelType =
      ArticleEditorAccessoryPanelType.none;
  String? _focusedNodeId;
  String? _selectedImageNodeId;
  String? _pendingFocusNodeId;

  /// 环绕图旁文本 node 的 id 集合——这些 node 在 _buildWrapFigureNode 中已渲染，
  /// 外层 _buildNodeWidgets 应跳过它们，避免重复渲染。
  final Set<String> _wrapBesideNodeIds = <String>{};

  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    for (final c in _nodeControllers.values) {
      c.dispose();
    }
    for (final f in _nodeFocusNodes.values) {
      f.dispose();
    }
    for (final c in _captionControllers.values) {
      c.dispose();
    }
    _placeholderBodyController?.dispose();
    _placeholderBodyFocusNode?.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  // ── 控制器管理 ──

  TextEditingController _controllerFor(String nodeId, String text) {
    return _nodeControllers.putIfAbsent(nodeId, () {
      return TextEditingController(text: text);
    });
  }

  FocusNode _focusNodeFor(String nodeId) {
    return _nodeFocusNodes.putIfAbsent(nodeId, () {
      final f = FocusNode(debugLabel: 'node_$nodeId');
      f.addListener(() {
        if (f.hasFocus) {
          _focusedNodeId = nodeId;
          widget.onActiveBlockChanged(nodeId);
          if (_selectedImageNodeId != null) {
            setState(() => _selectedImageNodeId = null);
          }
        }
      });
      return f;
    });
  }

  TextEditingController _captionControllerFor(String nodeId, String text) {
    return _captionControllers.putIfAbsent(nodeId, () {
      return TextEditingController(text: text);
    });
  }

  void _syncControllers(List<ArticleDocumentNode> nodes) {
    final liveIds = nodes.map((n) => n.id).toSet();
    final staleIds =
        _nodeControllers.keys.where((id) => !liveIds.contains(id)).toList();
    for (final id in staleIds) {
      _nodeControllers.remove(id)?.dispose();
      _nodeFocusNodes.remove(id)?.dispose();
      _captionControllers.remove(id)?.dispose();
    }
    for (final node in nodes) {
      final c = _controllerFor(node.id, node.text);
      final f = _nodeFocusNodes[node.id];
      // 仅在无焦点时同步文本，避免打断输入法 composing
      if (f != null && !f.hasFocus && c.text != node.text) {
        c.text = node.text;
      }
      if (node.isFigure) {
        final cc = _captionControllerFor(node.id, node.caption);
        if (cc.text != node.caption) {
          cc.text = node.caption;
        }
      }
    }
  }

  // ── 辅助面板 ──

  void _onEmojiSelected(String emoji) {
    if (_focusedNodeId == 'title') {
      _insertAtCursor(widget.titleController, emoji);
      widget.onTitleChanged(widget.titleController.text);
      return;
    }
    final c = _nodeControllers[_focusedNodeId];
    if (c != null && _focusedNodeId != null) {
      _insertAtCursor(c, emoji);
      widget.onUpdateNodeText(_focusedNodeId!, c.text);
    }
  }

  void _insertAtCursor(TextEditingController c, String text) {
    final sel = c.selection;
    if (!sel.isValid) {
      c.text = c.text + text;
      return;
    }
    final next = c.text.replaceRange(sel.start, sel.end, text);
    c.value = TextEditingValue(
      text: next,
      selection: TextSelection.collapsed(offset: sel.start + text.length),
    );
  }

  ArticleEditorStructureAction? _activeStructureAction() {
    return switch (widget.state.articleDocument.titleStyle) {
      ArticleDocumentTitleStyle.major =>
        ArticleEditorStructureAction.titleMajor,
      ArticleDocumentTitleStyle.minor =>
        ArticleEditorStructureAction.titleMinor,
      ArticleDocumentTitleStyle.none =>
        ArticleEditorStructureAction.titleNone,
    };
  }

  void _onStructureAction(ArticleEditorStructureAction action) {
    switch (action) {
      case ArticleEditorStructureAction.titleNone:
        widget.onTitleStyleChanged(ArticleDocumentTitleStyle.none);
      case ArticleEditorStructureAction.titleMajor:
        widget.onTitleStyleChanged(ArticleDocumentTitleStyle.major);
      case ArticleEditorStructureAction.titleMinor:
        widget.onTitleStyleChanged(ArticleDocumentTitleStyle.minor);
      case ArticleEditorStructureAction.orderedList:
      case ArticleEditorStructureAction.bulletList:
        break;
    }
  }

  void _togglePanel(ArticleEditorAccessoryPanelType panel) {
    setState(() {
      _panelType = _panelType == panel
          ? ArticleEditorAccessoryPanelType.none
          : panel;
    });
  }

  // ── 构建 ──

  @override
  Widget build(BuildContext context) {
    final doc = widget.state.articleDocument;
    final nodes = doc.nodes;
    _syncControllers(nodes);

    final template = ArticleTemplatePreset.values.firstWhere(
      (t) => t.name == doc.template,
      orElse: () => ArticleTemplatePreset.gentle,
    );
    final fontPreset = ArticleFontPreset.values.firstWhere(
      (f) => f.name == doc.fontPreset,
      orElse: () => ArticleFontPreset.clean,
    );
    final typography = resolveArticleTypography(context, template, fontPreset);

    final panelHeight = _panelType != ArticleEditorAccessoryPanelType.none
        ? 260.0
        : 0.0;

    return Stack(
      children: <Widget>[
        Positioned.fill(
          bottom: SettingsSemanticConstants.toolbarHeightOverKeyboard +
              panelHeight,
          child: GestureDetector(
            onTap: () {
              if (_selectedImageNodeId != null) {
                setState(() => _selectedImageNodeId = null);
              }
            },
            child: SingleChildScrollView(
              controller: _scrollController,
              padding: EdgeInsets.only(
                top: MediaQuery.of(context).padding.top +
                    AppSpacing.containerMd,
                bottom: AppSpacing.containerXl,
                left: AppSpacing.containerMd,
                right: AppSpacing.containerMd,
              ),
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(
                    maxWidth: AppSpacing.feedMaxContentWidth,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: _buildNodeWidgets(
                      context,
                      nodes,
                      typography,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
        Positioned(
          left: 0,
          right: 0,
          bottom: 0,
          child: ArticleEditorAccessoryHost(
            panelType: _panelType,
            panelHeight: panelHeight,
            template: template,
            paperTexture: widget.state.articlePaperTexture,
            fontPreset: fontPreset,
            coverImagePaths: widget.state.imagePaths,
            selectedCoverPath: doc.coverImageUrl,
            onImageTap: () async => widget.onInsertImageAfter(_focusedNodeId),
            onEmojiTap: () =>
                _togglePanel(ArticleEditorAccessoryPanelType.emoji),
            onStyleTap: () =>
                _togglePanel(ArticleEditorAccessoryPanelType.style),
            onListTap: () =>
                _togglePanel(ArticleEditorAccessoryPanelType.list),
            onTypographyTap: () =>
                _togglePanel(ArticleEditorAccessoryPanelType.typography),
            onEmojiSelected: _onEmojiSelected,
            onStructureActionSelected: _onStructureAction,
            onCoverSelected: (_) {},
            onTemplateSelected: (_) {},
            onPaperTextureSelected: (texture) {
              widget.onPaperTextureSelected?.call(texture);
            },
            onFontSelected: (preset) {
              widget.onFontSelected?.call(preset);
            },
            activeStructureAction: _activeStructureAction(),
            canUndo: widget.canUndo,
            canRedo: widget.canRedo,
            onUndo: widget.onUndo ?? () {},
            onRedo: widget.onRedo ?? () {},
          ),
        ),
      ],
    );
  }

  /// 将 document node 类型映射到间距语义。
  static ArticleSpacingSemantic _spacingSemanticForNode(
    ArticleDocumentNode node,
  ) {
    if (node.isFigure) return ArticleSpacingSemantic.figure;
    if (node.type == ArticleDocumentNodeType.headingMajor) {
      return ArticleSpacingSemantic.headingMajor;
    }
    if (node.type == ArticleDocumentNodeType.headingMinor) {
      return ArticleSpacingSemantic.headingMinor;
    }
    return ArticleSpacingSemantic.paragraph;
  }

  List<Widget> _buildNodeWidgets(
    BuildContext context,
    List<ArticleDocumentNode> nodes,
    ArticleTypographySpec typography,
  ) {
    _wrapBesideNodeIds.clear();

    // 预扫描：标记环绕图旁文本 node——紧跟 wrapLeft/wrapRight 之后的
    // 所有连续文本 node，它们会在 _buildWrapFigureNode 中一并渲染。
    for (var i = 0; i < nodes.length; i++) {
      final node = nodes[i];
      if (node.isFigure && node.usesWrappedLayout) {
        for (var j = i + 1; j < nodes.length; j++) {
          final next = nodes[j];
          if (next.isFigure || next.isDocumentTitle) break;
          _wrapBesideNodeIds.add(next.id);
        }
      }
    }

    final spacing = articleSpacingResolver();
    final widgets = <Widget>[];
    widgets.add(_buildTitleField(context, typography));

    // 跟踪上一个已渲染 node 的语义类型，用于计算间距。
    // 标题之后的第一个 node 使用 documentTitle 作为前驱。
    ArticleSpacingSemantic? prevSemantic =
        ArticleSpacingSemantic.documentTitle;

    bool hasVisibleTextNode = false;
    for (var i = 0; i < nodes.length; i++) {
      final node = nodes[i];
      if (node.isDocumentTitle) continue;
      if (_wrapBesideNodeIds.contains(node.id)) continue;

      final currentSemantic = _spacingSemanticForNode(node);

      // 连续图片使用专用间距，避免 figure 上下边距叠加过大
      final double gap;
      if (prevSemantic == ArticleSpacingSemantic.figure &&
          currentSemantic == ArticleSpacingSemantic.figure) {
        gap = spacing.betweenConsecutiveFigures();
      } else {
        gap = spacing.between(prevSemantic, currentSemantic);
      }
      if (gap > 0) {
        widgets.add(SizedBox(height: gap));
      }

      if (node.isFigure) {
        widgets.add(
          _buildFigureNode(context, node, nodes, i, typography),
        );
      } else {
        hasVisibleTextNode = true;
        widgets.add(_buildTextNode(context, node, typography));
      }

      prevSemantic = currentSemantic;
    }

    // 兜底：如果没有任何可编辑的文本 node（例如测试直接构造 state），
    // 显示一个占位输入框，确保用户始终能输入。
    if (!hasVisibleTextNode) {
      widgets.add(_buildPlaceholderBodyField(context, typography));
    }

    widgets.add(SizedBox(height: AppSpacing.oneHundred * 2));
    return widgets;
  }

  // ── 标题 ──

  Widget _buildTitleField(
    BuildContext context,
    ArticleTypographySpec typography,
  ) {
    return CupertinoTextField(
      key: TestKeys.createArticleTitleInput,
      controller: widget.titleController,
      focusNode: widget.titleFocusNode,
      keyboardType: TextInputType.text,
      textInputAction: TextInputAction.next,
      textAlignVertical: TextAlignVertical.top,
      maxLines: null,
      minLines: 1,
      padding: EdgeInsets.zero,
      decoration: const BoxDecoration(),
      style: typography.titleStyle,
      placeholder: '输入文章标题（可选）',
      placeholderStyle: typography.placeholderStyle.copyWith(
        fontSize: typography.titleStyle.fontSize,
      ),
      onTap: () {
        _focusedNodeId = 'title';
        widget.onActiveBlockChanged(null);
        if (_selectedImageNodeId != null) {
          setState(() => _selectedImageNodeId = null);
        }
      },
      onChanged: widget.onTitleChanged,
    );
  }

  // ── 占位正文输入框（文档无文本 node 时显示） ──

  TextEditingController? _placeholderBodyController;
  FocusNode? _placeholderBodyFocusNode;

  Widget _buildPlaceholderBodyField(
    BuildContext context,
    ArticleTypographySpec typography,
  ) {
    _placeholderBodyController ??= TextEditingController();
    _placeholderBodyFocusNode ??= FocusNode(debugLabel: 'placeholder_body');
    return CupertinoTextField(
      key: TestKeys.createMomentInput,
      controller: _placeholderBodyController!,
      focusNode: _placeholderBodyFocusNode!,
      keyboardType: TextInputType.multiline,
      textInputAction: TextInputAction.newline,
      textAlignVertical: TextAlignVertical.top,
      maxLines: null,
      minLines: 3,
      padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
      decoration: const BoxDecoration(),
      style: typography.bodyStyle,
      placeholder: '继续写内容，支持 emoji、图片、序号和模板',
      placeholderStyle: typography.placeholderStyle,
      onTap: () {
        _focusedNodeId = '_placeholder_body';
        widget.onActiveBlockChanged(null);
      },
      onChanged: (value) {
        // 当用户在占位框输入文字时，通知 provider 创建一个真正的 paragraph node
        if (value.trim().isNotEmpty) {
          widget.onUpdateNodeText('_placeholder_body', value);
          _placeholderBodyController?.clear();
        }
      },
    );
  }

  // ── 文本 node ──

  Widget _buildTextNode(
    BuildContext context,
    ArticleDocumentNode node,
    ArticleTypographySpec typography,
  ) {
    final c = _controllerFor(node.id, node.text);
    final f = _focusNodeFor(node.id);

    // 自动聚焦：由 _InsertSlot 创建新 node 后触发
    if (_pendingFocusNodeId == node.id) {
      _pendingFocusNodeId = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && !f.hasFocus) f.requestFocus();
      });
    }

    final style = switch (node.type) {
      ArticleDocumentNodeType.headingMajor => typography.bodyStyle.copyWith(
          fontSize:
              (typography.bodyStyle.fontSize ?? AppTypography.base) * 1.3,
          fontWeight: AppTypography.semiBold,
        ),
      ArticleDocumentNodeType.headingMinor => typography.bodyStyle.copyWith(
          fontSize:
              (typography.bodyStyle.fontSize ?? AppTypography.base) * 1.15,
          fontWeight: AppTypography.medium,
        ),
      _ => typography.bodyStyle,
    };

    String? placeholder;
    if (node.type == ArticleDocumentNodeType.paragraph && !node.hasText) {
      placeholder = '继续写内容，支持 emoji、图片、序号和模板';
    }

    return CupertinoTextField(
      key: ValueKey<String>('node_text_${node.id}'),
      controller: c,
      focusNode: f,
      keyboardType: TextInputType.multiline,
      textInputAction: TextInputAction.newline,
      textAlignVertical: TextAlignVertical.top,
      maxLines: null,
      minLines: 1,
      padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
      decoration: const BoxDecoration(),
      style: style,
      placeholder: placeholder,
      placeholderStyle: typography.placeholderStyle,
      onChanged: (value) => widget.onUpdateNodeText(node.id, value),
    );
  }

  // ── 图片 node ──

  Widget _buildFigureNode(
    BuildContext context,
    ArticleDocumentNode node,
    List<ArticleDocumentNode> allNodes,
    int nodeIndex,
    ArticleTypographySpec typography,
  ) {
    final isSelected = _selectedImageNodeId == node.id;
    final usesWrap =
        node.imageLayout == 'wrapLeft' || node.imageLayout == 'wrapRight';

    if (usesWrap) {
      return _buildWrapFigureNode(
        context,
        node,
        allNodes,
        nodeIndex,
        typography,
        isSelected,
      );
    }
    return _buildFullWidthFigureNode(context, node, typography, isSelected);
  }

  Widget _buildFullWidthFigureNode(
    BuildContext context,
    ArticleDocumentNode node,
    ArticleTypographySpec typography,
    bool isSelected,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _buildImageWidget(context, node, isSelected),
        if (node.caption.trim().isNotEmpty || isSelected)
          _buildCaptionField(context, node, typography),
        if (isSelected) _buildImageToolbar(context, node),
      ],
    );
  }

  Widget _buildWrapFigureNode(
    BuildContext context,
    ArticleDocumentNode node,
    List<ArticleDocumentNode> allNodes,
    int nodeIndex,
    ArticleTypographySpec typography,
    bool isSelected,
  ) {
    final isLeft = node.imageLayout == 'wrapLeft';
    final screenWidth =
        MediaQuery.of(context).size.width - AppSpacing.containerMd * 2;
    final imageWidth = (screenWidth * 0.42).clamp(100.0, 200.0);
    final aspect =
        ArticleImageIntrinsicRegistry.aspectRatioFor(node.imageUrl) ?? (4 / 3);
    final imageHeight = imageWidth / aspect;

    // 图片 + 说明列
    final imageColumn = SizedBox(
      width: imageWidth,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _buildImageWidget(context, node, isSelected, width: imageWidth),
          if (node.caption.trim().isNotEmpty || isSelected)
            _buildCaptionField(context, node, typography),
        ],
      ),
    );

    // 图旁文本：紧跟此 figure 之后的所有连续文本 node
    // 使用 Stack 实现环绕效果：文字占满全宽，图片浮在一侧上方
    final besideTextWidgets = <Widget>[];
    final besideSpacing = articleSpacingResolver();
    ArticleSpacingSemantic? prevBesideSemantic;
    for (var j = nodeIndex + 1; j < allNodes.length; j++) {
      final next = allNodes[j];
      if (next.isFigure || next.isDocumentTitle) break;
      final nextSemantic = _spacingSemanticForNode(next);
      final besideGap = besideSpacing.between(prevBesideSemantic, nextSemantic);
      if (besideGap > 0 && besideTextWidgets.isNotEmpty) {
        besideTextWidgets.add(SizedBox(height: besideGap));
      }
      besideTextWidgets.add(_buildTextNode(context, next, typography));
      prevBesideSemantic = nextSemantic;
    }

    Widget? besideTextNode;
    if (besideTextWidgets.isNotEmpty) {
      besideTextNode = Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: besideTextWidgets,
      );
    }

    // 图片区域的总高度（图片 + 可能的 caption）
    final captionExtra =
        (node.caption.trim().isNotEmpty || isSelected) ? 40.0 : 0.0;
    final floatHeight = imageHeight + captionExtra;
    final gap = AppSpacing.intraGroupSm;

    if (besideTextNode == null) {
      // 无旁文本，只渲染图片
      return Column(
        crossAxisAlignment:
            isLeft ? CrossAxisAlignment.start : CrossAxisAlignment.end,
        children: <Widget>[
          imageColumn,
          if (isSelected)
            _buildImageToolbar(
              context,
              node,
              imageWidth: imageWidth,
              alignment:
                  isLeft ? Alignment.centerLeft : Alignment.centerRight,
            ),
        ],
      );
    }

    // Stack 环绕布局：文字全宽，图片浮在一侧
    // 文字通过 padding 在图片区域留出空间，超出图片高度后自然占满全宽
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Stack(
          children: <Widget>[
            // 文字层：全宽，上方在图片侧留出 padding
            Padding(
              padding: EdgeInsets.only(
                left: isLeft ? imageWidth + gap : 0,
                right: isLeft ? 0 : imageWidth + gap,
              ),
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: floatHeight),
                child: besideTextNode,
              ),
            ),
            // 图片层：浮在一侧上方
            Positioned(
              left: isLeft ? 0 : null,
              right: isLeft ? null : 0,
              top: 0,
              width: imageWidth,
              child: imageColumn,
            ),
          ],
        ),
        if (isSelected)
          _buildImageToolbar(
            context,
            node,
            imageWidth: imageWidth,
            alignment:
                isLeft ? Alignment.centerLeft : Alignment.centerRight,
          ),
      ],
    );
  }

  Widget _buildImageWidget(
    BuildContext context,
    ArticleDocumentNode node,
    bool isSelected, {
    double? width,
  }) {
    final url = node.imageUrl.trim();
    if (url.isEmpty) return const SizedBox.shrink();

    final aspect = ArticleImageIntrinsicRegistry.aspectRatioFor(url) ?? (4 / 3);

    Widget image;
    if (url.startsWith('http://') || url.startsWith('https://')) {
      image = Image.network(url, fit: BoxFit.cover);
    } else {
      image = Image.file(File(url), fit: BoxFit.cover);
    }

    return GestureDetector(
      onTap: () => setState(() {
        _selectedImageNodeId =
            _selectedImageNodeId == node.id ? null : node.id;
      }),
      child: Container(
        decoration: isSelected
            ? BoxDecoration(
                border: Border.all(
                  color: CupertinoColors.activeBlue.resolveFrom(context),
                  width: AppSpacing.two,
                ),
              )
            : null,
        child: AspectRatio(aspectRatio: aspect, child: image),
      ),
    );
  }

  Widget _buildCaptionField(
    BuildContext context,
    ArticleDocumentNode node,
    ArticleTypographySpec typography,
  ) {
    final c = _captionControllerFor(node.id, node.caption);
    return Padding(
      padding: EdgeInsets.only(top: articleCaptionSpacing()),
      child: CupertinoTextField(
        key: ValueKey<String>('node_caption_${node.id}'),
        controller: c,
        keyboardType: TextInputType.text,
        textInputAction: TextInputAction.done,
        maxLines: 1,
        padding: EdgeInsets.zero,
        decoration: const BoxDecoration(),
        textAlign: TextAlign.center,
        style: typography.captionStyle,
        placeholder: '添加图片说明',
        placeholderStyle: typography.placeholderStyle.copyWith(
          fontSize: typography.captionStyle.fontSize,
        ),
        onChanged: (v) => widget.onUpdateNodeCaption(node.id, v),
      ),
    );
  }

  Widget _buildImageToolbar(
    BuildContext context,
    ArticleDocumentNode node, {
    double? imageWidth,
    Alignment alignment = Alignment.center,
  }) {
    final fg = CupertinoColors.secondaryLabel.resolveFrom(context);
    final toolbar = Row(
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        _ToolBtn(
          icon: CupertinoIcons.rectangle,
          label: '全宽',
          active: node.imageLayout == 'fullWidth',
          color: fg,
          onTap: () =>
              widget.onUpdateNodeImageLayout(node.id, 'fullWidth'),
        ),
        SizedBox(width: AppSpacing.md),
        _ToolBtn(
          icon: CupertinoIcons.rectangle_split_3x1,
          label: '左图',
          active: node.imageLayout == 'wrapLeft',
          color: fg,
          onTap: () =>
              widget.onUpdateNodeImageLayout(node.id, 'wrapLeft'),
        ),
        SizedBox(width: AppSpacing.md),
        _ToolBtn(
          icon: CupertinoIcons.rectangle_split_3x1,
          label: '右图',
          active: node.imageLayout == 'wrapRight',
          color: fg,
          onTap: () =>
              widget.onUpdateNodeImageLayout(node.id, 'wrapRight'),
        ),
        SizedBox(width: AppSpacing.md),
        _ToolBtn(
          icon: CupertinoIcons.pencil,
          label: '编辑',
          active: false,
          color: fg,
          onTap: () => widget.onEditNodeImage(node.id),
        ),
        SizedBox(width: AppSpacing.md),
        _ToolBtn(
          icon: CupertinoIcons.trash,
          label: '删除',
          active: false,
          color: fg, // 低调灰色，不用红色吸引眼球
          onTap: () {
            widget.onRemoveNodeImage(node.id);
            setState(() => _selectedImageNodeId = null);
          },
        ),
      ],
    );

    // 环绕布局时工具栏跟随图片对齐
    if (imageWidth != null) {
      return Padding(
        padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
        child: SizedBox(
          width: imageWidth,
          child: FittedBox(
            fit: BoxFit.scaleDown,
            alignment: alignment,
            child: toolbar,
          ),
        ),
      );
    }

    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
      child: toolbar,
    );
  }
}

class _ToolBtn extends StatelessWidget {
  const _ToolBtn({
    required this.icon,
    required this.label,
    required this.active,
    required this.color,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool active;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = active ? CupertinoColors.activeBlue : color;
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: AppSpacing.iconMedium, color: c),
          SizedBox(height: AppSpacing.two),
          Text(
            label,
            style: TextStyle(fontSize: AppTypography.xs, color: c),
          ),
        ],
      ),
    );
  }
}


