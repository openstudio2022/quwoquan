import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/content/content/post/application/create_editor_provider.dart';

void main() {
  test('四图链路里第二张图片之后仍可插入正文 node', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final paragraphId = container
        .read(createEditorProvider)
        .articleDocument
        .nodes
        .firstWhere((node) => node.isBodyText)
        .id;
    final firstFigureId = notifier.insertImageAfterNode(paragraphId, 'a.png');
    final secondFigureId = notifier.insertImageAfterNode(
      firstFigureId,
      'b.png',
    );
    final thirdFigureId = notifier.insertImageAfterNode(
      secondFigureId,
      'c.png',
    );
    notifier.insertImageAfterNode(thirdFigureId, 'd.png');
    final insertedTextId = notifier.insertTextNodeAfter(
      secondFigureId,
      initialText: '第二处图间正文',
    );

    final state = container.read(createEditorProvider);
    expect(state.articleDocument.assets.length, 4);
    expect(state.articleDocument.body, contains('第二处图间正文'));
    final nodes = state.articleDocument.nodes;
    expect(
      nodes.indexWhere((node) => node.id == insertedTextId),
      lessThan(nodes.indexWhere((node) => node.id == thirdFigureId)),
    );
    expect(
      state.articlePages.any((page) => page.body.contains('第二处图间正文')),
      isTrue,
    );
  });
}
