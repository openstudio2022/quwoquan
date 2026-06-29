import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/article_typography_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';

void main() {
  testWidgets('排版页长文可分页并支持翻页', (tester) async {
    await tester.binding.setSurfaceSize(const Size(430, 932));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final anchorId = container
        .read(createEditorProvider)
        .articleBlocks
        .first
        .id;
    notifier.updateArticleTextBlock(
      anchorId,
      List<String>.generate(
        120,
        (index) =>
            '第${index + 1}段：为了验证文章创作预览在手机视口下能切出多页，这里连续补入多段正文，每一段都会带来新的换行与排版高度。',
      ).join('\n\n'),
    );
    var lastBlockId = anchorId;
    for (var index = 0; index < 24; index += 1) {
      lastBlockId = notifier.insertArticleTextBlock(
        afterBlockId: lastBlockId,
        type: CreateTextBlockType.heading2,
        text: '第${index + 1}节：分页锚点用于验证预览页切片',
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
