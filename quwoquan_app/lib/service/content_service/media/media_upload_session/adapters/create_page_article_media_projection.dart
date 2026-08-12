import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_media_article_publication_draft.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class ResolvedArticleMediaPayload {
  const ResolvedArticleMediaPayload({
    required this.markdown,
    required this.assetManifest,
  });

  final String markdown;
  final PostArticleAssetManifestInput assetManifest;
}

PostArticleAssetManifestInput buildArticleAssetManifestForPayload(
  ContentMediaArticlePublicationDraft draft,
) {
  final assets = <PostArticleAssetInput>[];
  if (draft.coverImagePath.trim().isNotEmpty) {
    assets.add(_manifestRow('cover', role: 'cover'));
  }
  for (var index = 0; index < draft.document.assets.length; index++) {
    final asset = draft.document.assets[index];
    if (asset.imageUrl.trim().isEmpty) continue;
    assets.add(
      _manifestRow(
        asset.id.trim().isEmpty ? 'inline_$index' : asset.id.trim(),
        role: 'figure',
        layout: asset.imageLayout,
        caption: asset.caption,
      ),
    );
  }
  return _manifest(assets, markdownDialect: draft.markdownDialect);
}

PostArticleRenderProfile buildArticleRenderProfileForPayload(
  ContentMediaArticlePublicationDraft draft,
) {
  return PostArticleRenderProfile(
    template: draft.template,
    fontPreset: draft.fontPreset,
    layoutPolicy: const PostArticleLayoutPolicy(
      wrapDowngrade: 'compactWidthToFullWidth',
      galleryDowngrade: 'singleColumn',
    ),
  );
}

/// Rebinds editor-local figure identities to immutable MediaAsset identities.
/// No path, CAS key, upload URL, or delivery URL crosses the Post command.
ResolvedArticleMediaPayload projectResolvedArticleMediaPayload({
  required ArticleDocumentData document,
  required Map<String, String> assetIdBySource,
  required String coverAssetId,
  required String summary,
  required List<String> tagRefs,
  required List<String> entityRefs,
  required String visibility,
  required AssistantUsePolicy assistantUsePolicy,
  required String markdownDialect,
  required ContentMediaArticleMarkdownEncoder encodeMarkdown,
}) {
  final manifestRows = <PostArticleAssetInput>[];
  final seen = <String>{};
  void addManifestRow(
    String assetId, {
    required String role,
    String layout = '',
    String caption = '',
  }) {
    if (assetId.isEmpty || !seen.add(assetId)) return;
    manifestRows.add(
      _manifestRow(assetId, role: role, layout: layout, caption: caption),
    );
  }

  addManifestRow(coverAssetId, role: 'cover');
  final nodes = document.nodes
      .map((node) {
        if (!node.isFigure) return node;
        final source = node.imageUrl.trim();
        final assetId =
            assetIdBySource[source] ?? _assetIdFromReference(source);
        if (assetId.isEmpty) return node;
        addManifestRow(
          assetId,
          role: 'figure',
          layout: node.imageLayout.trim(),
          caption: node.caption.trim(),
        );
        return node.copyWith(assetId: assetId, imageUrl: 'asset://$assetId');
      })
      .toList(growable: false);
  final resolvedDocument = document.copyWith(nodes: nodes);
  final coverReference = coverAssetId.isEmpty ? '' : 'asset://$coverAssetId';
  return ResolvedArticleMediaPayload(
    markdown: encodeMarkdown(
      document: resolvedDocument,
      summary: summary,
      tagRefs: tagRefs,
      entityRefs: entityRefs,
      visibility: visibility,
      assistantUsePolicy: assistantUsePolicy,
      coverAssetId: coverAssetId,
      coverImageUrl: coverReference,
    ),
    assetManifest: _manifest(manifestRows, markdownDialect: markdownDialect),
  );
}

PostArticleAssetManifestInput _manifest(
  List<PostArticleAssetInput> assets, {
  required String markdownDialect,
}) => PostArticleAssetManifestInput(
  schema: 'article-asset-manifest',
  markdownVersion: markdownDialect,
  assets: assets,
);

PostArticleAssetInput _manifestRow(
  String assetId, {
  required String role,
  String layout = '',
  String caption = '',
}) {
  return PostArticleAssetInput(
    assetId: assetId,
    role: role,
    layout: layout.trim().isEmpty ? null : layout.trim(),
    caption: caption.trim().isEmpty ? null : caption.trim(),
  );
}

String _assetIdFromReference(String value) {
  final source = value.trim();
  return source.startsWith('asset://')
      ? source.substring('asset://'.length).trim()
      : '';
}
