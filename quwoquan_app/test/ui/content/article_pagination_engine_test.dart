import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_pagination_engine.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';

void main() {
  group('ArticlePaginationEngine', () {
    test('paginateSnapshot forwards contentHeightOverride to paginate', () {
      final doc = ArticleDocumentData(
        body: List<String>.filled(1200, '行').join('\n'),
      );
      final loose = ArticlePaginationEngine.paginateSnapshot(
        document: doc,
        stageWidth: 360,
        contentHeightOverride: 520,
      );
      final tight = ArticlePaginationEngine.paginateSnapshot(
        document: doc,
        stageWidth: 360,
        contentHeightOverride: 140,
      );
      expect(tight.length, greaterThanOrEqualTo(loose.length));
    });

    test('fullWidth image after long body lands on a page after text pages', () {
      final body = List<String>.filled(800, '文').join();
      const assetId = 'tail_image';
      final doc = ArticleDocumentData(
        body: body,
        assets: <ArticleDocumentAsset>[
          ArticleDocumentAsset(
            id: assetId,
            offset: body.length,
            imageUrl: 'file:///placeholder.jpg',
            imageLayout: 'fullWidth',
          ),
        ],
      );
      final pages = ArticlePaginationEngine.paginateSnapshot(
        document: doc,
        stageWidth: 320,
        contentHeightOverride: 160,
      );
      expect(pages.length, greaterThan(1));
      final imagePageIndex = pages.indexWhere((ArticlePageData p) {
        final ids = p.binding?.resolvedAssetIds ?? const <String>[];
        return p.binding?.assetId == assetId || ids.contains(assetId);
      });
      expect(imagePageIndex, greaterThan(0));
    });
  });
}
