import 'package:quwoquan_app/ui/content/article_render/markdown/qwq_markdown.dart';
import 'package:quwoquan_app/ui/content/models/article_document_models.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';

final class ResolvedArticleMediaPayload {
  const ResolvedArticleMediaPayload({
    required this.markdown,
    required this.assetManifest,
  });

  final String markdown;
  final Map<String, dynamic> assetManifest;
}

Map<String, dynamic> buildArticleAssetManifestForPayload(
  CreateEditorState state,
) {
  final assets = <Map<String, Object?>>[];
  if (state.articleCoverImagePath.trim().isNotEmpty) {
    assets.add(_manifestRow('cover', role: 'cover'));
  }
  for (var index = 0; index < state.articleDocument.assets.length; index++) {
    final asset = state.articleDocument.assets[index];
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
  return _manifest(assets);
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
  required String assistantUsePolicy,
}) {
  final manifestRows = <Map<String, Object?>>[];
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
    markdown: ArticleMarkdownCodec.serializeDocument(
      resolvedDocument,
      summary: summary,
      tagRefs: tagRefs,
      entityRefs: entityRefs,
      visibility: visibility,
      assistantUsePolicy: assistantUsePolicy,
      coverAssetId: coverAssetId,
      coverImageUrl: coverReference,
    ),
    assetManifest: _manifest(manifestRows),
  );
}

Map<String, dynamic> _manifest(List<Map<String, Object?>> assets) {
  return <String, dynamic>{
    'schema': 'article-asset-manifest',
    'markdownVersion': qwqRichMarkdownVersion,
    'assets': assets,
  };
}

Map<String, Object?> _manifestRow(
  String assetId, {
  required String role,
  String layout = '',
  String caption = '',
}) {
  return <String, Object?>{
    'assetId': assetId,
    'kind': 'image',
    'role': role,
    if (layout.trim().isNotEmpty) 'layout': layout.trim(),
    if (caption.trim().isNotEmpty) 'caption': caption.trim(),
  };
}

String _assetIdFromReference(String value) {
  final source = value.trim();
  return source.startsWith('asset://')
      ? source.substring('asset://'.length).trim()
      : '';
}
