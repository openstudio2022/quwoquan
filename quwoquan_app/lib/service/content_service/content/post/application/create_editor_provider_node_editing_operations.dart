part of 'create_editor_provider.dart';

mixin _CreateEditorNodeEditingOperations
    on
        Notifier<CreateEditorState>,
        _CreateEditorDocumentOperations,
        _CreateEditorNodeStructureOperations {
  // ── Node 级操作（纵向滚动编辑器使用） ──

  /// 更新指定 node 的文本内容。
  void updateArticleNodeText(String nodeId, String value) {
    final id = nodeId.trim();
    if (id.isEmpty) return;
    final doc = state.articleDocument;

    final nextNodes = doc.nodes
        .map((node) {
          if (node.id == id) return node.copyWith(text: value);
          return node;
        })
        .toList(growable: false);
    _applyArticleDocument(
      doc.copyWith(nodes: nextNodes),
      activeBlockId: state.activeArticleBlockId,
      recordUndoPoint: false,
    );
  }

  ArticleWrapNodeGroup? ensureArticleWrapNodeGroup(
    String figureNodeId, {
    int? splitOffset,
    bool recordUndoPoint = false,
  }) {
    final id = figureNodeId.trim();
    if (id.isEmpty) return null;
    final doc = state.articleDocument;
    final mutation = _ensureArticleWrapNodeGroupInNodes(
      doc.nodes,
      id,
      splitOffset: splitOffset,
    );
    if (mutation == null) {
      return null;
    }
    if (mutation.changed) {
      _applyArticleDocument(
        doc.copyWith(nodes: mutation.nodes),
        recordUndoPoint: recordUndoPoint,
      );
    }
    return resolveArticleWrapNodeGroupByFigureId(mutation.nodes, id);
  }

  void updateArticleWrapParagraphTexts(
    String figureNodeId, {
    required String narrowText,
    required String belowText,
  }) {
    final id = figureNodeId.trim();
    if (id.isEmpty) return;
    final doc = state.articleDocument;
    final mutation = _ensureArticleWrapNodeGroupInNodes(doc.nodes, id);
    if (mutation == null) {
      return;
    }
    final group = resolveArticleWrapNodeGroupByFigureId(mutation.nodes, id);
    if (group?.narrowParagraph == null || group?.belowParagraph == null) {
      return;
    }
    final normalizedNarrow = _normalizeArticleBody(narrowText);
    final normalizedBelow = _normalizeArticleBody(belowText);
    final nextNodes = mutation.nodes
        .map((node) {
          if (node.id == group!.narrowParagraph!.id) {
            return node.copyWith(text: normalizedNarrow);
          }
          if (node.id == group.belowParagraph!.id) {
            return node.copyWith(text: normalizedBelow);
          }
          return node;
        })
        .toList(growable: false);
    _applyArticleDocument(
      doc.copyWith(nodes: nextNodes),
      activeBlockId: state.activeArticleBlockId,
      recordUndoPoint: false,
    );
  }

  /// 更新指定 figure node 的图片布局。
  /// 更新段落对齐（'' / left / center / right；空串与 left 等价为默认）。
  /// 只作用于正文段落节点——qwq 方言的 :::align 指令只承载段落对齐。
  void updateArticleNodeAlignment(String nodeId, String alignment) {
    final id = nodeId.trim();
    if (id.isEmpty) return;
    final normalized = switch (alignment.trim()) {
      'center' => 'center',
      'right' => 'right',
      _ => '',
    };
    final doc = state.articleDocument;
    final nextNodes = doc.nodes
        .map((node) {
          if (node.id == id &&
              node.type == ArticleDocumentNodeType.paragraph) {
            return node.copyWith(textAlign: normalized);
          }
          return node;
        })
        .toList(growable: false);
    _applyArticleDocument(doc.copyWith(nodes: nextNodes));
  }

  void updateArticleNodeImageLayout(String nodeId, String layout) {
    final id = nodeId.trim();
    if (id.isEmpty) return;
    final doc = state.articleDocument;
    var nextNodes = doc.nodes
        .map((node) {
          if (node.id == id) return node.copyWith(imageLayout: layout);
          return node;
        })
        .toList(growable: false);
    if (layout == 'wrapLeft' || layout == 'wrapRight') {
      final mutation = _ensureArticleWrapNodeGroupInNodes(nextNodes, id);
      if (mutation != null) {
        nextNodes = mutation.nodes;
      }
    }
    _applyArticleDocument(doc.copyWith(nodes: nextNodes));
  }

  /// 更新指定 figure node 的图片说明。
  void updateArticleNodeCaption(String nodeId, String caption) {
    final id = nodeId.trim();
    if (id.isEmpty) return;
    final doc = state.articleDocument;
    final nextNodes = doc.nodes
        .map((node) {
          if (node.id == id) return node.copyWith(caption: caption);
          return node;
        })
        .toList(growable: false);
    _applyArticleDocument(
      doc.copyWith(nodes: nextNodes),
      recordUndoPoint: false,
    );
  }

  /// 提交一次文本编辑 undo 点。
  ///
  /// 由 Widget 层在输入间歇（防抖）或焦点离开时调用，
  /// 解决 [updateArticleNodeText] / [updateArticleNodeCaption] 逐字不记录 undo 的问题。
  void commitArticleTextEdit() {
    _recordUndoPointBeforeMutation();
  }

  /// 移除指定 figure node。
  void removeArticleNode(String nodeId) {
    final id = nodeId.trim();
    if (id.isEmpty) return;
    final doc = state.articleDocument;
    final nextNodes = doc.nodes
        .where((node) => node.id != id)
        .toList(growable: false);
    _applyArticleDocument(doc.copyWith(nodes: nextNodes));
  }

  /// 切换指定文本 node 的类型（段落 / H2 / H3 / 有序列表 / 无序列表）。
  void updateArticleNodeType(String nodeId, ArticleDocumentNodeType type) {
    final id = nodeId.trim();
    if (id.isEmpty) return;
    final doc = state.articleDocument;
    final node = doc.nodes.firstWhere(
      (n) => n.id == id,
      orElse: () => const ArticleDocumentNode(
        id: '',
        type: ArticleDocumentNodeType.paragraph,
      ),
    );
    if (node.id.isEmpty || node.isFigure || node.isDocumentTitle) return;
    if (node.type == type) return;
    final newId = _nextArticleTextNodeId(type);
    final nextNodes = doc.nodes
        .map((n) {
          if (n.id != id) return n;
          return ArticleDocumentNode(
            id: newId,
            type: type,
            text: n.text,
            textAlign: n.textAlign,
            listDepth: n.listDepth,
            spans: n.spans,
          );
        })
        .toList(growable: false);
    _applyArticleDocument(doc.copyWith(nodes: nextNodes), activeBlockId: newId);
  }

  /// 编辑指定 figure node 的图片（返回 imageUrl 供导航用）。
  String? articleNodeImageUrl(String nodeId) {
    final id = nodeId.trim();
    if (id.isEmpty) return null;
    for (final node in state.articleDocument.nodes) {
      if (node.id == id && node.isFigure) return node.imageUrl;
    }
    return null;
  }

  /// 替换指定 figure node 的图片路径。
  void replaceArticleNodeImage(String nodeId, String imagePath) {
    final id = nodeId.trim();
    final sanitized = imagePath.trim();
    if (id.isEmpty || sanitized.isEmpty) return;
    final doc = state.articleDocument;
    final nextNodes = doc.nodes
        .map((node) {
          if (node.id == id) return node.copyWith(imageUrl: sanitized);
          return node;
        })
        .toList(growable: false);
    _applyArticleDocument(doc.copyWith(nodes: nextNodes));
  }

  /// 在指定文本 node 的 [start, end) 范围内 toggle 行内样式。
  ///
  /// 传入的 bool 参数为 `true` 表示开启，`false` 表示关闭，`null` 表示不变。
  /// 如果范围内该样式已全部开启，则关闭；否则开启（toggle 语义）。
  void toggleArticleInlineStyle(
    String nodeId,
    int start,
    int end, {
    bool? bold,
    bool? italic,
    bool? underline,
    bool? strikethrough,
  }) {
    final id = nodeId.trim();
    if (id.isEmpty || start >= end) return;
    final doc = state.articleDocument;
    final node = doc.nodes.firstWhere(
      (n) => n.id == id,
      orElse: () => const ArticleDocumentNode(
        id: '',
        type: ArticleDocumentNodeType.paragraph,
      ),
    );
    if (node.id.isEmpty || node.isFigure || node.isDocumentTitle) return;
    final clampedStart = start.clamp(0, node.text.length);
    final clampedEnd = end.clamp(clampedStart, node.text.length);
    if (clampedStart >= clampedEnd) return;

    final nextSpans = _toggleSpansInRange(
      node.spans,
      clampedStart,
      clampedEnd,
      bold: bold,
      italic: italic,
      underline: underline,
      strikethrough: strikethrough,
    );
    final nextNodes = doc.nodes
        .map((n) {
          if (n.id != id) return n;
          return n.copyWith(spans: nextSpans);
        })
        .toList(growable: false);
    _applyArticleDocument(doc.copyWith(nodes: nextNodes));
  }

  /// 在指定文本 node 的 [start, end) 范围内插入对象提及元数据。
  void attachArticleEntityMention(
    String nodeId,
    int start,
    int end, {
    required String targetType,
    required String targetId,
    required String displayText,
  }) {
    final id = nodeId.trim();
    final normalizedTargetType = targetType.trim();
    final normalizedTargetId = targetId.trim();
    final normalizedDisplay = displayText.trim();
    if (id.isEmpty ||
        normalizedTargetType.isEmpty ||
        normalizedTargetId.isEmpty ||
        normalizedDisplay.isEmpty) {
      return;
    }
    final doc = state.articleDocument;
    final node = doc.nodes.firstWhere(
      (n) => n.id == id,
      orElse: () => const ArticleDocumentNode(
        id: '',
        type: ArticleDocumentNodeType.paragraph,
      ),
    );
    if (node.id.isEmpty || node.isFigure || node.isDocumentTitle) return;
    final clampedStart = start.clamp(0, node.text.length);
    final clampedEnd = end.clamp(clampedStart, node.text.length);
    if (clampedStart >= clampedEnd) return;
    final nextSpan = ArticleInlineSpan(
      start: clampedStart,
      end: clampedEnd,
      kind: 'entity',
      targetType: normalizedTargetType,
      targetId: normalizedTargetId,
      displayText: normalizedDisplay,
    );
    final nextNodes = doc.nodes
        .map((n) {
          if (n.id != id) return n;
          final spans = <ArticleInlineSpan>[
            ...n.spans.where(
              (span) =>
                  !(span.isEntity &&
                      span.start == clampedStart &&
                      span.end == clampedEnd),
            ),
            nextSpan,
          ]..sort((left, right) => left.start.compareTo(right.start));
          return n.copyWith(spans: spans);
        })
        .toList(growable: false);
    _applyArticleDocument(doc.copyWith(nodes: nextNodes));
  }

  /// 合并/拆分 spans 以在 [start, end) 范围内 toggle 指定样式。
  static List<ArticleInlineSpan> _toggleSpansInRange(
    List<ArticleInlineSpan> existing,
    int start,
    int end, {
    bool? bold,
    bool? italic,
    bool? underline,
    bool? strikethrough,
  }) {
    // 构建逐字符样式数组
    final maxOffset = existing.fold<int>(
      end,
      (prev, span) => span.end > prev ? span.end : prev,
    );
    final bolds = List<bool>.filled(maxOffset, false);
    final italics = List<bool>.filled(maxOffset, false);
    final underlines = List<bool>.filled(maxOffset, false);
    final strikethroughs = List<bool>.filled(maxOffset, false);
    for (final span in existing) {
      for (var i = span.start; i < span.end && i < maxOffset; i++) {
        if (span.bold) bolds[i] = true;
        if (span.italic) italics[i] = true;
        if (span.underline) underlines[i] = true;
        if (span.strikethrough) strikethroughs[i] = true;
      }
    }
    // 在 [start, end) 范围内 toggle
    if (bold != null) {
      for (var i = start; i < end; i++) {
        bolds[i] = bold;
      }
    }
    if (italic != null) {
      for (var i = start; i < end; i++) {
        italics[i] = italic;
      }
    }
    if (underline != null) {
      for (var i = start; i < end; i++) {
        underlines[i] = underline;
      }
    }
    if (strikethrough != null) {
      for (var i = start; i < end; i++) {
        strikethroughs[i] = strikethrough;
      }
    }
    // 从逐字符数组重建 spans（合并相邻同样式区间）
    final result = <ArticleInlineSpan>[];
    result.addAll(
      existing
          .where((span) => span.isInlineMention)
          .map((span) {
            return ArticleInlineSpan(
              start: span.start.clamp(0, maxOffset),
              end: span.end.clamp(span.start.clamp(0, maxOffset), maxOffset),
              bold: span.bold,
              italic: span.italic,
              underline: span.underline,
              strikethrough: span.strikethrough,
              kind: span.kind,
              targetType: span.targetType,
              targetId: span.targetId,
              displayText: span.displayText,
            );
          })
          .where((span) => span.start < span.end),
    );
    var i = 0;
    while (i < maxOffset) {
      final b = bolds[i];
      final it = italics[i];
      final u = underlines[i];
      final s = strikethroughs[i];
      if (!b && !it && !u && !s) {
        i++;
        continue;
      }
      final spanStart = i;
      while (i < maxOffset &&
          bolds[i] == b &&
          italics[i] == it &&
          underlines[i] == u &&
          strikethroughs[i] == s) {
        i++;
      }
      result.add(
        ArticleInlineSpan(
          start: spanStart,
          end: i,
          bold: b,
          italic: it,
          underline: u,
          strikethrough: s,
        ),
      );
    }
    return result;
  }
}
