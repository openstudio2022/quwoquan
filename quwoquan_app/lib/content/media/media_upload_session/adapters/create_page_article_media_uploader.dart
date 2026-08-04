import 'package:quwoquan_app/content/media/media_upload_session/adapters/create_page_article_media_projection.dart';
import 'package:quwoquan_app/ui/content/entry/services/prepared_post_publication_payload.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';

typedef ResolveArticleMediaAsset =
    Future<String> Function({
      required String source,
      required String slot,
      required int index,
      required int total,
    });

Future<PreparedPostPublicationPayload> uploadArticleMediaForPublication({
  required CreateEditorState state,
  required Map<String, Object?> basePayload,
  required String coverSource,
  required String summary,
  required List<String> tagRefs,
  required List<String> entityRefs,
  required ResolveArticleMediaAsset resolve,
}) async {
  final orderedSources = <String>[
    if (coverSource.isNotEmpty) coverSource,
    ...state.articleDocument.assets.map((asset) => asset.imageUrl.trim()),
    ...state.imagePaths.map((path) => path.trim()),
  ].where((source) => source.isNotEmpty).toSet().toList(growable: false);
  if (orderedSources.isEmpty) {
    return PreparedPostPublicationPayload(
      payload: basePayload,
      mediaAssetIds: const <String>[],
    );
  }

  final assetIdBySource = <String, String>{};
  for (var index = 0; index < orderedSources.length; index++) {
    final source = orderedSources[index];
    final assetId = await resolve(
      source: source,
      slot: 'article:image:$index',
      index: index,
      total: orderedSources.length,
    );
    if (assetId.isEmpty) {
      throw StateError('article media source did not produce a MediaAsset id');
    }
    assetIdBySource[source] = assetId;
  }
  final coverAssetId = assetIdBySource[coverSource] ?? '';
  final projected = projectResolvedArticleMediaPayload(
    document: state.articleDocument,
    assetIdBySource: assetIdBySource,
    coverAssetId: coverAssetId,
    summary: summary,
    tagRefs: tagRefs,
    entityRefs: entityRefs,
    visibility: state.settings.isPublic ? 'public' : 'private',
    assistantUsePolicy: state.settings.assistantUsePolicy.trim().isEmpty
        ? 'inherit'
        : state.settings.assistantUsePolicy.trim(),
  );
  final payload = Map<String, Object?>.from(basePayload)
    ..remove('mediaUrls')
    ..remove('coverUrl')
    ..remove('thumbnailUrl')
    ..remove('mediaItems')
    ..['articleMarkdown'] = projected.markdown
    ..['articleAssetManifest'] = projected.assetManifest;
  return PreparedPostPublicationPayload(
    payload: payload,
    mediaAssetIds: assetIdBySource.values.toSet().toList(growable: false),
  );
}
