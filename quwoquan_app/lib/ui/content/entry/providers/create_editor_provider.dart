import 'dart:math' as math;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_undo_snapshot.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';

class CreateEditorNotifier extends Notifier<CreateEditorState> {
  int _articleBlockSeed = 0;
  int _articleAssetSeed = 0;

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

  @override
  CreateEditorState build() {
    return CreateEditorState.initial();
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

  void reset({CreateEditorKind editorKind = CreateEditorKind.text}) {
    _clearUndoRedo();
    _paginationStageWidth = 390;
    _paginationContentHeight = null;
    _paginationMetrics = ArticleCanvasMetrics.snapshot();
    state = CreateEditorState.initial(editorKind: editorKind);
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

  void setStartAction(EditorStartAction? action) {
    switch (action) {
      case EditorStartAction.gallery:
      case EditorStartAction.capture:
        state = state.copyWith(editorKind: CreateEditorKind.media);
        return;
      case EditorStartAction.write:
      case null:
        state = state.copyWith(editorKind: CreateEditorKind.text);
        return;
    }
  }

  void updateTitle(String value) {
    _applyArticleDocument(
      state.articleDocument.copyWith(title: value),
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

  void updateBody(String value) {
    state = state.copyWith(body: value);
  }

  String _nextArticleBlockId(CreateTextBlockType type) {
    _articleBlockSeed += 1;
    return '${type.name}_$_articleBlockSeed';
  }

  String _nextArticleAssetId() {
    _articleAssetSeed += 1;
    return 'asset_$_articleAssetSeed';
  }

  String _normalizeArticleBody(String value) {
    return value.replaceAll('\r\n', '\n');
  }

  List<ArticleDocumentAsset> _normalizeAssets(
    List<ArticleDocumentAsset> assets,
    int bodyLength,
  ) {
    final normalized =
        assets
            .where((asset) => asset.hasImage)
            .map((asset) {
              final offset = asset.offset < 0
                  ? 0
                  : (asset.offset > bodyLength ? bodyLength : asset.offset);
              return asset.copyWith(offset: offset);
            })
            .toList(growable: false)
          ..sort((left, right) {
            final offsetCompare = left.offset.compareTo(right.offset);
            if (offsetCompare != 0) {
              return offsetCompare;
            }
            return left.id.compareTo(right.id);
          });
    return normalized;
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

  /// 从 [anchorOffset] 到「下一处严格更大的文内图/结构块 offset」之间的 body 区间终点（不含锚点上的并列图）。
  ///
  /// 无 [ArticlePageBinding.bodyRange] 时（如切片后环绕区折叠），编辑必须用整段替换，
  /// 禁止在固定点反复 `replaceRange(o,o,全文)`，否则会在每个字符前重复插入全文。
  int _bodySegmentEndExclusive(ArticleDocumentData document, int anchorOffset) {
    final safe = anchorOffset.clamp(0, document.body.length);
    var end = document.body.length;
    for (final asset in document.assets) {
      if (asset.offset > safe) {
        end = math.min(end, asset.offset);
      }
    }
    for (final block in document.blocks) {
      if (block.offset > safe) {
        end = math.min(end, block.offset);
      }
    }
    return end.clamp(safe, document.body.length);
  }

  ArticleDocumentData _replaceBodyRange(
    ArticleDocumentData document, {
    required int start,
    required int end,
    required String replacement,
  }) {
    final int safeStart = start < 0
        ? 0
        : (start > document.body.length ? document.body.length : start);
    final int safeEnd = end < safeStart
        ? safeStart
        : (end > document.body.length ? document.body.length : end);
    final normalizedReplacement = _normalizeArticleBody(replacement);
    final nextBody = document.body.replaceRange(
      safeStart,
      safeEnd,
      normalizedReplacement,
    );
    final int delta = normalizedReplacement.length - (safeEnd - safeStart);
    bool shouldShiftAnchor(int offset) {
      return offset > safeEnd || (safeEnd > safeStart && offset == safeEnd);
    }

    final nextAssets = document.assets
        .map((asset) {
          return shouldShiftAnchor(asset.offset)
              ? asset.copyWith(offset: asset.offset + delta)
              : asset;
        })
        .toList(growable: false);
    final nextBlocks = document.blocks
        .map((block) {
          return shouldShiftAnchor(block.offset)
              ? block.copyWith(offset: block.offset + delta)
              : block;
        })
        .toList(growable: false);
    return document.copyWith(
      body: nextBody,
      assets: _normalizeAssets(nextAssets, nextBody.length),
      blocks: nextBlocks,
    );
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
    bool nodesAreSourceOfTruth = false,
  }) {
    if (recordUndoPoint) {
      _recordUndoPointBeforeMutation();
    }
    final normalizedBody = _normalizeArticleBody(document.body);
    final normalizedCoverImagePath = _normalizeArticleCoverImagePath(
      document.coverImageUrl.trim().isNotEmpty
          ? document.coverImageUrl
          : state.articleCoverImagePath,
      extractArticleImagePathsFromDocument(document),
    );
    // 当 nodes 是唯一真相源时，不通过 copyWith(body:) 触发
    // _buildDocumentNodesFromLegacy，避免覆盖 node 级变更。
    final ArticleDocumentData normalizedDocument;
    if (nodesAreSourceOfTruth) {
      // 自动修复结构：确保每个 figure 前后都有 paragraph
      final fixedNodes = _ensureEditableNodes(document.nodes);
      normalizedDocument = ArticleDocumentData(
        nodes: fixedNodes,
        template: state.articleTemplate.name,
        fontPreset: state.articleFontPreset.name,
        coverImageUrl: normalizedCoverImagePath,
        titleStyle: document.titleStyle,
      );
    } else {
      final rawDocument = document.copyWith(
        body: normalizedBody,
        assets: _normalizeAssets(document.assets, normalizedBody.length),
        blocks: document.blocks,
        template: state.articleTemplate.name,
        fontPreset: state.articleFontPreset.name,
        coverImageUrl: normalizedCoverImagePath,
      );
      // 同样修复结构：确保每个 figure 前后都有 paragraph
      final fixedNodes = _ensureEditableNodes(rawDocument.nodes);
      normalizedDocument = ArticleDocumentData(
        nodes: fixedNodes,
        template: rawDocument.template,
        fontPreset: rawDocument.fontPreset,
        coverImageUrl: rawDocument.coverImageUrl,
        titleStyle: rawDocument.titleStyle,
      );
    }
    final imagePaths = extractArticleImagePathsFromDocument(normalizedDocument);
    final blocks = buildArticleBlocksFromDocument(normalizedDocument);
    final pages = buildArticlePagesSnapshotFromDocument(
      normalizedDocument,
      fontPreset: state.articleFontPreset,
      stageWidth: _paginationStageWidth,
      contentHeightOverride: _paginationContentHeight,
      metrics: _paginationMetrics,
    );
    final fallbackTextBlock = blocks.firstWhere(
      (block) => block.isTextLike,
      orElse: () => blocks.first,
    );
    state = state.copyWith(
      title: normalizedDocument.title,
      body: buildArticlePlainTextFromDocument(normalizedDocument),
      imagePaths: imagePaths,
      articleDocument: normalizedDocument,
      articlePages: pages,
      articleBlocks: blocks,
      articleCoverImagePath: normalizedCoverImagePath,
      activeArticlePageId: clearActivePageId
          ? null
          : _remapActiveArticlePageId(
              pages,
              activePageId ?? state.activeArticlePageId,
            ),
      activeArticleBlockId: clearActiveBlockId
          ? null
          : (activeBlockId ??
                state.activeArticleBlockId ??
                fallbackTextBlock.id),
      clearActiveArticlePageId: clearActivePageId,
      clearActiveArticleBlockId: clearActiveBlockId,
    );
  }

  void _applyArticleBlocks(
    List<CreateTextBlock> blocks, {
    String? activePageId,
    String? activeBlockId,
    bool clearActiveBlockId = false,
  }) {
    _recordUndoPointBeforeMutation();
    final normalized = blocks.isEmpty
        ? createDefaultArticleBlocks()
        : blocks.toList(growable: false);
    final document = buildArticleDocumentFromBlocks(
      normalized,
      title: state.title,
    );
    final normalizedBody = _normalizeArticleBody(document.body);
    final normalizedCoverImagePath = _normalizeArticleCoverImagePath(
      state.articleCoverImagePath,
      extractArticleImagePathsFromDocument(document),
    );
    final normalizedDocument = document.copyWith(
      body: normalizedBody,
      assets: _normalizeAssets(document.assets, normalizedBody.length),
      blocks: document.blocks,
      template: state.articleTemplate.name,
      fontPreset: state.articleFontPreset.name,
      coverImageUrl: normalizedCoverImagePath,
    );
    final imagePaths = extractArticleImagePathsFromDocument(normalizedDocument);
    final pages = buildArticlePagesSnapshotFromDocument(
      normalizedDocument,
      fontPreset: state.articleFontPreset,
      stageWidth: _paginationStageWidth,
      contentHeightOverride: _paginationContentHeight,
      metrics: _paginationMetrics,
    );
    final fallbackTextBlock = normalized.firstWhere(
      (block) => block.isTextLike,
      orElse: () => normalized.first,
    );
    state = state.copyWith(
      title: normalizedDocument.title,
      body: buildArticlePlainTextFromDocument(normalizedDocument),
      imagePaths: imagePaths,
      articleDocument: normalizedDocument,
      articlePages: pages,
      articleBlocks: normalized,
      articleCoverImagePath: normalizedCoverImagePath,
      activeArticlePageId: _remapActiveArticlePageId(
        pages,
        activePageId ?? state.activeArticlePageId,
      ),
      activeArticleBlockId: clearActiveBlockId
          ? null
          : (activeBlockId ??
                state.activeArticleBlockId ??
                fallbackTextBlock.id),
      clearActiveArticlePageId: false,
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

  String insertArticleParagraph({String? afterBlockId, String text = ''}) {
    final block = CreateTextBlock.paragraph(
      id: _nextArticleBlockId(CreateTextBlockType.paragraph),
      text: text,
    );
    _insertArticleBlock(block, afterBlockId: afterBlockId);
    return block.id;
  }

  String insertArticleOrderedItem({String? afterBlockId, String text = ''}) {
    final block = CreateTextBlock.orderedItem(
      id: _nextArticleBlockId(CreateTextBlockType.orderedItem),
      text: text,
    );
    _insertArticleBlock(block, afterBlockId: afterBlockId);
    return block.id;
  }

  String insertArticleTextBlock({
    String? afterBlockId,
    required CreateTextBlockType type,
    String text = '',
  }) {
    final block = switch (type) {
      CreateTextBlockType.heading2 => CreateTextBlock.heading2(
        id: _nextArticleBlockId(type),
        text: text,
      ),
      CreateTextBlockType.heading3 => CreateTextBlock.heading3(
        id: _nextArticleBlockId(type),
        text: text,
      ),
      CreateTextBlockType.sectionTitle => CreateTextBlock.sectionTitle(
        id: _nextArticleBlockId(type),
        text: text,
      ),
      CreateTextBlockType.orderedItem => CreateTextBlock.orderedItem(
        id: _nextArticleBlockId(type),
        text: text,
      ),
      CreateTextBlockType.bulletItem => CreateTextBlock.bulletItem(
        id: _nextArticleBlockId(type),
        text: text,
      ),
      CreateTextBlockType.paragraph => CreateTextBlock.paragraph(
        id: _nextArticleBlockId(type),
        text: text,
      ),
      CreateTextBlockType.image => CreateTextBlock.image(
        id: _nextArticleBlockId(type),
        imagePath: text,
      ),
    };
    _insertArticleBlock(block, afterBlockId: afterBlockId);
    return block.id;
  }

  void _insertArticleBlock(CreateTextBlock block, {String? afterBlockId}) {
    final blocks = List<CreateTextBlock>.from(state.articleBlocks);
    final insertIndex = afterBlockId == null
        ? blocks.length
        : blocks.indexWhere((item) => item.id == afterBlockId) + 1;
    final safeIndex = insertIndex.clamp(0, blocks.length);
    blocks.insert(safeIndex, block);
    _applyArticleBlocks(blocks, activeBlockId: block.id);
  }

  void updateArticleTextBlock(String blockId, String value) {
    final blocks = state.articleBlocks
        .map(
          (block) => block.id == blockId ? block.copyWith(text: value) : block,
        )
        .toList(growable: false);
    _applyArticleBlocks(blocks, activeBlockId: blockId);
  }

  void updateArticleTextBlockType(String blockId, CreateTextBlockType type) {
    final blocks = state.articleBlocks
        .map(
          (block) => block.id == blockId ? block.copyWith(type: type) : block,
        )
        .toList(growable: false);
    _applyArticleBlocks(blocks, activeBlockId: blockId);
  }

  String insertArticlePageAfter({String? afterPageId, String body = ''}) {
    final binding = _bindingForPageId(afterPageId);
    final insertionOffset =
        binding?.bodyRange?.end ??
        binding?.insertOffset ??
        state.articleDocument.body.length;
    final nextDocument = _replaceBodyRange(
      state.articleDocument,
      start: insertionOffset,
      end: insertionOffset,
      replacement: body.isEmpty ? '\n' : '\n${_normalizeArticleBody(body)}',
    );
    _applyArticleDocument(nextDocument);
    return state.articlePages.last.id;
  }

  void updateArticlePageText(String pageId, String value) {
    final binding = _bindingForPageId(pageId);
    if (binding == null) {
      return;
    }
    if (binding.hasBodySlice) {
      final nextDocument = _replaceBodyRange(
        state.articleDocument,
        start: binding.bodyRange!.start,
        end: binding.bodyRange!.end,
        replacement: value,
      );
      _applyArticleDocument(nextDocument, activePageId: pageId);
      return;
    }
    if (value.trim().isEmpty) {
      return;
    }
    final nextDocument = _replaceBodyRange(
      state.articleDocument,
      start: binding.insertOffset,
      end: binding.insertOffset,
      replacement: value,
    );
    _applyArticleDocument(nextDocument, activePageId: pageId);
  }

  void updateArticlePageTextFromBinding(
    ArticlePageBinding binding,
    String value,
  ) {
    if (binding.hasBodySlice) {
      final nextDocument = _replaceBodyRange(
        state.articleDocument,
        start: binding.bodyRange!.start,
        end: binding.bodyRange!.end,
        replacement: value,
      );
      _applyArticleDocument(nextDocument);
      return;
    }
    final doc = state.articleDocument;
    final anchor =
        (binding.assetOffset ?? binding.insertOffset).clamp(0, doc.body.length);
    final end = _bodySegmentEndExclusive(doc, anchor);
    final nextDocument = _replaceBodyRange(
      doc,
      start: anchor,
      end: end,
      replacement: value,
    );
    _applyArticleDocument(nextDocument);
  }

  List<ArticleDocumentAsset> _documentSortedImageAssets(
    ArticleDocumentData document,
  ) {
    final assets =
        document.assets.where((a) => a.hasImage).toList(growable: false)
          ..sort((ArticleDocumentAsset l, ArticleDocumentAsset r) {
            final oc = l.offset.compareTo(r.offset);
            if (oc != 0) {
              return oc;
            }
            return l.id.compareTo(r.id);
          });
    return assets;
  }

  /// 将「首图前插文槽」草稿实时写入 canonical body，使流式分页能按视口高度拆到多页。
  ///
  /// 不在每次按键记 undo；仅在「从空到有字」时记一点，避免撤销栈被逐字塞满。
  void syncParagraphDraftBeforeAsset(String assetId, String draft) {
    final id = assetId.trim();
    if (id.isEmpty) {
      return;
    }
    final document = state.articleDocument;
    final sorted = _documentSortedImageAssets(document);
    if (sorted.isEmpty || sorted.first.id != id) {
      return;
    }
    final o = sorted.first.offset.clamp(0, document.body.length);
    final newLeading = _normalizeArticleBody(draft.replaceAll('\r\n', '\n'));
    final oldLeading = document.body.substring(0, o);
    if (oldLeading == newLeading) {
      return;
    }
    final recordUndo =
        (oldLeading.trim().isEmpty && newLeading.trim().isNotEmpty) ||
        (oldLeading.trim().isNotEmpty && newLeading.trim().isEmpty);
    final nextBody = _normalizeArticleBody(
      newLeading + document.body.substring(o),
    );
    final delta = newLeading.length - o;
    final nextAssets = document.assets
        .map(
          (a) => a.offset >= o ? a.copyWith(offset: a.offset + delta) : a,
        )
        .toList(growable: false);
    _applyArticleDocument(
      document.copyWith(
        body: nextBody,
        assets: _normalizeAssets(nextAssets, nextBody.length),
      ),
      recordUndoPoint: recordUndo,
    );
  }

  /// 两图之间插文槽草稿与 [syncParagraphDraftBeforeAsset] 同理。
  void syncParagraphDraftBetweenAssets(String anchorAssetId, String draft) {
    final id = anchorAssetId.trim();
    if (id.isEmpty) {
      return;
    }
    final document = state.articleDocument;
    final sorted = _documentSortedImageAssets(document);
    final index = sorted.indexWhere((a) => a.id == id);
    if (index < 0 || index + 1 >= sorted.length) {
      return;
    }
    final cur = sorted[index];
    final nxt = sorted[index + 1];
    final a = cur.offset.clamp(0, document.body.length);
    final b = nxt.offset.clamp(a, document.body.length);
    final newMid = _normalizeArticleBody(draft.replaceAll('\r\n', '\n'));
    final oldMid = document.body.substring(a, b);
    if (oldMid == newMid) {
      return;
    }
    final recordUndo =
        (oldMid.trim().isEmpty && newMid.trim().isNotEmpty) ||
        (oldMid.trim().isNotEmpty && newMid.trim().isEmpty);
    final nextBody = _normalizeArticleBody(
      document.body.substring(0, a) + newMid + document.body.substring(b),
    );
    final delta = newMid.length - (b - a);
    final nextAssets = document.assets
        .map(
          (asset) => asset.offset >= b
              ? asset.copyWith(offset: asset.offset + delta)
              : asset,
        )
        .toList(growable: false);
    _applyArticleDocument(
      document.copyWith(
        body: nextBody,
        assets: _normalizeAssets(nextAssets, nextBody.length),
      ),
      recordUndoPoint: recordUndo,
    );
  }

  /// 末图后插文槽草稿实时写入文末。
  void syncParagraphDraftAfterLastAsset(String anchorAssetId, String draft) {
    final id = anchorAssetId.trim();
    if (id.isEmpty) {
      return;
    }
    final document = state.articleDocument;
    final sorted = _documentSortedImageAssets(document);
    if (sorted.isEmpty || sorted.last.id != id) {
      return;
    }
    final a = sorted.last.offset.clamp(0, document.body.length);
    final newTail = _normalizeArticleBody(draft.replaceAll('\r\n', '\n'));
    final oldTail = document.body.substring(a);
    if (oldTail == newTail) {
      return;
    }
    final recordUndo =
        (oldTail.trim().isEmpty && newTail.trim().isNotEmpty) ||
        (oldTail.trim().isNotEmpty && newTail.trim().isEmpty);
    final nextBody = _normalizeArticleBody(
      document.body.substring(0, a) + newTail,
    );
    _applyArticleDocument(
      document.copyWith(
        body: nextBody,
        assets: _normalizeAssets(document.assets, nextBody.length),
      ),
      recordUndoPoint: recordUndo,
    );
  }

  void removeArticlePage(String pageId) {
    final binding = _bindingForPageId(pageId);
    if (binding == null) {
      return;
    }
    var nextDocument = state.articleDocument;
    if (binding.hasTitleSlice) {
      nextDocument = nextDocument.copyWith(
        title: nextDocument.title.replaceRange(
          binding.titleRange!.start,
          binding.titleRange!.end,
          '',
        ),
      );
    }
    if (binding.hasBodySlice) {
      nextDocument = _replaceBodyRange(
        nextDocument,
        start: binding.bodyRange!.start,
        end: binding.bodyRange!.end,
        replacement: '',
      );
    }
    if (binding.hasAsset) {
      final removeIds = binding.resolvedAssetIds.toSet();
      nextDocument = nextDocument.copyWith(
        assets: nextDocument.assets
            .where((asset) => !removeIds.contains(asset.id))
            .toList(growable: false),
      );
    }
    _applyArticleDocument(nextDocument, activePageId: pageId);
  }

  /// 在全文 `body` 的指定偏移插入一张新图。
  ///
  /// 无论当前活动页本身是否已绑定图片，都新增 asset，而不是替换已有图片。
  /// [bodyInsertOffset] 为 null 时回落到文末；返回承载该新图的 [ArticlePageData.id]。
  String insertArticleImageAtBodyOffset(
    String imagePath, {
    int? bodyInsertOffset,
    String? fallbackActivePageId,
  }) {
    final sanitized = imagePath.trim();
    if (sanitized.isEmpty) {
      return fallbackActivePageId ??
          state.activeArticlePageId ??
          state.articlePages.first.id;
    }
    final body = state.articleDocument.body;
    final assetOffset = bodyInsertOffset != null
        ? bodyInsertOffset.clamp(0, body.length)
        : body.length;

    final assetId = _nextArticleAssetId();
    final nextAssets = <ArticleDocumentAsset>[
      ...state.articleDocument.assets,
      ArticleDocumentAsset(
        id: assetId,
        offset: assetOffset,
        imageUrl: sanitized,
      ),
    ];
    _applyArticleDocument(
      state.articleDocument.copyWith(
        assets: _normalizeAssets(nextAssets, body.length),
      ),
      activePageId: fallbackActivePageId,
    );
    final landingPageId =
        _pageIdForAssetId(assetId) ??
        fallbackActivePageId ??
        state.activeArticlePageId ??
        state.articlePages.first.id;
    if (landingPageId != state.activeArticlePageId) {
      state = state.copyWith(activeArticlePageId: landingPageId);
    }
    return landingPageId;
  }

  /// 替换当前页已绑定的文内图；若当前页无图片，则在给定 `body` 偏移新增一张。
  ///
  /// 仅供“替换当前图”语义调用，不应用作通用插图入口。
  String replaceArticlePageImage(
    String pageId,
    String imagePath, {
    int? bodyInsertOffset,
  }) {
    final sanitized = imagePath.trim();
    if (sanitized.isEmpty) {
      return pageId;
    }
    final binding = _bindingForPageId(pageId);
    if (binding == null) {
      return insertArticleImageAtBodyOffset(
        sanitized,
        bodyInsertOffset: bodyInsertOffset,
        fallbackActivePageId:
            state.activeArticlePageId ?? state.articlePages.first.id,
      );
    }
    if (binding.hasAsset) {
      final nextAssets = state.articleDocument.assets
          .map(
            (asset) => asset.id == binding.assetId
                ? asset.copyWith(imageUrl: sanitized)
                : asset,
          )
          .toList(growable: false);
      _applyArticleDocument(
        state.articleDocument.copyWith(
          assets: _normalizeAssets(
            nextAssets,
            state.articleDocument.body.length,
          ),
        ),
        activePageId: pageId,
      );
      return pageId;
    }
    return insertArticleImageAtBodyOffset(
      sanitized,
      bodyInsertOffset: bodyInsertOffset,
      fallbackActivePageId: pageId,
    );
  }

  String? _pageIdForAssetId(String assetId) {
    for (final page in state.articlePages) {
      final ids = page.binding?.resolvedAssetIds ?? const <String>[];
      if (ids.contains(assetId)) {
        return page.id;
      }
    }
    return null;
  }

  String? _pageIdForBodyRange(int start, int end) {
    final bodyLength = state.articleDocument.body.length;
    final safeStart = start.clamp(0, bodyLength);
    final safeEnd = end.clamp(safeStart, bodyLength);
    for (final page in state.articlePages) {
      final range = page.binding?.bodyRange;
      if (range == null || range.isCollapsed) {
        continue;
      }
      final overlaps = range.start < safeEnd && range.end > safeStart;
      if (overlaps) {
        return page.id;
      }
    }
    return null;
  }

  String _insertArticleParagraphRelativeToAsset(
    String assetId, {
    String text = '',
    required bool before,
    bool focusInsertedTextPage = false,
  }) {
    final id = assetId.trim();
    final fallbackPageId =
        state.activeArticlePageId ?? state.articlePages.first.id;
    if (id.isEmpty) {
      return fallbackPageId;
    }
    final document = state.articleDocument;
    final sortedAssets =
        document.assets.where((asset) => asset.hasImage).toList(growable: false)
          ..sort((left, right) {
            final offsetCompare = left.offset.compareTo(right.offset);
            if (offsetCompare != 0) {
              return offsetCompare;
            }
            return left.id.compareTo(right.id);
          });
    final targetIndex = sortedAssets.indexWhere((asset) => asset.id == id);
    if (targetIndex < 0) {
      return fallbackPageId;
    }
    final target = sortedAssets[targetIndex];
    final insertionOffset = target.offset.clamp(0, document.body.length);
    final normalizedText = _normalizeArticleBody(text);
    if (normalizedText.trim().isEmpty) {
      final landingPageId = _pageIdForAssetId(id) ?? fallbackPageId;
      setActiveArticlePage(landingPageId);
      return landingPageId;
    }
    final replacement = '$normalizedText\n';
    final insertedTextStart = insertionOffset;
    final insertedTextEnd = insertedTextStart + normalizedText.length;
    final shiftedDocument = _replaceBodyRange(
      document,
      start: insertionOffset,
      end: insertionOffset,
      replacement: replacement,
    );
    final delta = _normalizeArticleBody(replacement).length;
    final nextAssets = document.assets
        .map((asset) {
          if (asset.offset != target.offset) {
            return asset.offset > target.offset
                ? asset.copyWith(offset: asset.offset + delta)
                : asset;
          }
          final peerIndex = sortedAssets.indexWhere(
            (candidate) => candidate.id == asset.id,
          );
          final shouldShift = before
              ? peerIndex >= targetIndex
              : peerIndex > targetIndex;
          return shouldShift
              ? asset.copyWith(offset: asset.offset + delta)
              : asset;
        })
        .toList(growable: false);
    _applyArticleDocument(
      shiftedDocument.copyWith(
        assets: _normalizeAssets(nextAssets, shiftedDocument.body.length),
      ),
    );
    final landingPageId = focusInsertedTextPage && normalizedText.isNotEmpty
        ? _pageIdForBodyRange(insertedTextStart, insertedTextEnd) ??
              _pageIdForAssetId(id) ??
              fallbackPageId
        : _pageIdForAssetId(id) ?? fallbackPageId;
    setActiveArticlePage(landingPageId);
    return landingPageId;
  }

  void replaceArticlePageImageFromBinding(
    ArticlePageBinding binding,
    String imagePath,
  ) {
    final sanitized = imagePath.trim();
    if (sanitized.isEmpty) {
      return;
    }
    if (binding.hasAsset) {
      final nextAssets = state.articleDocument.assets
          .map(
            (asset) => asset.id == binding.assetId
                ? asset.copyWith(imageUrl: sanitized)
                : asset,
          )
          .toList(growable: false);
      _applyArticleDocument(
        state.articleDocument.copyWith(
          assets: _normalizeAssets(
            nextAssets,
            state.articleDocument.body.length,
          ),
        ),
      );
      return;
    }
    final nextAssets = <ArticleDocumentAsset>[
      ...state.articleDocument.assets,
      ArticleDocumentAsset(
        id: _nextArticleAssetId(),
        offset: binding.insertOffset,
        imageUrl: sanitized,
      ),
    ];
    _applyArticleDocument(
      state.articleDocument.copyWith(
        assets: _normalizeAssets(nextAssets, state.articleDocument.body.length),
      ),
    );
  }

  void updateArticlePageImageLayout(String pageId, String imageLayout) {
    final binding = _bindingForPageId(pageId);
    if (binding == null || !binding.hasAsset) {
      return;
    }
    final nextAssets = state.articleDocument.assets
        .map(
          (asset) => asset.id == binding.assetId
              ? asset.copyWith(imageLayout: imageLayout)
              : asset,
        )
        .toList(growable: false);
    _applyArticleDocument(
      state.articleDocument.copyWith(
        assets: _normalizeAssets(nextAssets, state.articleDocument.body.length),
      ),
      activePageId: pageId,
    );
  }

  void updateArticlePageCaptionFromBinding(
    ArticlePageBinding binding,
    String caption,
  ) {
    if (!binding.hasAsset) {
      return;
    }
    final nextAssets = state.articleDocument.assets
        .map(
          (asset) => asset.id == binding.assetId
              ? asset.copyWith(caption: caption)
              : asset,
        )
        .toList(growable: false);
    _applyArticleDocument(
      state.articleDocument.copyWith(
        assets: _normalizeAssets(nextAssets, state.articleDocument.body.length),
      ),
      activePageId: state.activeArticlePageId,
    );
  }

  void updateArticlePageImageLayoutFromBinding(
    ArticlePageBinding binding,
    String imageLayout,
  ) {
    if (!binding.hasAsset) {
      return;
    }
    final nextAssets = state.articleDocument.assets
        .map(
          (asset) => asset.id == binding.assetId
              ? asset.copyWith(imageLayout: imageLayout)
              : asset,
        )
        .toList(growable: false);
    _applyArticleDocument(
      state.articleDocument.copyWith(
        assets: _normalizeAssets(nextAssets, state.articleDocument.body.length),
      ),
    );
  }

  /// 仅移除当前页绑定的文内图，不删除正文/标题（spec §8.6）。
  ///
  /// 多图同页时请用 [removeArticleImageAssetById]。
  void removeArticleImageAsset(ArticlePageBinding binding) {
    final id = binding.assetId?.trim();
    if (id == null || id.isEmpty) {
      return;
    }
    removeArticleImageAssetById(id);
  }

  void removeArticlePageFromBinding(ArticlePageBinding binding) {
    var nextDocument = state.articleDocument;
    if (binding.hasTitleSlice) {
      nextDocument = nextDocument.copyWith(
        title: nextDocument.title.replaceRange(
          binding.titleRange!.start,
          binding.titleRange!.end,
          '',
        ),
      );
    }
    if (binding.hasBodySlice) {
      nextDocument = _replaceBodyRange(
        nextDocument,
        start: binding.bodyRange!.start,
        end: binding.bodyRange!.end,
        replacement: '',
      );
    }
    if (binding.hasAsset) {
      final removeIds = binding.resolvedAssetIds.toSet();
      nextDocument = nextDocument.copyWith(
        assets: nextDocument.assets
            .where((asset) => !removeIds.contains(asset.id))
            .toList(growable: false),
      );
    }
    _applyArticleDocument(nextDocument);
  }

  void removeArticleImageAssetById(String assetId) {
    final id = assetId.trim();
    if (id.isEmpty) {
      return;
    }
    final nextAssets = state.articleDocument.assets
        .where((asset) => asset.id != id)
        .toList(growable: false);
    _applyArticleDocument(
      state.articleDocument.copyWith(
        assets: _normalizeAssets(nextAssets, state.articleDocument.body.length),
      ),
      activePageId: state.activeArticlePageId,
    );
  }

  void updateArticlePageCaptionForAsset(String assetId, String caption) {
    final id = assetId.trim();
    if (id.isEmpty) {
      return;
    }
    final nextAssets = state.articleDocument.assets
        .map(
          (asset) => asset.id == id ? asset.copyWith(caption: caption) : asset,
        )
        .toList(growable: false);
    _applyArticleDocument(
      state.articleDocument.copyWith(
        assets: _normalizeAssets(nextAssets, state.articleDocument.body.length),
      ),
      activePageId: state.activeArticlePageId,
    );
  }

  void updateArticlePageImageLayoutForAsset(
    String assetId,
    String imageLayout,
  ) {
    final id = assetId.trim();
    if (id.isEmpty) {
      return;
    }
    final nextAssets = state.articleDocument.assets
        .map(
          (asset) =>
              asset.id == id ? asset.copyWith(imageLayout: imageLayout) : asset,
        )
        .toList(growable: false);
    _applyArticleDocument(
      state.articleDocument.copyWith(
        assets: _normalizeAssets(nextAssets, state.articleDocument.body.length),
      ),
      activePageId: state.activeArticlePageId,
    );
  }

  void replaceArticleImageForAsset(String assetId, String imagePath) {
    final id = assetId.trim();
    final sanitized = imagePath.trim();
    if (id.isEmpty || sanitized.isEmpty) {
      return;
    }
    final nextAssets = state.articleDocument.assets
        .map(
          (asset) =>
              asset.id == id ? asset.copyWith(imageUrl: sanitized) : asset,
        )
        .toList(growable: false);
    _applyArticleDocument(
      state.articleDocument.copyWith(
        assets: _normalizeAssets(nextAssets, state.articleDocument.body.length),
      ),
    );
  }

  // ── Node 级操作（纵向滚动编辑器使用） ──

  /// 更新指定 node 的文本内容。
  void updateArticleNodeText(String nodeId, String value) {
    final id = nodeId.trim();
    if (id.isEmpty) return;
    final doc = state.articleDocument;

    // 占位正文：文档中无文本 node 时，编辑器发送此 id
    if (id == '_placeholder_body') {
      _articleBlockSeed += 1;
      final newNode = ArticleDocumentNode(
        id: 'paragraph_$_articleBlockSeed',
        type: ArticleDocumentNodeType.paragraph,
        text: value,
      );
      final nextNodes = List<ArticleDocumentNode>.from(doc.nodes)
        ..add(newNode);
      _applyArticleDocument(
        doc.copyWith(nodes: nextNodes),
        nodesAreSourceOfTruth: true,
      );
      return;
    }

    final nextNodes = doc.nodes.map((node) {
      if (node.id == id) return node.copyWith(text: value);
      return node;
    }).toList(growable: false);
    _applyArticleDocument(
      doc.copyWith(nodes: nextNodes),
      activeBlockId: state.activeArticleBlockId,
      recordUndoPoint: false,
      nodesAreSourceOfTruth: true,
    );
  }

  /// 更新指定 figure node 的图片布局。
  void updateArticleNodeImageLayout(String nodeId, String layout) {
    final id = nodeId.trim();
    if (id.isEmpty) return;
    final doc = state.articleDocument;
    final nextNodes = doc.nodes.map((node) {
      if (node.id == id) return node.copyWith(imageLayout: layout);
      return node;
    }).toList(growable: false);
    _applyArticleDocument(
      doc.copyWith(nodes: nextNodes),
      nodesAreSourceOfTruth: true,
    );
  }

  /// 更新指定 figure node 的图片说明。
  void updateArticleNodeCaption(String nodeId, String caption) {
    final id = nodeId.trim();
    if (id.isEmpty) return;
    final doc = state.articleDocument;
    final nextNodes = doc.nodes.map((node) {
      if (node.id == id) return node.copyWith(caption: caption);
      return node;
    }).toList(growable: false);
    _applyArticleDocument(
      doc.copyWith(nodes: nextNodes),
      recordUndoPoint: false,
      nodesAreSourceOfTruth: true,
    );
  }

  /// 移除指定 figure node。
  void removeArticleNode(String nodeId) {
    final id = nodeId.trim();
    if (id.isEmpty) return;
    final doc = state.articleDocument;
    final nextNodes =
        doc.nodes.where((node) => node.id != id).toList(growable: false);
    _applyArticleDocument(
      doc.copyWith(nodes: nextNodes),
      nodesAreSourceOfTruth: true,
    );
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
    final nextNodes = doc.nodes.map((node) {
      if (node.id == id) return node.copyWith(imageUrl: sanitized);
      return node;
    }).toList(growable: false);
    _applyArticleDocument(
      doc.copyWith(nodes: nextNodes),
      nodesAreSourceOfTruth: true,
    );
  }

  /// 在指定 node 之后插入一个空文本 node。
  /// 在指定 node 之后插入一个空段落。返回新 node 的 id。
  String insertTextNodeAfter(String afterNodeId, {String initialText = ''}) {
    final id = afterNodeId.trim();
    if (id.isEmpty) return '';
    final doc = state.articleDocument;
    final index = doc.nodes.indexWhere((n) => n.id == id);
    if (index < 0) return '';
    _articleBlockSeed += 1;
    final newNodeId = 'paragraph_$_articleBlockSeed';
    final newNode = ArticleDocumentNode(
      id: newNodeId,
      type: ArticleDocumentNodeType.paragraph,
      text: initialText,
    );
    final nextNodes = List<ArticleDocumentNode>.from(doc.nodes)
      ..insert(index + 1, newNode);
    _applyArticleDocument(
      doc.copyWith(nodes: nextNodes),
      nodesAreSourceOfTruth: true,
    );
    return newNodeId;
  }

  /// 保证文档结构可编辑：每个 figure 前后都有 paragraph node。
  void ensureEditableStructure() {
    final doc = state.articleDocument;
    final nodes = doc.nodes;
    if (nodes.isEmpty) return;

    final fixed = _ensureEditableNodes(nodes);
    if (fixed.length != nodes.length) {
      _applyArticleDocument(
        doc.copyWith(nodes: fixed),
        nodesAreSourceOfTruth: true,
      );
    }
  }

  /// 纯函数：在 figure 前后插入空 paragraph，返回修复后的 nodes。
  List<ArticleDocumentNode> _ensureEditableNodes(
    List<ArticleDocumentNode> nodes,
  ) {
    if (nodes.isEmpty) return nodes;

    final result = <ArticleDocumentNode>[];

    for (var i = 0; i < nodes.length; i++) {
      final node = nodes[i];

      if (node.isFigure) {
        // 前一个 node 不是普通 paragraph → 插入空 paragraph
        final prev = result.isNotEmpty ? result.last : null;
        final needGapBefore =
            prev == null || prev.isDocumentTitle || prev.isFigure;
        if (needGapBefore) {
          _articleBlockSeed += 1;
          result.add(ArticleDocumentNode(
            id: 'paragraph_$_articleBlockSeed',
            type: ArticleDocumentNodeType.paragraph,
          ));
        }
      }

      result.add(node);
    }

    // 末尾如果是 figure，追加一个空 paragraph
    if (result.isNotEmpty && result.last.isFigure) {
      _articleBlockSeed += 1;
      result.add(ArticleDocumentNode(
        id: 'paragraph_$_articleBlockSeed',
        type: ArticleDocumentNodeType.paragraph,
      ));
    }

    return result;
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
    if (afterNodeId != null && afterNodeId.trim().isNotEmpty) {
      final index = nextNodes.indexWhere((n) => n.id == afterNodeId);
      if (index >= 0) {
        nextNodes.insert(index + 1, newNode);
      } else {
        nextNodes.add(newNode);
      }
    } else {
      nextNodes.add(newNode);
    }
    _applyArticleDocument(
      doc.copyWith(nodes: nextNodes),
      nodesAreSourceOfTruth: true,
    );
    return newNode.id;
  }

  /// 在上一页之后插入文内图。
  ///
  /// 图间可输入空位由 editor-only 邻接锚点提供，不再把占位换行写入 canonical body。
  String insertArticleImageAfterPage(String? afterPageId, String imagePath) {
    final sanitized = imagePath.trim();
    if (sanitized.isEmpty) {
      return state.activeArticlePageId ?? state.articlePages.first.id;
    }
    final binding = _bindingForPageId(afterPageId);
    final doc = state.articleDocument;
    var base =
        binding?.bodyRange?.end ?? binding?.insertOffset ?? doc.body.length;
    base = base.clamp(0, doc.body.length);

    final assetId = _nextArticleAssetId();
    final nextAssets = <ArticleDocumentAsset>[
      ...doc.assets,
      ArticleDocumentAsset(id: assetId, offset: base, imageUrl: sanitized),
    ];
    _applyArticleDocument(
      doc.copyWith(assets: _normalizeAssets(nextAssets, doc.body.length)),
    );
    final landingPageId =
        _pageIdForAssetId(assetId) ??
        state.activeArticlePageId ??
        state.articlePages.first.id;
    if (landingPageId != state.activeArticlePageId) {
      state = state.copyWith(activeArticlePageId: landingPageId);
    }
    return landingPageId;
  }

  String insertArticleParagraphAfterAsset(String assetId, {String text = ''}) {
    return _insertArticleParagraphRelativeToAsset(
      assetId,
      text: text,
      before: false,
    );
  }

  String insertArticleParagraphBeforeAsset(String assetId, {String text = ''}) {
    return _insertArticleParagraphRelativeToAsset(
      assetId,
      text: text,
      before: true,
    );
  }

  String materializeArticleParagraphBeforeAsset(
    String assetId, {
    required String text,
  }) {
    if (text.trim().isEmpty) {
      return _pageIdForAssetId(assetId) ??
          state.activeArticlePageId ??
          state.articlePages.first.id;
    }
    return _insertArticleParagraphRelativeToAsset(
      assetId,
      text: text,
      before: true,
      focusInsertedTextPage: true,
    );
  }

  String materializeArticleParagraphAfterAsset(
    String assetId, {
    required String text,
  }) {
    if (text.trim().isEmpty) {
      return _pageIdForAssetId(assetId) ??
          state.activeArticlePageId ??
          state.articlePages.first.id;
    }
    return _insertArticleParagraphRelativeToAsset(
      assetId,
      text: text,
      before: false,
      focusInsertedTextPage: true,
    );
  }

  void setArticleTemplate(ArticleTemplatePreset preset) {
    state = state.copyWith(articleTemplate: preset);
    _applyArticleDocument(
      state.articleDocument.copyWith(template: preset.name),
      activePageId: state.activeArticlePageId,
      activeBlockId: state.activeArticleBlockId,
    );
  }

  void setArticlePaperTexture(ArticlePaperTexture texture) {
    state = state.copyWith(articlePaperTexture: texture);
    _applyArticleDocument(
      state.articleDocument,
      activePageId: state.activeArticlePageId,
      activeBlockId: state.activeArticleBlockId,
    );
  }

  void setArticleFontPreset(ArticleFontPreset preset) {
    state = state.copyWith(articleFontPreset: preset);
    _applyArticleDocument(
      state.articleDocument.copyWith(fontPreset: preset.name),
      activePageId: state.activeArticlePageId,
      activeBlockId: state.activeArticleBlockId,
    );
  }

  void setArticleCoverImage(String? imagePath) {
    final normalizedCoverImagePath = _normalizeArticleCoverImagePath(
      imagePath ?? '',
      state.imagePaths,
    );
    state = state.copyWith(articleCoverImagePath: normalizedCoverImagePath);
    _applyArticleDocument(
      state.articleDocument.copyWith(coverImageUrl: normalizedCoverImagePath),
      activePageId: state.activeArticlePageId,
      activeBlockId: state.activeArticleBlockId,
    );
  }

  void replaceArticleImageBlock(String blockId, String imagePath) {
    final sanitized = imagePath.trim();
    if (sanitized.isEmpty) {
      return;
    }
    final blocks = state.articleBlocks
        .map(
          (block) => block.id == blockId
              ? block.copyWith(imagePath: sanitized)
              : block,
        )
        .toList(growable: false);
    _applyArticleBlocks(blocks, activeBlockId: blockId);
  }

  void updateArticleImageLayout(
    String blockId,
    CreateTextImageLayout imageLayout,
  ) {
    final blocks = state.articleBlocks
        .map(
          (block) => block.id == blockId
              ? block.copyWith(imageLayout: imageLayout)
              : block,
        )
        .toList(growable: false);
    _applyArticleBlocks(blocks, activeBlockId: blockId);
  }

  void insertArticleImages(List<String> paths, {String? afterBlockId}) {
    final sanitized = paths
        .map((path) => path.trim())
        .where((path) => path.isNotEmpty)
        .toList(growable: false);
    if (sanitized.isEmpty) {
      return;
    }
    final blocks = List<CreateTextBlock>.from(state.articleBlocks);
    final insertIndex = afterBlockId == null
        ? blocks.length
        : blocks.indexWhere((item) => item.id == afterBlockId) + 1;
    final safeIndex = insertIndex.clamp(0, blocks.length);
    blocks.insertAll(
      safeIndex,
      sanitized.map(
        (path) => CreateTextBlock.image(
          id: _nextArticleBlockId(CreateTextBlockType.image),
          imagePath: path,
        ),
      ),
    );
    _applyArticleBlocks(
      blocks,
      activeBlockId: afterBlockId ?? state.activeArticleBlockId,
    );
  }

  void removeArticleBlock(String blockId) {
    final removedBlock = state.articleBlocks
        .where((block) => block.id == blockId)
        .cast<CreateTextBlock?>()
        .firstWhere((block) => block != null, orElse: () => null);
    final removedImagePath = removedBlock?.imagePath.trim() ?? '';
    final shouldClearCover =
        removedBlock?.hasImage == true &&
        removedImagePath.isNotEmpty &&
        removedImagePath == state.articleCoverImagePath;
    if (shouldClearCover) {
      state = state.copyWith(articleCoverImagePath: '');
    }
    final next = state.articleBlocks
        .where((block) => block.id != blockId)
        .toList(growable: false);
    if (next.isEmpty) {
      final fallbackId = insertArticleParagraph();
      setActiveArticleBlock(fallbackId);
      return;
    }
    final fallback = next.firstWhere(
      (block) => block.isTextLike,
      orElse: () => next.first,
    );
    _applyArticleBlocks(next, activeBlockId: fallback.id);
  }

  void removeArticleBlocks(Iterable<String> blockIds) {
    final idSet = blockIds.where((id) => id.trim().isNotEmpty).toSet();
    if (idSet.isEmpty) {
      return;
    }
    final shouldClearCover = state.articleBlocks.any(
      (block) =>
          idSet.contains(block.id) &&
          block.hasImage &&
          block.imagePath.trim().isNotEmpty &&
          block.imagePath.trim() == state.articleCoverImagePath,
    );
    if (shouldClearCover) {
      state = state.copyWith(articleCoverImagePath: '');
    }
    final next = state.articleBlocks
        .where((block) => !idSet.contains(block.id))
        .toList(growable: false);
    if (next.isEmpty) {
      final fallbackId = insertArticleParagraph();
      setActiveArticleBlock(fallbackId);
      return;
    }
    final fallback = next.firstWhere(
      (block) => block.isTextLike,
      orElse: () => next.first,
    );
    _applyArticleBlocks(next, activeBlockId: fallback.id);
  }

  void expandTitle() {
    state = state.copyWith(titlePresentation: TitlePresentation.expanded);
  }

  void collapseTitleIfEmpty() {
    if (state.title.trim().isNotEmpty) {
      return;
    }
    state = state.copyWith(titlePresentation: TitlePresentation.collapsed);
  }

  void dismissTitleHint() {
    state = state.copyWith(titleHintDismissed: true);
  }

  void restoreTitleHint() {
    state = state.copyWith(titleHintDismissed: false);
  }

  void setSettings(PublishSettings settings) {
    state = state.copyWith(settings: settings);
  }

  void setCurrentMediaIndex(int index) {
    final maxIndex = state.hasVideo
        ? 0
        : (state.imagePaths.isEmpty ? 0 : state.imagePaths.length - 1);
    state = state.copyWith(currentMediaIndex: index.clamp(0, maxIndex));
  }

  void setDraftId(String? id) {
    state = state.copyWith(draftId: id, clearDraftId: id == null);
  }

  void setImages(
    List<String> paths, {
    required CreateEditorKind editorKind,
    int currentIndex = 0,
  }) {
    final sanitized = paths
        .map((path) => path.trim())
        .where((path) => path.isNotEmpty)
        .toList(growable: false);
    state = state.copyWith(
      editorKind: editorKind,
      mediaKind: sanitized.isEmpty
          ? CreateMediaKind.none
          : CreateMediaKind.images,
      imagePaths: sanitized,
      videoPath: '',
      originalVideoPath: '',
      videoThumbnail: '',
      videoDurationMs: 0,
      videoTrimStartMs: 0,
      videoTrimEndMs: 0,
      videoCoverTimeMs: 0,
      videoMuted: false,
      currentMediaIndex: sanitized.isEmpty
          ? 0
          : currentIndex.clamp(0, sanitized.length - 1),
    );
  }

  void appendImages(
    List<String> paths, {
    required CreateEditorKind editorKind,
    int maxImages = 20,
  }) {
    final merged = <String>[
      ...state.imagePaths,
      ...paths.map((path) => path.trim()).where((path) => path.isNotEmpty),
    ];
    setImages(
      merged.take(maxImages).toList(growable: false),
      editorKind: editorKind,
      currentIndex: state.imagePaths.isEmpty ? 0 : state.currentMediaIndex,
    );
  }

  void removeImageAt(int index) {
    if (index < 0 || index >= state.imagePaths.length) {
      return;
    }
    final next = List<String>.from(state.imagePaths)..removeAt(index);
    setImages(
      next,
      editorKind: state.editorKind,
      currentIndex: state.currentMediaIndex > index
          ? state.currentMediaIndex - 1
          : state.currentMediaIndex,
    );
  }

  void reorderImages(int oldIndex, int newIndex) {
    if (oldIndex < 0 ||
        oldIndex >= state.imagePaths.length ||
        newIndex < 0 ||
        newIndex > state.imagePaths.length ||
        oldIndex == newIndex) {
      return;
    }
    final currentCoverPath =
        state.imagePaths[state.currentMediaIndex.clamp(
          0,
          state.imagePaths.length - 1,
        )];
    final next = List<String>.from(state.imagePaths);
    final moved = next.removeAt(oldIndex);
    final targetIndex = oldIndex < newIndex ? newIndex - 1 : newIndex;
    next.insert(targetIndex, moved);
    final nextCoverIndex = next.indexOf(currentCoverPath);
    state = state.copyWith(
      imagePaths: next,
      mediaKind: next.isEmpty ? CreateMediaKind.none : CreateMediaKind.images,
      currentMediaIndex: nextCoverIndex < 0 ? 0 : nextCoverIndex,
    );
  }

  void clearImages() {
    setImages(const <String>[], editorKind: state.editorKind);
  }

  void setVideo(
    String path, {
    required CreateEditorKind editorKind,
    String thumbnail = '',
    String? originalPath,
    int durationMs = 0,
    int trimStartMs = 0,
    int trimEndMs = 0,
    int coverTimeMs = 0,
    bool muted = false,
  }) {
    final sanitizedPath = path.trim();
    state = state.copyWith(
      editorKind: editorKind,
      mediaKind: sanitizedPath.isEmpty
          ? CreateMediaKind.none
          : CreateMediaKind.video,
      imagePaths: const <String>[],
      videoPath: sanitizedPath,
      originalVideoPath: (originalPath ?? sanitizedPath).trim(),
      videoThumbnail: thumbnail.trim(),
      videoDurationMs: durationMs.clamp(0, 999999999),
      videoTrimStartMs: trimStartMs.clamp(0, 999999999),
      videoTrimEndMs: trimEndMs.clamp(0, 999999999),
      videoCoverTimeMs: coverTimeMs.clamp(0, 999999999),
      videoMuted: muted,
      currentMediaIndex: 0,
    );
  }

  void applyVideoEditing({
    required String videoPath,
    required String thumbnailPath,
    required int videoDurationMs,
    required int trimStartMs,
    required int trimEndMs,
    required int coverTimeMs,
    required bool muted,
    String? originalVideoPath,
  }) {
    final sanitizedVideoPath = videoPath.trim();
    if (sanitizedVideoPath.isEmpty) {
      return;
    }
    state = state.copyWith(
      editorKind: CreateEditorKind.media,
      mediaKind: CreateMediaKind.video,
      imagePaths: const <String>[],
      videoPath: sanitizedVideoPath,
      originalVideoPath: (originalVideoPath ?? state.originalVideoPath).trim(),
      videoThumbnail: thumbnailPath.trim(),
      videoDurationMs: videoDurationMs.clamp(0, 999999999),
      videoTrimStartMs: trimStartMs.clamp(0, 999999999),
      videoTrimEndMs: trimEndMs.clamp(0, 999999999),
      videoCoverTimeMs: coverTimeMs.clamp(0, 999999999),
      videoMuted: muted,
      currentMediaIndex: 0,
    );
  }

  void clearVideo() {
    state = state.copyWith(
      mediaKind: state.imagePaths.isNotEmpty
          ? CreateMediaKind.images
          : CreateMediaKind.none,
      videoPath: '',
      originalVideoPath: '',
      videoThumbnail: '',
      videoDurationMs: 0,
      videoTrimStartMs: 0,
      videoTrimEndMs: 0,
      videoCoverTimeMs: 0,
      videoMuted: false,
      currentMediaIndex: 0,
    );
  }

  void restoreFromDraft(CreateDraft draft) {
    state = draft.state.copyWith(
      draftId: draft.id,
      activeArticleBlockId:
          draft.state.activeArticleBlockId ??
          draft.state.articleBlocks.first.id,
    );
  }
}

final createEditorProvider =
    NotifierProvider.autoDispose<CreateEditorNotifier, CreateEditorState>(
      CreateEditorNotifier.new,
    );
