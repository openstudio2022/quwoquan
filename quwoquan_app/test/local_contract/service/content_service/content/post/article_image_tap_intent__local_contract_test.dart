// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-017
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-017.t3

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_asset.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_content_block_renderer.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/content/article_reader_page_surfaces.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/pageflip/host/article_read_only_book_deck.dart';

const ArticleDocumentAsset _fullWidthAsset = ArticleDocumentAsset(
  id: 'asset-full-canonical',
  offset: 0,
  imageUrl: 'diagnostic://pageflip/FULL',
);
const ArticleDocumentAsset _wrappedAsset = ArticleDocumentAsset(
  id: 'asset-wrap-canonical',
  offset: 16,
  imageUrl: 'diagnostic://pageflip/WRAP',
  imageLayout: 'wrapLeft',
);

void main() {
  testWidgets('正文图片 tap 上报 canonical asset，并赢过文章 curl 点击翻页', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final tapped = <ArticleDocumentAsset>[];
    final changedPages = <int>[];
    final commits = <ArticleReaderPageFlipCommit>[];

    await tester.pumpWidget(
      MaterialApp(
        home: ArticleReadOnlyBookDeck(
          pages: const <ArticlePageData>[
            ArticlePageData(
              id: 'page-0',
              fragments: <ArticleLayoutFragment>[
                ArticleLayoutFragment(
                  kind: ArticleLayoutFragmentKind.fullWidthImage,
                  asset: _fullWidthAsset,
                ),
              ],
            ),
            ArticlePageData(id: 'page-1', body: '第二页用于证明 curl 确实可触发'),
          ],
          template: ArticleTemplatePreset.gentle,
          fontPreset: ArticleFontPreset.clean,
          metrics: ArticleCanvasMetrics.snapshot(),
          enablePageCurl: true,
          showFooterPageLabel: false,
          onPageChanged: changedPages.add,
          onPageFlipCommitted: commits.add,
          onImageTap: tapped.add,
        ),
      ),
    );
    await tester.pump();
    for (var frame = 0; frame < 8; frame += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    changedPages.clear();
    commits.clear();

    final image = find.byType(ArticleAdaptiveImage).hitTestable().first;
    expect(image, findsOneWidget);
    await tester.tap(image);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 320));

    expect(tapped.map((asset) => asset.id), <String>[_fullWidthAsset.id]);
    expect(changedPages, isEmpty, reason: '图片 tap 必须被子图片层吸收，不得同时触发文章翻页');
    expect(commits, isEmpty, reason: '图片 tap 不得产生 page_curl commit 事实');
  });

  testWidgets('环绕图片沿同一 typed 通道上报对应 canonical asset', (tester) async {
    final tapped = <ArticleDocumentAsset>[];
    await tester.pumpWidget(
      MaterialApp(
        home: SizedBox(
          width: 390,
          height: 700,
          child: ArticlePageReadOnlyView(
            page: const ArticlePageData(
              id: 'wrap-page',
              fragments: <ArticleLayoutFragment>[
                ArticleLayoutFragment(
                  kind: ArticleLayoutFragmentKind.wrapContent,
                  text: '环绕图片旁的正文用于形成真实布局。',
                  asset: _wrappedAsset,
                ),
              ],
            ),
            template: ArticleTemplatePreset.gentle,
            fontPreset: ArticleFontPreset.clean,
            onImageTap: tapped.add,
          ),
        ),
      ),
    );
    await tester.pump();

    await tester.tap(find.byType(ArticleAdaptiveImage).hitTestable().first);
    await tester.pump();

    expect(tapped.map((asset) => asset.id), <String>[_wrappedAsset.id]);
  });
}
