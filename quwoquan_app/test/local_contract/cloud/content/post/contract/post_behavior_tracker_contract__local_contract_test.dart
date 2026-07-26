import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_behaviors.g.dart';

/// L1a 契约测试：ContentBehaviorTracker — 覆盖 mock.yaml behavior_scenarios
///
/// 三维度覆盖：
///   常规契约  — 批量路由正确、各事件类型入队
///   单轨契约 — 重置后队列清空；多事件累积不串扰
///   异常/边界契约 — 无效参数不崩溃
void main() {
  setUp(() {
    ContentBehaviorTracker.reset();
  });

  // ──────────────────────────────────────────────────────────────────
  // 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('ContentBehaviorTracker — 常规契约', () {
    test('batch_route_matches_service_yaml — route == /content/behaviors', () {
      expect(ContentBehaviorTracker.batchRoute, equals('/content/behaviors'));
    });

    test('trackImpression enqueues impression event with postId and state', () {
      ContentBehaviorTracker.trackImpression('post1', 'visible');
      final queue = ContentBehaviorTracker.pendingQueue;
      expect(queue, hasLength(1));
      expect(queue.first['type'], equals('impression'));
      expect(queue.first['postId'], equals('post1'));
      expect(queue.first['state'], equals('visible'));
    });

    test('trackClick enqueues click event with correct type', () {
      ContentBehaviorTracker.trackClick('post1');
      final queue = ContentBehaviorTracker.pendingQueue;
      expect(queue, hasLength(1));
      expect(queue.first['type'], equals('click'));
      expect(queue.first['postId'], equals('post1'));
    });

    test('trackDwell enqueues dwell event with duration (seconds)', () {
      ContentBehaviorTracker.trackDwell('post1', 15);
      final queue = ContentBehaviorTracker.pendingQueue;
      expect(queue, hasLength(1));
      expect(queue.first['type'], equals('dwell'));
      expect(queue.first['postId'], equals('post1'));
      expect(queue.first['duration'], equals(15));
      expect(
        queue.first.containsKey('dwellMs'),
        isFalse,
        reason: '契约单轨：旧毫秒键 dwellMs 已删除',
      );
    });

    test('trackShare enqueues share event', () {
      ContentBehaviorTracker.trackShare('post1');
      final queue = ContentBehaviorTracker.pendingQueue;
      expect(queue, hasLength(1));
      expect(queue.first['type'], equals('share'));
    });

    test('trackDislike enqueues dislike event', () {
      ContentBehaviorTracker.trackDislike('post1', 'author1');
      final queue = ContentBehaviorTracker.pendingQueue;
      expect(queue, hasLength(1));
      expect(queue.first['type'], equals('dislike'));
    });

    test('impression payload no longer carries legacy feedPosition key', () {
      ContentBehaviorTracker.trackImpression('post1', 'impressed');
      final event = ContentBehaviorTracker.pendingQueue.first;
      expect(
        event.containsKey('feedPosition'),
        isFalse,
        reason: '契约单轨：位置唯一 wire 键为 common_fields.position',
      );
    });

    test('share carries shareTarget when provided', () {
      ContentBehaviorTracker.trackShare('post1', shareTarget: 'wechat');
      final event = ContentBehaviorTracker.pendingQueue.first;
      expect(event['shareTarget'], equals('wechat'));
    });

    test('like_not_in_behavior_tracker — queue types do not include like', () {
      ContentBehaviorTracker.trackImpression('x', 'impressed');
      ContentBehaviorTracker.trackClick('x');
      ContentBehaviorTracker.trackDwell('x', 1000);
      ContentBehaviorTracker.trackShare('x');
      ContentBehaviorTracker.trackDislike('x', 'author1');

      final types = ContentBehaviorTracker.pendingQueue
          .map((e) => e['type'] as String)
          .toSet();
      expect(types, isNot(contains('like')));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 单轨契约：重置/多事件累积
  // ──────────────────────────────────────────────────────────────────
  group('ContentBehaviorTracker — 单轨契约', () {
    test('multiple events accumulate in queue without dropping', () {
      ContentBehaviorTracker.trackImpression('p1', 'visible');
      ContentBehaviorTracker.trackImpression('p2', 'impressed');
      ContentBehaviorTracker.trackClick('p1');
      expect(ContentBehaviorTracker.pendingQueue, hasLength(3));
    });

    test('reset clears the queue completely', () {
      ContentBehaviorTracker.trackImpression('p1', 'visible');
      ContentBehaviorTracker.trackClick('p2');
      expect(ContentBehaviorTracker.pendingQueue, hasLength(2));
      ContentBehaviorTracker.reset();
      expect(ContentBehaviorTracker.pendingQueue, isEmpty);
    });

    test('events from different posts do not merge postId', () {
      ContentBehaviorTracker.trackImpression('postA', 'impressed');
      ContentBehaviorTracker.trackClick('postB');
      final queue = ContentBehaviorTracker.pendingQueue;
      expect(queue[0]['postId'], equals('postA'));
      expect(queue[1]['postId'], equals('postB'));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 异常/边界契约：无效参数不崩溃
  // ──────────────────────────────────────────────────────────────────
  group('ContentBehaviorTracker — 异常/边界契约', () {
    test('trackImpression with empty postId does not crash', () {
      expect(
        () => ContentBehaviorTracker.trackImpression('', 'visible'),
        returnsNormally,
      );
    });

    test('trackDwell with zero duration does not crash', () {
      expect(() => ContentBehaviorTracker.trackDwell('p1', 0), returnsNormally);
    });

    test('trackDwell forwards duration in seconds unit', () {
      ContentBehaviorTracker.trackDwell('p1', 12);
      expect(
        ContentBehaviorTracker.pendingQueue.single['duration'],
        equals(12),
      );
    });

    test('trackShare with null shareTarget does not crash', () {
      expect(() => ContentBehaviorTracker.trackShare('p1'), returnsNormally);
    });

    test('reset on empty queue does not crash', () {
      expect(() => ContentBehaviorTracker.reset(), returnsNormally);
    });
  });
}
