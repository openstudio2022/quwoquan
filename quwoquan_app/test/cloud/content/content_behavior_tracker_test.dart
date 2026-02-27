/// L1a Unit Tests: ContentBehaviorTracker 批量缓冲 + flush + 去重
///
/// 守护：Tracker 使用 MockBehaviorRepository，不发 HTTP。
/// 覆盖以下行为：
///   - impression 去重（同一 contentId 只上报一次）
///   - dwell < 1s 不上报
///   - batch 满 maxBatchSize 时自动 flush
///   - dispose 时 flush 剩余事件
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';

void main() {
  group('ContentBehaviorTracker', () {
    late MockBehaviorRepository repo;
    late ContentBehaviorTracker tracker;

    setUp(() {
      repo = MockBehaviorRepository();
      tracker = ContentBehaviorTracker(
        repository: repo,
        // 设置很长的 flush 间隔，避免定时器干扰
        flushInterval: const Duration(hours: 1),
        maxBatchSize: 5,
      );
    });

    tearDown(() => tracker.dispose());

    test('impression 同一 contentId 只上报一次（去重）', () async {
      tracker.trackImpression('post_1');
      tracker.trackImpression('post_1');
      tracker.trackImpression('post_2');
      await tracker.flush();

      final impressions = repo.recorded
          .where((e) => e.action == 'impression')
          .map((e) => e.contentId)
          .toList();
      expect(impressions, equals(['post_1', 'post_2']));
    });

    test('dwell < 1s 不上报', () async {
      tracker.trackDwell('post_1', durationSeconds: 0.5);
      await tracker.flush();
      expect(repo.recorded, isEmpty);
    });

    test('dwell >= 1s 正常上报', () async {
      tracker.trackDwell('post_1', durationSeconds: 3.5);
      await tracker.flush();

      expect(repo.recorded.length, equals(1));
      expect(repo.recorded.first.action, equals('dwell'));
      expect(repo.recorded.first.duration, equals(3.5));
    });

    test('达到 maxBatchSize 时自动 flush', () async {
      for (var i = 0; i < 5; i++) {
        tracker.trackClick('post_$i');
      }
      // maxBatchSize=5，第 5 条触发自动 flush
      // 等待异步 flush 完成
      await Future<void>.delayed(Duration.zero);
      expect(repo.recorded.length, equals(5));
    });

    test('dispose 时 flush 剩余事件', () async {
      tracker.trackClick('post_a');
      tracker.trackShare('post_b');
      expect(repo.recorded, isEmpty); // 还未 flush
      await tracker.dispose();
      expect(repo.recorded.length, equals(2));
    });

    test('dislike 事件正确上报', () async {
      tracker.trackDislike('post_1');
      await tracker.flush();
      expect(repo.recorded.first.action, equals('dislike'));
      expect(repo.recorded.first.contentId, equals('post_1'));
    });

    test('share 事件正确上报', () async {
      tracker.trackShare('post_1');
      await tracker.flush();
      expect(repo.recorded.first.action, equals('share'));
    });
  });
}
