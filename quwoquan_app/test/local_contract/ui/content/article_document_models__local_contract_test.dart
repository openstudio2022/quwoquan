import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/models/article_document_models.dart';

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

  test('copyWith nodes 更新标题时保留 canonical body 节点顺序', () {
    final original = ArticleDocumentData(
      nodes: <ArticleDocumentNode>[
        const ArticleDocumentNode(
          id: 'document_title',
          type: ArticleDocumentNodeType.documentTitle,
          text: '旧标题',
        ),
        const ArticleDocumentNode(
          id: 'p1',
          type: ArticleDocumentNodeType.paragraph,
          text: '第一段',
        ),
        const ArticleDocumentNode(
          id: 'fig_1',
          type: ArticleDocumentNodeType.figure,
          imageUrl: 'file:///image.jpg',
          imageLayout: 'wrapLeft',
        ),
        const ArticleDocumentNode(
          id: 'p2',
          type: ArticleDocumentNodeType.paragraph,
          text: '第二段',
        ),
      ],
    );

    final updated = original.copyWith(
      nodes: original.nodes
          .map(
            (node) => node.isDocumentTitle ? node.copyWith(text: '新标题') : node,
          )
          .toList(growable: false),
    );

    expect(updated.title, '新标题');
    expect(
      updated.nodes.map((node) => node.id).toList(growable: false),
      <String>['document_title', 'p1', 'fig_1', 'p2'],
    );
    expect(updated.body, '第一段\n第二段');
    expect(updated.assets.single.id, 'fig_1');
  });

  // ── 阶段 1 回归测试：nodes 为唯一真相源 ──

  test('body/assets/title 只从 nodes 投影', () {
    final doc = ArticleDocumentData(
      nodes: const <ArticleDocumentNode>[
        ArticleDocumentNode(
          id: 'title_1',
          type: ArticleDocumentNodeType.documentTitle,
          text: '标题',
        ),
        ArticleDocumentNode(
          id: 'p1',
          type: ArticleDocumentNodeType.paragraph,
          text: '正文内容',
        ),
        ArticleDocumentNode(
          id: 'fig_1',
          type: ArticleDocumentNodeType.figure,
          imageUrl: '/img.jpg',
          imageLayout: 'wrapLeft',
          caption: '图说',
        ),
      ],
    );

    expect(doc.body, '正文内容');
    expect(doc.assets.length, 1);
    expect(doc.assets.first.imageUrl, '/img.jpg');
    expect(doc.assets.first.caption, '图说');
    expect(doc.title, '标题');
  });

  test('fromMap 不再从旧 title/body/assets/blocks 键反向构造 nodes', () {
    final document = ArticleDocumentData.fromMap(<String, dynamic>{
      'title': '旧标题',
      'body': '旧正文',
      'assets': <Map<String, dynamic>>[
        <String, dynamic>{'id': 'old_asset', 'imageUrl': '/old.jpg'},
      ],
      'blocks': <Map<String, dynamic>>[
        <String, dynamic>{'id': 'old_block', 'type': 'paragraph', 'text': '旧块'},
      ],
    });

    expect(document.nodes, isEmpty);
    expect(document.title, isEmpty);
    expect(document.body, isEmpty);
    expect(document.assets, isEmpty);
  });

  test('copyWith(nodes: ...) 后 body/assets 自动更新', () {
    final original = ArticleDocumentData(
      nodes: const <ArticleDocumentNode>[
        ArticleDocumentNode(
          id: 'title_1',
          type: ArticleDocumentNodeType.documentTitle,
          text: '原标题',
        ),
        ArticleDocumentNode(
          id: 'p1',
          type: ArticleDocumentNodeType.paragraph,
          text: '原正文',
        ),
      ],
    );

    final updated = original.copyWith(
      nodes: const <ArticleDocumentNode>[
        ArticleDocumentNode(
          id: 'title_1',
          type: ArticleDocumentNodeType.documentTitle,
          text: '新标题',
        ),
        ArticleDocumentNode(
          id: 'p1',
          type: ArticleDocumentNodeType.paragraph,
          text: '新正文',
        ),
        ArticleDocumentNode(
          id: 'fig_1',
          type: ArticleDocumentNodeType.figure,
          imageUrl: '/new.jpg',
        ),
      ],
    );

    expect(updated.title, '新标题');
    expect(updated.body, '新正文');
    expect(updated.assets.length, 1);
    expect(updated.assets.first.imageUrl, '/new.jpg');
  });

  test('wrap 双段 paragraph 在 body 只读投影中保持连续文本', () {
    final document = ArticleDocumentData(
      nodes: const <ArticleDocumentNode>[
        ArticleDocumentNode(
          id: 'title_1',
          type: ArticleDocumentNodeType.documentTitle,
          text: '标题',
        ),
        ArticleDocumentNode(
          id: 'fig_1',
          type: ArticleDocumentNodeType.figure,
          imageUrl: '/img.jpg',
          imageLayout: 'wrapLeft',
        ),
        ArticleDocumentNode(
          id: 'p_narrow',
          type: ArticleDocumentNodeType.paragraph,
          text: '窄文',
        ),
        ArticleDocumentNode(
          id: 'p_below',
          type: ArticleDocumentNodeType.paragraph,
          text: '下文',
        ),
      ],
    );

    expect(document.body, '窄文下文');
    final wrapGroup = resolveArticleWrapNodeGroupByFigureId(
      document.nodes,
      'fig_1',
    );
    expect(wrapGroup, isNotNull);
    expect(wrapGroup!.narrowText, '窄文');
    expect(wrapGroup.belowText, '下文');
  });

  test('wrap 空下文 paragraph 会在 document.nodes 中保留', () {
    final document = ArticleDocumentData(
      nodes: const <ArticleDocumentNode>[
        ArticleDocumentNode(
          id: 'title_1',
          type: ArticleDocumentNodeType.documentTitle,
          text: '标题',
        ),
        ArticleDocumentNode(
          id: 'fig_1',
          type: ArticleDocumentNodeType.figure,
          imageUrl: '/img.jpg',
          imageLayout: 'wrapLeft',
        ),
        ArticleDocumentNode(
          id: 'p_narrow',
          type: ArticleDocumentNodeType.paragraph,
          text: '窄文',
        ),
        ArticleDocumentNode(
          id: 'p_below',
          type: ArticleDocumentNodeType.paragraph,
          text: '',
        ),
      ],
    );

    final contentNodes = document.nodes
        .where((node) => !node.isDocumentTitle)
        .toList(growable: false);
    expect(contentNodes.map((node) => node.id), <String>[
      'fig_1',
      'p_narrow',
      'p_below',
    ]);
    expect(document.body, '窄文');

    final wrapGroup = resolveArticleWrapNodeGroupByFigureId(
      document.nodes,
      'fig_1',
    );
    expect(wrapGroup, isNotNull);
    expect(wrapGroup!.belowParagraph, isNotNull);
    expect(wrapGroup.belowText, isEmpty);
  });
}
