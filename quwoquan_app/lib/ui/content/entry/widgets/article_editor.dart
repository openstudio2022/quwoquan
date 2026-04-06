// 文章编辑器：纵向滚动模式，按 document.nodes 遍历渲染。
// 编辑态不分页，预览态由 ArticleReadOnlyBookDeck 独立分页渲染。
import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_image_intrinsic_registry.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/article_theme.dart';
import 'package:quwoquan_app/ui/content/entry/models/article_editor_projection.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/article_editor_accessory_panels.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/article_wrap_layout.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/article_wrap_paragraph_editor.dart';

const String _kEmptyDocumentBodyFocusId = '__article_editor_empty_body__';

class ArticleEditor extends StatefulWidget {
  const ArticleEditor({
    super.key,
    required this.state,
    required this.titleController,
    required this.titleFocusNode,
    required this.onTitleChanged,
    required this.onTitleStyleChanged,
    required this.onUpdateNodeText,
    required this.onUpdateWrapParagraphTexts,
    required this.onUpdateNodeImageLayout,
    required this.onUpdateNodeCaption,
    required this.onEditNodeImage,
    required this.onRemoveNodeImage,
    required this.onInsertImageAfter,
    required this.onInsertImageAtSelection,
    required this.onActiveBlockChanged,
    required this.onInsertTextNodeAfter,
    required this.onEnsureWrapNodeGroup,
    this.onArticleIntrinsicImageResolved,
    this.onPaperTextureSelected,
    this.onFontSelected,
    this.immersive = false,
    this.canUndo = false,
    this.canRedo = false,
    this.onUndo,
    this.onRedo,
    this.onUpdateNodeType,
    this.onToggleInlineStyle,
    this.onCommitTextEdit,
    this.onUpdateNodeAlignment,
  });

  final CreateEditorState state;
  final TextEditingController titleController;
  final FocusNode titleFocusNode;
  final ValueChanged<String> onTitleChanged;
  final ValueChanged<ArticleDocumentTitleStyle> onTitleStyleChanged;
  final void Function(String nodeId, String value) onUpdateNodeText;
  final void Function(String figureNodeId, String narrowText, String belowText)
      onUpdateWrapParagraphTexts;
  final void Function(String nodeId, String layout) onUpdateNodeImageLayout;
  final void Function(String nodeId, String caption) onUpdateNodeCaption;
  final Future<void> Function(String nodeId) onEditNodeImage;
  final void Function(String nodeId) onRemoveNodeImage;
  final Future<void> Function(String? afterNodeId) onInsertImageAfter;
  final Future<void> Function(String nodeId, int selectionOffset)
  onInsertImageAtSelection;
  final ValueChanged<String?> onActiveBlockChanged;
  final String Function(String afterNodeId, {String initialText}) onInsertTextNodeAfter;
  final ArticleWrapNodeGroup? Function(String figureNodeId, {int? splitOffset})
      onEnsureWrapNodeGroup;
  final VoidCallback? onArticleIntrinsicImageResolved;
  final ValueChanged<ArticlePaperTexture>? onPaperTextureSelected;
  final ValueChanged<ArticleFontPreset>? onFontSelected;
  final bool immersive;
  final bool canUndo;
  final bool canRedo;
  final VoidCallback? onUndo;
  final VoidCallback? onRedo;
  final void Function(String nodeId, ArticleDocumentNodeType type)? onUpdateNodeType;
  final void Function(String nodeId, int start, int end, {bool? bold, bool? italic, bool? underline, bool? strikethrough})? onToggleInlineStyle;
  final VoidCallback? onCommitTextEdit;
  final void Function(String nodeId, String alignment)? onUpdateNodeAlignment;

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
  final Map<String, FocusNode> _captionFocusNodes =
      <String, FocusNode>{};
  final Map<String, TextSelection> _nodeSelections = <String, TextSelection>{};
  final Map<String, GlobalKey<ArticleWrapParagraphEditorState>> _wrapEditorKeys =
      <String, GlobalKey<ArticleWrapParagraphEditorState>>{};
  final Map<String, Set<String>> _wrapEditorGroupNodeIds =
      <String, Set<String>>{};
  final Set<String> _pendingWrapNormalizations = <String>{};

  ArticleEditorAccessoryPanelType _panelType =
      ArticleEditorAccessoryPanelType.none;
  String? _focusedNodeId;
  String? _selectedImageNodeId;
  String? _pendingFocusNodeId;
  int? _pendingFocusSelectionOffset;
  String? _activeSlotId;
  TextEditingController? _activeSlotController;
  FocusNode? _activeSlotFocusNode;
  TextEditingController? _emptyDocumentController;
  FocusNode? _emptyDocumentFocusNode;

  final ScrollController _scrollController = ScrollController();
  Timer? _textCommitDebounce;

  void _scheduleTextCommit() {
    _textCommitDebounce?.cancel();
    _textCommitDebounce = Timer(const Duration(seconds: 1), () {
      widget.onCommitTextEdit?.call();
    });
  }

  @override
  void dispose() {
    _textCommitDebounce?.cancel();
    for (final c in _nodeControllers.values) {
      c.dispose();
    }
    for (final f in _nodeFocusNodes.values) {
      f.dispose();
    }
    for (final c in _captionControllers.values) {
      c.dispose();
    }
    for (final f in _captionFocusNodes.values) {
      f.dispose();
    }
    _emptyDocumentController?.dispose();
    _emptyDocumentFocusNode?.dispose();
    _activeSlotController?.dispose();
    _activeSlotFocusNode?.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  // ── 控制器管理 ──

  TextEditingController _controllerFor(String nodeId, String text) {
    return _nodeControllers.putIfAbsent(nodeId, () {
      final controller = TextEditingController(text: text);
      controller.addListener(() {
        final focusNode = _nodeFocusNodes[nodeId];
        if (focusNode?.hasFocus == true) {
          _nodeSelections[nodeId] = controller.selection;
        }
      });
      return controller;
    });
  }

  FocusNode _focusNodeFor(String nodeId) {
    return _nodeFocusNodes.putIfAbsent(nodeId, () {
      final f = FocusNode(debugLabel: 'node_$nodeId');
      f.addListener(() {
        if (f.hasFocus) {
          _unfocusAllExcept(nodeId);
          widget.onActiveBlockChanged(nodeId);
          final controller = _nodeControllers[nodeId];
          if (controller != null) {
            _nodeSelections[nodeId] = controller.selection;
          }
          if (mounted) {
            setState(() {
              _focusedNodeId = nodeId;
              _activeSlotId = null;
              _activeSlotController?.clear();
              if (_selectedImageNodeId != null) {
                _selectedImageNodeId = null;
              }
            });
          }
        } else if (mounted) {
          // 焦点离开时提交一次 undo 点
          _textCommitDebounce?.cancel();
          widget.onCommitTextEdit?.call();
          setState(() {});
        }
      });
      return f;
    });
  }

  /// 清除除 [exceptNodeId] 以外的所有已知 FocusNode。
  /// 不使用 FocusManager.instance.primaryFocus?.unfocus()，
  /// 因为它会把刚获焦的目标也 unfocus 掉，导致焦点丢失后
  /// Flutter 自动把焦点给下一个可聚焦 widget，形成"双焦点"。
  void _unfocusAllExcept(String? exceptNodeId) {
    for (final entry in _nodeFocusNodes.entries) {
      if (entry.key != exceptNodeId && entry.value.hasFocus) {
        entry.value.unfocus();
      }
    }
    for (final entry in _wrapEditorKeys.entries) {
      final handledNodeIds = _wrapEditorGroupNodeIds[entry.key] ?? const <String>{};
      if (exceptNodeId != null && handledNodeIds.contains(exceptNodeId)) {
        continue;
      }
      entry.value.currentState?.unfocus();
    }
    for (final entry in _captionFocusNodes.entries) {
      if (entry.value.hasFocus) {
        entry.value.unfocus();
      }
    }
    if (_activeSlotFocusNode?.hasFocus ?? false) {
      _activeSlotFocusNode?.unfocus();
    }
  }

  FocusNode _captionFocusNodeFor(String nodeId) {
    return _captionFocusNodes.putIfAbsent(nodeId, () {
      return FocusNode(debugLabel: 'caption_$nodeId');
    });
  }

  TextEditingController _captionControllerFor(String nodeId, String text) {
    return _captionControllers.putIfAbsent(nodeId, () {
      return TextEditingController(text: text);
    });
  }

  void _syncControllers(
    List<ArticleDocumentNode> nodes, {
    Set<String> unmanagedNodeIds = const <String>{},
  }) {
    final liveIds = nodes.map((n) => n.id).toSet();
    final staleIds =
        _nodeControllers.keys
            .where((id) => !liveIds.contains(id) || unmanagedNodeIds.contains(id))
            .toList();
    for (final id in staleIds) {
      _nodeControllers.remove(id)?.dispose();
      _nodeFocusNodes.remove(id)?.dispose();
      if (!liveIds.contains(id)) {
        _captionControllers.remove(id)?.dispose();
        _nodeSelections.remove(id);
      }
    }
    for (final node in nodes) {
      if (unmanagedNodeIds.contains(node.id)) {
        continue;
      }
      final c = _controllerFor(node.id, node.text);
      final f = _nodeFocusNodes[node.id];
      // 仅在无焦点时同步文本，避免打断输入法 composing
      if (f != null && !f.hasFocus && c.text != node.text) {
        // 用 c.value= 一次性赋值，避免 c.text= 触发 listener 把 selection 重置到末尾
        final savedSelection = c.selection;
        final len = node.text.length;
        final clampedSelection = savedSelection.isValid
            ? TextSelection(
                baseOffset: savedSelection.baseOffset.clamp(0, len),
                extentOffset: savedSelection.extentOffset.clamp(0, len),
              )
            : TextSelection.collapsed(offset: len);
        c.value = TextEditingValue(
          text: node.text,
          selection: clampedSelection,
        );
      } else if (f == null && c.text != node.text) {
        // focusNode 还未创建（节点第一次出现），直接同步文本
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

  TextEditingController _ensureActiveSlotController() {
    return _activeSlotController ??= TextEditingController();
  }

  FocusNode _ensureActiveSlotFocusNode() {
    return _activeSlotFocusNode ??= FocusNode(debugLabel: 'article_slot')
      ..addListener(() {
        final controller = _activeSlotController;
        if (!(_activeSlotFocusNode?.hasFocus ?? false) &&
            (controller == null || controller.text.trim().isEmpty) &&
            mounted) {
          setState(() {
            _activeSlotId = null;
          });
        } else if (mounted) {
          setState(() {});
        }
      });
  }

  void _activateSlot(ArticleEditorSlotProjection slot) {
    final controller = _ensureActiveSlotController();
    controller.clear();
    final focusNode = _ensureActiveSlotFocusNode();
    // 先 unfocus 所有 node 和 wrap 内部的 FocusNode
    _unfocusAllExcept(null);
    widget.onActiveBlockChanged(null);
    setState(() {
      _activeSlotId = slot.id;
      _focusedNodeId = null;
      _selectedImageNodeId = null;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        focusNode.requestFocus();
      }
    });
  }

  // ── 辅助面板 ──

  void _onEmojiSelected(String emoji) {
    if (_focusedNodeId == 'title') {
      _insertAtCursor(widget.titleController, emoji);
      widget.onTitleChanged(widget.titleController.text);
      return;
    }
    final activeSlot = _activeSlotId == null
        ? null
        : projectionSlotById(
            buildArticleEditorProjection(widget.state.articleDocument.nodes),
            _activeSlotId,
          );
    if (activeSlot != null && _activeSlotController != null) {
      _insertAtCursor(_activeSlotController!, emoji);
      final value = _activeSlotController!.text;
      if (value.trim().isNotEmpty) {
        final newNodeId = widget.onInsertTextNodeAfter(
          activeSlot.anchorNodeId,
          initialText: value,
        );
        final selectionOffset =
            _activeSlotController!.selection.extentOffset.clamp(0, value.length);
        _nodeSelections[newNodeId] = TextSelection.collapsed(
          offset: selectionOffset,
        );
        setState(() {
          _pendingFocusNodeId = newNodeId;
          _pendingFocusSelectionOffset = selectionOffset;
          _focusedNodeId = newNodeId;
          _activeSlotId = null;
          _activeSlotController?.clear();
        });
      }
      return;
    }
    if (_focusedNodeId == _kEmptyDocumentBodyFocusId &&
        _emptyDocumentController != null) {
      _insertAtCursor(_emptyDocumentController!, emoji);
      final value = _emptyDocumentController!.text;
      if (value.trim().isNotEmpty) {
        final newNodeId = widget.onInsertTextNodeAfter(
          _bodyStartAnchorId(widget.state.articleDocument),
          initialText: value,
        );
        final selectionOffset =
            _emptyDocumentController!.selection.extentOffset.clamp(
              0,
              value.length,
            );
        _nodeSelections[newNodeId] = TextSelection.collapsed(
          offset: selectionOffset,
        );
        setState(() {
          _pendingFocusNodeId = newNodeId;
          _pendingFocusSelectionOffset = selectionOffset;
          _focusedNodeId = newNodeId;
          _emptyDocumentController?.clear();
        });
      }
      return;
    }
    final focusedNodeId = _focusedNodeId;
    if (focusedNodeId == null) {
      return;
    }
    final c = _nodeControllers[focusedNodeId];
    if (c != null) {
      _insertAtCursor(c, emoji);
      widget.onUpdateNodeText(focusedNodeId, c.text);
      _scheduleTextCommit();
      return;
    }
    for (final node in widget.state.articleDocument.nodes) {
      if (node.id != focusedNodeId || node.isFigure) {
        continue;
      }
      final selection =
          _nodeSelections[focusedNodeId] ??
          TextSelection.collapsed(offset: node.text.length);
      final start = selection.start.clamp(0, node.text.length);
      final end = selection.end.clamp(0, node.text.length);
      final nextText = node.text.replaceRange(start, end, emoji);
      final nextOffset = (start + emoji.length).clamp(0, nextText.length);
      _nodeSelections[focusedNodeId] = TextSelection.collapsed(
        offset: nextOffset,
      );
      widget.onUpdateNodeText(focusedNodeId, nextText);
      _scheduleTextCommit();
      return;
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
    // 如果焦点在正文节点上，返回该节点的类型对应的 action
    final focusedId = _focusedNodeId;
    if (focusedId != null && focusedId != 'title') {
      final node = widget.state.articleDocument.nodes
          .where((n) => n.id == focusedId)
          .firstOrNull;
      if (node != null && !node.isFigure && !node.isDocumentTitle) {
        return switch (node.type) {
          ArticleDocumentNodeType.headingMajor =>
            ArticleEditorStructureAction.headingMajor,
          ArticleDocumentNodeType.headingMinor =>
            ArticleEditorStructureAction.headingMinor,
          ArticleDocumentNodeType.orderedItem =>
            ArticleEditorStructureAction.orderedList,
          ArticleDocumentNodeType.bulletItem =>
            ArticleEditorStructureAction.bulletList,
          _ => null,
        };
      }
    }
    // 否则返回标题样式
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
      case ArticleEditorStructureAction.headingMajor:
        _updateFocusedNodeType(ArticleDocumentNodeType.headingMajor);
      case ArticleEditorStructureAction.headingMinor:
        _updateFocusedNodeType(ArticleDocumentNodeType.headingMinor);
      case ArticleEditorStructureAction.orderedList:
        _updateFocusedNodeType(ArticleDocumentNodeType.orderedItem);
      case ArticleEditorStructureAction.bulletList:
        _updateFocusedNodeType(ArticleDocumentNodeType.bulletItem);
      case ArticleEditorStructureAction.paragraph:
        _updateFocusedNodeType(ArticleDocumentNodeType.paragraph);
      case ArticleEditorStructureAction.blockquote:
        // TODO: 引用块暂未在文档模型中实现，占位
        break;
    }
  }

  void _updateFocusedNodeType(ArticleDocumentNodeType type) {
    final focusedId = _focusedNodeId;
    if (focusedId == null || focusedId == 'title') return;
    // 如果当前已经是该类型，切回段落
    final node = widget.state.articleDocument.nodes
        .where((n) => n.id == focusedId)
        .firstOrNull;
    if (node == null || node.isFigure || node.isDocumentTitle) return;
    final targetType = node.type == type
        ? ArticleDocumentNodeType.paragraph
        : type;
    widget.onUpdateNodeType?.call(focusedId, targetType);
  }

  /// 当前焦点节点的选区范围（用于行内样式 toggle）。
  TextSelection? _focusedNodeSelection() {
    final focusedId = _focusedNodeId;
    if (focusedId == null || focusedId == 'title') return null;
    return _nodeSelections[focusedId];
  }

  /// 当前焦点节点的 spans（用于行内样式按钮状态）。
  List<ArticleInlineSpan> _focusedNodeSpans() {
    final focusedId = _focusedNodeId;
    if (focusedId == null || focusedId == 'title') {
      return const <ArticleInlineSpan>[];
    }
    final node = widget.state.articleDocument.nodes
        .where((n) => n.id == focusedId)
        .firstOrNull;
    return node?.spans ?? const <ArticleInlineSpan>[];
  }

  void _onToggleInlineStyle({
    bool? bold,
    bool? italic,
    bool? underline,
    bool? strikethrough,
  }) {
    final focusedId = _focusedNodeId;
    if (focusedId == null || focusedId == 'title') return;
    final selection = _nodeSelections[focusedId];
    if (selection == null || selection.isCollapsed) return;
    // Toggle 语义：如果选区内该样式已全部激活，则关闭；否则开启
    final resolvedBold = bold != null
        ? !_isInlineStyleActive((s) => s.bold)
        : null;
    final resolvedItalic = italic != null
        ? !_isInlineStyleActive((s) => s.italic)
        : null;
    final resolvedUnderline = underline != null
        ? !_isInlineStyleActive((s) => s.underline)
        : null;
    final resolvedStrikethrough = strikethrough != null
        ? !_isInlineStyleActive((s) => s.strikethrough)
        : null;
    widget.onToggleInlineStyle?.call(
      focusedId,
      selection.start,
      selection.end,
      bold: resolvedBold,
      italic: resolvedItalic,
      underline: resolvedUnderline,
      strikethrough: resolvedStrikethrough,
    );
  }

  /// 检查当前焦点节点选区内某个行内样式是否全部激活。
  bool _isInlineStyleActive(bool Function(ArticleInlineSpan) predicate) {
    final focusedId = _focusedNodeId;
    if (focusedId == null || focusedId == 'title') return false;
    final selection = _nodeSelections[focusedId];
    if (selection == null || selection.isCollapsed) return false;
    final spans = _focusedNodeSpans();
    if (spans.isEmpty) return false;
    // 检查选区内每个字符是否都被至少一个满足 predicate 的 span 覆盖
    for (var i = selection.start; i < selection.end; i++) {
      final covered = spans.any(
        (s) => s.start <= i && i < s.end && predicate(s),
      );
      if (!covered) return false;
    }
    return true;
  }

  /// 当前焦点节点的对齐方式。
  String _activeAlignment() {
    final focusedId = _focusedNodeId;
    if (focusedId == null || focusedId == 'title') return 'left';
    final node = widget.state.articleDocument.nodes
        .where((n) => n.id == focusedId)
        .firstOrNull;
    if (node == null) return 'left';
    final align = node.textAlign.trim();
    return align.isEmpty ? 'left' : align;
  }

  /// 设置当前焦点节点的对齐方式。
  void _onAlignmentSelected(String alignment) {
    final focusedId = _focusedNodeId;
    if (focusedId == null || focusedId == 'title') return;
    widget.onUpdateNodeAlignment?.call(focusedId, alignment);
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
    final projection = buildArticleEditorProjection(nodes);
    final wrapParagraphIds = projection.entries
        .whereType<ArticleEditorWrapGroupProjection>()
        .expand((entry) => entry.paragraphNodeIds)
        .toSet();
    _syncControllers(nodes, unmanagedNodeIds: wrapParagraphIds);

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
                      projection,
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
            onImageTap: () async {
              final selectionTarget = _currentSelectionInsertionTarget();
              if (selectionTarget != null) {
                await widget.onInsertImageAtSelection(
                  selectionTarget.nodeId,
                  selectionTarget.selectionOffset,
                );
                return;
              }
              final activeSlot = projectionSlotById(projection, _activeSlotId);
              if (activeSlot != null) {
                await widget.onInsertImageAfter(activeSlot.anchorNodeId);
                return;
              }
              final titleAnchor = projection.entries.isNotEmpty
                  ? (projection.entries.first is ArticleEditorSlotProjection
                        ? (projection.entries.first as ArticleEditorSlotProjection)
                              .anchorNodeId
                        : kArticleEditorStartAnchorId)
                  : widget.state.articleDocument.nodes
                            .where((node) => node.isDocumentTitle)
                            .map((node) => node.id)
                            .firstWhere(
                              (id) => id.trim().isNotEmpty,
                              orElse: () => kArticleEditorStartAnchorId,
                            );
              final fallbackAnchor = switch (_focusedNodeId) {
                'title' => titleAnchor,
                _kEmptyDocumentBodyFocusId => titleAnchor,
                _ => _focusedNodeId,
              };
              await widget.onInsertImageAfter(
                _selectedImageNodeId ?? fallbackAnchor,
              );
            },
            onEmojiTap: () =>
                _togglePanel(ArticleEditorAccessoryPanelType.emoji),
            onStyleTap: () =>
                _togglePanel(ArticleEditorAccessoryPanelType.style),
            onEmojiSelected: _onEmojiSelected,
            onStructureActionSelected: _onStructureAction,
            activeStructureAction: _activeStructureAction(),
            canUndo: widget.canUndo,
            canRedo: widget.canRedo,
            onUndo: widget.onUndo ?? () {},
            onRedo: widget.onRedo ?? () {},
            onToggleBold: () => _onToggleInlineStyle(bold: true),
            onToggleItalic: () => _onToggleInlineStyle(italic: true),
            onToggleUnderline: () => _onToggleInlineStyle(underline: true),
            isBoldActive: _isInlineStyleActive((s) => s.bold),
            isItalicActive: _isInlineStyleActive((s) => s.italic),
            isUnderlineActive: _isInlineStyleActive((s) => s.underline),
            activeAlignment: _activeAlignment(),
            onAlignmentSelected: _onAlignmentSelected,
          ),
        ),
      ],
    );
  }

  String _bodyStartAnchorId(ArticleDocumentData document) {
    final titleNode = document.titleNode;
    if (titleNode != null && titleNode.id.trim().isNotEmpty) {
      return titleNode.id;
    }
    return kArticleEditorStartAnchorId;
  }

  double _slotGap(
    ArticleEditorSlotProjection slot,
    ArticleSpacingResolver spacing,
  ) {
    if (slot.previousSemantic != null && slot.nextSemantic != null) {
      return slot.previousSemantic == ArticleSpacingSemantic.figure &&
              slot.nextSemantic == ArticleSpacingSemantic.figure
          ? spacing.betweenConsecutiveFigures()
          : spacing.between(slot.previousSemantic, slot.nextSemantic!);
    }
    if (slot.previousSemantic != null) {
      return spacing.after(slot.previousSemantic!);
    }
    if (slot.nextSemantic != null) {
      return spacing.before(slot.nextSemantic!);
    }
    return slot.collapsedHeight;
  }

  List<Widget> _buildNodeWidgets(
    BuildContext context,
    ArticleEditorProjection projection,
    ArticleTypographySpec typography,
  ) {
    final widgets = <Widget>[];
    widgets.add(_buildTitleField(context, typography));

    if (!projection.hasContent) {
      widgets.add(_buildEmptyDocumentField(context, typography));
      widgets.add(SizedBox(height: AppSpacing.oneHundred * 2));
      return widgets;
    }

    final spacing = articleSpacingResolver();

    for (final entry in projection.entries) {
      if (entry is ArticleEditorSlotProjection) {
        final gap = _slotGap(entry, spacing);
        final shouldRenderStandalone = entry.isFigureFigureSlot ||
            entry.isTailSlot ||
            (entry.isStartSlot && entry.hasFigureBelow);
        if (gap > 0) {
          widgets.add(SizedBox(height: gap));
        }
        if (shouldRenderStandalone) {
          widgets.add(_buildInsertionSlot(context, entry, typography));
        }
        continue;
      }

      if (entry is ArticleEditorWrapGroupProjection) {
        widgets.add(_buildWrapGroup(context, entry, typography));
        continue;
      }

      if (entry is ArticleEditorNodeProjection) {
        if (entry.node.isFigure) {
          widgets.add(
            _buildFigureNode(
              context,
              entry.node,
              <ArticleDocumentNode>[entry.node],
              0,
              typography,
            ),
          );
        } else {
          widgets.add(_buildTextNode(context, entry.node, typography));
        }
      }
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
        widget.onActiveBlockChanged(null);
        setState(() {
          _focusedNodeId = 'title';
          _activeSlotId = null;
          _activeSlotController?.clear();
          if (_selectedImageNodeId != null) {
            _selectedImageNodeId = null;
          }
        });
      },
      onChanged: widget.onTitleChanged,
    );
  }

  // ── 空文档 materialize 输入框 ──

  Widget _buildEmptyDocumentField(
    BuildContext context,
    ArticleTypographySpec typography,
  ) {
    _emptyDocumentController ??= TextEditingController();
    _emptyDocumentFocusNode ??=
        FocusNode(debugLabel: _kEmptyDocumentBodyFocusId);
    return CupertinoTextField(
      key: TestKeys.createMomentInput,
      controller: _emptyDocumentController!,
      focusNode: _emptyDocumentFocusNode!,
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
        widget.onActiveBlockChanged(null);
        setState(() {
          _focusedNodeId = _kEmptyDocumentBodyFocusId;
          _activeSlotId = null;
          _activeSlotController?.clear();
          _selectedImageNodeId = null;
        });
      },
      onChanged: (value) {
        if (value.trim().isNotEmpty) {
          final newNodeId = widget.onInsertTextNodeAfter(
            _bodyStartAnchorId(widget.state.articleDocument),
            initialText: value,
          );
          final selectionOffset = value.length;
          _nodeSelections[newNodeId] = TextSelection.collapsed(
            offset: selectionOffset,
          );
          setState(() {
            _pendingFocusNodeId = newNodeId;
            _pendingFocusSelectionOffset = selectionOffset;
            _focusedNodeId = newNodeId;
            _emptyDocumentController?.clear();
          });
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
      final pendingSelection = _pendingFocusSelectionOffset;
      _pendingFocusSelectionOffset = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && !f.hasFocus) {
          f.requestFocus();
          final offset = (pendingSelection ?? c.text.length).clamp(0, c.text.length);
          c.selection = TextSelection.collapsed(offset: offset);
          _nodeSelections[node.id] = c.selection;
        }
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
      placeholderStyle: typography.placeholderStyle,
      onTap: () {
        // 延迟一帧读取 selection，确保 Flutter 已完成 hit test 和 selection 更新
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) {
            _nodeSelections[node.id] = c.selection;
          }
        });
      },
      onChanged: (value) {
        widget.onUpdateNodeText(node.id, value);
        _scheduleTextCommit();
      },
    );
  }

  Widget _buildInsertionSlot(
    BuildContext context,
    ArticleEditorSlotProjection slot,
    ArticleTypographySpec typography,
  ) {
    final isActive = _activeSlotId == slot.id;
    if (!isActive) {
      final showHint = slot.isFigureFigureSlot;
      // slot 只负责可点击区域，不承担语义间距
      final double effectiveHeight = slot.isTailSlot ? 88.0 : 44.0;
      return GestureDetector(
        key: ValueKey<String>('article_slot_${slot.id}'),
        behavior: HitTestBehavior.opaque,
        onTap: () => _activateSlot(slot),
        child: SizedBox(
          height: effectiveHeight,
          width: double.infinity,
          child: showHint
              ? Center(
                  child: Text(
                    '+ 想写点什么',
                    style: typography.bodyStyle.copyWith(
                      color: typography.placeholderStyle.color,
                    ),
                  ),
                )
              : null,
        ),
      );
    }

    final controller = _ensureActiveSlotController();
    final focusNode = _ensureActiveSlotFocusNode();
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () {
        if (!focusNode.hasFocus) {
          focusNode.requestFocus();
        }
      },
      child: CupertinoTextField(
        key: ValueKey<String>('article_slot_input_${slot.id}'),
        controller: controller,
        focusNode: focusNode,
        keyboardType: TextInputType.multiline,
        textInputAction: TextInputAction.newline,
        textAlignVertical: TextAlignVertical.top,
        maxLines: null,
        minLines: 1,
        padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
        decoration: const BoxDecoration(),
        style: typography.bodyStyle,
        placeholderStyle: typography.placeholderStyle,
        onChanged: (value) {
          if (value.trim().isEmpty) {
            return;
          }
          final newNodeId = widget.onInsertTextNodeAfter(
            slot.anchorNodeId,
            initialText: value,
          );
          if (newNodeId.trim().isEmpty) {
            return;
          }
          final selectionOffset = value.length;
          _nodeSelections[newNodeId] = TextSelection.collapsed(
            offset: selectionOffset,
          );
          setState(() {
            _pendingFocusNodeId = newNodeId;
            _pendingFocusSelectionOffset = selectionOffset;
            _focusedNodeId = newNodeId;
            _activeSlotId = null;
            controller.clear();
          });
        },
      ),
    );
  }

  /// 渲染激活状态的 slot TextField，不含图片缓冲 padding。
  /// 供 [_buildWrapGroup] 在图片旁边内联渲染激活的 slot 使用。
  Widget _buildInsertionSlotTextField(
    BuildContext context,
    ArticleEditorSlotProjection slot,
    ArticleTypographySpec typography,
  ) {
    final controller = _ensureActiveSlotController();
    final focusNode = _ensureActiveSlotFocusNode();
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () {
        if (!focusNode.hasFocus) {
          focusNode.requestFocus();
        }
      },
      child: CupertinoTextField(
        key: ValueKey<String>('article_slot_input_${slot.id}'),
        controller: controller,
        focusNode: focusNode,
        keyboardType: TextInputType.multiline,
        textInputAction: TextInputAction.newline,
        textAlignVertical: TextAlignVertical.top,
        maxLines: null,
        minLines: 1,
        padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
        decoration: const BoxDecoration(),
        style: typography.bodyStyle,
        placeholderStyle: typography.placeholderStyle,
        onChanged: (value) {
          if (value.trim().isEmpty) {
            return;
          }
          final newNodeId = widget.onInsertTextNodeAfter(
            slot.anchorNodeId,
            initialText: value,
          );
          if (newNodeId.trim().isEmpty) {
            return;
          }
          final selectionOffset = value.length;
          _nodeSelections[newNodeId] = TextSelection.collapsed(
            offset: selectionOffset,
          );
          setState(() {
            _pendingFocusNodeId = newNodeId;
            _pendingFocusSelectionOffset = selectionOffset;
            _focusedNodeId = newNodeId;
            _activeSlotId = null;
            controller.clear();
          });
        },
      ),
    );
  }

  _TextSelectionInsertionTarget? _currentSelectionInsertionTarget() {
    final nodeId = _focusedNodeId;
    if (nodeId == null ||
        nodeId == 'title' ||
        nodeId == _kEmptyDocumentBodyFocusId ||
        _activeSlotId != null ||
        _selectedImageNodeId != null) {
      return null;
    }
    ArticleDocumentNode? node;
    for (final entry in widget.state.articleDocument.nodes) {
      if (entry.id == nodeId) {
        node = entry;
        break;
      }
    }
    if (node == null || node.isFigure) {
      return null;
    }
    final controller = _nodeControllers[nodeId];
    final selection =
        _nodeSelections[nodeId] ?? controller?.selection ?? const TextSelection.collapsed(offset: 0);
    final rawOffset = selection.isValid ? selection.extentOffset : node.text.length;
    final selectionOffset = rawOffset.clamp(0, node.text.length);
    return _TextSelectionInsertionTarget(
      nodeId: nodeId,
      selectionOffset: selectionOffset,
    );
  }

  void _scheduleWrapGroupNormalization(
    String figureNodeId, {
    int? splitOffset,
  }) {
    if (_pendingWrapNormalizations.contains(figureNodeId)) {
      return;
    }
    _pendingWrapNormalizations.add(figureNodeId);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _pendingWrapNormalizations.remove(figureNodeId);
      if (!mounted) {
        return;
      }
      widget.onEnsureWrapNodeGroup(
        figureNodeId,
        splitOffset: splitOffset,
      );
    });
  }

  String? _ensureWrapSegmentNodeId(
    ArticleEditorWrapGroupProjection group,
    ArticleWrapEditorSegment segment, {
    int? splitOffset,
    int selectionOffset = 0,
  }) {
    final existingNode = segment == ArticleWrapEditorSegment.narrow
        ? group.narrowParagraphNode
        : group.belowParagraphNode;
    if (existingNode != null) {
      return existingNode.id;
    }
    final ensured = widget.onEnsureWrapNodeGroup(
      group.figure.id,
      splitOffset: splitOffset,
    );
    final targetNode = segment == ArticleWrapEditorSegment.narrow
        ? ensured?.narrowParagraph
        : ensured?.belowParagraph;
    if (targetNode != null) {
      _pendingFocusNodeId = targetNode.id;
      _pendingFocusSelectionOffset = selectionOffset;
      return targetNode.id;
    }
    return null;
  }

  Widget _buildWrapGroup(
    BuildContext context,
    ArticleEditorWrapGroupProjection group,
    ArticleTypographySpec typography,
  ) {
    final node = group.figure;
    final isSelected = _selectedImageNodeId == node.id;
    final isLeft = node.imageLayout == 'wrapLeft';
    final narrowNode = group.narrowParagraphNode;
    final belowNode = group.belowParagraphNode;

    return LayoutBuilder(
      builder: (context, constraints) {
        // ── 共享几何：复用阅读态的 resolveArticleWrapLayout() ──
        final contentWidth = constraints.maxWidth;
        final captionStyle = TextStyle(
          color: CupertinoColors.secondaryLabel.resolveFrom(context),
          fontSize: AppTypography.sm,
          height: articleCaptionLineHeight(),
        );
        final wrapResult = resolveArticleWrapLayout(
          ArticleWrapLayoutInput(
            body: group.combinedText,
            leadingText: group.hasBelowParagraph ? group.narrowText : null,
            trailingText: group.hasBelowParagraph ? group.belowText : null,
            rowContentWidth: contentWidth,
            bodyStyle: typography.bodyStyle,
            captionText: node.caption,
            captionStyle: captionStyle,
            captionPlaceholderWhenEmpty: isSelected,
            imageLayout: node.imageLayout,
          ),
        );
        final wrapData = wrapResult.layout;
        final imageWidth = wrapData.imageWidth;
        final gap = wrapData.sideGap;
        final narrowWidth = wrapData.besideWidth;
        final floatHeight = wrapData.besideHeight;
        final resolvedNarrowText =
            group.hasBelowParagraph ? group.narrowText : wrapResult.leadingText;
        final resolvedBelowText =
            group.hasBelowParagraph ? group.belowText : wrapResult.trailingText;

        if (!group.hasNarrowParagraph || !group.hasBelowParagraph) {
          _scheduleWrapGroupNormalization(
            node.id,
            splitOffset: group.hasNarrowParagraph ? wrapData.splitOffset : null,
          );
        }

        // 图片列加 Padding(top: halfLeading)，让图片视觉顶部
        // 与文字视觉顶部对齐。
        final imageColumn = Padding(
          padding: EdgeInsets.only(top: wrapData.textHalfLeading),
          child: SizedBox(
            width: imageWidth,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                _buildImageWidget(context, node, isSelected,
                    width: imageWidth, height: wrapData.imageHeight),
                if (node.caption.trim().isNotEmpty || isSelected)
                  _buildCaptionField(context, node, typography),
                // 工具栏紧跟配文，在 imageColumn 内部，
                // 不在全宽文字之后。
                if (isSelected)
                  _buildImageToolbar(
                    context,
                    node,
                    imageWidth: imageWidth,
                    alignment: Alignment.centerLeft,
                  ),
              ],
            ),
          ),
        );
        ArticleWrapEditorSegment? autofocusSegment;
        int? autofocusSelectionOffset;
        if (_pendingFocusNodeId != null) {
          if (narrowNode != null && _pendingFocusNodeId == narrowNode.id) {
            autofocusSegment = ArticleWrapEditorSegment.narrow;
            autofocusSelectionOffset = _pendingFocusSelectionOffset;
            _pendingFocusNodeId = null;
            _pendingFocusSelectionOffset = null;
          } else if (belowNode != null && _pendingFocusNodeId == belowNode.id) {
            autofocusSegment = ArticleWrapEditorSegment.below;
            autofocusSelectionOffset = _pendingFocusSelectionOffset;
            _pendingFocusNodeId = null;
            _pendingFocusSelectionOffset = null;
          }
        }
        final wrapKey = _wrapEditorKeys.putIfAbsent(
          group.id,
          () => GlobalKey<ArticleWrapParagraphEditorState>(
            debugLabel: 'wrap_${group.id}',
          ),
        );
        _wrapEditorGroupNodeIds[group.id] = group.paragraphNodeIds;
        final wrapContent = ArticleWrapParagraphEditor(
          key: wrapKey,
          groupId: node.id,
          narrowText: resolvedNarrowText,
          belowText: resolvedBelowText,
          imageChild: imageColumn,
          imageWidth: imageWidth,
          narrowWidth: narrowWidth,
          gap: gap,
          isLeft: isLeft,
          floatHeight: floatHeight,
          style: typography.bodyStyle,
          placeholderStyle: typography.placeholderStyle,
          placeholder: '+ 想写点什么',
          autofocusSegment: autofocusSegment,
          autofocusSelectionOffset: autofocusSelectionOffset,
          belowSpacing: wrapData.sameParagraphSpacing,
          maxLinesBeside: wrapData.maxLinesBeside,
          onChanged: (narrowText, belowText) {
            widget.onUpdateWrapParagraphTexts(node.id, narrowText, belowText);
            _scheduleTextCommit();
          },
          onFocused: (segment) {
            final targetNodeId = _ensureWrapSegmentNodeId(
                  group,
                  segment,
                  splitOffset: wrapData.splitOffset,
                  selectionOffset: segment == ArticleWrapEditorSegment.narrow
                      ? resolvedNarrowText.length
                      : resolvedBelowText.length,
                ) ??
                (segment == ArticleWrapEditorSegment.narrow
                    ? narrowNode?.id
                    : belowNode?.id);
            _unfocusAllExcept(targetNodeId);
            if (targetNodeId != null) {
              widget.onActiveBlockChanged(targetNodeId);
            }
            if (mounted) {
              setState(() {
                _focusedNodeId = targetNodeId;
                _activeSlotId = null;
                _activeSlotController?.clear();
                _selectedImageNodeId = null;
              });
            }
          },
          onSelectionChanged: (segment, offset) {
            final targetNodeId = segment == ArticleWrapEditorSegment.narrow
                ? (narrowNode?.id ?? _pendingFocusNodeId)
                : (belowNode?.id ?? _pendingFocusNodeId);
            if (targetNodeId != null) {
              _nodeSelections[targetNodeId] =
                  TextSelection.collapsed(offset: offset);
            }
          },
        );

        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            wrapContent,
          ],
        );
      },
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
    // wrapLeft/wrapRight 的 figure 已由 projection 层的 WrapGroup 处理，
    // 这里只处理 fullWidth figure（或作为 fallback）。
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

  Widget _buildImageWidget(
    BuildContext context,
    ArticleDocumentNode node,
    bool isSelected, {
    double? width,
    double? height,
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
        _activeSlotId = null;
        _activeSlotController?.clear();
        // 选中图片时收起键盘，确保工具栏可见
        FocusManager.instance.primaryFocus?.unfocus();
      }),
      // 选中边框用 foregroundDecoration 叠加在内容之上，
      // 不增加容器尺寸，确保图片高度精确等于 wrapData.imageHeight。
      child: Container(
        foregroundDecoration: isSelected
            ? BoxDecoration(
                border: Border.all(
                  color: CupertinoColors.activeBlue.resolveFrom(context),
                  width: AppSpacing.two,
                ),
              )
            : null,
        // 环绕模式传入明确 height，用 SizedBox 固定尺寸；
        // 全宽模式用 AspectRatio 自然撑高。
        child: height != null
            ? SizedBox(
                width: width,
                height: height,
                child: ClipRect(child: FittedBox(fit: BoxFit.cover, child: image)),
              )
            : AspectRatio(aspectRatio: aspect, child: image),
      ),
    );
  }

  Widget _buildCaptionField(
    BuildContext context,
    ArticleDocumentNode node,
    ArticleTypographySpec typography,
  ) {
    final c = _captionControllerFor(node.id, node.caption);
    final fn = _captionFocusNodeFor(node.id);
    return Padding(
      padding: EdgeInsets.only(top: articleCaptionSpacing()),
      child: CupertinoTextField(
        key: ValueKey<String>('node_caption_${node.id}'),
        controller: c,
        focusNode: fn,
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

class _TextSelectionInsertionTarget {
  const _TextSelectionInsertionTarget({
    required this.nodeId,
    required this.selectionOffset,
  });

  final String nodeId;
  final int selectionOffset;
}
