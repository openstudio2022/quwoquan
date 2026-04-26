import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/pageflip/release_policy.dart';

void main() {
  test('release policy makes fast forward flings settle sooner', () {
    const dragStart = Offset(560, 600);
    const dragLatest = Offset(440, 600);
    const progress = 0.3;

    final slow = resolvePageflipReleaseDecision(
      isForwardDirection: true,
      progress: progress,
      pageWidth: 398,
      velocityDx: -80,
      dragStart: dragStart,
      dragLatest: dragLatest,
      dragStartedAt: DateTime.now().subtract(const Duration(milliseconds: 640)),
    );
    final fast = resolvePageflipReleaseDecision(
      isForwardDirection: true,
      progress: progress,
      pageWidth: 398,
      velocityDx: -1400,
      dragStart: dragStart,
      dragLatest: dragLatest,
      dragStartedAt: DateTime.now().subtract(const Duration(milliseconds: 640)),
    );

    expect(slow.commitsTurn, isTrue);
    expect(fast.commitsTurn, isTrue);
    expect(fast.settleDuration, lessThan(slow.settleDuration));
  });

  test('release policy keeps a slow pull on the revert path', () {
    const dragStart = Offset(560, 600);
    const dragLatest = Offset(620, 620);

    final slow = resolvePageflipReleaseDecision(
      isForwardDirection: true,
      progress: 0.32,
      pageWidth: 398,
      velocityDx: 60,
      dragStart: dragStart,
      dragLatest: dragLatest,
      dragStartedAt: DateTime.now().subtract(const Duration(milliseconds: 640)),
    );

    expect(slow.commitsTurn, isFalse);
    expect(slow.settleDuration.inMilliseconds, greaterThanOrEqualTo(180));
  });

  test('release policy treats a strong backward fling as commit', () {
    const dragStart = Offset(80, 500);
    const dragLatest = Offset(170, 500);

    final backward = resolvePageflipReleaseDecision(
      isForwardDirection: false,
      progress: 0.28,
      pageWidth: 398,
      velocityDx: 1400,
      dragStart: dragStart,
      dragLatest: dragLatest,
      dragStartedAt: DateTime.now().subtract(const Duration(milliseconds: 640)),
    );

    expect(backward.commitsTurn, isTrue);
  });
}
