import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/content/content/post/adapters/create_draft_session_controller.dart';

void main() {
  test('草稿自动保存失败进入可见失败态并上报原始异常语义', () async {
    final expected = StateError('persist failed');
    Object? recordedError;
    StackTrace? recordedStackTrace;
    String? recordedReason;
    final controller = CreateDraftSessionController(
      onFlushDirty: (_) async => throw expected,
      onFlushFailure: (error, stackTrace, reason) {
        recordedError = error;
        recordedStackTrace = stackTrace;
        recordedReason = reason;
      },
    );
    addTearDown(controller.dispose);

    controller.markDirty();
    await controller.flushIfDirty(reason: 'focus_loss');

    expect(controller.saveStatus, CreateDraftSaveStatus.failed);
    expect(recordedError, same(expected));
    expect(recordedStackTrace, isNotNull);
    expect(recordedReason, 'focus_loss');
  });

  test('草稿自动保存成功只更新保存态且不产生失败上报', () async {
    var failureCount = 0;
    final controller = CreateDraftSessionController(
      onFlushDirty: (_) async {},
      onFlushFailure: (_, _, _) => failureCount += 1,
    );
    addTearDown(controller.dispose);

    controller.markDirty();
    await controller.flushIfDirty(reason: 'manual');

    expect(controller.saveStatus, CreateDraftSaveStatus.saved);
    expect(failureCount, 0);
  });
}
