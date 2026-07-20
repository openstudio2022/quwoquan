part of 'create_editor_models.dart';

@immutable
class CreateDraft {
  const CreateDraft({
    required this.id,
    required this.updatedAtMs,
    required this.state,
    this.sourceType,
  });

  final String id;
  final int updatedAtMs;
  final CreateEditorState state;
  final String? sourceType;

  factory CreateDraft.fromStorageMap(Map<String, dynamic> map) {
    final editorKind = (map['editorKind']?.toString() ?? 'text') == 'media'
        ? CreateEditorKind.media
        : CreateEditorKind.text;
    final mediaKindName = (map['mediaKind']?.toString() ?? 'none').trim();
    final mediaKind = switch (mediaKindName) {
      'images' => CreateMediaKind.images,
      'video' => CreateMediaKind.video,
      _ => CreateMediaKind.none,
    };
    final settingsMap = Map<String, dynamic>.from(
      map['settings'] as Map? ?? const <String, dynamic>{},
    );
    final storedBody = (map['body'] ?? '').toString();
    final storedImagePaths = List<String>.from(
      map['imagePaths'] as List? ?? const <String>[],
    );
    final storedMarkdown = (map['articleMarkdown'] ?? '').toString();
    final storedAssetManifest = Map<String, dynamic>.from(
      map['articleAssetManifest'] as Map? ?? const <String, dynamic>{},
    );
    // 本地草稿唯一正文真相源为 articleMarkdown；不再从 articleDocument /
    // articlePages / articleBlocks 等旧存储键恢复（未上线，不做兼容读取）。
    final articleDocument =
        editorKind == CreateEditorKind.text && storedMarkdown.trim().isNotEmpty
        ? ArticleMarkdownCodec.parseDocument(
            storedMarkdown,
            assetManifest: storedAssetManifest,
          )
        : createDefaultArticleDocument();
    final normalizedPages = buildArticlePagesSnapshotFromDocument(
      articleDocument,
      fontPreset: articleFontPresetFromString(
        map['articleFontPreset']?.toString(),
      ),
    );
    String? fallbackActiveNodeId;
    for (final node in articleDocument.nodes) {
      if (!node.isDocumentTitle && !node.isFigure) {
        fallbackActiveNodeId = node.id;
        break;
      }
    }
    fallbackActiveNodeId ??= articleDocument.nodes.isEmpty
        ? null
        : articleDocument.nodes.first.id;
    final storedCover = (map['articleCoverImagePath'] ?? '').toString().trim();
    final draftType = (map['type'] ?? editorKind.name).toString().trim();
    final draftFlowKind = _draftFlowKindFromStorage(
      rawDraftFlowKind: map['draftFlowKind']?.toString(),
      sourceType: draftType,
      editorKind: editorKind,
      mediaKind: mediaKind,
    );
    return CreateDraft(
      id: (map['id'] ?? '').toString(),
      updatedAtMs: (map['updatedAt'] as num?)?.toInt() ?? 0,
      state: CreateEditorState(
        editorKind: editorKind,
        draftFlowKind: draftFlowKind,
        mediaKind: mediaKind,
        imagePaths: editorKind == CreateEditorKind.text
            ? extractArticleImagePathsFromDocument(articleDocument)
            : storedImagePaths,
        videoPath: (map['videoPath'] ?? '').toString(),
        originalVideoPath: (map['originalVideoPath'] ?? '').toString(),
        videoThumbnail: (map['videoThumbnail'] ?? '').toString(),
        videoDurationMs: (map['videoDurationMs'] as num?)?.toInt() ?? 0,
        videoTrimStartMs: (map['videoTrimStartMs'] as num?)?.toInt() ?? 0,
        videoTrimEndMs: (map['videoTrimEndMs'] as num?)?.toInt() ?? 0,
        videoCoverTimeMs: (map['videoCoverTimeMs'] as num?)?.toInt() ?? 0,
        videoCoverStrategy:
            (map['videoCoverStrategy'] ?? '').toString().trim().isNotEmpty
            ? (map['videoCoverStrategy'] ?? '').toString().trim()
            : (((map['videoCoverTimeMs'] as num?)?.toInt() ?? 0) > 0
                  ? 'manual'
                  : 'first_frame'),
        videoWidth: (map['videoWidth'] as num?)?.toInt() ?? 0,
        videoHeight: (map['videoHeight'] as num?)?.toInt() ?? 0,
        videoMuted: map['videoMuted'] == true,
        isOneTapMovie: map['isOneTapMovie'] == true,
        oneTapMoviePath: (map['oneTapMoviePath'] ?? '').toString(),
        oneTapMovieEffectId: (map['oneTapMovieEffectId'] ?? '').toString(),
        currentMediaIndex:
            (map['currentMediaIndex'] as num?)?.toInt().clamp(0, 9999) ?? 0,
        title: editorKind == CreateEditorKind.text
            ? articleDocument.title
            : (map['title'] ?? '').toString(),
        body: editorKind == CreateEditorKind.text
            ? buildArticlePlainTextFromDocument(articleDocument)
            : storedBody,
        articleDocument: articleDocument,
        articlePages: normalizedPages,
        activeArticlePageId:
            (map['activeArticlePageId'] ?? '').toString().trim().isEmpty
            ? normalizedPages.first.id
            : (map['activeArticlePageId'] ?? '').toString().trim(),
        activeArticleBlockId:
            (map['activeArticleBlockId'] ?? '').toString().trim().isEmpty
            ? fallbackActiveNodeId
            : (map['activeArticleBlockId'] ?? '').toString().trim(),
        articleTemplate: articleTemplatePresetFromString(
          map['articleTemplate']?.toString(),
        ),
        articlePaperTexture: articlePaperTextureFromString(
          map['articlePaperTexture']?.toString(),
        ),
        articleFontPreset: articleFontPresetFromString(
          map['articleFontPreset']?.toString(),
        ),
        articleCoverImagePath: storedCover,
        titlePresentation:
            (map['titlePresentation']?.toString() ?? 'collapsed') == 'expanded'
            ? TitlePresentation.expanded
            : TitlePresentation.collapsed,
        titleHintDismissed: map['titleHintDismissed'] == true,
        settings: PublishSettings.fromMap(settingsMap),
        draftId: (map['id'] ?? '').toString(),
      ),
      sourceType: draftType,
    );
  }

  Map<String, dynamic> toStorageMap() {
    final articleMarkdown = _articleMarkdownForStorage();
    final articleAssetManifest = _articleAssetManifestForStorage();
    final articleRenderProfile = _articleRenderProfileForStorage();
    return <String, dynamic>{
      'id': id,
      'type': storageType,
      'updatedAt': updatedAtMs,
      'identity': identity.value,
      'editorKind': state.editorKind.name,
      'draftFlowKind': state.draftFlowKind.name,
      'mediaKind': state.mediaKind.name,
      'imagePaths': state.imagePaths,
      'videoPath': state.videoPath,
      'originalVideoPath': state.originalVideoPath,
      'videoThumbnail': state.videoThumbnail,
      'videoDurationMs': state.videoDurationMs,
      'videoTrimStartMs': state.videoTrimStartMs,
      'videoTrimEndMs': state.videoTrimEndMs,
      'videoCoverTimeMs': state.videoCoverTimeMs,
      'videoCoverStrategy': state.videoCoverStrategy,
      'videoWidth': state.videoWidth,
      'videoHeight': state.videoHeight,
      'videoMuted': state.videoMuted,
      'isOneTapMovie': state.isOneTapMovie,
      'oneTapMoviePath': state.oneTapMoviePath,
      'oneTapMovieEffectId': state.oneTapMovieEffectId,
      'currentMediaIndex': state.currentMediaIndex,
      'title': state.title,
      'body': state.body,
      'articleMarkdown': articleMarkdown,
      'markdownDialect': qwqRichMarkdownVersion,
      'articleAssetManifest': articleAssetManifest,
      'articleRenderProfile': articleRenderProfile,
      'activeArticlePageId': state.activeArticlePageId,
      'activeArticleBlockId': state.activeArticleBlockId,
      'articleTemplate': state.articleTemplate.name,
      'articlePaperTexture': state.articlePaperTexture.name,
      'articleFontPreset': state.articleFontPreset.name,
      'articleCoverImagePath': state.articleCoverImagePath,
      'coverUrl': state.articleCoverImagePath,
      'titlePresentation': state.titlePresentation.name,
      'titleHintDismissed': state.titleHintDismissed,
      'settings': state.settings.toMap(),
      'data': data,
    };
  }

  String get storageType {
    if (state.editorKind == CreateEditorKind.media) {
      return state.mediaKind == CreateMediaKind.video ? 'video' : 'media';
    }
    return 'text';
  }

  CreateDraftFlowKind get flowKind => state.draftFlowKind;

  String get tabKey {
    if (sourceType != null && sourceType!.isNotEmpty) {
      return sourceType!;
    }
    return storageType;
  }

  CreateContentIdentity get identity {
    switch (tabKey) {
      case 'media':
      case 'photo':
      case 'video':
      case 'article':
        return CreateContentIdentity.work;
      default:
        return CreateContentIdentity.moment;
    }
  }

  Map<String, dynamic> get data {
    final articleMarkdown = _articleMarkdownForStorage();
    final articleAssetManifest = _articleAssetManifestForStorage();
    final articleRenderProfile = _articleRenderProfileForStorage();
    return <String, dynamic>{
      ...state.settings.toMap(),
      'title': state.title,
      'body': state.body,
      'articleMarkdown': articleMarkdown,
      'markdownDialect': qwqRichMarkdownVersion,
      'articleAssetManifest': articleAssetManifest,
      'articleRenderProfile': articleRenderProfile,
      'articleTemplate': state.articleTemplate.name,
      'articlePaperTexture': state.articlePaperTexture.name,
      'articleFontPreset': state.articleFontPreset.name,
      'articleCoverImagePath': state.articleCoverImagePath,
      'coverUrl': state.articleCoverImagePath,
      'imagePaths': state.imagePaths,
      'videoPath': state.videoPath,
      'originalVideoPath': state.originalVideoPath,
      'videoThumbnail': state.videoThumbnail,
      'videoDurationMs': state.videoDurationMs,
      'videoTrimStartMs': state.videoTrimStartMs,
      'videoTrimEndMs': state.videoTrimEndMs,
      'videoCoverTimeMs': state.videoCoverTimeMs,
      'videoCoverStrategy': state.videoCoverStrategy,
      'videoWidth': state.videoWidth,
      'videoHeight': state.videoHeight,
      'videoMuted': state.videoMuted,
      'isOneTapMovie': state.isOneTapMovie,
      'oneTapMoviePath': state.oneTapMoviePath,
      'oneTapMovieEffectId': state.oneTapMovieEffectId,
    };
  }

  String _articleMarkdownForStorage() {
    return ArticleMarkdownCodec.serializeDocument(
      state.articleDocument,
      summary: state.settings.summary,
      tagRefs: state.settings.tagRefs,
      entityRefs: state.settings.entityRefs,
      visibility: state.settings.isPublic ? 'public' : 'private',
      assistantUsePolicy: state.settings.assistantUsePolicy,
      coverAssetId: state.articleCoverImagePath.trim().isNotEmpty
          ? 'cover'
          : '',
      coverImageUrl: state.articleCoverImagePath,
    );
  }

  Map<String, dynamic> _articleAssetManifestForStorage() {
    final assets = <Map<String, Object?>>[];
    final cover = state.articleCoverImagePath.trim();
    if (cover.isNotEmpty) {
      assets.add(_articleDraftManifestRow('cover', cover, role: 'cover'));
    }
    for (final asset in state.articleDocument.assets) {
      final imageUrl = asset.imageUrl.trim();
      if (imageUrl.isEmpty) {
        continue;
      }
      final assetId = asset.id.trim().isNotEmpty ? asset.id.trim() : imageUrl;
      assets.add(_articleDraftManifestRow(assetId, imageUrl, role: 'figure'));
    }
    return <String, dynamic>{
      'schema': 'article-asset-manifest',
      'markdownVersion': qwqRichMarkdownVersion,
      'assets': assets,
    };
  }

  Map<String, dynamic> _articleRenderProfileForStorage() {
    return <String, dynamic>{
      'template': state.articleTemplate.name,
      'paperTexture': state.articlePaperTexture.name,
      'fontPreset': state.articleFontPreset.name,
      'titleStyle': state.articleDocument.titleStyle.name,
    };
  }

  String get previewText {
    final primary = state.title.trim();
    if (primary.isNotEmpty) {
      return primary;
    }
    return state.body.trim();
  }

  String get draftLabel {
    return switch (flowKind) {
      CreateDraftFlowKind.image => '图片草稿',
      CreateDraftFlowKind.video => '视频草稿',
      CreateDraftFlowKind.article => '文章草稿',
    };
  }

  bool get shouldSuggestTitle {
    if (state.title.trim().isNotEmpty) {
      return false;
    }
    if (state.editorKind == CreateEditorKind.media) {
      return state.mediaKind == CreateMediaKind.video ||
          state.imagePaths.length >= 4 ||
          state.body.trim().length >= 80;
    }
    final body = state.body.trim();
    final paragraphCount = body
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .length;
    return body.length >= 140 ||
        paragraphCount >= 2 ||
        state.imagePaths.isNotEmpty;
  }
}

CreateDraftFlowKind _draftFlowKindFromStorage({
  required String? rawDraftFlowKind,
  required String? sourceType,
  required CreateEditorKind editorKind,
  required CreateMediaKind mediaKind,
}) {
  final normalizedFlow = (rawDraftFlowKind ?? '').trim();
  switch (normalizedFlow) {
    case 'image':
      return CreateDraftFlowKind.image;
    case 'video':
      return CreateDraftFlowKind.video;
    case 'article':
      return CreateDraftFlowKind.article;
  }

  final normalizedSource = (sourceType ?? '').trim();
  switch (normalizedSource) {
    case 'media':
    case 'photo':
    case 'gallery':
    case 'image':
      return CreateDraftFlowKind.image;
    case 'video':
    case 'capture':
      return CreateDraftFlowKind.video;
    case 'text':
    case 'article':
    case 'write':
      return CreateDraftFlowKind.article;
  }

  if (mediaKind == CreateMediaKind.video) {
    return CreateDraftFlowKind.video;
  }
  if (editorKind == CreateEditorKind.media) {
    return CreateDraftFlowKind.image;
  }
  return CreateDraftFlowKind.article;
}

Map<String, Object?> _articleDraftManifestRow(
  String assetId,
  String path, {
  required String role,
}) {
  return <String, Object?>{
    'assetId': assetId,
    'kind': 'image',
    'role': role,
    'scope': 'draft',
    'localPath': path,
    'objectKey': path.startsWith('asset://')
        ? path.substring('asset://'.length)
        : path,
    'sha256': '',
  };
}
