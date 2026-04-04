import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';

void main() {
  test('ArticleDocumentData toMap/fromMap 往返含 canonical nodes 与 spans', () {
    final original = ArticleDocumentData(
      template: 'journal',
      fontPreset: 'handwritten',
      coverImageUrl: 'https://example.com/cover.jpg',
      titleStyle: ArticleDocumentTitleStyle.minor,
      nodes: <ArticleDocumentNode>[
        const ArticleDocumentNode(
          id: 'title_1',
          type: ArticleDocumentNodeType.documentTitle,
          text: 'T',
        ),
        const ArticleDocumentNode(
          id: 'heading_1',
          type: ArticleDocumentNodeType.headingMajor,
          text: '第一章',
          textAlign: 'center',
        ),
        const ArticleDocumentNode(
          id: 'p1',
          type: ArticleDocumentNodeType.paragraph,
          text: 'hello',
          spans: <ArticleInlineSpan>[
            ArticleInlineSpan(start: 0, end: 5, bold: true),
          ],
        ),
      ],
    );
    final map = original.toMap();
    final restored = ArticleDocumentData.fromMap(map);
    expect(restored.template, 'journal');
    expect(restored.fontPreset, 'handwritten');
    expect(restored.coverImageUrl, 'https://example.com/cover.jpg');
    expect(restored.titleStyle, ArticleDocumentTitleStyle.minor);
    expect(restored.title, 'T');
    expect(restored.blocks.single.textAlign, 'center');
    expect(restored.nodes.last.spans.single.bold, isTrue);
    expect(restored.body, 'hello');
  });
}
