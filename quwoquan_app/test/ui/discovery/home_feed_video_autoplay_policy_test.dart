import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/discovery/models/home_feed_video_autoplay_policy.dart';

void main() {
  group('shouldAutoPlayHomeFeedVideo', () {
    HomeFeedVideoAutoPlayInput input({
      bool hasPlayableSource = true,
      double visibleFraction = 0.86,
      Duration stableVisibleDuration = const Duration(milliseconds: 220),
      double scrollVelocityPxPerSecond = 0,
      bool isUserDragging = false,
      bool isScrolling = false,
      Duration timeSinceScrollEnd = const Duration(milliseconds: 180),
      Duration timeSinceHighVelocity = const Duration(milliseconds: 600),
    }) {
      return HomeFeedVideoAutoPlayInput(
        hasPlayableSource: hasPlayableSource,
        visibleFraction: visibleFraction,
        stableVisibleDuration: stableVisibleDuration,
        scrollVelocityPxPerSecond: scrollVelocityPxPerSecond,
        isUserDragging: isUserDragging,
        isScrolling: isScrolling,
        timeSinceScrollEnd: timeSinceScrollEnd,
        timeSinceHighVelocity: timeSinceHighVelocity,
      );
    }

    test('稳定阅读且大比例可见时放行自动播放', () {
      expect(shouldAutoPlayHomeFeedVideo(input()), isTrue);
    });

    test('拖拽中、高速滑动、刚结束滚动或驻留不足都会拦截', () {
      expect(shouldAutoPlayHomeFeedVideo(input(isUserDragging: true)), isFalse);
      expect(
        shouldAutoPlayHomeFeedVideo(input(scrollVelocityPxPerSecond: 1200)),
        isFalse,
      );
      expect(
        shouldAutoPlayHomeFeedVideo(
          input(timeSinceScrollEnd: const Duration(milliseconds: 40)),
        ),
        isFalse,
      );
      expect(
        shouldAutoPlayHomeFeedVideo(
          input(stableVisibleDuration: const Duration(milliseconds: 80)),
        ),
        isFalse,
      );
    });

    test('惯性滚动和快速滑过冷却期间不会触发播放', () {
      expect(shouldAutoPlayHomeFeedVideo(input(isScrolling: true)), isFalse);
      expect(
        shouldAutoPlayHomeFeedVideo(
          input(timeSinceHighVelocity: const Duration(milliseconds: 180)),
        ),
        isFalse,
      );
      expect(
        shouldAutoPlayHomeFeedVideo(
          input(
            scrollVelocityPxPerSecond:
                homeFeedVideoFastScrollVelocityPxPerSecond + 1,
          ),
        ),
        isFalse,
      );
    });

    test('可见比例不足或没有可播源时不预热不播放', () {
      expect(shouldAutoPlayHomeFeedVideo(input(visibleFraction: 0.4)), isFalse);
      expect(
        shouldAutoPlayHomeFeedVideo(input(hasPlayableSource: false)),
        isFalse,
      );
    });
  });
}
