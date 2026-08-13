import 'package:quwoquan_app/service/content_service/content/post/adapters/content_media_cover_selection.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/content_media_preparation_checkpoint.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/content_media_upload_service.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/create_page_article_media_projection.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/create_page_article_media_uploader.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/prepared_post_publication_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/generated/content_publication_policy.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/publish_settings_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/qwq_markdown.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

export 'package:quwoquan_app/service/content_service/content/post/adapters/create_page_article_media_projection.dart'
    show
        buildArticleAssetManifestForPayload,
        buildArticleRenderProfileForPayload;

part 'create_page_remote_payload_helpers.part.dart';

int paragraphCountForPayload(String text) {
  return text
      .split('\n')
      .map((line) => line.trim())
      .where((line) => line.isNotEmpty)
      .length;
}

/// 系统对文字形态的「建议」：只用于确认页初始化与预览等非提交路径。
/// 阈值与云端 `publication_policy.yaml` 同源（codegen），不维护第二份。
bool shouldPublishAsArticleForPayload(CreateEditorState state) {
  return (ContentPublicationPolicy.articleWhenTitlePresent &&
          state.title.trim().isNotEmpty) ||
      state.body.trim().length >= ContentPublicationPolicy.articleBodyMinRunes ||
      paragraphCountForPayload(state.body) >=
          ContentPublicationPolicy.articleParagraphMinCount;
}

/// 提交/预览共用的文字形态判定：用户在发布确认页固化的
/// [PublishSettings.textContentType] 是唯一确认值；仅当尚未经过确认页
/// （草稿投影预览等非提交路径）时才回落到建议函数。提交路径由
/// `_publish` 在确认页返回后 fail-closed 校验确认值非空（GWT-001）。
bool resolveTextPublishAsArticle(CreateEditorState state) {
  return switch (state.settings.textContentType.trim()) {
    'article' => true,
    'micro' => false,
    _ => shouldPublishAsArticleForPayload(state),
  };
}

String articleSummaryForPayload(CreateEditorState state) {
  final documentText = state.articleDocument.body.trim();
  final plainText = documentText.isNotEmpty ? documentText : state.body.trim();
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
    return resolveTextPublishAsArticle(state)
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
    assistantUsePolicy: state.settings.assistantUsePolicy,
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

/// 与 [entityRefsForPayload] 对称：合并发布设置里的 tagRefs 与正文
/// inline tag mention（剥离 `tag:` 前缀，对齐 front matter `tag_refs` 不带前缀的格式），
/// 去重后投影为 active tagRefs。只采纳正文里已存在的 `@[label](tag:ref)`，
/// 不在创作端自造 tag 候选。
///
/// EXIF 只随 MediaAsset 上传并由服务端投影内部推荐特征；这里禁止把器材、参数或光线
/// 写入公开 tagRefs，避免它们进入搜索筛选、Creator chip 或可见交集文案。
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
/// active refs 投影为 canonical [PostSemanticMention]。
///
/// 服务端 `semantic.Project`（content-service domain/post/semantic）把 `status=published`
/// 且 `targetRef` 合法的 mention 投影为只读 `post.entityRefs/tagRefs`；本函数与
/// [entityRefsForPayload]/[tagRefsForPayload] 同源（同一去重 ref 集），保证服务端投影
/// 结果 == 端侧 active refs == 文章 front matter 的 entity_refs/tag_refs，三者一致。
///
/// targetRef 形态：entity 用完整 `entity:`/`homepage_` id；tag 用层级 bare ref（去 `tag:`
/// 前缀，与全应用 tagRef 口径一致）。[isSemanticTargetRefValid] 防御性过滤畸形 ref，
/// 避免单个非法内联触发服务端整篇发布拒绝。
List<PostSemanticMention> semanticMentionsForPayload(CreateEditorState state) {
  final rows = <PostSemanticMention>[];
  final seen = <String>{};
  void addRow(
    String kind,
    String rawRef, {
    required String surface,
    required String location,
    int? rangeStart,
    int? rangeEnd,
  }) {
    final ref = rawRef.trim();
    if (ref.isEmpty || !isSemanticTargetRefValid(kind, ref)) {
      return;
    }
    if (!seen.add('$kind|$ref')) {
      return;
    }
    rows.add(
      PostSemanticMention(
        mentionId: 'published:$kind:$ref',
        kind: kind,
        surface: surface.trim().isEmpty ? ref : surface.trim(),
        location: location,
        rangeStart: rangeStart,
        rangeEnd: rangeEnd,
        status: 'published',
        targetRef: ref,
      ),
    );
  }

  var bodyOffset = 0;
  for (final node in state.articleDocument.nodes) {
    for (final span in node.spans.where((span) => span.isInlineMention)) {
      final rawTarget = span.targetId?.trim() ?? '';
      final kind = span.isEntity ? 'entity' : 'tag';
      final target = kind == 'tag' && rawTarget.startsWith('tag:')
          ? rawTarget.substring('tag:'.length).trim()
          : rawTarget;
      final start = span.start.clamp(0, node.text.length);
      final end = span.end.clamp(start, node.text.length);
      final inlineSurface = span.displayText?.trim().isNotEmpty == true
          ? span.displayText!.trim()
          : node.text.substring(start, end).trim();
      addRow(
        kind,
        target,
        surface: inlineSurface,
        location: node.isDocumentTitle ? 'title' : 'body',
        rangeStart: node.isDocumentTitle ? start : bodyOffset + start,
        rangeEnd: node.isDocumentTitle ? end : bodyOffset + end,
      );
    }
    if (!node.isDocumentTitle && !node.isFigure) {
      bodyOffset += node.text.length + 1;
    }
  }

  final entityLabels = _semanticLabelsByRef(
    state.settings.entityRefs,
    state.settings.entityNames,
  );
  final homepage = state.settings.homepage;
  if (homepage != null) {
    final ref = homepageEntityRef(homepage);
    if (ref.isNotEmpty) entityLabels[ref] = homepage.title;
  }
  for (final ref in entityRefsForPayload(state)) {
    addRow(
      'entity',
      ref,
      surface: entityLabels[ref] ?? ref,
      location: 'publicationSettings',
    );
  }
  final tagLabels = _semanticLabelsByRef(
    state.settings.tagRefs,
    state.settings.tagLabels,
  );
  for (final ref in tagRefsForPayload(state)) {
    addRow(
      'tag',
      ref,
      surface: tagLabels[ref] ?? ref,
      location: 'publicationSettings',
    );
  }
  return rows;
}

Map<String, String> _semanticLabelsByRef(
  List<String> refs,
  List<String> labels,
) {
  final result = <String, String>{};
  for (var index = 0; index < refs.length; index++) {
    final ref = refs[index].trim();
    if (ref.isEmpty || index >= labels.length) continue;
    final label = labels[index].trim();
    if (label.isNotEmpty) result[ref] = label;
  }
  return result;
}

/// 防御性镜像服务端 `semantic.ValidTargetRef`（唯一权威：
/// `quwoquan_service/services/content-service/internal/content/post/domain/semantic/mentions.go`）。
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
  // R-CS06：发布唯一可写 grounding 字段。canonical 请求实体不拥有顶层只读
  // tagRefs/entityRefs；entity/tag 内联只有经 semanticMentions 才落服务端 refs。
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
        if (coverUrl.isNotEmpty) 'coverUrl': coverUrl,
        if (thumbnailUrl.isNotEmpty) 'thumbnailUrl': thumbnailUrl,
        'coverStrategy': coverStrategy,
        'coverFrameTimeMs': state.videoCoverTimeMs,
        if (state.videoDurationMs > 0) 'durationMs': state.videoDurationMs,
        if (state.videoWidth > 0) 'width': state.videoWidth,
        if (state.videoHeight > 0) 'height': state.videoHeight,
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
  final asArticle = resolveTextPublishAsArticle(state);
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
  required ContentMediaUploadService uploadService,
  required CreateEditorState state,
  required ContentMediaSourceReader sourceReader,
  required ContentMediaStreamObjectUpload uploadStream,
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
  final publishesArticle =
      state.editorKind == CreateEditorKind.text &&
      resolveTextPublishAsArticle(state);
  final hasMediaSource =
      state.hasVideo ||
      state.imagePaths.isNotEmpty ||
      (publishesArticle &&
          (state.articleCoverImagePath.trim().isNotEmpty ||
              state.articleDocument.assets.isNotEmpty));
  if (preparationIdentity.isEmpty && hasMediaSource) {
    throw StateError('media publication requires a durable draft identity');
  }
  final basePayload = Map<String, Object?>.from(
    buildPostPublicationPayloadMap(state),
  );
  if (publishesArticle) {
    return uploadArticleMediaForPublication(
      state: state,
      basePayload: basePayload,
      coverSource: coverAssetPathForPayload(state),
      summary: state.settings.summary.trim().isNotEmpty
          ? state.settings.summary.trim()
          : articleSummaryForPayload(state),
      tagRefs: tagRefsForPayload(state),
      entityRefs: entityRefsForPayload(state),
      resolve:
          ({
            required source,
            required slot,
            required index,
            required total,
          }) async {
            final resolved = await _resolveMediaReference(
              uploadService: uploadService,
              localOrRemotePath: source,
              mediaType: MediaType.image,
              sourceReader: sourceReader,
              uploadStream: uploadStream,
              onProgress: (uploaded, length) {
                final progress = length == 0 ? 0 : uploaded / length;
                onUploadProgress?.call((index + progress) / total);
              },
              cancellationSignal: cancellationSignal,
              preparationIdentity: preparationIdentity,
              slot: slot,
              preparedAssetsBySlot: preparedAssetsBySlot,
              onMediaPrepared: onMediaPrepared,
            );
            return resolved.assetId;
          },
    );
  }
  if (state.editorKind != CreateEditorKind.media && state.imagePaths.isEmpty) {
    return PreparedPostPublicationPayload(
      payload: basePayload,
      mediaAssetIds: const <String>[],
    );
  }
  // 上传完成后的 publicSliceKey 只服务交付解析，Post 写入只携带 assetId。
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
      uploadService: uploadService,
      state: state,
      basePayload: basePayload,
      sourceReader: sourceReader,
      uploadStream: uploadStream,
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
      uploadService: uploadService,
      localOrRemotePath: path,
      mediaType: MediaType.image,
      captureMetadata: index == 0
          ? _contentMediaCaptureMetadata(state.settings)
          : null,
      sourceReader: sourceReader,
      uploadStream: uploadStream,
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
  required ContentMediaUploadService uploadService,
  required CreateEditorState state,
  required Map<String, Object?> basePayload,
  required ContentMediaSourceReader sourceReader,
  required ContentMediaStreamObjectUpload uploadStream,
  PostMediaUploadProgressCallback? onUploadProgress,
  ContentMediaUploadCancellationSignal? cancellationSignal,
  required String preparationIdentity,
  required Map<String, ContentMediaPreparationCheckpoint> preparedAssetsBySlot,
  Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)?
  onMediaPrepared,
}) async {
  final itemCount = state.videoThumbnail.trim().isEmpty ? 1 : 2;
  final video = await _resolveMediaReference(
    uploadService: uploadService,
    localOrRemotePath: state.videoPath,
    mediaType: MediaType.video,
    sourceReader: sourceReader,
    uploadStream: uploadStream,
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
    uploadService: uploadService,
    localOrRemoteCoverPath: state.videoThumbnail,
    sourceReader: sourceReader,
    uploadStream: uploadStream,
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
  final selectedCover = await selectContentMediaCoverWhenReady(
    cancellationSignal: cancellationSignal,
    command: () => cover.assetId.isNotEmpty
        ? media.selectManualCover(
            SelectManualContentMediaCoverCommand(
              mediaId: video.assetId,
              coverAssetId: cover.assetId,
            ),
            ContentMediaAssetCommandContext(
              idempotencyKey:
                  'content.media.cover.manual:${video.assetId}:${cover.assetId}',
            ),
          )
        : media.selectAutoCover(
            SelectAutoContentMediaCoverCommand(mediaId: video.assetId),
            ContentMediaAssetCommandContext(
              idempotencyKey: 'content.media.cover.auto:${video.assetId}',
            ),
          ),
  );

  // payload 是发布命令的 untyped 中转 map，最终经 `_optionalPayloadText` 变成
  // canonical wire 字符串：这里必须写 wireName，否则会把 Dart 枚举的 toString
  // （`MediaCoverStrategy.manual`）当成 coverStrategy 发给云侧。
  basePayload['coverStrategy'] = selectedCover.coverStrategy.wireName;
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
  required ContentMediaUploadService uploadService,
  required String localOrRemotePath,
  required MediaType mediaType,
  MediaCaptureMetadata? captureMetadata,
  required ContentMediaSourceReader sourceReader,
  required ContentMediaStreamObjectUpload uploadStream,
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
      : uploadService.createPreparationCheckpoint(
          preparationIdentity: preparationIdentity,
          slot: slot,
          mediaType: mediaType,
          sha256Digest: source.sha256Digest,
        );
  if (checkpoint == null || !identical(checkpoint, durableCheckpoint)) {
    await onMediaPrepared?.call(durableCheckpoint);
    preparedAssetsBySlot[slot] = durableCheckpoint;
  }
  final uploaded = await uploadService.uploadPreparedSource(
    source: source,
    mediaType: mediaType,
    mimeType: contentMediaMimeTypeForPath(path, mediaType),
    uploadStream: uploadStream,
    onProgress: onProgress,
    cancellationSignal: cancellationSignal,
    accessPolicy: MediaAssetAccessPolicy.referencedPost,
    captureMetadata: captureMetadata,
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

MediaCaptureMetadata? _contentMediaCaptureMetadata(PublishSettings settings) {
  final value = settings.disclosedCaptureMetadata;
  if (value.isEmpty) return null;
  return MediaCaptureMetadata(
    cameraMake: value.cameraMake,
    cameraModel: value.cameraModel,
    lensModel: value.lensModel,
    focalLengthMm: value.focalLengthMm,
    apertureFNumber: value.apertureFNumber,
    shutterSpeedSeconds: value.shutterSpeedSeconds,
    isoSensitivity: value.isoSensitivity,
    capturedAt: value.capturedAt,
    gpsLatitude: value.gpsLatitude,
    gpsLongitude: value.gpsLongitude,
  );
}

Future<_ResolvedVideoCoverReference> _resolveRemoteVideoCover({
  required ContentMediaUploadService uploadService,
  required String localOrRemoteCoverPath,
  required ContentMediaSourceReader sourceReader,
  required ContentMediaStreamObjectUpload uploadStream,
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
      uploadService: uploadService,
      localOrRemotePath: coverPath,
      mediaType: MediaType.image,
      sourceReader: sourceReader,
      uploadStream: uploadStream,
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

/// 判定媒体引用是否已经是「远端 / 已上传」形态。
///
/// canonical 形态只有四种：`http(s)://` 交付 URL、`media://` 与 `asset://`
/// MediaAsset 引用。其余一律视为本地可读路径。发布链路上任何「要不要读本地
/// 文件」的判断都必须走这里，避免各处自己拼前缀而漏掉某一种引用。
bool isRemoteMediaReference(String value) {
  final lower = value.trim().toLowerCase();
  return lower.startsWith('http://') ||
      lower.startsWith('https://') ||
      lower.startsWith('media://') ||
      lower.startsWith('asset://');
}

bool _isRemoteMediaReference(String value) => isRemoteMediaReference(value);

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

SubmitContentPostPublicationCommand
submitContentPostPublicationCommandFromPreparedPayload(
  Map<String, Object?> payload, {
  required String localDraftId,
  required Iterable<String> mediaAssetIds,
  String? authorDisplayNameSnapshot,
  String? authorAvatarUrlSnapshot,
  int? personaContextVersion,
}) => SubmitContentPostPublicationCommand(
  publishIntentId: _postPublicationIntentIdForLocalDraft(localDraftId),
  localDraftId: localDraftId,
  contentType: _requiredPostType(payload['contentType']),
  contentIdentity: _optionalPostIdentity(payload['contentIdentity']),
  title: _optionalPayloadText(payload['title']),
  body: _optionalPayloadText(payload['body']),
  summary: _optionalPayloadText(payload['summary']),
  semanticMentions: _postSemanticMentionsFromPayload(
    payload['semanticMentions'],
  ),
  mediaAssetIds: mediaAssetIds,
  articleMarkdown: _optionalPayloadText(payload['articleMarkdown']),
  markdownDialect: _optionalPayloadText(payload['markdownDialect']),
  articleAssetManifest: _optionalGeneratedWireValue(
    payload['articleAssetManifest'],
    'articleAssetManifest',
    PostArticleAssetManifestInput.fromWire,
  ),
  articleRenderProfile: _optionalGeneratedWireValue(
    payload['articleRenderProfile'],
    'articleRenderProfile',
    PostArticleRenderProfile.fromWire,
  ),
  coverStrategy: _optionalPayloadText(payload['coverStrategy']),
  coverFrameTimeMs: _optionalPayloadInt(
    payload['coverFrameTimeMs'],
    'coverFrameTimeMs',
  ),
  illustrationAssetId: _optionalPayloadText(payload['illustrationAssetId']),
  location: _optionalGeneratedWireValue(
    payload['location'],
    'location',
    GeoPoint.fromWire,
  ),
  locationName: _optionalPayloadText(payload['locationName']),
  geoTagRef: _optionalPayloadText(payload['geoTagRef']),
  visitedAt: _optionalPayloadTimestamp(payload['visitedAt'], 'visitedAt'),
  captureDisclosure: _payloadCaptureDisclosureList(
    payload['captureDisclosure'],
  ),
  primaryHomepageId: _optionalPayloadText(payload['primaryHomepageId']),
  primaryHomepageType: _optionalPayloadText(payload['primaryHomepageType']),
  primaryHomepageSnapshot: _optionalGeneratedWireValue(
    payload['primaryHomepageSnapshot'],
    'primaryHomepageSnapshot',
    PostHomepageSnapshot.fromWire,
  ),
  visibility: _optionalPostVisibility(payload['visibility']),
  assistantUsePolicy: _optionalAssistantUsePolicy(
    payload['assistantUsePolicy'],
  ),
  sourcePostId: _optionalPayloadText(payload['sourcePostId']),
  sourceType: _optionalPostSourceType(payload['sourceType']),
  gatheringRef: _optionalPayloadText(payload['gatheringRef']),
  deviceInfo: _optionalGeneratedWireValue(
    payload['deviceInfo'],
    'deviceInfo',
    PostDeviceInfo.fromWire,
  ),
  publishLocation: _optionalGeneratedWireValue(
    payload['publishLocation'],
    'publishLocation',
    PostPublishLocation.fromWire,
  ),
  authorDisplayNameSnapshot: _optionalPayloadText(authorDisplayNameSnapshot),
  authorAvatarUrlSnapshot: _optionalPayloadText(authorAvatarUrlSnapshot),
  personaContextVersion: personaContextVersion,
);
