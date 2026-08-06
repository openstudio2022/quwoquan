import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show BehaviorEventType;

/// L1a 契约测试：ContentBehaviorTracker — 覆盖 behavior batch 缓冲语义
void main() {
  late _RecordingBehaviorReporter reporter;
  late ContentBehaviorTracker tracker;

  setUp(() {
    reporter = _RecordingBehaviorReporter();
    tracker = ContentBehaviorTracker(
      reporter: reporter,
      enablePeriodicFlush: false,
    );
  });

  Future<List<BehaviorEvent>> flushEvents() async {
    await tracker.flush();
    return reporter.flushedBatches.last;
  }

  group('ContentBehaviorTracker — 常规契约', () {
    test('trackImpression enqueues impression event with contentId and state', () async {
      tracker.trackImpression('post1');
      final events = await flushEvents();
      expect(events, hasLength(1));
      expect(events.single.action, BehaviorEventType.impression);
      expect(events.single.contentId, 'post1');
      expect(events.single.state, 'impressed');
    });

    test('trackClick enqueues click event with correct type', () async {
      tracker.trackClick('post1');
      final events = await flushEvents();
      expect(events.single.action, BehaviorEventType.click);
      expect(events.single.contentId, 'post1');
    });

    test('trackDwell enqueues dwell event with duration (seconds)', () async {
      tracker.trackDwell('post1', durationSeconds: 15);
      final events = await flushEvents();
      expect(events.single.action, BehaviorEventType.dwell);
      expect(events.single.contentId, 'post1');
      expect(events.single.duration, 15);
    });

    test('trackShare enqueues share event', () async {
      tracker.trackShare('post1');
      final events = await flushEvents();
      expect(events.single.action, BehaviorEventType.share);
    });

    test('trackDislike enqueues dislike event', () async {
      tracker.trackDislike('post1', authorId: 'author1');
      final events = await flushEvents();
      expect(events.single.action, BehaviorEventType.dislike);
    });

    test('like_not_in_behavior_tracker — buffered types do not include like', () async {
      tracker.trackImpression('x');
      tracker.trackClick('x');
      tracker.trackDwell('x', durationSeconds: 12);
      tracker.trackShare('x');
      tracker.trackDislike('x', authorId: 'author1');
      final events = await flushEvents();
      final types = events.map((event) => event.action).toSet();
      expect(types, isNot(contains(BehaviorEventType.like)));
    });
  });

  group('ContentBehaviorTracker — 单轨契约', () {
    test('multiple events accumulate in buffer without dropping', () async {
      tracker.trackImpression('p1');
      tracker.trackImpression('p2');
      tracker.trackClick('p1');
      expect(tracker.debugPendingEventCount, 3);
      final events = await flushEvents();
      expect(events, hasLength(3));
    });

    test('flush clears the buffer completely', () async {
      tracker.trackImpression('p1');
      tracker.trackClick('p2');
      expect(tracker.debugPendingEventCount, 2);
      await tracker.flush();
      expect(tracker.debugPendingEventCount, 0);
      expect(reporter.flushedBatches.single, hasLength(2));
    });

    test('events from different posts do not merge contentId', () async {
      tracker.trackImpression('postA');
      tracker.trackClick('postB');
      final events = await flushEvents();
      expect(events[0].contentId, 'postA');
      expect(events[1].contentId, 'postB');
    });
  });

  group('ContentBehaviorTracker — 异常/边界契约', () {
    test('trackImpression with empty contentId does not crash', () {
      expect(() => tracker.trackImpression(''), returnsNormally);
    });

    test('trackDwell with zero duration does not enqueue', () async {
      tracker.trackDwell('p1', durationSeconds: 0);
      expect(tracker.debugPendingEventCount, 0);
    });

    test('trackDwell forwards duration in seconds unit', () async {
      tracker.trackDwell('p1', durationSeconds: 12);
      final events = await flushEvents();
      expect(events.single.duration, 12);
    });

    test('trackShare without extra args does not crash', () {
      expect(() => tracker.trackShare('p1'), returnsNormally);
    });

    test('flush on empty buffer does not crash', () async {
      await expectLater(tracker.flush(), completes);
      expect(reporter.flushedBatches, isEmpty);
    });
  });
}

final class _RecordingBehaviorReporter implements BehaviorReporter {
  final List<List<BehaviorEvent>> flushedBatches = <List<BehaviorEvent>>[];

  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {
    flushedBatches.add(List<BehaviorEvent>.from(events));
  }
}
