import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_behaviors.g.dart';

/// 契约测试：ContentBehaviorTracker — 覆盖 mock.yaml behavior_scenarios
///
/// 验证：
/// - impression/click/dwell 写入缓冲（批量路由正确）
/// - 批量路由 == "/v1/content/behaviors"（对齐 service.yaml）
/// - trackLike 方法不存在（dedicated route）
void main() {
  setUp(() {
    // Reset queue before each test by sending a no-op flush
    ContentBehaviorTracker.reset();
  });

  group('ContentBehaviorTracker — behavior_scenarios contract', () {
    test('batch_route_matches_service_yaml — route == /v1/content/behaviors', () {
      expect(ContentBehaviorTracker.batchRoute, equals('/v1/content/behaviors'));
    });

    test('impression_goes_to_batch — enqueues impression event, not flushed', () {
      ContentBehaviorTracker.trackImpression('post1');
      final queue = ContentBehaviorTracker.pendingQueue;
      expect(queue, hasLength(1));
      expect(queue.first['type'], equals('impression'));
      expect(queue.first['postId'], equals('post1'));
    });

    test('click enqueues click event with correct type', () {
      ContentBehaviorTracker.trackClick('post1');
      final queue = ContentBehaviorTracker.pendingQueue;
      expect(queue, hasLength(1));
      expect(queue.first['type'], equals('click'));
      expect(queue.first['postId'], equals('post1'));
    });

    test('dwell_includes_ms — enqueues dwell event with dwellMs', () {
      ContentBehaviorTracker.trackDwell('post1', 15000);
      final queue = ContentBehaviorTracker.pendingQueue;
      expect(queue, hasLength(1));
      expect(queue.first['type'], equals('dwell'));
      expect(queue.first['postId'], equals('post1'));
      expect(queue.first['dwellMs'], equals(15000));
    });

    test('multiple events accumulate in queue', () {
      ContentBehaviorTracker.trackImpression('p1');
      ContentBehaviorTracker.trackImpression('p2');
      ContentBehaviorTracker.trackClick('p1');
      expect(ContentBehaviorTracker.pendingQueue, hasLength(3));
    });

    test('like_not_in_behavior_tracker — no trackLike method exists', () {
      // This test documents the contract: trackLike is NOT on BehaviorTracker.
      // The test passes by compilation: there is no such symbol.
      // We verify indirectly: none of the queued event types should be 'like'.
      ContentBehaviorTracker.trackImpression('x');
      ContentBehaviorTracker.trackClick('x');
      ContentBehaviorTracker.trackDwell('x', 1000);
      ContentBehaviorTracker.trackShare('x');
      ContentBehaviorTracker.trackDislike('x');

      final types = ContentBehaviorTracker.pendingQueue
          .map((e) => e['type'] as String)
          .toSet();
      expect(types, isNot(contains('like')));
    });

    test('impression carries feedPosition when provided', () {
      ContentBehaviorTracker.trackImpression('post1', feedPosition: 3);
      final event = ContentBehaviorTracker.pendingQueue.first;
      expect(event['feedPosition'], equals(3));
    });

    test('share carries shareTarget when provided', () {
      ContentBehaviorTracker.trackShare('post1', shareTarget: 'wechat');
      final event = ContentBehaviorTracker.pendingQueue.first;
      expect(event['shareTarget'], equals('wechat'));
    });
  });
}
