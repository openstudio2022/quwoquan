import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/home_feed_video_autoplay_policy.dart';

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

  group('shouldSuppressHomeFeedVideoFastScroll', () {
    HomeFeedVideoFastScrollSuppressionInput input({
      bool hasPlayableSource = true,
      double visibleFraction = 0.70,
      Duration prewarmStableVisibleDuration = const Duration(milliseconds: 180),
      double scrollVelocityPxPerSecond =
          homeFeedVideoFastScrollVelocityPxPerSecond + 10,
      Duration timeSinceHighVelocity = const Duration(milliseconds: 600),
    }) {
      return HomeFeedVideoFastScrollSuppressionInput(
        hasPlayableSource: hasPlayableSource,
        visibleFraction: visibleFraction,
        prewarmStableVisibleDuration: prewarmStableVisibleDuration,
        scrollVelocityPxPerSecond: scrollVelocityPxPerSecond,
        timeSinceHighVelocity: timeSinceHighVelocity,
      );
    }

    test('预热可见且快滑时抑制视频初始化', () {
      expect(shouldSuppressHomeFeedVideoFastScroll(input()), isTrue);
      expect(
        shouldSuppressHomeFeedVideoFastScroll(
          input(
            scrollVelocityPxPerSecond: 0,
            timeSinceHighVelocity: const Duration(milliseconds: 120),
          ),
        ),
        isTrue,
      );
    });

    test('无可播源、未达预热可见或驻留不足时不记录抑制', () {
      expect(
        shouldSuppressHomeFeedVideoFastScroll(input(hasPlayableSource: false)),
        isFalse,
      );
      expect(
        shouldSuppressHomeFeedVideoFastScroll(input(visibleFraction: 0.4)),
        isFalse,
      );
      expect(
        shouldSuppressHomeFeedVideoFastScroll(
          input(prewarmStableVisibleDuration: const Duration(milliseconds: 80)),
        ),
        isFalse,
      );
    });

    test('telemetry attributes clamp negative cooldown to zero', () {
      final attributes = homeFeedVideoFastScrollSuppressedTelemetryAttributes(
        videoId: 'video_1',
        visibleFraction: 0.88,
        velocityPxPerSecond: 1800,
        cooldownRemaining: const Duration(milliseconds: -20),
      );

      expect(attributes['videoId'], 'video_1');
      expect(attributes['visibleFraction'], 0.88);
      expect(attributes['velocityPxPerSecond'], 1800);
      expect(attributes['cooldownRemainingMs'], 0);
    });
  });
}
