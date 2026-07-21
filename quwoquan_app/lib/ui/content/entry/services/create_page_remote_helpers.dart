import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/article_render/markdown/qwq_markdown.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

int paragraphCountForPayload(String text) {
  return text
      .split('\n')
      .map((line) => line.trim())
      .where((line) => line.isNotEmpty)
      .length;
}

bool shouldPublishAsArticleForPayload(CreateEditorState state) {
  return state.title.trim().isNotEmpty ||
      state.imagePaths.isNotEmpty ||
      state.body.trim().length >= 140 ||
      paragraphCountForPayload(state.body) >= 2;
}

String articleSummaryForPayload(CreateEditorState state) {
  final plainText = state.body.trim();
  if (plainText.isEmpty) {
    return state.imagePaths.isNotEmpty ? '图文内容' : '';
  }
  if (plainText.length <= 120) {
    return plainText;
  }
  return '${plainText.substring(0, 120)}...';
}

String coverAssetPathForPayload(CreateEditorState state) {
  if (state.editorKind == CreateEditorKind.text) {
    return shouldPublishAsArticleForPayload(state)
        ? state.articleCoverImagePath.trim()
        : '';
  }
  if (state.hasVideo) {
    if (state.videoThumbnail.trim().isNotEmpty) {
      return state.videoThumbnail.trim();
    }
    return state.videoPath.trim();
  }
  if (state.imagePaths.isEmpty) {
    return '';
  }
  return state.imagePaths.first;
}

String buildArticleMarkdownForPayload(CreateEditorState state) {
  final cover = coverAssetPathForPayload(state);
  final summary = state.settings.summary.trim().isNotEmpty
      ? state.settings.summary.trim()
      : articleSummaryForPayload(state);
  final entityRefs = entityRefsForPayload(state);
  final tagRefs = tagRefsForPayload(state);
  return ArticleMarkdownCodec.serializeDocument(
    state.articleDocument,
    summary: summary,
    tagRefs: tagRefs,
    entityRefs: entityRefs,
    visibility: state.settings.isPublic ? 'public' : 'private',
    assistantUsePolicy: state.settings.assistantUsePolicy.trim().isNotEmpty
        ? state.settings.assistantUsePolicy.trim()
        : 'inherit',
    coverAssetId: cover.trim().isNotEmpty ? 'cover' : '',
    coverImageUrl: cover,
  );
}

List<String> entityRefsForPayload(CreateEditorState state) {
  final refs = <String>{
    ...state.settings.entityRefs
        .map((ref) => ref.trim())
        .where((ref) => ref.isNotEmpty),
  };
  final homepage = state.settings.homepage;
  if (homepage != null) {
    final ref = homepageEntityRef(homepage);
    if (ref.isNotEmpty) refs.add(ref);
  }
  for (final node in state.articleDocument.nodes) {
    for (final span in node.spans) {
      if (!span.isEntity) continue;
      final id = span.targetId?.trim() ?? '';
      if (id.startsWith('entity:') && id.isNotEmpty) {
        refs.add(id);
      }
    }
  }
  return refs.toList(growable: false);
}

/// 与 [entityRefsForPayload] 对称：合并发布设置里的 tagRefs 与正文 inline tag
/// mention（剥离 `tag:` 前缀，对齐 front matter `tag_refs` 不带前缀的格式），
/// 去重后投影为 active tagRefs。只采纳正文里已存在的 `@[label](tag:ref)`，
/// 不在创作端自造 tag 候选。
List<String> tagRefsForPayload(CreateEditorState state) {
  final refs = <String>{
    ...state.settings.tagRefs
        .map((ref) => ref.trim())
        .where((ref) => ref.isNotEmpty),
  };
  for (final node in state.articleDocument.nodes) {
    for (final span in node.spans) {
      if (!span.isTag) continue;
      final id = span.targetId?.trim() ?? '';
      if (!id.startsWith('tag:')) continue;
      final ref = id.substring('tag:'.length).trim();
      if (ref.isNotEmpty) {
        refs.add(ref);
      }
    }
  }
  return refs.toList(growable: false);
}

/// 发布侧 grounding 真相源（R-CS06）：把正文 entity / tag 内联 + 发布设置里的
/// active refs 投影为结构化 `semanticMentions` 行 `{kind,status:published,targetRef}`。
///
/// 服务端 `semantic.Project`（content-service domain/post/semantic）把 `status=published`
/// 且 `targetRef` 合法的 mention 投影为只读 `post.entityRefs/tagRefs`；本函数与
/// [entityRefsForPayload]/[tagRefsForPayload] 同源（同一去重 ref 集），保证服务端投影
/// 结果 == 端侧 active refs == 文章 front matter 的 entity_refs/tag_refs，三者一致。
///
/// targetRef 形态：entity 用完整 `entity:`/`homepage_` id；tag 用层级 bare ref（去 `tag:`
/// 前缀，与全应用 tagRef 口径一致）。[isSemanticTargetRefValid] 防御性过滤畸形 ref，
/// 避免单个非法内联触发服务端整篇发布拒绝。
List<Map<String, dynamic>> semanticMentionsForPayload(CreateEditorState state) {
  final rows = <Map<String, dynamic>>[];
  final seen = <String>{};
  void addRow(String kind, String rawRef) {
    final ref = rawRef.trim();
    if (ref.isEmpty || !isSemanticTargetRefValid(kind, ref)) {
      return;
    }
    if (!seen.add('$kind|$ref')) {
      return;
    }
    rows.add(<String, dynamic>{
      'kind': kind,
      'status': 'published',
      'targetRef': ref,
    });
  }

  for (final ref in entityRefsForPayload(state)) {
    addRow('entity', ref);
  }
  for (final ref in tagRefsForPayload(state)) {
    addRow('tag', ref);
  }
  return rows;
}

/// 防御性镜像服务端 `semantic.ValidTargetRef`（唯一权威：
/// `quwoquan_service/services/content-service/internal/domain/post/semantic/mentions.go`）。
/// 仅用于发布前过滤必然非法 / candidate 的 targetRef；服务端仍为最终校验权威。
bool isSemanticTargetRefValid(String kind, String ref) {
  final value = ref.trim();
  if (value.isEmpty || value.toLowerCase().contains('candidate')) {
    return false;
  }
  if (value.contains('\n') || value.contains('\r') || value.contains('\t')) {
    return false;
  }
  int nonEmptyParts(List<String> parts) =>
      parts.where((part) => part.trim().isNotEmpty).length;
  switch (kind) {
    case 'entity':
      if (value.startsWith('entity:')) {
        return nonEmptyParts(value.split(':')) >= 3;
      }
      if (value.startsWith('/entity/') || value.startsWith('entity/')) {
        final trimmed = value.startsWith('/') ? value.substring(1) : value;
        return nonEmptyParts(trimmed.split('/')) >= 4;
      }
      return value.startsWith('homepage_');
    case 'tag':
      if (value.startsWith('tag:')) {
        return nonEmptyParts(value.split(':')) >= 2;
      }
      if (value.startsWith('/tag/')) {
        return nonEmptyParts(value.substring('/tag/'.length).split('/')) >= 2;
      }
      if (value.startsWith('tag/')) {
        return nonEmptyParts(value.substring('tag/'.length).split('/')) >= 2;
      }
      return nonEmptyParts(value.split('/')) >= 2;
    default:
      return false;
  }
}

Map<String, dynamic> buildArticleAssetManifestForPayload(
  CreateEditorState state,
) {
  final assets = <Map<String, Object?>>[];
  final cover = coverAssetPathForPayload(state);
  if (cover.trim().isNotEmpty) {
    assets.add(_assetManifestRow('cover', cover.trim(), role: 'cover'));
  }
  for (final asset in state.articleDocument.assets) {
    final imagePath = asset.imageUrl.trim();
    if (imagePath.isEmpty) {
      continue;
    }
    final assetId = asset.id.trim().isNotEmpty
        ? asset.id.trim()
        : _assetIdForPath(imagePath, 'inline');
    assets.add(_assetManifestRow(assetId, imagePath, role: 'figure'));
  }
  return <String, dynamic>{
    'schema': 'article-asset-manifest',
    'markdownVersion': qwqRichMarkdownVersion,
    'assets': assets,
  };
}

Map<String, dynamic> buildArticleRenderProfileForPayload(
  CreateEditorState state,
) {
  return <String, dynamic>{
    'template': state.articleTemplate.name,
    'fontPreset': state.articleFontPreset.name,
    'layoutPolicy': <String, Object?>{
      'wrapDowngrade': 'compactWidthToFullWidth',
      'galleryDowngrade': 'singleColumn',
    },
  };
}

String _assetIdForPath(String path, String prefix) {
  final normalized = path.trim().replaceAll(RegExp(r'[^A-Za-z0-9]+'), '_');
  final suffix = normalized.length > 40
      ? normalized.substring(normalized.length - 40)
      : normalized;
  return '${prefix}_${suffix.isEmpty ? 'asset' : suffix}';
}

Map<String, Object?> _assetManifestRow(
  String assetId,
  String path, {
  required String role,
}) {
  return <String, Object?>{
    'assetId': assetId,
    'kind': 'image',
    'role': role,
    'scope': 'draft',
    'variantGeneration': <String, Object?>{
      'required': true,
      'profiles': <String>['thumbnail', 'display', 'cover', 'full', 'original'],
      'source': 'server',
    },
    'localPath': path,
    'objectKey': path.startsWith('asset://')
        ? path.substring('asset://'.length)
        : path,
    'sha256': '',
  };
}

/// 创作编辑器到原子发布命令的唯一 payload 出口。
Map<String, Object?> buildPostPublicationPayloadMap(CreateEditorState state) {
  final settings = state.settings.toPayloadFields();
  final summary = state.settings.summary.trim().isNotEmpty
      ? state.settings.summary.trim()
      : articleSummaryForPayload(state);
  final entityRefs = entityRefsForPayload(state);
  if (entityRefs.isNotEmpty) {
    settings['entityRefs'] = entityRefs;
  }
  final tagRefs = tagRefsForPayload(state);
  if (tagRefs.isNotEmpty) {
    settings['tagRefs'] = tagRefs;
  }
  // R-CS06：发布唯一可写 grounding 字段。顶层 tagRefs/entityRefs 是只读投影，会被
  // wire writable_fields 剥离；entity/tag 内联只有经 semanticMentions 才落服务端 refs。
  final semanticMentions = semanticMentionsForPayload(state);
  if (semanticMentions.isNotEmpty) {
    settings['semanticMentions'] = semanticMentions;
  }
  final coverAssetPath = coverAssetPathForPayload(state);
  if (state.editorKind == CreateEditorKind.media) {
    if (state.hasVideo) {
      final videoPath = state.videoPath.trim();
      final thumbnailUrl = state.videoThumbnail.trim();
      final coverUrl = thumbnailUrl.isNotEmpty ? thumbnailUrl : coverAssetPath;
      final coverStrategy = _videoCoverStrategyForPayload(state);
      return <String, Object?>{
        'contentType': 'video',
        'title': state.title.trim(),
        'body': state.body.trim(),
        if (summary.isNotEmpty) 'summary': summary,
        'videoUrl': videoPath,
        'mediaUrls': <String>[videoPath],
        'mediaItems': <Map<String, Object?>>[
          <String, Object?>{
            'kind': 'video',
            'url': videoPath,
            if (thumbnailUrl.isNotEmpty) 'thumbnailUrl': thumbnailUrl,
            if (coverUrl.isNotEmpty) 'coverUrl': coverUrl,
            'coverStrategy': coverStrategy,
            'coverFrameTimeMs': state.videoCoverTimeMs,
            if (state.videoDurationMs > 0) 'durationMs': state.videoDurationMs,
            if (state.videoWidth > 0) 'width': state.videoWidth,
            if (state.videoHeight > 0) 'height': state.videoHeight,
          },
        ],
        if (coverUrl.isNotEmpty) 'coverUrl': coverUrl,
        if (thumbnailUrl.isNotEmpty) 'thumbnailUrl': thumbnailUrl,
        'coverStrategy': coverStrategy,
        'coverFrameTimeMs': state.videoCoverTimeMs,
        if (state.videoDurationMs > 0) 'durationMs': state.videoDurationMs,
        if (state.videoWidth > 0) 'width': state.videoWidth,
        if (state.videoHeight > 0) 'height': state.videoHeight,
        'deviceInfo': <String, Object?>{
          if (state.videoDurationMs > 0) 'durationMs': state.videoDurationMs,
          if (state.videoWidth > 0) 'width': state.videoWidth,
          if (state.videoHeight > 0) 'height': state.videoHeight,
          if (state.videoTrimStartMs > 0) 'trimStartMs': state.videoTrimStartMs,
          if (state.videoTrimEndMs > 0) 'trimEndMs': state.videoTrimEndMs,
          'coverFrameTimeMs': state.videoCoverTimeMs,
          'muted': state.videoMuted,
        },
        ...settings,
      };
    }
    return <String, Object?>{
      'contentType': 'image',
      'title': state.title.trim(),
      'body': state.body.trim(),
      if (summary.isNotEmpty) 'summary': summary,
      'mediaUrls': state.imagePaths,
      'coverUrl': coverAssetPath,
      ...settings,
    };
  }
  final asArticle = shouldPublishAsArticleForPayload(state);
  if (asArticle) {
    return <String, Object?>{
      'contentType': 'article',
      'title': state.title.trim(),
      'summary': summary,
      'coverUrl': coverAssetPath,
      'articleMarkdown': buildArticleMarkdownForPayload(state),
      'markdownDialect': qwqRichMarkdownVersion,
      'articleAssetManifest': buildArticleAssetManifestForPayload(state),
      'articleRenderProfile': buildArticleRenderProfileForPayload(state),
      ...settings,
    };
  }
  return <String, Object?>{
    'contentType': 'micro',
    'title': state.title.trim(),
    'body': state.body.trim(),
    if (summary.isNotEmpty) 'summary': summary,
    'mediaUrls': state.imagePaths,
    'coverUrl': coverAssetPath,
    ...settings,
  };
}

typedef PostMediaUploadProgressCallback = void Function(double progress);

class PreparedPostPublicationPayload {
  const PreparedPostPublicationPayload({
    required this.payload,
    required this.mediaAssetIds,
  });

  final Map<String, Object?> payload;
  final List<String> mediaAssetIds;
}

/// 返回首次点击发布时可持久化的媒体准备意图。
///
/// 本地路径仅属于草稿和本次流式读取，不能进入持久发布命令；MediaAsset 尚未产生时，
/// 队列只记录不可变发布身份和非交付展示元数据，并在上传完成后原子替换为最终命令。
PreparedPostPublicationPayload buildPostPublicationMediaPreparationPayload(
  CreateEditorState state,
) {
  final payload =
      Map<String, Object?>.from(buildPostPublicationPayloadMap(state))
        ..remove('mediaUrls')
        ..remove('videoUrl')
        ..remove('coverUrl')
        ..remove('thumbnailUrl')
        ..remove('mediaItems');
  return PreparedPostPublicationPayload(
    payload: payload,
    mediaAssetIds: const <String>[],
  );
}

Future<PreparedPostPublicationPayload>
buildPostPublicationPayloadWithRemoteMedia({
  required ContentMediaFacet media,
  required CreateEditorState state,
  required ContentMediaSourceReader sourceReader,
  required ContentMediaStreamObjectUpload uploadStream,
  AppTelemetryRecorder? telemetry,
  PostMediaUploadProgressCallback? onUploadProgress,
  ContentMediaUploadCancellationSignal? cancellationSignal,
  String? mediaPreparationIdentity,
  Iterable<ContentMediaPreparationCheckpoint> preparedMediaAssets =
      const <ContentMediaPreparationCheckpoint>[],
  Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)?
  onMediaPrepared,
}) async {
  final preparedAssetsBySlot = <String, ContentMediaPreparationCheckpoint>{
    for (final checkpoint in preparedMediaAssets) checkpoint.slot: checkpoint,
  };
  final preparationIdentity =
      mediaPreparationIdentity?.trim().isNotEmpty == true
      ? mediaPreparationIdentity!.trim()
      : state.draftId?.trim() ?? '';
  if (preparationIdentity.isEmpty &&
      state.editorKind == CreateEditorKind.media) {
    throw StateError('media publication requires a durable draft identity');
  }
  final basePayload = Map<String, Object?>.from(
    buildPostPublicationPayloadMap(state),
  );
  if (state.editorKind != CreateEditorKind.media) {
    return PreparedPostPublicationPayload(
      payload: basePayload,
      mediaAssetIds: const <String>[],
    );
  }
  // 上传服务的 cdnUrl 只用于本次上传协议，绝不能进入 Post 写入 payload。
  // 发布时由 SubmitPostPublication 原子绑定并投影 canonical publicSliceKey。
  basePayload
    ..remove('mediaUrls')
    ..remove('videoUrl')
    ..remove('coverUrl')
    ..remove('thumbnailUrl')
    ..remove('mediaItems');
  if (state.hasVideo) {
    return _buildPostPublicationPayloadWithRemoteVideoMedia(
      media: media,
      state: state,
      basePayload: basePayload,
      sourceReader: sourceReader,
      uploadStream: uploadStream,
      telemetry: telemetry,
      onUploadProgress: onUploadProgress,
      cancellationSignal: cancellationSignal,
      preparationIdentity: preparationIdentity,
      preparedAssetsBySlot: preparedAssetsBySlot,
      onMediaPrepared: onMediaPrepared,
    );
  }
  if (state.imagePaths.isEmpty) {
    return PreparedPostPublicationPayload(
      payload: basePayload,
      mediaAssetIds: const <String>[],
    );
  }

  final assetIds = <String>[];
  for (var index = 0; index < state.imagePaths.length; index++) {
    final path = state.imagePaths[index];
    final resolved = await _resolveMediaReference(
      media: media,
      localOrRemotePath: path,
      mediaType: ContentMediaType.image,
      sourceReader: sourceReader,
      uploadStream: uploadStream,
      telemetry: telemetry,
      onProgress: (uploadedBytes, totalBytes) {
        final itemProgress = totalBytes == 0 ? 0 : uploadedBytes / totalBytes;
        onUploadProgress?.call(
          (index + itemProgress) / state.imagePaths.length,
        );
      },
      cancellationSignal: cancellationSignal,
      preparationIdentity: preparationIdentity,
      slot: 'image:$index',
      preparedAssetsBySlot: preparedAssetsBySlot,
      onMediaPrepared: onMediaPrepared,
    );
    if (resolved.assetId.isNotEmpty) {
      assetIds.add(resolved.assetId);
    }
  }
  if (assetIds.isEmpty) {
    throw StateError('image publish requires uploaded media asset ids');
  }
  return PreparedPostPublicationPayload(
    payload: basePayload,
    mediaAssetIds: assetIds,
  );
}

Future<PreparedPostPublicationPayload>
_buildPostPublicationPayloadWithRemoteVideoMedia({
  required ContentMediaFacet media,
  required CreateEditorState state,
  required Map<String, Object?> basePayload,
  required ContentMediaSourceReader sourceReader,
  required ContentMediaStreamObjectUpload uploadStream,
  AppTelemetryRecorder? telemetry,
  PostMediaUploadProgressCallback? onUploadProgress,
  ContentMediaUploadCancellationSignal? cancellationSignal,
  required String preparationIdentity,
  required Map<String, ContentMediaPreparationCheckpoint> preparedAssetsBySlot,
  Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)?
  onMediaPrepared,
}) async {
  final itemCount = state.videoThumbnail.trim().isEmpty ? 1 : 2;
  final video = await _resolveMediaReference(
    media: media,
    localOrRemotePath: state.videoPath,
    mediaType: ContentMediaType.video,
    sourceReader: sourceReader,
    uploadStream: uploadStream,
    telemetry: telemetry,
    onProgress: (uploadedBytes, totalBytes) {
      final itemProgress = totalBytes == 0 ? 0 : uploadedBytes / totalBytes;
      onUploadProgress?.call(itemProgress / itemCount);
    },
    cancellationSignal: cancellationSignal,
    preparationIdentity: preparationIdentity,
    slot: 'video:0',
    preparedAssetsBySlot: preparedAssetsBySlot,
    onMediaPrepared: onMediaPrepared,
  );
  if (video.assetId.isEmpty) {
    throw StateError('video publish requires an uploaded MediaAsset id');
  }
  final assetIds = <String>[if (video.assetId.isNotEmpty) video.assetId];

  final cover = await _resolveRemoteVideoCover(
    media: media,
    localOrRemoteCoverPath: state.videoThumbnail,
    sourceReader: sourceReader,
    uploadStream: uploadStream,
    telemetry: telemetry,
    onProgress: (uploadedBytes, totalBytes) {
      final itemProgress = totalBytes == 0 ? 0 : uploadedBytes / totalBytes;
      onUploadProgress?.call((1 + itemProgress) / itemCount);
    },
    cancellationSignal: cancellationSignal,
    preparationIdentity: preparationIdentity,
    preparedAssetsBySlot: preparedAssetsBySlot,
    onMediaPrepared: onMediaPrepared,
  );
  if (cover.assetId.isNotEmpty) {
    assetIds.add(cover.assetId);
  }
  final selectedCover = cover.assetId.isNotEmpty
      ? await media.selectManualCover(
          SelectManualContentMediaCoverCommand(
            mediaId: video.assetId,
            coverAssetId: cover.assetId,
          ),
        )
      : await media.selectAutoCover(
          SelectAutoContentMediaCoverCommand(mediaId: video.assetId),
        );

  basePayload['coverStrategy'] = selectedCover.coverStrategy;
  basePayload['coverFrameTimeMs'] = state.videoCoverTimeMs;
  if (state.videoDurationMs > 0) {
    basePayload['durationMs'] = state.videoDurationMs;
  }
  if (state.videoWidth > 0) {
    basePayload['width'] = state.videoWidth;
  }
  if (state.videoHeight > 0) {
    basePayload['height'] = state.videoHeight;
  }
  return PreparedPostPublicationPayload(
    payload: basePayload,
    mediaAssetIds: assetIds,
  );
}

class _ResolvedMediaReference {
  const _ResolvedMediaReference({this.assetId = ''});

  final String assetId;
}

class _ResolvedVideoCoverReference {
  const _ResolvedVideoCoverReference({this.assetId = ''});

  final String assetId;
}

Future<_ResolvedMediaReference> _resolveMediaReference({
  required ContentMediaFacet media,
  required String localOrRemotePath,
  required ContentMediaType mediaType,
  required ContentMediaSourceReader sourceReader,
  required ContentMediaStreamObjectUpload uploadStream,
  AppTelemetryRecorder? telemetry,
  ContentMediaUploadProgressCallback? onProgress,
  ContentMediaUploadCancellationSignal? cancellationSignal,
  required String preparationIdentity,
  required String slot,
  required Map<String, ContentMediaPreparationCheckpoint> preparedAssetsBySlot,
  Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)?
  onMediaPrepared,
}) async {
  cancellationSignal?.throwIfCancelled();
  final path = localOrRemotePath.trim();
  if (path.isEmpty) {
    throw StateError('empty media path');
  }
  if (_isRemoteMediaReference(path)) {
    final assetId = _mediaAssetIdFromReference(path);
    if (assetId.isEmpty) {
      throw StateError(
        'media publish requires a MediaAsset reference, not a delivery URL',
      );
    }
    onProgress?.call(1, 1);
    return _ResolvedMediaReference(assetId: assetId);
  }
  final coordinator = ContentMediaUploadCoordinator(
    media: media,
    telemetry: telemetry,
  );
  final source = await sourceReader.prepare(path);
  cancellationSignal?.throwIfCancelled();
  final checkpoint = preparedAssetsBySlot[slot];
  if (checkpoint != null &&
      checkpoint.matches(
        expectedSlot: slot,
        expectedMediaType: mediaType,
        expectedSha256Digest: source.sha256Digest,
      ) &&
      checkpoint.isCompleted) {
    onProgress?.call(source.fileSize, source.fileSize);
    return _ResolvedMediaReference(assetId: checkpoint.assetId);
  }
  final durableCheckpoint =
      checkpoint != null &&
          checkpoint.matches(
            expectedSlot: slot,
            expectedMediaType: mediaType,
            expectedSha256Digest: source.sha256Digest,
          )
      ? checkpoint
      : ContentMediaPreparationCheckpoint.forSource(
          preparationIdentity: preparationIdentity,
          slot: slot,
          mediaType: mediaType,
          sha256Digest: source.sha256Digest,
        );
  if (checkpoint == null || !identical(checkpoint, durableCheckpoint)) {
    await onMediaPrepared?.call(durableCheckpoint);
    preparedAssetsBySlot[slot] = durableCheckpoint;
  }
  final uploaded = await coordinator.uploadPreparedSource(
    source: source,
    mediaType: mediaType,
    contentType: contentMediaTypeForPath(path, mediaType),
    uploadStream: uploadStream,
    onProgress: onProgress,
    cancellationSignal: cancellationSignal,
    checkpoint: durableCheckpoint,
    onCheckpoint: (updated) async {
      await onMediaPrepared?.call(updated);
      preparedAssetsBySlot[slot] = updated;
    },
  );
  final assetId = uploaded.assetId.trim();
  if (assetId.isEmpty) {
    throw StateError('uploaded media is missing its MediaAsset id');
  }
  final prepared = durableCheckpoint.copyWith(
    sessionId: uploaded.sessionId,
    assetId: assetId,
    phase: ContentMediaPreparationPhase.completed,
  );
  await onMediaPrepared?.call(prepared);
  preparedAssetsBySlot[slot] = prepared;
  return _ResolvedMediaReference(assetId: assetId);
}

Future<_ResolvedVideoCoverReference> _resolveRemoteVideoCover({
  required ContentMediaFacet media,
  required String localOrRemoteCoverPath,
  required ContentMediaSourceReader sourceReader,
  required ContentMediaStreamObjectUpload uploadStream,
  AppTelemetryRecorder? telemetry,
  ContentMediaUploadProgressCallback? onProgress,
  ContentMediaUploadCancellationSignal? cancellationSignal,
  required String preparationIdentity,
  required Map<String, ContentMediaPreparationCheckpoint> preparedAssetsBySlot,
  Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)?
  onMediaPrepared,
}) async {
  cancellationSignal?.throwIfCancelled();
  final coverPath = localOrRemoteCoverPath.trim();
  if (coverPath.isNotEmpty) {
    final cover = await _resolveMediaReference(
      media: media,
      localOrRemotePath: coverPath,
      mediaType: ContentMediaType.image,
      sourceReader: sourceReader,
      uploadStream: uploadStream,
      telemetry: telemetry,
      onProgress: onProgress,
      cancellationSignal: cancellationSignal,
      preparationIdentity: preparationIdentity,
      slot: 'cover:0',
      preparedAssetsBySlot: preparedAssetsBySlot,
      onMediaPrepared: onMediaPrepared,
    );
    return _ResolvedVideoCoverReference(assetId: cover.assetId);
  }

  onProgress?.call(1, 1);
  return const _ResolvedVideoCoverReference();
}

bool _isRemoteMediaReference(String value) {
  final lower = value.toLowerCase();
  return lower.startsWith('http://') ||
      lower.startsWith('https://') ||
      lower.startsWith('media://') ||
      lower.startsWith('asset://');
}

String _mediaAssetIdFromReference(String value) {
  final source = value.trim();
  if (source.startsWith('media://')) {
    return source.substring('media://'.length).trim();
  }
  if (source.startsWith('asset://')) {
    return source.substring('asset://'.length).trim();
  }
  return '';
}

String _videoCoverStrategyForPayload(CreateEditorState state) {
  final strategy = state.videoCoverStrategy.trim();
  if (strategy == 'manual') {
    return 'manual';
  }
  return state.videoCoverTimeMs > 0 ? 'manual' : 'first_frame';
}

List<CreateDraft> decodeCreateDraftsList(Object? decoded) {
  if (decoded is! List) {
    return const <CreateDraft>[];
  }
  return decoded
      .whereType<Map>()
      .map(
        (entry) => CreateDraft.fromStorageMap(Map<String, dynamic>.from(entry)),
      )
      .toList(growable: false);
}

SubmitContentPostPublicationCommand
submitContentPostPublicationCommandFromPreparedPayload(
  Map<String, Object?> payload, {
  required String localDraftId,
  required Iterable<String> mediaAssetIds,
  String? authorDisplayNameSnapshot,
  String? authorAvatarUrlSnapshot,
  int? personaContextVersion,
}) => SubmitContentPostPublicationCommand(
  publishIntentId: postPublicationIntentIdForLocalDraft(localDraftId),
  localDraftId: localDraftId,
  contentType: _requiredPostType(payload['contentType']),
  contentIdentity: _optionalPostIdentity(payload['contentIdentity']),
  title: _optionalPayloadText(payload['title']),
  body: _optionalPayloadText(payload['body']),
  summary: _optionalPayloadText(payload['summary']),
  semanticMentions: _structuredObjectList(
    payload['semanticMentions'],
    'semanticMentions',
  ),
  mediaAssetIds: mediaAssetIds,
  mediaItems: _structuredObjectList(payload['mediaItems'], 'mediaItems'),
  articleMarkdown: _optionalPayloadText(payload['articleMarkdown']),
  markdownDialect: _optionalPayloadText(payload['markdownDialect']),
  articleAssetManifest: _optionalStructuredObject(
    payload['articleAssetManifest'],
    'articleAssetManifest',
  ),
  articleRenderProfile: _optionalStructuredObject(
    payload['articleRenderProfile'],
    'articleRenderProfile',
  ),
  coverStrategy: _optionalPayloadText(payload['coverStrategy']),
  coverFrameTimeMs: _optionalPayloadInt(
    payload['coverFrameTimeMs'],
    'coverFrameTimeMs',
  ),
  illustrationAssetId: _optionalPayloadText(payload['illustrationAssetId']),
  location: _optionalStructuredObject(payload['location'], 'location'),
  locationName: _optionalPayloadText(payload['locationName']),
  primaryHomepageId: _optionalPayloadText(payload['primaryHomepageId']),
  primaryHomepageType: _optionalPayloadText(payload['primaryHomepageType']),
  primaryHomepageSnapshot: _optionalStructuredObject(
    payload['primaryHomepageSnapshot'],
    'primaryHomepageSnapshot',
  ),
  visibility: _optionalPostVisibility(payload['visibility']),
  assistantUsePolicy: _optionalAssistantUsePolicy(
    payload['assistantUsePolicy'],
  ),
  sourcePostId: _optionalPayloadText(payload['sourcePostId']),
  sourceType: _optionalPostSourceType(payload['sourceType']),
  deviceInfo: _optionalStructuredObject(payload['deviceInfo'], 'deviceInfo'),
  publishLocation: _optionalStructuredObject(
    payload['publishLocation'],
    'publishLocation',
  ),
  authorDisplayNameSnapshot: _optionalPayloadText(authorDisplayNameSnapshot),
  authorAvatarUrlSnapshot: _optionalPayloadText(authorAvatarUrlSnapshot),
  personaContextVersion: personaContextVersion,
);

// ─── 创作页埋点 extras（避免在 UI 散写 Map 字面量）────────────────────────────

Map<String, Object?> createEditorSurfaceExtrasEditorKind(
  CreateEditorKind kind,
) => <String, Object?>{'editorKind': kind.name};

Map<String, Object?> createEditorSurfaceExtrasReady({
  required CreateEditorKind editorKind,
  required bool unifiedCreateEditorEnabled,
}) => <String, Object?>{
  'editorKind': editorKind.name,
  'flag': unifiedCreateEditorEnabled,
};

Map<String, Object?> createEditorSurfaceExtrasMediaBatch({
  required int count,
  required CreateEditorKind editorKind,
}) => <String, Object?>{'count': count, 'editorKind': editorKind.name};

Map<String, Object?> createEditorSurfaceExtrasVideoEdited({
  required bool muted,
  required int trimStartMs,
  required int trimEndMs,
}) => <String, Object?>{
  'muted': muted,
  'trimStartMs': trimStartMs,
  'trimEndMs': trimEndMs,
};

/// 与 [buildPostPublicationPayloadMap] 写入的 `contentType` 一致，供发布成功打点使用。
Map<String, Object?> createEditorSurfaceExtrasPublishSuccess(
  Map<String, Object?> payload,
) => <String, Object?>{'contentType': payload['contentType']};

ContentPostType _requiredPostType(Object? raw) => switch ('$raw'.trim()) {
  'image' => ContentPostType.image,
  'video' => ContentPostType.video,
  'micro' => ContentPostType.micro,
  'article' => ContentPostType.article,
  final value => throw ArgumentError.value(value, 'contentType', 'unsupported'),
};

ContentPostIdentity? _optionalPostIdentity(Object? raw) =>
    switch (_optionalPayloadText(raw)) {
      null => null,
      'moment' => ContentPostIdentity.moment,
      'work' => ContentPostIdentity.work,
      final value => throw ArgumentError.value(
        value,
        'contentIdentity',
        'unsupported',
      ),
    };

ContentPostVisibility? _optionalPostVisibility(Object? raw) =>
    switch (_optionalPayloadText(raw)) {
      null => null,
      'public' => ContentPostVisibility.public,
      'private' => ContentPostVisibility.private,
      final value => throw ArgumentError.value(
        value,
        'visibility',
        'unsupported',
      ),
    };

ContentPostAssistantUsePolicy? _optionalAssistantUsePolicy(Object? raw) =>
    switch (_optionalPayloadText(raw)) {
      null => null,
      'inherit' => ContentPostAssistantUsePolicy.inherit,
      'exclude' => ContentPostAssistantUsePolicy.exclude,
      final value => throw ArgumentError.value(
        value,
        'assistantUsePolicy',
        'unsupported',
      ),
    };

ContentPostSourceType? _optionalPostSourceType(Object? raw) =>
    switch (_optionalPayloadText(raw)) {
      null => null,
      'original' => ContentPostSourceType.original,
      'repost' => ContentPostSourceType.repost,
      'quote' => ContentPostSourceType.quote,
      final value => throw ArgumentError.value(
        value,
        'sourceType',
        'unsupported',
      ),
    };

String? _optionalPayloadText(Object? raw) {
  final value = raw?.toString().trim() ?? '';
  return value.isEmpty ? null : value;
}

int? _optionalPayloadInt(Object? raw, String field) {
  if (raw == null) return null;
  if (raw is int) return raw;
  final parsed = int.tryParse('$raw');
  if (parsed == null) {
    throw ArgumentError.value(raw, field, 'must be an integer');
  }
  return parsed;
}

List<ContentPostStructuredObject> _structuredObjectList(
  Object? raw,
  String field,
) {
  if (raw == null) return const <ContentPostStructuredObject>[];
  if (raw is! List) throw ArgumentError.value(raw, field, 'must be a list');
  return raw
      .map((value) => _requiredStructuredObject(value, field))
      .toList(growable: false);
}

ContentPostStructuredObject? _optionalStructuredObject(
  Object? raw,
  String field,
) => raw == null ? null : _requiredStructuredObject(raw, field);

ContentPostStructuredObject _requiredStructuredObject(
  Object? raw,
  String field,
) {
  final value = _structuredValue(raw, field);
  if (value is! ContentPostStructuredObject) {
    throw ArgumentError.value(raw, field, 'must be an object');
  }
  return value;
}

ContentPostStructuredValue _structuredValue(Object? raw, String field) {
  if (raw == null) return const ContentPostStructuredNull();
  if (raw is String) return ContentPostStructuredText(raw);
  if (raw is num) return ContentPostStructuredNumber(raw);
  if (raw is bool) return ContentPostStructuredBoolean(raw);
  if (raw is List) {
    return ContentPostStructuredArray(
      raw.map((value) => _structuredValue(value, field)),
    );
  }
  if (raw is Map) {
    return ContentPostStructuredObject(<String, ContentPostStructuredValue>{
      for (final entry in raw.entries)
        entry.key.toString(): _structuredValue(entry.value, field),
    });
  }
  throw ArgumentError.value(raw, field, 'unsupported structured value');
}
