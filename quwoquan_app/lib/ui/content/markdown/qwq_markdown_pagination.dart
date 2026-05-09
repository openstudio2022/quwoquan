import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

import 'qwq_markdown_ast.dart';

@immutable
class QwqMarkdownPaginationProfile {
  const QwqMarkdownPaginationProfile({
    required this.viewportSize,
    this.textScaleFactor = 1,
    this.template = 'journal',
    this.fontPreset = 'clean',
    this.horizontalPadding = 24,
    this.verticalPadding = 28,
  });

  final Size viewportSize;
  final double textScaleFactor;
  final String template;
  final String fontPreset;
  final double horizontalPadding;
  final double verticalPadding;

  bool get isCompactWidth => viewportSize.width < 420 || textScaleFactor >= 1.25;

  double get effectiveHeight =>
      (viewportSize.height - verticalPadding * 2).clamp(240, 2400).toDouble();
}

@immutable
class QwqMarkdownPageData {
  const QwqMarkdownPageData({
    required this.pageIndex,
    required this.blocks,
    required this.profile,
  });

  final int pageIndex;
  final List<QwqMarkdownBlock> blocks;
  final QwqMarkdownPaginationProfile profile;

  List<String> get blockIds => blocks.map((block) => block.id).toList(growable: false);

  Map<String, Object?> toMap() {
    return <String, Object?>{
      'pageIndex': pageIndex,
      'blockIds': blockIds,
      'isCompactWidth': profile.isCompactWidth,
    };
  }
}

class MarkdownPaginationEngine {
  const MarkdownPaginationEngine();

  List<QwqMarkdownPageData> paginate({
    required QwqMarkdownDocument document,
    required QwqMarkdownPaginationProfile profile,
  }) {
    if (document.blocks.isEmpty) {
      return <QwqMarkdownPageData>[
        QwqMarkdownPageData(pageIndex: 0, blocks: const <QwqMarkdownBlock>[], profile: profile),
      ];
    }
    final maxUnits = _pageCapacityUnits(profile);
    final pages = <QwqMarkdownPageData>[];
    var current = <QwqMarkdownBlock>[];
    var usedUnits = 0;

    void flush() {
      if (current.isEmpty) {
        return;
      }
      pages.add(
        QwqMarkdownPageData(
          pageIndex: pages.length,
          blocks: List<QwqMarkdownBlock>.unmodifiable(current),
          profile: profile,
        ),
      );
      current = <QwqMarkdownBlock>[];
      usedUnits = 0;
    }

    for (final block in document.blocks) {
      final normalizedBlock = _normalizeBlockForProfile(block, profile);
      final blockUnits = _estimateBlockUnits(normalizedBlock, profile);
      if (current.isNotEmpty && usedUnits + blockUnits > maxUnits) {
        flush();
      }
      current.add(normalizedBlock);
      usedUnits += blockUnits;
      if (blockUnits >= maxUnits) {
        flush();
      }
    }
    flush();
    return pages;
  }

  int _pageCapacityUnits(QwqMarkdownPaginationProfile profile) {
    final heightFactor = profile.effectiveHeight / 36;
    final scaleFactor = profile.textScaleFactor.clamp(1, 2);
    return (heightFactor / scaleFactor).floor().clamp(6, 42);
  }

  int _estimateBlockUnits(
    QwqMarkdownBlock block,
    QwqMarkdownPaginationProfile profile,
  ) {
    final textUnits = (block.text.trim().length / 42).ceil().clamp(1, 12);
    return switch (block.kind) {
      QwqMarkdownBlockKind.heading => 2 + block.level.clamp(1, 3),
      QwqMarkdownBlockKind.paragraph => textUnits,
      QwqMarkdownBlockKind.orderedItem || QwqMarkdownBlockKind.bulletItem => textUnits,
      QwqMarkdownBlockKind.quote => textUnits + 1,
      QwqMarkdownBlockKind.codeBlock => (block.text.split('\n').length + 1).clamp(2, 16),
      QwqMarkdownBlockKind.image => profile.isCompactWidth ? 8 : 7,
      QwqMarkdownBlockKind.figure => _figureUnits(block, profile),
      QwqMarkdownBlockKind.gallery => profile.isCompactWidth ? 12 : 10,
      QwqMarkdownBlockKind.callout => textUnits + 2,
      QwqMarkdownBlockKind.card => textUnits + 3,
      QwqMarkdownBlockKind.section => 3,
      QwqMarkdownBlockKind.spacer => 1,
      QwqMarkdownBlockKind.horizontalRule => 1,
    };
  }

  int _figureUnits(QwqMarkdownBlock block, QwqMarkdownPaginationProfile profile) {
    final layout = block.assetRef?.layout ?? QwqMarkdownImageLayout.fullWidth;
    if (profile.isCompactWidth || layout == QwqMarkdownImageLayout.fullWidth) {
      return 9;
    }
    return 6;
  }

  QwqMarkdownBlock _normalizeBlockForProfile(
    QwqMarkdownBlock block,
    QwqMarkdownPaginationProfile profile,
  ) {
    final asset = block.assetRef;
    if (!profile.isCompactWidth ||
        asset == null ||
        asset.layout == QwqMarkdownImageLayout.fullWidth) {
      return block;
    }
    return QwqMarkdownBlock(
      id: block.id,
      kind: block.kind,
      text: block.text,
      level: block.level,
      language: block.language,
      inlines: block.inlines,
      assetRef: QwqMarkdownAssetRef(
        assetId: asset.assetId,
        kind: asset.kind,
        layout: QwqMarkdownImageLayout.fullWidth,
        caption: asset.caption,
        alt: asset.alt,
        sourceUrl: asset.sourceUrl,
        width: asset.width,
        height: asset.height,
      ),
      assetRefs: block.assetRefs,
      children: block.children,
      attributes: <String, Object?>{
        ...block.attributes,
        'layoutDowngradedFrom': asset.layout.name,
      },
      sourceStartLine: block.sourceStartLine,
      sourceEndLine: block.sourceEndLine,
    );
  }
}
