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
        BehaviorEvent(
          contentId: 'post_1',
          action: BehaviorAction.impression,
        ),
        BehaviorEvent(contentId: 'post_2', action: BehaviorAction.click),
      ]);
      expect(repo.recorded.length, 2);
    });

    test('reportSingle 记录单个事件', () async {
      await repo.reportSingle(
        contentId: 'post_3',
        action: BehaviorAction.share,
      );
      expect(repo.recorded.length, 1);
      expect(repo.recorded.first.action, BehaviorAction.share);
      expect(repo.recorded.first.contentId, 'post_3');
    });

    test('BehaviorEvent 支持 tags 和 duration', () {
      final event = BehaviorEvent(
        contentId: 'post_4',
        action: BehaviorAction.dwell,
        tags: ['photo'],
        duration: 3.5,
      );
      expect(event.contentId, 'post_4');
      expect(event.action, BehaviorAction.dwell);
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

  group('BehaviorAction — 端云枚举一致性', () {
    test('wireValue 与 Go supportedBehaviorActions 对齐', () {
      const expectedWireValues = <String>[
        'impression',
        'click',
        'dwell',
        'like',
        'favorite',
        'share',
        'dislike',
        'report',
        'skip',
        'comment',
        'follow',
        'author_view',
        'tag_click',
        'play_progress',
        'content_depth',
      ];
      final actualWireValues =
          BehaviorAction.values.map((a) => a.wireValue).toList();
      expect(actualWireValues, containsAll(expectedWireValues));
      expect(actualWireValues.length, expectedWireValues.length);
    });

    test('toJson 使用 wireValue 而非 enum name', () {
      final event = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorAction.authorView,
      );
      final json = event.toJson();
      expect(json['action'], 'author_view');
    });

    test('深度行为事件包含 engagementDepth 和 consumedRatio', () {
      final event = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorAction.contentDepth,
        engagementDepth: 3,
        consumedRatio: 0.85,
        totalUnits: 12,
      );
      final json = event.toJson();
      expect(json['engagementDepth'], 3);
      expect(json['consumedRatio'], 0.85);
      expect(json['totalUnits'], 12);
    });

    test('feedRequestId 透传到 JSON', () {
      final event = BehaviorEvent(
        contentId: 'post_1',
        action: BehaviorAction.impression,
        feedRequestId: 'req-uuid-123',
      );
      final json = event.toJson();
      expect(json['feedRequestId'], 'req-uuid-123');
    });
  });
}
