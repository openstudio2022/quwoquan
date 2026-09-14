import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_markdown_codec.dart';

/// 文章编辑撤销点（与 [CreateEditorState] 中文章相关字段一致，用于 undo/redo）。
abstract final class CreateEditorUndoSnapshot {
  static const int maxStack = 25;

  static Map<String, dynamic> serialize(CreateEditorState state) {
    return <String, dynamic>{
      // authority 永不序列化；只保存 canonical markdown，恢复时重新解析重建。
      'articleMarkdown': ArticleMarkdownCodec.serializeDocument(
        state.articleDocument,
      ),
      'articleAssetManifest': _snapshotAssetManifest(state.articleDocument),
      'articleNodeIds': _serializedNodeIds(state.articleDocument),
      'articleEmptyNodes': _emptyNodeSnapshots(state.articleDocument),
      'activeArticlePageId': state.activeArticlePageId,
      'activeArticleBlockId': state.activeArticleBlockId,
      'articleTemplate': state.articleTemplate.name,
      'articleFontPreset': state.articleFontPreset.name,
      'articleCoverImagePath': state.articleCoverImagePath,
      'titlePresentation': state.titlePresentation.name,
      'titleHintDismissed': state.titleHintDismissed,
    };
  }

  static List<Map<String, Object?>> _emptyNodeSnapshots(
    ArticleDocumentData document,
  ) {
    final result = <Map<String, Object?>>[];
    for (var index = 0; index < document.nodes.length; index++) {
      final node = document.nodes[index];
      if (node.isDocumentTitle ||
          node.isFigure ||
          node.type == ArticleDocumentNodeType.divider ||
          node.text.trim().isNotEmpty) {
        continue;
      }
      result.add(<String, Object?>{
        'index': index,
        'id': node.id,
        'type': node.type.name,
      });
    }
    return result;
  }

  static List<String> _serializedNodeIds(ArticleDocumentData document) {
    return document.nodes
        .where((node) {
          if (node.isDocumentTitle) {
            return node.text.trim().isNotEmpty;
          }
          if (node.type == ArticleDocumentNodeType.divider) {
            return true;
          }
          if (node.isFigure) {
            return node.assetId.trim().isNotEmpty || node.id.trim().isNotEmpty;
          }
          return node.text.trim().isNotEmpty;
        })
        .map((node) => node.id)
        .toList(growable: false);
  }

  static Map<String, Object?> _snapshotAssetManifest(
    ArticleDocumentData document,
  ) {
    final assets = document.nodes
        .where(
          (node) =>
              node.isFigure &&
              (node.assetId.trim().isNotEmpty || node.id.trim().isNotEmpty),
        )
        .map(
          (node) => <String, Object?>{
            'assetId': node.assetId.trim().isNotEmpty ? node.assetId : node.id,
            if (node.imageUrl.trim().isNotEmpty) 'url': node.imageUrl,
            if (node.imageWidth != null) 'width': node.imageWidth,
            if (node.imageHeight != null) 'height': node.imageHeight,
          },
        )
        .toList(growable: false);
    return <String, Object?>{'assets': assets};
  }

  static List<ArticleDocumentNode> _restoreEmptyNodes(
    List<ArticleDocumentNode> nodes,
    Object? raw,
  ) {
    final restored = List<ArticleDocumentNode>.from(nodes);
    if (raw is! List) return restored;
    for (final entry in raw.whereType<Map>()) {
      final index = ((entry['index'] as num?)?.toInt() ?? restored.length)
          .clamp(0, restored.length);
      final id = (entry['id'] ?? '').toString();
      final typeName = (entry['type'] ?? 'paragraph').toString();
      final type = ArticleDocumentNodeType.values.firstWhere(
        (value) => value.name == typeName,
        orElse: () => ArticleDocumentNodeType.paragraph,
      );
      if (id.isNotEmpty) {
        restored.insert(index, ArticleDocumentNode(id: id, type: type));
      }
    }
    return restored;
  }

  static Map<String, Map<String, Object?>> _snapshotAssetsById(Object? raw) {
    if (raw is! Map || raw['assets'] is! List) {
      return const <String, Map<String, Object?>>{};
    }
    return <String, Map<String, Object?>>{
      for (final entry in (raw['assets'] as List).whereType<Map>())
        if ((entry['assetId'] ?? '').toString().trim().isNotEmpty)
          (entry['assetId'] ?? '').toString(): Map<String, Object?>.from(entry),
    };
  }

  static CreateEditorState deserialize(
    CreateEditorState base,
    Map<String, dynamic> map,
  ) {
    final markdown = map['articleMarkdown'];
    if (markdown is! String || markdown.trim().isEmpty) {
      throw const FormatException('文章撤销快照缺少 canonical articleMarkdown。');
    }
    final manifestRaw = map['articleAssetManifest'];
    final nodeIdsRaw = map['articleNodeIds'];
    final restoredNodeIds = nodeIdsRaw is List
        ? nodeIdsRaw.map((value) => value.toString()).toList(growable: false)
        : const <String>[];
    final parsedDocument = ArticleMarkdownCodec.parseDocument(
      markdown,
      restoredNodeIds: restoredNodeIds,
      assetManifest: manifestRaw is Map
          ? Map<String, Object?>.from(manifestRaw)
          : null,
    );
    final emptyNodesRaw = map['articleEmptyNodes'];
    final restoredWithEmptyNodes = parsedDocument.copyWith(
      nodes: _restoreEmptyNodes(parsedDocument.nodes, emptyNodesRaw),
    );
    final snapshotAssets = _snapshotAssetsById(manifestRaw);
    final document = restoredWithEmptyNodes.copyWith(
      nodes: parsedDocument.nodes
          .map((node) {
            final assetIdentity = node.assetId.trim().isNotEmpty
                ? node.assetId
                : node.id;
            final asset = snapshotAssets[assetIdentity];
            if (!node.isFigure || asset == null) return node;
            return node.copyWith(
              imageUrl: asset['url']?.toString() ?? node.imageUrl,
              imageWidth: (asset['width'] as num?)?.toInt(),
              imageHeight: (asset['height'] as num?)?.toInt(),
            );
          })
          .toList(growable: false),
    );
    final pages = buildArticlePagesSnapshotFromDocument(
      document,
      fontPreset: articleFontPresetFromString(
        map['articleFontPreset']?.toString(),
      ),
    );
    final activePageId = (map['activeArticlePageId'] as String?)?.trim();
    final activeBlockId = (map['activeArticleBlockId'] as String?)?.trim();
    final template = articleTemplatePresetFromString(
      map['articleTemplate']?.toString(),
    );
    final font = articleFontPresetFromString(
      map['articleFontPreset']?.toString(),
    );
    final imagePaths = extractArticleImagePathsFromDocument(document);
    final cover = (map['articleCoverImagePath'] ?? '').toString();
    final tp =
        (map['titlePresentation']?.toString() ?? 'collapsed') == 'expanded'
        ? TitlePresentation.expanded
        : TitlePresentation.collapsed;
    return base.copyWith(
      title: document.title,
      body: buildArticlePlainTextFromDocument(document),
      articleDocument: document,
      articlePages: pages.isNotEmpty ? pages : base.articlePages,
      activeArticlePageId: activePageId != null && activePageId.isNotEmpty
          ? activePageId
          : base.activeArticlePageId,
      activeArticleBlockId: activeBlockId != null && activeBlockId.isNotEmpty
          ? activeBlockId
          : base.activeArticleBlockId,
      articleTemplate: template,
      articleFontPreset: font,
      articleCoverImagePath: cover,
      imagePaths: imagePaths,
      titlePresentation: tp,
      titleHintDismissed: map['titleHintDismissed'] == true,
    );
  }
}
