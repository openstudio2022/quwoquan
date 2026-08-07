import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/create_page_article_media_projection.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_media_article_publication_draft.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/prepared_post_publication_payload.dart';

typedef ResolveArticleMediaAsset =
    Future<String> Function({
      required String source,
      required String slot,
      required int index,
      required int total,
    });

Future<PreparedPostPublicationPayload> uploadArticleMediaForPublication({
  required ContentMediaArticlePublicationDraft draft,
  required Map<String, Object?> basePayload,
  required String coverSource,
  required String summary,
  required List<String> tagRefs,
  required List<String> entityRefs,
  required ResolveArticleMediaAsset resolve,
  required ContentMediaArticleMarkdownEncoder encodeMarkdown,
}) async {
  final orderedSources = <String>[
    if (coverSource.isNotEmpty) coverSource,
    ...draft.document.assets.map((asset) => asset.imageUrl.trim()),
    ...draft.imagePaths.map((path) => path.trim()),
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
    document: draft.document,
    assetIdBySource: assetIdBySource,
    coverAssetId: coverAssetId,
    summary: summary,
    tagRefs: tagRefs,
    entityRefs: entityRefs,
    visibility: draft.isPublic ? 'public' : 'private',
    assistantUsePolicy: draft.assistantUsePolicy,
    markdownDialect: draft.markdownDialect,
    encodeMarkdown: encodeMarkdown,
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
