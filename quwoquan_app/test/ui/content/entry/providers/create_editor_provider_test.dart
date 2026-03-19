import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';

void main() {
  test('重排图片后保持新的顺序结果', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setImages(<String>[
      'a.png',
      'b.png',
      'c.png',
    ], editorKind: CreateEditorKind.media);
    notifier.setCurrentMediaIndex(2);

    notifier.reorderImages(2, 0);

    final state = container.read(createEditorProvider);
    expect(state.imagePaths, <String>['c.png', 'a.png', 'b.png']);
  });
}
