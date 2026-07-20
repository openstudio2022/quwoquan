part of 'create_editor_provider.dart';

mixin _CreateEditorMediaOperations
    on Notifier<CreateEditorState>, _CreateEditorDocumentOperations {
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

  void updateMediaBody(String value) {
    state = state.copyWith(body: value);
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
      draftFlowKind: CreateDraftFlowKind.image,
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
      videoCoverStrategy: 'first_frame',
      videoWidth: 0,
      videoHeight: 0,
      videoMuted: false,
      isOneTapMovie: false,
      oneTapMoviePath: '',
      oneTapMovieEffectId: '',
      currentMediaIndex: sanitized.isEmpty
          ? 0
          : currentIndex.clamp(0, sanitized.length - 1),
    );
  }

  void setOneTapMovie({
    required List<String> sourceImagePaths,
    required String generatedMediaPath,
    required String effectId,
  }) {
    final sanitizedSources = sourceImagePaths
        .map((path) => path.trim())
        .where((path) => path.isNotEmpty)
        .take(1)
        .toList(growable: false);
    state = state.copyWith(
      editorKind: CreateEditorKind.media,
      draftFlowKind: CreateDraftFlowKind.image,
      mediaKind: sanitizedSources.isEmpty
          ? CreateMediaKind.none
          : CreateMediaKind.images,
      imagePaths: sanitizedSources,
      videoPath: '',
      originalVideoPath: '',
      videoThumbnail: '',
      videoDurationMs: 0,
      videoTrimStartMs: 0,
      videoTrimEndMs: 0,
      videoCoverTimeMs: 0,
      videoCoverStrategy: 'first_frame',
      videoWidth: 0,
      videoHeight: 0,
      videoMuted: false,
      isOneTapMovie: sanitizedSources.isNotEmpty,
      oneTapMoviePath: generatedMediaPath.trim(),
      oneTapMovieEffectId: effectId.trim(),
      currentMediaIndex: 0,
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
    String coverStrategy = 'first_frame',
    int width = 0,
    int height = 0,
    bool muted = false,
  }) {
    final sanitizedPath = path.trim();
    state = state.copyWith(
      editorKind: editorKind,
      draftFlowKind: CreateDraftFlowKind.video,
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
      videoCoverStrategy: _normalizedVideoCoverStrategy(
        coverStrategy,
        coverTimeMs,
      ),
      videoWidth: width.clamp(0, 999999999),
      videoHeight: height.clamp(0, 999999999),
      videoMuted: muted,
      isOneTapMovie: false,
      oneTapMoviePath: '',
      oneTapMovieEffectId: '',
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
    String coverStrategy = 'first_frame',
    int width = 0,
    int height = 0,
    required bool muted,
    String? originalVideoPath,
  }) {
    final sanitizedVideoPath = videoPath.trim();
    if (sanitizedVideoPath.isEmpty) {
      return;
    }
    state = state.copyWith(
      editorKind: CreateEditorKind.media,
      draftFlowKind: CreateDraftFlowKind.video,
      mediaKind: CreateMediaKind.video,
      imagePaths: const <String>[],
      videoPath: sanitizedVideoPath,
      originalVideoPath: (originalVideoPath ?? state.originalVideoPath).trim(),
      videoThumbnail: thumbnailPath.trim(),
      videoDurationMs: videoDurationMs.clamp(0, 999999999),
      videoTrimStartMs: trimStartMs.clamp(0, 999999999),
      videoTrimEndMs: trimEndMs.clamp(0, 999999999),
      videoCoverTimeMs: coverTimeMs.clamp(0, 999999999),
      videoCoverStrategy: _normalizedVideoCoverStrategy(
        coverStrategy,
        coverTimeMs,
      ),
      videoWidth: width.clamp(0, 999999999),
      videoHeight: height.clamp(0, 999999999),
      videoMuted: muted,
      isOneTapMovie: false,
      oneTapMoviePath: '',
      oneTapMovieEffectId: '',
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
      videoCoverStrategy: 'first_frame',
      videoWidth: 0,
      videoHeight: 0,
      videoMuted: false,
      isOneTapMovie: false,
      oneTapMoviePath: '',
      oneTapMovieEffectId: '',
      currentMediaIndex: 0,
    );
  }

  void restoreFromDraft(CreateDraft draft) {
    _clearUndoRedo();
    final restored = draft.state.copyWith(draftId: draft.id);
    state = restored;
    if (restored.editorKind != CreateEditorKind.text) {
      return;
    }
    _applyArticleDocument(
      restored.articleDocument,
      activePageId: restored.activeArticlePageId,
      activeBlockId: restored.activeArticleBlockId,
      recordUndoPoint: false,
    );
    state = state.copyWith(draftId: draft.id);
  }
}

String _normalizedVideoCoverStrategy(String value, int coverTimeMs) {
  final trimmed = value.trim();
  if (trimmed == 'manual') {
    return 'manual';
  }
  return coverTimeMs > 0 ? 'manual' : 'first_frame';
}

class _WrapGroupMutationResult {
  const _WrapGroupMutationResult({required this.nodes, required this.changed});

  final List<ArticleDocumentNode> nodes;
  final bool changed;
}
