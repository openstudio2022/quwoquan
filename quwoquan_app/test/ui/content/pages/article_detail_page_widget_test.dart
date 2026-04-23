import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/pages/article_detail_page.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

class _ArticleGetPostRepo extends MockContentRepository {
  _ArticleGetPostRepo(this._item);

  final Map<String, dynamic> _item;

  @override
  Future<ContentPostDetailPayload> getPost({required String postId}) async =>
      ContentPostDetailPayload.fromWire(_item);
}

void main() {
  testWidgets('ArticleDetailPage 渲染连续图文阅读布局', (tester) async {
    final article = <String, dynamic>{
      'postId': 'art_continuous',
      'contentType': 'article',
      'authorId': 'writer1',
      'displayName': '连续阅读作者',
      'authorAvatarUrl': 'https://example.com/avatar.jpg',
      'title': '连续阅读标题',
      'body': '这里是摘要',
      'coverUrl': 'https://example.com/cover.jpg',
      'likeCount': 12,
      'commentCount': 4,
      'favoriteCount': 6,
      'shareCount': 3,
      'publishedAt': '2026-03-21T08:00:00Z',
      'articleBlocks': <Map<String, dynamic>>[
        {'id': 'p1', 'type': 'paragraph', 'text': '第一段内容', 'imagePath': ''},
        {'id': 'o1', 'type': 'orderedItem', 'text': '第二条清单', 'imagePath': ''},
        {
          'id': 'i1',
          'type': 'image',
          'text': '',
          'imagePath': 'https://example.com/inline.jpg',
        },
      ],
    };

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          contentRepositoryProvider.overrideWithValue(
            _ArticleGetPostRepo(article),
          ),
          behaviorRepositoryProvider.overrideWithValue(
            MockBehaviorRepository(),
          ),
        ],
        child: MaterialApp(
          locale: const Locale('zh'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: const ArticleDetailPage(articleId: 'art_continuous'),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('连续阅读标题'), findsWidgets);
    expect(find.text('连续阅读作者'), findsOneWidget);
    expect(find.text('文章内容'), findsOneWidget);
    expect(find.textContaining('第一段内容'), findsWidgets);
    expect(find.textContaining('1. 第二条清单'), findsWidgets);
    expect(find.byType(CachedNetworkImage), findsNWidgets(3));
    expect(find.text('分享'), findsOneWidget);
  });

  testWidgets('ArticleReadOnlyBookDeck 会锁定 pageflip stage 宽度', (tester) async {
    const surfaceSize = Size(1440, 900);
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = surfaceSize;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final article = <String, dynamic>{
      'postId': 'art_continuous',
      'contentType': 'article',
      'authorId': 'writer1',
      'displayName': '连续阅读作者',
      'authorAvatarUrl': 'https://example.com/avatar.jpg',
      'title': '连续阅读标题',
      'body': '这里是摘要',
      'coverUrl': 'https://example.com/cover.jpg',
      'likeCount': 12,
      'commentCount': 4,
      'favoriteCount': 6,
      'shareCount': 3,
      'publishedAt': '2026-03-21T08:00:00Z',
      'articleBlocks': <Map<String, dynamic>>[
        {'id': 'p1', 'type': 'paragraph', 'text': '第一段内容', 'imagePath': ''},
      ],
    };

    double? capturedStageWidth;

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          contentRepositoryProvider.overrideWithValue(
            _ArticleGetPostRepo(article),
          ),
          behaviorRepositoryProvider.overrideWithValue(
            MockBehaviorRepository(),
          ),
        ],
        child: MaterialApp(
          locale: const Locale('zh'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: Column(
              children: [
                Expanded(
                  child: SingleChildScrollView(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      AppSpacing.containerMd,
                      AppSpacing.containerMd,
                      AppSpacing.containerLg,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        LayoutBuilder(
                          builder: (context, constraints) {
                            final metrics = resolveArticleCanvasMetrics(
                              context,
                              constraints,
                              variant: ArticleCanvasVariant.detail,
                            );
                            final pagePadding = articleReaderStagePagePadding();
                            final stageWidth = resolveArticlePaperStageWidth(
                              context,
                              constraints,
                              stagePadding: pagePadding,
                              allowLandscapeSpread: true,
                            );
                            final stageHeight =
                                metrics.frameSpecForStageWidth(stageWidth).paperSize.height +
                                pagePadding.vertical;
                            capturedStageWidth = stageWidth;
                            return UnconstrainedBox(
                              alignment: Alignment.topCenter,
                              child: SizedBox(
                                width: stageWidth,
                                height: stageHeight,
                                child: ArticleReadOnlyBookDeck(
                                  pages: _pagesFrom(article),
                                  template: ArticleTemplatePreset.tech,
                                  fontPreset: ArticleFontPreset.mono,
                                  metrics: metrics,
                                  pagePadding: pagePadding,
                                  coverUrl: '',
                                  showFooterPageLabel: false,
                                ),
                              ),
                            );
                          },
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(capturedStageWidth, isNotNull);
    final outerWidth = surfaceSize.width - AppSpacing.containerMd * 2;
    final stageSize = tester.getSize(find.byKey(TestKeys.articlePageCurlLayer));
    final visiblePage = tester.widgetList<ArticlePageShell>(
      find.byType(ArticlePageShell),
    ).first;
    final visiblePageFinder = find.byWidget(visiblePage);
    final pageSize = tester.getSize(visiblePageFinder);

    expect(stageSize.width, closeTo(capturedStageWidth!, 0.01));
    expect(stageSize.width, lessThan(outerWidth));
    expect(pageSize.width, lessThan(outerWidth));
    expect(pageSize.width, lessThan(stageSize.width));
    expect(pageSize.width, lessThan(surfaceSize.width));
  });

  testWidgets('ArticleReadOnlyBookDeck 支持前翻后翻回到原页', (tester) async {
    const surfaceSize = Size(1440, 900);
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = surfaceSize;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final pageChanges = <int>[];

    await tester.pumpWidget(
      MaterialApp(
        locale: const Locale('zh'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: LayoutBuilder(
            builder: (context, constraints) {
              final metrics = resolveArticleCanvasMetrics(
                context,
                constraints,
                variant: ArticleCanvasVariant.detail,
              );
              final pagePadding = articleReaderStagePagePadding();
              final stageWidth = resolveArticlePaperStageWidth(
                context,
                constraints,
                stagePadding: pagePadding,
                allowLandscapeSpread: true,
              );
              final stageHeight =
                  metrics.frameSpecForStageWidth(stageWidth).paperSize.height +
                  pagePadding.vertical;
              return Center(
                child: SizedBox(
                  width: stageWidth,
                  height: stageHeight,
                  child: ArticleReadOnlyBookDeck(
                    pages: _bookPages(),
                    template: ArticleTemplatePreset.tech,
                    fontPreset: ArticleFontPreset.mono,
                    metrics: metrics,
                    pagePadding: pagePadding,
                    coverUrl: '',
                    showFooterPageLabel: false,
                    onPageChanged: pageChanges.add,
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
      const Offset(260, -40),
    );
    await tester.pumpAndSettle();

    expect(pageChanges.length, greaterThanOrEqualTo(2));
    expect(
      pageChanges.sublist(pageChanges.length - 2),
      equals(<int>[1, 0]),
    );
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);
  });
}

List<ArticlePageData> _pagesFrom(Map<String, dynamic> article) {
  return <ArticlePageData>[
    ArticlePageData(
      id: 'page_0',
      title: article['title'] as String,
      body: article['body'] as String,
    ),
  ];
}

List<ArticlePageData> _bookPages() {
  return const <ArticlePageData>[
    ArticlePageData(id: 'page_0', title: '第一页', body: '第一页正文'),
    ArticlePageData(id: 'page_1', title: '第二页', body: '第二页正文'),
  ];
}
