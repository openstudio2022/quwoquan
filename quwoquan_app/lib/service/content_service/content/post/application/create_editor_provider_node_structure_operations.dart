part of 'create_editor_provider.dart';

mixin _CreateEditorNodeStructureOperations
    on Notifier<CreateEditorState>, _CreateEditorDocumentOperations {
  /// 在指定 node 之后插入一个空文本 node。
  /// 在指定 node 之后插入一个空段落。返回新 node 的 id。
  String insertTextNodeAfter(
    String afterNodeId, {
    String initialText = '',
    ArticleDocumentNodeType type = ArticleDocumentNodeType.paragraph,
  }) {
    final resolvedType =
        type == ArticleDocumentNodeType.figure ||
            type == ArticleDocumentNodeType.documentTitle
        ? ArticleDocumentNodeType.paragraph
        : type;
    final doc = state.articleDocument;
    final insertIndex = _resolveNodeInsertionIndex(
      doc.nodes,
      afterNodeId: afterNodeId,
    );
    final newNodeId = _nextArticleTextNodeId(resolvedType);
    final newNode = ArticleDocumentNode(
      id: newNodeId,
      type: resolvedType,
      text: initialText,
    );
    final nextNodes = List<ArticleDocumentNode>.from(doc.nodes)
      ..insert(insertIndex, newNode);
    _applyArticleDocument(
      doc.copyWith(nodes: nextNodes),
      activeBlockId: newNodeId,
    );
    return newNodeId;
  }

  /// 把图片插入点归一化到 node 边界；选区位于文本中部时拆成左右两个 node。
  String prepareTextNodeForImageInsertion(String nodeId, int offset) {
    final id = nodeId.trim();
    final document = state.articleDocument;
    final index = document.nodes.indexWhere((node) => node.id == id);
    if (index < 0) return kArticleEditorStartAnchorId;
    final node = document.nodes[index];
    if (node.isFigure || node.isDocumentTitle) return node.id;

    final split = offset.clamp(0, node.text.length);
    if (split == 0) {
      return index == 0
          ? kArticleEditorStartAnchorId
          : document.nodes[index - 1].id;
    }
    if (split == node.text.length) return node.id;

    _recordUndoPointBeforeMutation();
    final left = _cloneTextNode(
      node,
      id: node.id,
      text: node.text.substring(0, split),
      spans: _sliceInlineSpans(node.spans, 0, split),
    );
    final right = _cloneTextNode(
      node,
      id: _nextArticleTextNodeId(node.type),
      text: node.text.substring(split),
      spans: _sliceInlineSpans(node.spans, split, node.text.length),
    );
    final nextNodes = List<ArticleDocumentNode>.from(document.nodes)
      ..[index] = left
      ..insert(index + 1, right);
    _applyArticleDocument(
      document.copyWith(nodes: nextNodes),
      activeBlockId: left.id,
      recordUndoPoint: false,
    );
    return left.id;
  }

  /// 在指定 node 之后插入一张图片（node 级操作）。
  /// 返回新 figure node 的 id，方便连续插入多张。
  String insertImageAfterNode(String? afterNodeId, String imagePath) {
    final sanitized = imagePath.trim();
    if (sanitized.isEmpty) return afterNodeId ?? '';
    _articleBlockSeed += 1;
    final newNode = ArticleDocumentNode(
      id: 'figure_$_articleBlockSeed',
      type: ArticleDocumentNodeType.figure,
      imageUrl: sanitized,
      imageLayout: 'fullWidth',
    );
    final doc = state.articleDocument;
    final nextNodes = List<ArticleDocumentNode>.from(doc.nodes);
    final insertIndex = _resolveNodeInsertionIndex(
      nextNodes,
      afterNodeId: afterNodeId,
    );
    nextNodes.insert(insertIndex, newNode);
    _applyArticleDocument(
      doc.copyWith(nodes: nextNodes),
      activeBlockId: newNode.id,
    );
    return newNode.id;
  }

  int _resolveNodeInsertionIndex(
    List<ArticleDocumentNode> nodes, {
    String? afterNodeId,
  }) {
    final anchor = afterNodeId?.trim() ?? '';
    if (anchor.isEmpty) {
      return nodes.length;
    }
    if (anchor == kArticleEditorStartAnchorId) {
      return 0;
    }
    final index = nodes.indexWhere((node) => node.id == anchor);
    if (index < 0) {
      return nodes.length;
    }
    return index + 1;
  }

  _WrapGroupMutationResult? _ensureArticleWrapNodeGroupInNodes(
    List<ArticleDocumentNode> nodes,
    String figureNodeId, {
    int? splitOffset,
  }) {
    final figureId = figureNodeId.trim();
    if (figureId.isEmpty) {
      return null;
    }
    final figureIndex = nodes.indexWhere((node) => node.id == figureId);
    if (figureIndex < 0) {
      return null;
    }
    final figure = nodes[figureIndex];
    if (!figure.isFigure || !figure.usesWrappedLayout) {
      return null;
    }

    final nextNodes = List<ArticleDocumentNode>.from(nodes);
    var changed = false;

    ArticleDocumentNode? narrowParagraph;
    ArticleDocumentNode? belowParagraph;
    if (figureIndex + 1 < nextNodes.length &&
        nextNodes[figureIndex + 1].type == ArticleDocumentNodeType.paragraph) {
      narrowParagraph = nextNodes[figureIndex + 1];
      if (figureIndex + 2 < nextNodes.length &&
          nextNodes[figureIndex + 2].type ==
              ArticleDocumentNodeType.paragraph) {
        belowParagraph = nextNodes[figureIndex + 2];
      }
    }

    if (narrowParagraph == null) {
      changed = true;
      final newNarrow = ArticleDocumentNode(
        id: _nextArticleTextNodeId(ArticleDocumentNodeType.paragraph),
        type: ArticleDocumentNodeType.paragraph,
      );
      nextNodes.insert(figureIndex + 1, newNarrow);
      narrowParagraph = newNarrow;
    }

    if (belowParagraph == null) {
      changed = true;
      final rawSplitOffset = splitOffset;
      final canSplitCurrentParagraph =
          rawSplitOffset != null && narrowParagraph.text.isNotEmpty;
      final clampedSplit = canSplitCurrentParagraph
          ? rawSplitOffset.clamp(0, narrowParagraph.text.length)
          : narrowParagraph.text.length;
      final leftText = canSplitCurrentParagraph
          ? narrowParagraph.text.substring(0, clampedSplit)
          : narrowParagraph.text;
      final rightText = canSplitCurrentParagraph
          ? narrowParagraph.text.substring(clampedSplit)
          : '';
      final leftSpans = canSplitCurrentParagraph
          ? _sliceInlineSpans(narrowParagraph.spans, 0, clampedSplit)
          : narrowParagraph.spans;
      final rightSpans = canSplitCurrentParagraph
          ? _sliceInlineSpans(
              narrowParagraph.spans,
              clampedSplit,
              narrowParagraph.text.length,
            )
          : const <ArticleInlineSpan>[];
      if (canSplitCurrentParagraph) {
        nextNodes[figureIndex + 1] = narrowParagraph.copyWith(
          text: leftText,
          spans: leftSpans,
        );
        narrowParagraph = nextNodes[figureIndex + 1];
      }
      final newBelow = ArticleDocumentNode(
        id: _nextArticleTextNodeId(ArticleDocumentNodeType.paragraph),
        type: ArticleDocumentNodeType.paragraph,
        text: rightText,
        spans: rightSpans,
      );
      nextNodes.insert(figureIndex + 2, newBelow);
      belowParagraph = newBelow;
    }

    return _WrapGroupMutationResult(nodes: nextNodes, changed: changed);
  }

  String _nextArticleTextNodeId(ArticleDocumentNodeType type) {
    _articleBlockSeed += 1;
    final prefix = switch (type) {
      ArticleDocumentNodeType.orderedItem => 'ordered',
      ArticleDocumentNodeType.bulletItem => 'bullet',
      ArticleDocumentNodeType.headingMajor => 'heading_major',
      ArticleDocumentNodeType.headingMinor => 'heading_minor',
      _ => 'paragraph',
    };
    return '${prefix}_$_articleBlockSeed';
  }

  ArticleDocumentNode _cloneTextNode(
    ArticleDocumentNode source, {
    required String id,
    required String text,
    required List<ArticleInlineSpan> spans,
  }) {
    return ArticleDocumentNode(
      id: id,
      type: source.type,
      text: text,
      textAlign: source.textAlign,
      listDepth: source.listDepth,
      spans: spans,
    );
  }

  List<ArticleInlineSpan> _sliceInlineSpans(
    List<ArticleInlineSpan> spans,
    int start,
    int end,
  ) {
    final result = <ArticleInlineSpan>[];
    for (final span in spans) {
      final nextStart = math.max(span.start, start);
      final nextEnd = math.min(span.end, end);
      if (nextEnd <= nextStart) {
        continue;
      }
      result.add(
        ArticleInlineSpan(
          start: nextStart - start,
          end: nextEnd - start,
          bold: span.bold,
          italic: span.italic,
          underline: span.underline,
          strikethrough: span.strikethrough,
          kind: span.kind,
          targetType: span.targetType,
          targetId: span.targetId,
          displayText: span.displayText,
        ),
      );
    }
    return result;
  }
}
