import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';

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

/// 发布用请求体（JSON 可序列化）；在页面扫描路径外组装为 [Map<String, dynamic>]。
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
    final canonicalDocument = state.articleDocument.copyWith(
      template: state.articleTemplate.name,
      fontPreset: state.articleFontPreset.name,
      coverImageUrl: coverAssetPath,
    );
    return <String, Object?>{
      'type': 'article',
      'contentType': 'article',
      'articleDocument': canonicalDocument.toMap(),
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
          events: <Map<String, dynamic>>[Map<String, dynamic>.from(row)],
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
  final mode = ref.read(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote && activeContext.isFallback) {
    throw StateError('active persona context unavailable');
  }
  return <String, Object?>{
    ...payload,
    if (activeContext.subAccountId.isNotEmpty)
      'personaId': activeContext.subAccountId,
    if (activeContext.profileSubjectId.isNotEmpty)
      'profileSubjectId': activeContext.profileSubjectId,
    if (activeContext.personaContextVersion.isNotEmpty)
      'personaContextVersion': activeContext.personaContextVersion,
  };
}

Future<Map<String, Object?>> repositoryCreatePost(
  ContentRepository repository,
  Map<String, Object?> payload,
) async {
  final created = await repository.createPost(
    payload: Map<String, dynamic>.from(payload),
  );
  return Map<String, Object?>.from(created);
}

Future<void> repositoryPublishPostWithSettings(
  ContentRepository repository, {
  required String postId,
  required PublishSettings settings,
}) async {
  await repository.publishPost(
    postId: postId,
    payload: settings.toPayloadFields(),
  );
}

String extractCreatedPostId(Map<String, Object?> payload) {
  return (payload['_id'] ?? payload['postId'] ?? payload['id'] ?? '')
      .toString()
      .trim();
}
