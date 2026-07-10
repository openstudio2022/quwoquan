import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';

void main() {
  test('四图链路里后续图片之后仍可 materialize 正文', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final firstPageId =
        container.read(createEditorProvider).articlePages.first.id;
    final p1 = notifier.insertArticleImageAtBodyOffset(
      'a.png',
      bodyInsertOffset: 0,
      fallbackActivePageId: firstPageId,
    );
    final p2 = notifier.insertArticleImageAfterPage(p1, 'b.png');
    final p3 = notifier.insertArticleImageAfterPage(p2, 'c.png');
    notifier.insertArticleImageAfterPage(p3, 'd.png');

    final targetAssetId =
        container.read(createEditorProvider).articleDocument.assets[1].id;
    final landingPageId = notifier.materializeArticleParagraphAfterAsset(
      targetAssetId,
      text: '第二处图间正文',
    );

    final state = container.read(createEditorProvider);
    expect(state.articleDocument.assets.length, 4);
    expect(state.articleDocument.body, contains('第二处图间正文'));
    expect(
      state.articlePages.any(
        (page) => page.id == landingPageId && page.body.contains('第二处图间正文'),
      ),
      isTrue,
    );
    expect(
      state.articleDocument.assets.last.offset,
      greaterThanOrEqualTo(state.articleDocument.assets[1].offset),
    );
  });
}
