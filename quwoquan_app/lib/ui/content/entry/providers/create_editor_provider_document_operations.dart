part of 'create_editor_provider.dart';

mixin _CreateEditorDocumentOperations on Notifier<CreateEditorState> {
  int _articleBlockSeed = 0;

  /// 与 [ArticleEditor] / [resolvePaginatedArticlePages] 对齐，避免 Provider 侧固定 390 宽分页与屏上不一致。
  double _paginationStageWidth = 390;
  double? _paginationContentHeight;
  ArticleCanvasMetrics _paginationMetrics = ArticleCanvasMetrics.snapshot();

  final List<Map<String, dynamic>> _undoStack = <Map<String, dynamic>>[];
  final List<Map<String, dynamic>> _redoStack = <Map<String, dynamic>>[];

  bool _sameMetrics(ArticleCanvasMetrics left, ArticleCanvasMetrics right) {
    return (left.aspectRatio - right.aspectRatio).abs() < 0.001 &&
        left.outerPadding == right.outerPadding &&
        left.contentPadding == right.contentPadding &&
        (left.headerReservedHeight - right.headerReservedHeight).abs() <
            0.001 &&
        (left.footerReservedHeight - right.footerReservedHeight).abs() <
            0.001 &&
        (left.wrapImageGap - right.wrapImageGap).abs() < 0.001 &&
        (left.wrapImageMaxWidth - right.wrapImageMaxWidth).abs() < 0.001 &&
        (left.fullWidthImageAspectRatio - right.fullWidthImageAspectRatio)
                .abs() <
            0.001 &&
        (left.journalImageAspectRatio - right.journalImageAspectRatio).abs() <
            0.001 &&
        (left.inlineImageSpacing - right.inlineImageSpacing).abs() < 0.001;
  }

  bool get canUndoArticle => _undoStack.isNotEmpty;
  bool get canRedoArticle => _redoStack.isNotEmpty;

  void undoArticle() {
    if (_undoStack.isEmpty) {
      return;
    }
    final current = CreateEditorUndoSnapshot.serialize(state);
    final previous = _undoStack.removeLast();
    _redoStack.add(current);
    state = CreateEditorUndoSnapshot.deserialize(state, previous);
  }

  void redoArticle() {
    if (_redoStack.isEmpty) {
      return;
    }
    final current = CreateEditorUndoSnapshot.serialize(state);
    final next = _redoStack.removeLast();
    _undoStack.add(current);
    state = CreateEditorUndoSnapshot.deserialize(state, next);
  }

  void _clearUndoRedo() {
    _undoStack.clear();
    _redoStack.clear();
  }

  void _recordUndoPointBeforeMutation() {
    if (state.editorKind != CreateEditorKind.text) {
      return;
    }
    _undoStack.add(CreateEditorUndoSnapshot.serialize(state));
    if (_undoStack.length > CreateEditorUndoSnapshot.maxStack) {
      _undoStack.removeAt(0);
    }
    _redoStack.clear();
  }

  void reset({
    CreateEditorKind editorKind = CreateEditorKind.text,
    CreateDraftFlowKind draftFlowKind = CreateDraftFlowKind.article,
  }) {
    _clearUndoRedo();
    _paginationStageWidth = 390;
    _paginationContentHeight = null;
    _paginationMetrics = ArticleCanvasMetrics.snapshot();
    state = CreateEditorState.initial(
      editorKind: editorKind,
      draftFlowKind: draftFlowKind,
    );
  }

  /// 仅重算分页，不写撤销栈；由编辑器 LayoutBuilder 在宽度/可视高度变化时调用。
  void reportArticlePaginationLayout({
    required double stageWidth,
    double? contentHeight,
    ArticleCanvasMetrics? metrics,
  }) {
    final sw = stageWidth.clamp(240.0, 1600.0);
    final nextMetrics = metrics ?? _paginationMetrics;
    final ch =
        (contentHeight ?? nextMetrics.contentSizeForStageWidth(sw).height)
            .clamp(160.0, 3200.0);
    final swSame = (sw - _paginationStageWidth).abs() < 3;
    final chSame =
        _paginationContentHeight != null &&
        (ch - _paginationContentHeight!).abs() < 12;
    final metricsSame = _sameMetrics(nextMetrics, _paginationMetrics);
    if (swSame && chSame && metricsSame) {
      return;
    }
    _paginationStageWidth = sw;
    _paginationContentHeight = ch;
    _paginationMetrics = nextMetrics;
    final pages = buildArticlePagesSnapshotFromDocument(
      state.articleDocument,
      fontPreset: state.articleFontPreset,
      stageWidth: _paginationStageWidth,
      contentHeightOverride: _paginationContentHeight,
      metrics: _paginationMetrics,
    );
    final activeId = state.activeArticlePageId;
    final nextActive = activeId != null && pages.any((p) => p.id == activeId)
        ? activeId
        : pages.first.id;
    state = state.copyWith(
      articlePages: pages,
      activeArticlePageId: nextActive,
    );
  }

  void setEditorKind(CreateEditorKind editorKind) {
    state = state.copyWith(editorKind: editorKind);
  }

  void setDraftFlowKind(CreateDraftFlowKind draftFlowKind) {
    state = state.copyWith(draftFlowKind: draftFlowKind);
  }

  void setStartAction(EditorStartAction? action) {
    switch (action) {
      case EditorStartAction.gallery:
        state = state.copyWith(
          editorKind: CreateEditorKind.media,
          draftFlowKind: CreateDraftFlowKind.image,
        );
        return;
      case EditorStartAction.video:
        state = state.copyWith(
          editorKind: CreateEditorKind.media,
          draftFlowKind: CreateDraftFlowKind.video,
        );
        return;
      case EditorStartAction.capture:
        state = state.copyWith(
          editorKind: CreateEditorKind.media,
          draftFlowKind: CreateDraftFlowKind.image,
        );
        return;
      case EditorStartAction.write:
      case null:
        state = state.copyWith(
          editorKind: CreateEditorKind.text,
          draftFlowKind: CreateDraftFlowKind.article,
        );
        return;
    }
  }

  void updateTitle(String value) {
    final document = state.articleDocument;
    final normalized = _normalizeArticleBody(value).trim();
    final nodes = List<ArticleDocumentNode>.from(document.nodes);
    final titleIndex = nodes.indexWhere((node) => node.isDocumentTitle);
    if (normalized.isEmpty) {
      if (titleIndex >= 0) {
        nodes.removeAt(titleIndex);
      }
    } else if (titleIndex >= 0) {
      nodes[titleIndex] = nodes[titleIndex].copyWith(text: normalized);
    } else {
      nodes.insert(
        0,
        ArticleDocumentNode(
          id: 'document_title',
          type: ArticleDocumentNodeType.documentTitle,
          text: normalized,
        ),
      );
    }
    _applyArticleDocument(
      document.copyWith(nodes: nodes),
      activePageId: state.activeArticlePageId,
      activeBlockId: state.activeArticleBlockId,
    );
    state = state.copyWith(
      titlePresentation: value.trim().isEmpty
          ? state.titlePresentation
          : TitlePresentation.expanded,
    );
  }

  void updateArticleTitleStyle(ArticleDocumentTitleStyle style) {
    _applyArticleDocument(
      state.articleDocument.copyWith(titleStyle: style),
      activePageId: state.activeArticlePageId,
      activeBlockId: state.activeArticleBlockId,
    );
  }

  String _normalizeArticleBody(String value) {
    return value.replaceAll('\r\n', '\n');
  }

  String _normalizeArticleCoverImagePath(
    String candidate,
    List<String> imagePaths,
  ) {
    final sanitized = candidate.trim();
    if (sanitized.isEmpty) {
      return '';
    }
    return imagePaths.contains(sanitized) ? sanitized : '';
  }

  ArticlePageBinding? _bindingForPageId(String? pageId) {
    if (pageId == null) {
      return null;
    }
    for (final page in state.articlePages) {
      if (page.id == pageId) {
        return page.binding;
      }
    }
    return null;
  }

  /// 分页切片 id 会随正文变化而变；保留「同一卡片序号 / 同一锚点图」以稳定 [activeArticlePageId]，避免编辑器 Key 抖动失焦。
  String? _remapActiveArticlePageId(
    List<ArticlePageData> pages,
    String? previousActiveId,
  ) {
    if (pages.isEmpty) {
      return null;
    }
    final prev = previousActiveId?.trim();
    if (prev != null &&
        prev.isNotEmpty &&
        pages.any((ArticlePageData p) => p.id == prev)) {
      return prev;
    }
    final oldPages = state.articlePages;
    final oldIndex = prev != null && prev.isNotEmpty
        ? oldPages.indexWhere((ArticlePageData p) => p.id == prev)
        : -1;
    if (oldIndex >= 0) {
      final idx = oldIndex.clamp(0, pages.length - 1);
      return pages[idx].id;
    }
    final prevBinding = _bindingForPageId(prev);
    final anchorAsset = prevBinding?.assetId?.trim();
    if (anchorAsset != null && anchorAsset.isNotEmpty) {
      for (final ArticlePageData p in pages) {
        for (final f in p.fragments) {
          if (f.asset?.id == anchorAsset) {
            return p.id;
          }
        }
      }
    }
    return pages.first.id;
  }

  void _applyArticleDocument(
    ArticleDocumentData document, {
    String? activePageId,
    String? activeBlockId,
    bool clearActivePageId = false,
    bool clearActiveBlockId = false,
    bool recordUndoPoint = true,
  }) {
    if (recordUndoPoint) {
      _recordUndoPointBeforeMutation();
    }
    final normalizedCoverImagePath = _normalizeArticleCoverImagePath(
      document.coverImageUrl.trim().isNotEmpty
          ? document.coverImageUrl
          : state.articleCoverImagePath,
      extractArticleImagePathsFromDocument(document),
    );
    final normalizedDocument = ArticleDocumentData(
      nodes: document.nodes,
      template: document.template,
      fontPreset: document.fontPreset,
      coverImageUrl: normalizedCoverImagePath,
      titleStyle: document.titleStyle,
    );
    final imagePaths = extractArticleImagePathsFromDocument(normalizedDocument);
    final pages = buildArticlePagesSnapshotFromDocument(
      normalizedDocument,
      fontPreset: state.articleFontPreset,
      stageWidth: _paginationStageWidth,
      contentHeightOverride: _paginationContentHeight,
      metrics: _paginationMetrics,
    );
    final editableNodes = normalizedDocument.nodes
        .where((node) => !node.isDocumentTitle && !node.isFigure)
        .toList(growable: false);
    final fallbackNodeId = editableNodes.isNotEmpty
        ? editableNodes.first.id
        : (normalizedDocument.nodes.isEmpty
              ? null
              : normalizedDocument.nodes.first.id);
    final activeNodeCandidate = activeBlockId ?? state.activeArticleBlockId;
    final resolvedActiveNodeId =
        activeNodeCandidate != null &&
            normalizedDocument.nodes.any(
              (node) => node.id == activeNodeCandidate,
            )
        ? activeNodeCandidate
        : fallbackNodeId;
    state = state.copyWith(
      title: normalizedDocument.title,
      body: buildArticlePlainTextFromDocument(normalizedDocument),
      imagePaths: imagePaths,
      articleDocument: normalizedDocument,
      articlePages: pages,
      articleCoverImagePath: normalizedCoverImagePath,
      activeArticlePageId: clearActivePageId
          ? null
          : _remapActiveArticlePageId(
              pages,
              activePageId ?? state.activeArticlePageId,
            ),
      activeArticleBlockId: clearActiveBlockId ? null : resolvedActiveNodeId,
      clearActiveArticlePageId: clearActivePageId,
      clearActiveArticleBlockId: clearActiveBlockId,
    );
  }

  void setActiveArticleBlock(String? blockId) {
    state = state.copyWith(
      activeArticleBlockId: blockId,
      clearActiveArticleBlockId: blockId == null,
    );
  }

  void setActiveArticlePage(String? pageId) {
    state = state.copyWith(
      activeArticlePageId: pageId,
      clearActiveArticlePageId: pageId == null,
    );
  }
}
