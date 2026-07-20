import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/article_reader/content/article_reader_pagination.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart';
import 'package:quwoquan_app/ui/content/models/article_document_models.dart';
import 'package:quwoquan_app/ui/content/models/article_editor_projection.dart';
import 'package:quwoquan_app/ui/content/models/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/article_typography_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';

void main() {
  testWidgets('含图文档在排版预览中优先走 document flow', (tester) async {
    const imagePath = 'diagnostic://pageflip/typography-picked-image';
    late List<ArticlePageData> resolvedPages;

    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) {
            resolvedPages = resolvePaginatedArticlePages(
              context: context,
              constraints: const BoxConstraints.tightFor(
                width: 430,
                height: 620,
              ),
              document: ArticleDocumentData(
                nodes: const <ArticleDocumentNode>[
                  ArticleDocumentNode(
                    id: 'picked_asset',
                    type: ArticleDocumentNodeType.figure,
                    assetId: 'picked_asset',
                    imageUrl: imagePath,
                  ),
                ],
              ),
              template: ArticleTemplatePreset.gentle,
              fontPreset: ArticleFontPreset.clean,
              fallbackPages: const <ArticlePageData>[
                ArticlePageData(id: 'fallback_0', body: '旧 fallback 首页'),
                ArticlePageData(id: 'fallback_1', body: '旧 fallback 结构页'),
              ],
              variant: ArticleCanvasVariant.preview,
              paperTexture: ArticlePaperTexture.darkPaper,
            );
            return const SizedBox.shrink();
          },
        ),
      ),
    );

    expect(
      resolvedPages.any(
        (page) =>
            page.imageUrl == imagePath ||
            page.fragments.any(
              (fragment) => fragment.asset?.imageUrl == imagePath,
            ),
      ),
      isTrue,
    );
    expect(
      resolvedPages.any((page) => page.id.startsWith('fallback_')),
      isFalse,
    );
  });

  testWidgets('排版页会显示编辑器插入的图片页', (tester) async {
    await tester.binding.setSurfaceSize(const Size(430, 932));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    const imagePath = 'diagnostic://pageflip/typography-picked-image';
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.updateTitle('图文排版预览');
    notifier.insertImageAfterNode(kArticleEditorStartAnchorId, imagePath);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ArticleTypographyPage()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    final deck = tester.widget<ArticleReadOnlyBookDeck>(
      find.byType(ArticleReadOnlyBookDeck),
    );
    expect(
      deck.pages.any(
        (page) =>
            page.imageUrl == imagePath ||
            page.fragments.any(
              (fragment) => fragment.asset?.imageUrl == imagePath,
            ),
      ),
      isTrue,
    );

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  });

  testWidgets('排版页长文可分页并支持翻页', (tester) async {
    await tester.binding.setSurfaceSize(const Size(430, 932));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final anchorId = container
        .read(createEditorProvider)
        .articleDocument
        .nodes
        .firstWhere((node) => node.isBodyText)
        .id;
    notifier.updateArticleNodeText(
      anchorId,
      List<String>.generate(
        120,
        (index) =>
            '第${index + 1}段：为了验证文章创作预览在手机视口下能切出多页，这里连续补入多段正文，每一段都会带来新的换行与排版高度。',
      ).join('\n\n'),
    );
    var lastBlockId = anchorId;
    for (var index = 0; index < 24; index += 1) {
      lastBlockId = notifier.insertTextNodeAfter(
        lastBlockId,
        type: ArticleDocumentNodeType.headingMajor,
        initialText: '第${index + 1}节：分页锚点用于验证预览页切片',
      );
    }

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ArticleTypographyPage()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.byType(ArticleTypographyPage), findsOneWidget);
    final deck = tester.widget<ArticleReadOnlyBookDeck>(
      find.byType(ArticleReadOnlyBookDeck),
    );
    expect(deck.pages.length, greaterThan(1));

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  });
}
