import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/article_preview_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';

void main() {
  testWidgets('预览页可切换封面并与模板字体共用同一阅读壳层', (tester) async {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.updateTitle('扉页标题');
    final anchorId = container
        .read(createEditorProvider)
        .articleBlocks
        .first
        .id;
    notifier.updateArticleTextBlock(anchorId, '第一页导语');
    notifier.insertArticleImages(<String>[
      '/tmp/article_cover.png',
    ], afterBlockId: anchorId);
    notifier.setArticleCoverImage('/tmp/article_cover.png');
    notifier.setArticleTemplate(ArticleTemplatePreset.ritual);
    notifier.setArticleFontPreset(ArticleFontPreset.classic);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ArticlePreviewPage()),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('article-frontispiece-image')),
      findsOneWidget,
    );
    expect(find.byKey(TestKeys.articlePreviewCoverStrip), findsOneWidget);

    await tester.tap(find.text('等宽').first);
    await tester.pumpAndSettle();
    expect(
      container.read(createEditorProvider).articleFontPreset,
      ArticleFontPreset.mono,
    );

    await tester.tap(find.byKey(TestKeys.createArticleCoverNoneOption));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey<String>('article-frontispiece-image')),
      findsNothing,
    );
  });
}
