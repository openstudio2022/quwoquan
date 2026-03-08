import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';

void main() {
  group('BehaviorRepository — 常规契约', () {
    late MockBehaviorRepository repo;

    setUp(() {
      repo = MockBehaviorRepository();
    });

    test('reportEvents 记录行为事件', () async {
      await repo.reportEvents(events: [
        BehaviorEvent(contentId: 'post_1', action: 'impression'),
        BehaviorEvent(contentId: 'post_2', action: 'click'),
      ]);
      expect(repo.recorded.length, 2);
    });

    test('reportSingle 记录单个事件', () async {
      await repo.reportSingle(
        contentId: 'post_3',
        action: 'share',
      );
      expect(repo.recorded.length, 1);
      expect(repo.recorded.first.action, 'share');
      expect(repo.recorded.first.contentId, 'post_3');
    });

    test('BehaviorEvent 支持 tags 和 duration', () {
      final event = BehaviorEvent(
        contentId: 'post_4',
        action: 'dwell',
        tags: ['photo'],
        duration: 3.5,
      );
      expect(event.contentId, 'post_4');
      expect(event.action, 'dwell');
      expect(event.tags, ['photo']);
      expect(event.duration, 3.5);
    });
  });

  group('BehaviorRepository — 异常/边界契约', () {
    late MockBehaviorRepository repo;

    setUp(() {
      repo = MockBehaviorRepository();
    });

    test('reportEvents 空事件列表不崩溃', () async {
      await repo.reportEvents(events: []);
      expect(repo.recorded, isEmpty);
    });
  });
}
