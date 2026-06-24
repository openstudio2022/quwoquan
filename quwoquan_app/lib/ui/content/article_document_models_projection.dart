part of 'article_document_models.dart';

List<ArticleDocumentNode> _buildDocumentNodesFromCurrent({
  required String title,
  required String body,
  required List<ArticleDocumentAsset> assets,
  required List<ArticleDocumentBlock> blocks,
  bool useFullBlockSequence = false,
}) {
  final nodes = <ArticleDocumentNode>[];
  final normalizedTitle = _normalizeArticleText(title).trim();

  // 新格式路径：仅当 fromMap 明确检测到 wire 中含有效 image block 时才启用，
  // 避免编辑器内部构造时误触发。
  if (useFullBlockSequence) {
    if (normalizedTitle.isNotEmpty) {
      nodes.add(
        ArticleDocumentNode(
          id: 'document_title',
          type: ArticleDocumentNodeType.documentTitle,
          text: normalizedTitle,
        ),
      );
    }
    for (final block in blocks) {
      switch (block.type) {
        case ArticleDocumentBlockType.heading2:
          nodes.add(
            ArticleDocumentNode(
              id: block.id,
              type: ArticleDocumentNodeType.headingMajor,
              text: block.text,
              textAlign: block.textAlign,
              spans: block.spans,
            ),
          );
          break;
        case ArticleDocumentBlockType.heading3:
          nodes.add(
            ArticleDocumentNode(
              id: block.id,
              type: ArticleDocumentNodeType.headingMinor,
              text: block.text,
              textAlign: block.textAlign,
              spans: block.spans,
            ),
          );
          break;
        case ArticleDocumentBlockType.sectionTitle:
          nodes.add(
            ArticleDocumentNode(
              id: block.id,
              type: ArticleDocumentNodeType.headingMajor,
              text: block.text,
              textAlign: block.textAlign,
              spans: block.spans,
            ),
          );
          break;
        case ArticleDocumentBlockType.image:
          if (block.hasImage) {
            nodes.add(
              ArticleDocumentNode(
                id: block.id,
                type: ArticleDocumentNodeType.figure,
                imageUrl: block.imageUrl,
                imageLayout: block.imageLayout,
                caption: block.caption,
              ),
            );
          }
          break;
        case ArticleDocumentBlockType.paragraph:
          if (block.text.trim().isNotEmpty) {
            nodes.add(
              ArticleDocumentNode(
                id: block.id,
                type: ArticleDocumentNodeType.paragraph,
                text: block.text,
                textAlign: block.textAlign,
                spans: block.spans,
              ),
            );
          }
          break;
        case ArticleDocumentBlockType.orderedItem:
          nodes.add(
            ArticleDocumentNode(
              id: block.id,
              type: ArticleDocumentNodeType.orderedItem,
              text: block.text,
              textAlign: block.textAlign,
              spans: block.spans,
            ),
          );
          break;
        case ArticleDocumentBlockType.bulletItem:
          nodes.add(
            ArticleDocumentNode(
              id: block.id,
              type: ArticleDocumentNodeType.bulletItem,
              text: block.text,
              textAlign: block.textAlign,
              spans: block.spans,
            ),
          );
          break;
      }
    }
    return nodes;
  }

  if (normalizedTitle.isNotEmpty) {
    nodes.add(
      ArticleDocumentNode(
        id: 'document_title',
        type: ArticleDocumentNodeType.documentTitle,
        text: normalizedTitle,
      ),
    );
  }

  final normalizedBody = _normalizeArticleText(body);
  final semanticBlocks =
      blocks
          .where(
            (block) =>
                block.type == ArticleDocumentBlockType.heading2 ||
                block.type == ArticleDocumentBlockType.heading3 ||
                block.type == ArticleDocumentBlockType.sectionTitle,
          )
          .toList(growable: false)
        ..sort((left, right) {
          final offsetCompare = left.offset.compareTo(right.offset);
          if (offsetCompare != 0) {
            return offsetCompare;
          }
          return left.id.compareTo(right.id);
        });

  // image 类型的 blocks 也作为图片资产参与排版（仅新格式路径使用，此处保留供参考）
  // 旧路径直接使用传入的 assets，不从 blocks 提取图片。
  final sortedAssets =
      assets.where((asset) => asset.hasImage).toList(growable: false)
        ..sort((left, right) {
          final offsetCompare = left.offset.compareTo(right.offset);
          if (offsetCompare != 0) {
            return offsetCompare;
          }
          return left.id.compareTo(right.id);
        });

  var cursor = 0;
  var semanticIndex = 0;
  var assetIndex = 0;
  var textSeed = 0;

  while (semanticIndex < semanticBlocks.length ||
      assetIndex < sortedAssets.length) {
    final nextSemanticOffset = semanticIndex < semanticBlocks.length
        ? semanticBlocks[semanticIndex].offset.clamp(
            cursor,
            normalizedBody.length,
          )
        : normalizedBody.length;
    final nextAssetOffset = assetIndex < sortedAssets.length
        ? sortedAssets[assetIndex].offset.clamp(cursor, normalizedBody.length)
        : normalizedBody.length;
    final nextOffset = nextSemanticOffset < nextAssetOffset
        ? nextSemanticOffset
        : nextAssetOffset;
    _appendTextNodesFromBodySegment(
      nodes,
      normalizedBody.substring(cursor, nextOffset),
      seedPrefix: 'paragraph',
      seedStart: textSeed,
    );
    textSeed += _countTextNodesFromBodySegment(
      normalizedBody.substring(cursor, nextOffset),
    );
    cursor = nextOffset;

    while (semanticIndex < semanticBlocks.length &&
        semanticBlocks[semanticIndex].offset.clamp(0, normalizedBody.length) <=
            cursor) {
      final block = semanticBlocks[semanticIndex];
      nodes.add(
        ArticleDocumentNode(
          id: block.id,
          type: block.type == ArticleDocumentBlockType.heading3
              ? ArticleDocumentNodeType.headingMinor
              : ArticleDocumentNodeType.headingMajor,
          text: block.text,
          textAlign: block.textAlign,
          listDepth: block.listDepth,
          spans: block.spans,
        ),
      );
      semanticIndex += 1;
    }

    while (assetIndex < sortedAssets.length &&
        sortedAssets[assetIndex].offset.clamp(0, normalizedBody.length) <=
            cursor) {
      final asset = sortedAssets[assetIndex];
      nodes.add(
        ArticleDocumentNode(
          id: asset.id,
          type: ArticleDocumentNodeType.figure,
          assetId: asset.id,
          imageUrl: asset.imageUrl,
          imageLayout: asset.imageLayout,
          caption: asset.caption,
        ),
      );
      assetIndex += 1;
    }
  }

  _appendTextNodesFromBodySegment(
    nodes,
    normalizedBody.substring(cursor),
    seedPrefix: 'paragraph',
    seedStart: textSeed,
  );
  return _normalizeDocumentNodes(nodes);
}
