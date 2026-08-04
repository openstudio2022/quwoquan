// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002
import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/content/content/post/domain/home_feed_impression_sampling_clock.dart';

void main() {
  test('所有已挂载 feed 卡片共用一个采样 Timer，最后一个退出后停止', () {
    fakeAsync((async) {
      final clock = HomeFeedImpressionSamplingClock(
        interval: const Duration(milliseconds: 250),
      );
      var firstTicks = 0;
      var secondTicks = 0;
      void first() => firstTicks += 1;
      void second() => secondTicks += 1;

      clock.addListener(first);
      clock.addListener(second);

      expect(clock.listenerCount, 2);
      expect(clock.isRunning, isTrue);
      expect(async.pendingTimers, hasLength(1));

      async.elapse(const Duration(milliseconds: 500));
      expect(firstTicks, 2);
      expect(secondTicks, 2);
      expect(async.pendingTimers, hasLength(1));

      clock.removeListener(first);
      async.elapse(const Duration(milliseconds: 250));
      expect(firstTicks, 2);
      expect(secondTicks, 3);
      expect(async.pendingTimers, hasLength(1));

      clock.removeListener(second);
      expect(clock.listenerCount, 0);
      expect(clock.isRunning, isFalse);
      expect(async.pendingTimers, isEmpty);
    });
  });

  test('监听回调可在 tick 内安全移除自身', () {
    fakeAsync((async) {
      final clock = HomeFeedImpressionSamplingClock(
        interval: const Duration(milliseconds: 250),
      );
      var ticks = 0;
      late final void Function() listener;
      listener = () {
        ticks += 1;
        clock.removeListener(listener);
      };
      clock.addListener(listener);

      async.elapse(const Duration(milliseconds: 500));

      expect(ticks, 1);
      expect(clock.isRunning, isFalse);
      expect(async.pendingTimers, isEmpty);
    });
  });
}
