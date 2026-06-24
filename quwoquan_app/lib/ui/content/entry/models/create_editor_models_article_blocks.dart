part of 'create_editor_models.dart';

List<CreateTextBlock> buildArticleBlocksFromDocument(
  ArticleDocumentData document,
) {
  final body = _normalizeArticleBody(document.body);
  final semanticBlocks =
      document.blocks
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
  final assets =
      document.assets.where((asset) => asset.hasImage).toList(growable: false)
        ..sort((left, right) => left.offset.compareTo(right.offset));
  final blocks = <CreateTextBlock>[];
  var cursor = 0;
  var textSeed = 0;
  var semanticIndex = 0;
  var assetIndex = 0;

  void appendTextSegment(String value) {
    final lines = _normalizeArticleBody(value)
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .toList(growable: false);
    for (final line in lines) {
      final orderedMatch = _orderedArticleLinePattern.firstMatch(line);
      if (orderedMatch != null) {
        final content = line.substring(orderedMatch.end).trim();
        blocks.add(
          CreateTextBlock.orderedItem(
            id: 'ordered_${textSeed++}',
            text: content,
          ),
        );
      } else {
        final bulletMatch = _bulletArticleLinePattern.firstMatch(line);
        if (bulletMatch != null) {
          final content = line.substring(bulletMatch.end).trim();
          blocks.add(
            CreateTextBlock.bulletItem(
              id: 'bullet_${textSeed++}',
              text: content,
            ),
          );
        } else {
          blocks.add(
            CreateTextBlock.paragraph(
              id: 'paragraph_${textSeed++}',
              text: line,
            ),
          );
        }
      }
    }
  }

  while (semanticIndex < semanticBlocks.length || assetIndex < assets.length) {
    final nextSemanticOffset = semanticIndex < semanticBlocks.length
        ? semanticBlocks[semanticIndex].offset.clamp(cursor, body.length)
        : body.length;
    final nextAssetOffset = assetIndex < assets.length
        ? assets[assetIndex].offset.clamp(cursor, body.length)
        : body.length;
    final nextOffset = nextSemanticOffset < nextAssetOffset
        ? nextSemanticOffset
        : nextAssetOffset;
    appendTextSegment(body.substring(cursor, nextOffset));
    cursor = nextOffset;

    while (semanticIndex < semanticBlocks.length &&
        semanticBlocks[semanticIndex].offset.clamp(0, body.length) <= cursor) {
      blocks.add(_editorBlockFromDocumentBlock(semanticBlocks[semanticIndex]));
      semanticIndex += 1;
    }
    while (assetIndex < assets.length &&
        assets[assetIndex].offset.clamp(0, body.length) <= cursor) {
      final asset = assets[assetIndex];
      blocks.add(
        CreateTextBlock.image(
          id: asset.id,
          imagePath: asset.imageUrl.trim(),
          imageLayout: _imageLayoutFromPage(asset.imageLayout),
        ),
      );
      assetIndex += 1;
    }
  }
  appendTextSegment(body.substring(cursor));

  if (blocks.isEmpty) {
    return createDefaultArticleBlocks();
  }
  return blocks;
}
