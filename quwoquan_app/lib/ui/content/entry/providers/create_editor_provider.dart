import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';

class CreateEditorNotifier extends Notifier<CreateEditorStateV2> {
  int _articleBlockSeed = 0;

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
    state = state.copyWith(
      title: value,
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

  void _applyArticleBlocks(
    List<CreateTextBlock> blocks, {
    String? activeBlockId,
    bool clearActiveBlockId = false,
  }) {
    final normalized = blocks.isEmpty
        ? createDefaultArticleBlocks()
        : blocks.toList(growable: false);
    final fallbackTextBlock = normalized.firstWhere(
      (block) => block.isTextLike,
      orElse: () => normalized.first,
    );
    state = state.copyWith(
      articleBlocks: normalized,
      body: buildArticlePlainText(normalized),
      imagePaths: extractArticleImagePaths(normalized),
      activeArticleBlockId: clearActiveBlockId
          ? null
          : (activeBlockId ?? state.activeArticleBlockId ?? fallbackTextBlock.id),
      clearActiveArticleBlockId: clearActiveBlockId,
    );
  }

  void setActiveArticleBlock(String? blockId) {
    state = state.copyWith(
      activeArticleBlockId: blockId,
      clearActiveArticleBlockId: blockId == null,
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

  void insertArticleImages(
    List<String> paths, {
    String? afterBlockId,
  }) {
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
      mediaKind: sanitized.isEmpty ? CreateMediaKind.none : CreateMediaKind.images,
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
    final currentCoverPath = state.imagePaths[
        state.currentMediaIndex.clamp(0, state.imagePaths.length - 1)];
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
      mediaKind: sanitizedPath.isEmpty ? CreateMediaKind.none : CreateMediaKind.video,
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
      mediaKind: state.imagePaths.isNotEmpty ? CreateMediaKind.images : CreateMediaKind.none,
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
