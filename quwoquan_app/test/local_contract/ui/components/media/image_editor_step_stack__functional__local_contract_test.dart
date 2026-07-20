import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/image/editor/models/image_editor_step.dart';
import 'package:quwoquan_app/components/media/image/editor/models/image_editor_step_payload.dart';
import 'package:quwoquan_app/components/media/image/editor/shared/image_editor_step_stack.dart';

ImageEditorStep _step(String tag, {int index = 0}) {
  return ImageEditorStep(
    payload: ImageEditorCropStepPayload(ratio: tag),
    imageIndex: index,
    beforePath: '/tmp/$tag-before.png',
    afterPath: '/tmp/$tag-after.png',
  );
}

String _tagOf(ImageEditorStep step) =>
    (step.payload as ImageEditorCropStepPayload).ratio;

void main() {
  group('ImageEditorStepStack 文件快照撤销/重做语义', () {
    test('push 后可撤销；undo 返回被撤销步骤且移入重做栈', () {
      final stack = ImageEditorStepStack();
      expect(stack.canUndo, isFalse);
      stack.push(_step('crop'));
      stack.push(_step('filter'));
      expect(stack.canUndo, isTrue);
      expect(stack.length, 2);

      final undone = stack.undo();
      expect(undone == null ? null : _tagOf(undone), 'filter');
      expect(stack.length, 1);
      expect(stack.canRedo, isTrue);

      final redone = stack.redo();
      expect(redone == null ? null : _tagOf(redone), 'filter');
      expect(stack.length, 2);
      expect(stack.canRedo, isFalse);
    });

    test('撤销后 push 新步骤清空重做栈（标准编辑器语义）', () {
      final stack = ImageEditorStepStack();
      stack.push(_step('crop'));
      stack.push(_step('filter'));
      stack.undo();
      expect(stack.canRedo, isTrue);
      stack.push(_step('mosaic'));
      expect(stack.canRedo, isFalse);
      expect(stack.committed.map(_tagOf), ['crop', 'mosaic']);
    });

    test('undoToBefore 弹出目标步骤及其后全部步骤，时间倒序返回', () {
      final stack = ImageEditorStepStack();
      stack.push(_step('crop'));
      stack.push(_step('filter'));
      stack.push(_step('text'));
      final popped = stack.undoToBefore(1);
      expect(popped.map(_tagOf), ['text', 'filter']);
      expect(stack.committed.map(_tagOf), ['crop']);
      expect(stack.canRedo, isTrue);
    });

    test('undoToBefore 越界索引不产生副作用', () {
      final stack = ImageEditorStepStack();
      stack.push(_step('crop'));
      expect(stack.undoToBefore(5), isEmpty);
      expect(stack.undoToBefore(-1), isEmpty);
      expect(stack.length, 1);
    });

    test('超出 maxSteps 时移除最早步骤', () {
      final stack = ImageEditorStepStack(maxSteps: 2);
      stack.push(_step('a'));
      stack.push(_step('b'));
      stack.push(_step('c'));
      expect(stack.committed.map(_tagOf), ['b', 'c']);
    });

    test('多图撤销重做始终返回原步骤所属 imageIndex', () {
      final stack = ImageEditorStepStack()
        ..push(_step('crop', index: 0))
        ..push(_step('curves', index: 2));

      expect(stack.undo()?.imageIndex, 2);
      expect(stack.undo()?.imageIndex, 0);
      expect(stack.redo()?.imageIndex, 0);
      expect(stack.redo()?.imageIndex, 2);
    });

    test('步骤快照字段完整（imageIndex/beforePath/afterPath）', () {
      final step = _step('rotate', index: 3);
      expect(step.imageIndex, 3);
      expect(step.beforePath, contains('before'));
      expect(step.afterPath, contains('after'));
      final copied = step.copyWith(afterPath: '/tmp/new.png');
      expect(copied.afterPath, '/tmp/new.png');
      expect(copied.beforePath, step.beforePath);
    });
  });
}
