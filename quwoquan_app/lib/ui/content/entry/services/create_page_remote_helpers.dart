import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
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
  final buffer = StringBuffer()
    ..writeln('---')
    ..writeln('title: ${_escapeFrontMatterValue(state.title.trim())}')
    ..writeln(
      'summary: ${_escapeFrontMatterValue(articleSummaryForPayload(state))}',
    )
    ..writeln('template: ${state.articleTemplate.name}')
    ..writeln('fontPreset: ${state.articleFontPreset.name}');
  final cover = coverAssetPathForPayload(state);
  if (cover.trim().isNotEmpty) {
    buffer.writeln('coverImage: asset://cover');
  }
  buffer
    ..writeln("visibility: ${state.settings.isPublic ? 'public' : 'private'}")
    ..writeln('assistantUsePolicy: inherit')
    ..writeln('---')
    ..writeln();
  if (state.title.trim().isNotEmpty) {
    buffer
      ..write('# ')
      ..writeln(state.title.trim())
      ..writeln();
  }
  if (cover.trim().isNotEmpty) {
    buffer
      ..writeln(':::figure id="cover" layout="fullWidth" caption=""')
      ..writeln('asset://cover')
      ..writeln(':::')
      ..writeln();
  }
  for (final block in state.articleBlocks) {
    final text = block.text.trim();
    switch (block.type) {
      case CreateTextBlockType.heading2:
      case CreateTextBlockType.sectionTitle:
        if (text.isNotEmpty) {
          buffer
            ..write('## ')
            ..writeln(text)
            ..writeln();
        }
      case CreateTextBlockType.heading3:
        if (text.isNotEmpty) {
          buffer
            ..write('### ')
            ..writeln(text)
            ..writeln();
        }
      case CreateTextBlockType.orderedItem:
        if (text.isNotEmpty) {
          buffer
            ..write('1. ')
            ..writeln(text)
            ..writeln();
        }
      case CreateTextBlockType.bulletItem:
        if (text.isNotEmpty) {
          buffer
            ..write('- ')
            ..writeln(text)
            ..writeln();
        }
      case CreateTextBlockType.image:
        final imagePath = block.imagePath.trim();
        if (imagePath.isNotEmpty) {
          final assetId = _assetIdForPath(imagePath, 'inline');
          buffer
            ..writeln(
              ':::figure id="$assetId" layout="${block.imageLayout.name}" caption=""',
            )
            ..writeln('asset://$assetId')
            ..writeln(':::')
            ..writeln();
        }
      case CreateTextBlockType.paragraph:
        if (text.isNotEmpty) {
          buffer
            ..writeln(text)
            ..writeln();
        }
    }
  }
  return buffer.toString().trimRight();
}

Map<String, dynamic> buildArticleAssetManifestForPayload(
  CreateEditorState state,
) {
  final assets = <Map<String, Object?>>[];
  final cover = coverAssetPathForPayload(state);
  if (cover.trim().isNotEmpty) {
    assets.add(_assetManifestRow('cover', cover.trim(), role: 'cover'));
  }
  for (final path in extractArticleImagePaths(state.articleBlocks)) {
    final assetId = _assetIdForPath(path, 'inline');
    assets.add(_assetManifestRow(assetId, path, role: 'figure'));
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

String _escapeFrontMatterValue(String value) {
  return value.replaceAll('"', '\\"');
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
  final coverAssetPath = coverAssetPathForPayload(state);
  if (state.editorKind == CreateEditorKind.media) {
    if (state.hasVideo) {
      return <String, Object?>{
        'type': 'video',
        'contentType': 'video',
        'title': state.title.trim(),
        'body': state.body.trim(),
        'videoUrl': state.videoPath,
        'mediaUrls': <String>[state.videoPath],
        'coverUrl': coverAssetPath,
        ...settings,
      };
    }
    return <String, Object?>{
      'type': 'image',
      'contentType': 'image',
      'title': state.title.trim(),
      'body': state.body.trim(),
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
      'summary': articleSummaryForPayload(state),
      'coverUrl': coverAssetPath,
      'articleMarkdown': buildArticleMarkdownForPayload(state),
      'articleMarkdownVersion': qwqRichMarkdownVersion,
      'articleAssetManifest': buildArticleAssetManifestForPayload(state),
      'articleRenderProfile': buildArticleRenderProfileForPayload(state),
      ...settings,
    };
  }
  return <String, Object?>{
    'type': 'moment',
    'contentType': 'micro',
    'title': state.title.trim(),
    'body': state.body.trim(),
    'mediaUrls': state.imagePaths,
    'coverUrl': coverAssetPath,
    ...settings,
  };
}

Future<void> reportCreateEditorSurfaceEvent(
  WidgetRef ref,
  String event, [
  Map<String, Object?> extras = const {},
]) async {
  try {
    final row = <String, Object?>{
      'event': event,
      'surface': 'create_editor',
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
  } catch (_) {}
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
