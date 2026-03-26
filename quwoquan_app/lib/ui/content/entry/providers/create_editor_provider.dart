import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';

class CreateEditorNotifier extends Notifier<CreateEditorStateV2> {
  int _articleBlockSeed = 0;
  int _articleAssetSeed = 0;

  @override
  CreateEditorStateV2 build() {
    return CreateEditorStateV2.initial();
  }

  void reset({CreateEditorKind editorKind = CreateEditorKind.text}) {
    state = CreateEditorStateV2.initial(editorKind: editorKind);
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
    final nextAssets = document.assets
        .map((asset) {
          final shouldShift =
              asset.offset > safeEnd ||
              (safeEnd > safeStart && asset.offset == safeEnd);
          return shouldShift
              ? asset.copyWith(offset: asset.offset + delta)
              : asset;
        })
        .toList(growable: false);
    return document.copyWith(
      body: nextBody,
      assets: _normalizeAssets(nextAssets, nextBody.length),
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

  void _applyArticleDocument(
    ArticleDocumentData document, {
    String? activePageId,
    String? activeBlockId,
    bool clearActivePageId = false,
    bool clearActiveBlockId = false,
  }) {
    final normalizedBody = _normalizeArticleBody(document.body);
    final normalizedDocument = ArticleDocumentData(
      title: document.title,
      body: normalizedBody,
      assets: _normalizeAssets(document.assets, normalizedBody.length),
      blocks: document.blocks,
    );
    final imagePaths = extractArticleImagePathsFromDocument(normalizedDocument);
    final blocks = buildArticleBlocksFromDocument(normalizedDocument);
    final pages = buildArticlePagesSnapshotFromDocument(
      normalizedDocument,
      fontPreset: state.articleFontPreset,
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
      articleCoverImagePath: _normalizeArticleCoverImagePath(
        state.articleCoverImagePath,
        imagePaths,
      ),
      activeArticlePageId: clearActivePageId
          ? null
          : (activePageId ?? state.activeArticlePageId ?? pages.first.id),
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
    final normalized = blocks.isEmpty
        ? createDefaultArticleBlocks()
        : blocks.toList(growable: false);
    final document = buildArticleDocumentFromBlocks(
      normalized,
      title: state.title,
    );
    final normalizedBody = _normalizeArticleBody(document.body);
    final normalizedDocument = ArticleDocumentData(
      title: document.title,
      body: normalizedBody,
      assets: _normalizeAssets(document.assets, normalizedBody.length),
      blocks: document.blocks,
    );
    final imagePaths = extractArticleImagePathsFromDocument(normalizedDocument);
    final pages = buildArticlePagesSnapshotFromDocument(
      normalizedDocument,
      fontPreset: state.articleFontPreset,
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
      articleCoverImagePath: _normalizeArticleCoverImagePath(
        state.articleCoverImagePath,
        imagePaths,
      ),
      activeArticlePageId:
          activePageId ?? state.activeArticlePageId ?? pages.first.id,
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
    if (value.trim().isEmpty) {
      return;
    }
    final nextDocument = _replaceBodyRange(
      state.articleDocument,
      start: binding.insertOffset,
      end: binding.insertOffset,
      replacement: value,
    );
    _applyArticleDocument(nextDocument);
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
      nextDocument = nextDocument.copyWith(
        assets: nextDocument.assets
            .where((asset) => asset.id != binding.assetId)
            .toList(growable: false),
      );
    }
    _applyArticleDocument(nextDocument, activePageId: pageId);
  }

  void replaceArticlePageImage(String pageId, String imagePath) {
    final sanitized = imagePath.trim();
    if (sanitized.isEmpty) {
      return;
    }
    final binding = _bindingForPageId(pageId);
    if (binding == null) {
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
        activePageId: pageId,
      );
      return;
    }
    final assetId = _nextArticleAssetId();
    final nextAssets = <ArticleDocumentAsset>[
      ...state.articleDocument.assets,
      ArticleDocumentAsset(
        id: assetId,
        offset: binding.insertOffset,
        imageUrl: sanitized,
      ),
    ];
    _applyArticleDocument(
      state.articleDocument.copyWith(
        assets: _normalizeAssets(nextAssets, state.articleDocument.body.length),
      ),
      activePageId: pageId,
    );
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
      nextDocument = nextDocument.copyWith(
        assets: nextDocument.assets
            .where((asset) => asset.id != binding.assetId)
            .toList(growable: false),
      );
    }
    _applyArticleDocument(nextDocument);
  }

  String insertArticleImageAfterPage(String? afterPageId, String imagePath) {
    final sanitized = imagePath.trim();
    if (sanitized.isEmpty) {
      return state.activeArticlePageId ?? state.articlePages.first.id;
    }
    final binding = _bindingForPageId(afterPageId);
    final insertionOffset =
        binding?.bodyRange?.end ??
        binding?.insertOffset ??
        state.articleDocument.body.length;
    final assetId = _nextArticleAssetId();
    final nextAssets = <ArticleDocumentAsset>[
      ...state.articleDocument.assets,
      ArticleDocumentAsset(
        id: assetId,
        offset: insertionOffset,
        imageUrl: sanitized,
      ),
    ];
    _applyArticleDocument(
      state.articleDocument.copyWith(
        assets: _normalizeAssets(nextAssets, state.articleDocument.body.length),
      ),
    );
    for (final page in state.articlePages) {
      if (page.binding?.assetId == assetId) {
        return page.id;
      }
    }
    return state.activeArticlePageId ?? state.articlePages.first.id;
  }

  void setArticleTemplate(ArticleTemplatePreset preset) {
    state = state.copyWith(articleTemplate: preset);
  }

  void setArticleFontPreset(ArticleFontPreset preset) {
    state = state.copyWith(articleFontPreset: preset);
    _applyArticleDocument(
      state.articleDocument,
      activePageId: state.activeArticlePageId,
      activeBlockId: state.activeArticleBlockId,
    );
  }

  void setArticleCoverImage(String? imagePath) {
    state = state.copyWith(
      articleCoverImagePath: _normalizeArticleCoverImagePath(
        imagePath ?? '',
        state.imagePaths,
      ),
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
    NotifierProvider.autoDispose<CreateEditorNotifier, CreateEditorStateV2>(
      CreateEditorNotifier.new,
    );
