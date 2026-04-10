import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/entry/pages/article_typography_page.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';

void main() {
  testWidgets('排版页可独立挂载', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 2200));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final anchorId = container
        .read(createEditorProvider)
        .articleBlocks
        .first
        .id;
    notifier.insertArticleImages(<String>[
      '/tmp/article_cover.png',
    ], afterBlockId: anchorId);
    notifier.setArticleCoverImage('/tmp/article_cover.png');
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ArticleTypographyPage()),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.byType(ArticleTypographyPage), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  });
}
