import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/markdown/qwq_markdown.dart';

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
    'schemaVersion': 1,
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

/// 创作编辑器 → 云端发帖的**唯一 wire 出口**：先 [buildCreatePostPayloadMap]，
/// 再 [attachActivePersonaToCreatePayload]，最后 [repositoryCreatePost] 内 [CreatePostRequestWire.fromMap]。
Map<String, Object?> buildCreatePostPayloadMap(CreateEditorState state) {
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
        'type': 'video',
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
      'type': 'image',
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
      'type': 'article',
      'contentType': 'article',
      'title': state.title.trim(),
      'summary': summary,
      'coverUrl': coverAssetPath,
      'articleMarkdown': buildArticleMarkdownForPayload(state),
      'articleMarkdownVersion': qwqRichMarkdownVersion,
      'articleAssetManifest': buildArticleAssetManifestForPayload(state),
      'articleRenderProfile': buildArticleRenderProfileForPayload(state),
      ...settings,
    };
  }
  return <String, Object?>{
    'type': 'micro',
    'contentType': 'micro',
    'title': state.title.trim(),
    'body': state.body.trim(),
    if (summary.isNotEmpty) 'summary': summary,
    'mediaUrls': state.imagePaths,
    'coverUrl': coverAssetPath,
    ...settings,
  };
}

typedef CreateMediaObjectUploader =
    Future<void> Function(
      Uri uploadUri,
      List<int> bytes, {
      required String contentType,
    });

class PreparedCreatePostPayload {
  const PreparedCreatePostPayload({
    required this.payload,
    required this.mediaAssetIds,
  });

  final Map<String, Object?> payload;
  final List<String> mediaAssetIds;
}

Future<PreparedCreatePostPayload> buildCreatePostPayloadWithRemoteImageMedia({
  required ContentRepository repository,
  required FileStorageGateway fileStorageGateway,
  required CreateEditorState state,
  CreateMediaObjectUploader? uploadObject,
}) async {
  final basePayload = Map<String, Object?>.from(
    buildCreatePostPayloadMap(state),
  );
  if (state.editorKind != CreateEditorKind.media) {
    return PreparedCreatePostPayload(
      payload: basePayload,
      mediaAssetIds: const <String>[],
    );
  }
  if (state.hasVideo) {
    return _buildCreatePostPayloadWithRemoteVideoMedia(
      repository: repository,
      fileStorageGateway: fileStorageGateway,
      state: state,
      basePayload: basePayload,
      uploadObject: uploadObject ?? _defaultUploadMediaObject,
    );
  }
  if (state.imagePaths.isEmpty) {
    return PreparedCreatePostPayload(
      payload: basePayload,
      mediaAssetIds: const <String>[],
    );
  }

  final uploader = uploadObject ?? _defaultUploadMediaObject;
  final remoteUrls = <String>[];
  final assetIds = <String>[];
  for (final path in state.imagePaths) {
    final resolved = await _resolveMediaReference(
      repository: repository,
      fileStorageGateway: fileStorageGateway,
      localOrRemotePath: path,
      mediaType: 'image',
      uploadObject: uploader,
    );
    remoteUrls.add(resolved.url);
    if (resolved.assetId.isNotEmpty) {
      assetIds.add(resolved.assetId);
    }
  }
  basePayload['mediaUrls'] = remoteUrls;
  basePayload['coverUrl'] = remoteUrls.first;
  return PreparedCreatePostPayload(
    payload: basePayload,
    mediaAssetIds: assetIds,
  );
}

Future<PreparedCreatePostPayload> _buildCreatePostPayloadWithRemoteVideoMedia({
  required ContentRepository repository,
  required FileStorageGateway fileStorageGateway,
  required CreateEditorState state,
  required Map<String, Object?> basePayload,
  required CreateMediaObjectUploader uploadObject,
}) async {
  final video = await _resolveMediaReference(
    repository: repository,
    fileStorageGateway: fileStorageGateway,
    localOrRemotePath: state.videoPath,
    mediaType: 'video',
    uploadObject: uploadObject,
  );
  final assetIds = <String>[if (video.assetId.isNotEmpty) video.assetId];

  final cover = await _resolveRemoteVideoCover(
    repository: repository,
    fileStorageGateway: fileStorageGateway,
    videoAssetId: video.assetId,
    localOrRemoteCoverPath: state.videoThumbnail,
    coverStrategy: _videoCoverStrategyForPayload(state),
    coverFrameTimeMs: state.videoCoverTimeMs,
    uploadObject: uploadObject,
  );
  if (cover.assetId.isNotEmpty) {
    assetIds.add(cover.assetId);
  }

  basePayload['videoUrl'] = video.url;
  basePayload['mediaUrls'] = <String>[video.url];
  basePayload['thumbnailUrl'] = cover.thumbnailUrl;
  basePayload['coverUrl'] = cover.coverUrl;
  basePayload['coverStrategy'] = cover.coverStrategy;
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
  basePayload['mediaItems'] = <Map<String, Object?>>[
    <String, Object?>{
      'kind': 'video',
      'url': video.url,
      'thumbnailUrl': cover.thumbnailUrl,
      'coverUrl': cover.coverUrl,
      'coverStrategy': cover.coverStrategy,
      'coverFrameTimeMs': state.videoCoverTimeMs,
      if (state.videoDurationMs > 0) 'durationMs': state.videoDurationMs,
      if (state.videoWidth > 0) 'width': state.videoWidth,
      if (state.videoHeight > 0) 'height': state.videoHeight,
      if (video.assetId.isNotEmpty) 'mediaId': video.assetId,
      if (cover.assetId.isNotEmpty) 'coverAssetId': cover.assetId,
    },
  ];

  return PreparedCreatePostPayload(
    payload: basePayload,
    mediaAssetIds: assetIds,
  );
}

class _ResolvedMediaReference {
  const _ResolvedMediaReference({required this.url, this.assetId = ''});

  final String url;
  final String assetId;
}

class _ResolvedVideoCoverReference {
  const _ResolvedVideoCoverReference({
    required this.thumbnailUrl,
    required this.coverUrl,
    required this.coverStrategy,
    this.assetId = '',
  });

  final String thumbnailUrl;
  final String coverUrl;
  final String coverStrategy;
  final String assetId;
}

Future<_ResolvedMediaReference> _resolveMediaReference({
  required ContentRepository repository,
  required FileStorageGateway fileStorageGateway,
  required String localOrRemotePath,
  required String mediaType,
  required CreateMediaObjectUploader uploadObject,
}) async {
  final path = localOrRemotePath.trim();
  if (path.isEmpty) {
    throw StateError('empty media path');
  }
  if (_isRemoteMediaReference(path)) {
    return _ResolvedMediaReference(
      url: path,
      assetId: path.startsWith('media://')
          ? path.substring('media://'.length)
          : '',
    );
  }
  final init = await repository.initMediaUpload(mediaType: mediaType);
  final sessionId = init.sessionId.trim();
  if (sessionId.isEmpty) {
    throw StateError('media upload session is missing');
  }
  try {
    final uploadUrl = (init.presignUrl ?? init.uploadUrl ?? '').trim();
    if (uploadUrl.isNotEmpty) {
      final bytes = await fileStorageGateway.readAsBytes(path);
      await uploadObject(
        Uri.parse(uploadUrl),
        bytes,
        contentType: _contentTypeForMediaPath(path, mediaType),
      );
    }
    final completed = await repository.completeMediaUpload(
      sessionId: sessionId,
    );
    final assetId = (completed.assetId ?? init.mediaId ?? '').trim();
    final cdnUrl = (completed.cdnUrl ?? '').trim();
    final url = cdnUrl.isNotEmpty
        ? cdnUrl
        : assetId.isNotEmpty
        ? 'media://$assetId'
        : '';
    if (url.isEmpty) {
      throw StateError('completed media upload is missing remote url');
    }
    return _ResolvedMediaReference(url: url, assetId: assetId);
  } catch (_) {
    await repository.abortMediaUpload(sessionId: sessionId);
    rethrow;
  }
}

Future<_ResolvedVideoCoverReference> _resolveRemoteVideoCover({
  required ContentRepository repository,
  required FileStorageGateway fileStorageGateway,
  required String videoAssetId,
  required String localOrRemoteCoverPath,
  required String coverStrategy,
  required int coverFrameTimeMs,
  required CreateMediaObjectUploader uploadObject,
}) async {
  final coverPath = localOrRemoteCoverPath.trim();
  if (coverPath.isNotEmpty) {
    final cover = await _resolveMediaReference(
      repository: repository,
      fileStorageGateway: fileStorageGateway,
      localOrRemotePath: coverPath,
      mediaType: 'image',
      uploadObject: uploadObject,
    );
    var thumbnailUrl = cover.url;
    var coverUrl = cover.url;
    var resolvedStrategy = coverStrategy == 'manual' ? 'manual' : 'first_frame';
    if (videoAssetId.isNotEmpty && cover.assetId.isNotEmpty) {
      final selected = await repository.selectManualVideoCover(
        mediaId: videoAssetId,
        coverAssetId: cover.assetId,
        coverFrameTimeMs: coverFrameTimeMs,
      );
      thumbnailUrl = selected.thumbnailUrl.trim().isNotEmpty
          ? selected.thumbnailUrl.trim()
          : thumbnailUrl;
      coverUrl = selected.coverUrl.trim().isNotEmpty
          ? selected.coverUrl.trim()
          : coverUrl;
      resolvedStrategy = selected.coverStrategy.trim().isNotEmpty
          ? selected.coverStrategy.trim()
          : resolvedStrategy;
    }
    return _ResolvedVideoCoverReference(
      thumbnailUrl: thumbnailUrl,
      coverUrl: coverUrl,
      coverStrategy: resolvedStrategy,
      assetId: cover.assetId,
    );
  }

  if (videoAssetId.isEmpty) {
    throw StateError('video cover is missing');
  }
  final selected = await repository.selectAutoVideoCover(mediaId: videoAssetId);
  final thumbnailUrl = selected.thumbnailUrl.trim();
  final coverUrl = selected.coverUrl.trim().isNotEmpty
      ? selected.coverUrl.trim()
      : thumbnailUrl;
  if (thumbnailUrl.isEmpty && coverUrl.isEmpty) {
    throw StateError('video cover selection is missing remote url');
  }
  return _ResolvedVideoCoverReference(
    thumbnailUrl: thumbnailUrl.isNotEmpty ? thumbnailUrl : coverUrl,
    coverUrl: coverUrl,
    coverStrategy: selected.coverStrategy.trim().isNotEmpty
        ? selected.coverStrategy.trim()
        : 'first_frame',
  );
}

bool _isRemoteMediaReference(String value) {
  final lower = value.toLowerCase();
  return lower.startsWith('http://') ||
      lower.startsWith('https://') ||
      lower.startsWith('media://') ||
      lower.startsWith('asset://');
}

String _contentTypeForMediaPath(String path, String mediaType) {
  if (mediaType == 'video') {
    return _videoContentTypeForPath(path);
  }
  return _imageContentTypeForPath(path);
}

String _imageContentTypeForPath(String path) {
  final lower = path.toLowerCase();
  if (lower.endsWith('.png')) {
    return 'image/png';
  }
  if (lower.endsWith('.gif')) {
    return 'image/gif';
  }
  if (lower.endsWith('.webp')) {
    return 'image/webp';
  }
  return 'image/jpeg';
}

String _videoContentTypeForPath(String path) {
  final lower = path.toLowerCase();
  if (lower.endsWith('.mov')) {
    return 'video/quicktime';
  }
  if (lower.endsWith('.m4v')) {
    return 'video/x-m4v';
  }
  if (lower.endsWith('.webm')) {
    return 'video/webm';
  }
  return 'video/mp4';
}

String _videoCoverStrategyForPayload(CreateEditorState state) {
  final strategy = state.videoCoverStrategy.trim();
  if (strategy == 'manual') {
    return 'manual';
  }
  return state.videoCoverTimeMs > 0 ? 'manual' : 'first_frame';
}

Future<void> _defaultUploadMediaObject(
  Uri uploadUri,
  List<int> bytes, {
  required String contentType,
}) async {
  final client = http.Client();
  try {
    final response = await client.put(
      uploadUri,
      headers: <String, String>{'Content-Type': contentType},
      body: bytes,
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError('media object upload failed: ${response.statusCode}');
    }
  } finally {
    client.close();
  }
}

Future<void> reportCreateEditorSurfaceEvent(
  WidgetRef ref,
  String event, [
  Map<String, Object?> extras = const {},
  String surfaceId = 'create_editor',
]) async {
  try {
    final row = <String, Object?>{
      'event': event,
      'surface': surfaceId,
      'timestamp': DateTime.now().toIso8601String(),
      ...extras,
    };
    await ref
        .read(contentRepositoryProvider)
        .reportBehaviors(
          events: <ContentBehaviorBatchEventDto>[
            ContentBehaviorBatchEventDto.fromMap(
              Map<String, dynamic>.from(row),
            ),
          ],
        );
  } catch (e, st) {
    // 创作埋点上报为非关键路径：失败仅降级为日志，不阻断创作流程（R17）。
    developer.log(
      'reportCreateEditorSurfaceEvent failed: event=$event',
      name: 'CreateEditor',
      error: e,
      stackTrace: st,
    );
  }
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

Future<Map<String, Object?>> attachActivePersonaToCreatePayload(
  WidgetRef ref,
  Map<String, Object?> payload,
) async {
  final activeContext = await ref.read(activePersonaContextProvider.future);
  if (ref.read(contentRepositoryProvider).requiresResolvedPersonaForMutations &&
      activeContext.isFallback) {
    throw StateError('active persona context unavailable');
  }
  return <String, Object?>{
    ...payload,
    ...activeContext.toTypedEnvelope(sourceSurfaceId: 'create_editor'),
    if (activeContext.displayName.isNotEmpty)
      'authorDisplayNameSnapshot': activeContext.displayName,
    if (activeContext.avatarUrl.isNotEmpty)
      'authorAvatarUrlSnapshot': activeContext.avatarUrl,
  };
}

Future<PostBaseDto> repositoryCreatePost(
  ContentRepository repository,
  Map<String, Object?> payload,
) async {
  return repository.createPost(
    body: CreatePostRequestWire.fromMap(Map<String, dynamic>.from(payload)),
  );
}

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

/// 与 [buildCreatePostPayloadMap] 写入的 `contentType` 一致，供发布成功打点使用。
Map<String, Object?> createEditorSurfaceExtrasPublishSuccess(
  Map<String, Object?> payload,
) => <String, Object?>{'contentType': payload['contentType']};

Future<void> repositoryPublishPostWithSettings(
  ContentRepository repository, {
  required String postId,
  required PublishSettings settings,
}) async {
  await repository.publishPost(
    postId: postId,
    body: PublishPostRequestWire.fromMap(settings.toPayloadFields()),
  );
}
