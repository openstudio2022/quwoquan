import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip/release_policy.dart';

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
    expect(fast.settleDuration.inMilliseconds, greaterThanOrEqualTo(320));
    expect(slow.settleDuration.inMilliseconds, lessThanOrEqualTo(520));
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
    expect(slow.settleDuration.inMilliseconds, greaterThanOrEqualTo(220));
    expect(slow.settleDuration.inMilliseconds, lessThanOrEqualTo(360));
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

  test('release policy clamps commit and cancel to comfort ranges', () {
    final cases = <PageflipReleaseDecision>[
      resolvePageflipReleaseDecision(
        isForwardDirection: true,
        progress: 0.9,
        pageWidth: 398,
        velocityDx: -6000,
        dragStart: const Offset(560, 600),
        dragLatest: const Offset(120, 600),
      ),
      resolvePageflipReleaseDecision(
        isForwardDirection: false,
        progress: 0.04,
        pageWidth: 398,
        velocityDx: 4,
        dragStart: const Offset(80, 600),
        dragLatest: const Offset(88, 600),
      ),
      resolvePageflipReleaseDecision(
        isForwardDirection: true,
        progress: 0.5,
        pageWidth: 1,
        velocityDx: -1,
      ),
    ];

    for (final decision in cases) {
      if (decision.commitsTurn) {
        expect(
          decision.settleDuration.inMilliseconds,
          greaterThanOrEqualTo(320),
        );
        expect(decision.settleDuration.inMilliseconds, lessThanOrEqualTo(520));
      } else {
        expect(
          decision.settleDuration.inMilliseconds,
          greaterThanOrEqualTo(220),
        );
        expect(decision.settleDuration.inMilliseconds, lessThanOrEqualTo(360));
      }
    }
  });

  test(
    'release policy keeps the fastest visible turn above flash threshold',
    () {
      final fastest = resolvePageflipReleaseDecision(
        isForwardDirection: true,
        progress: 0.96,
        pageWidth: 398,
        velocityDx: -9000,
        dragStart: const Offset(560, 600),
        dragLatest: const Offset(90, 600),
        dragStartedAt: DateTime.now().subtract(
          const Duration(milliseconds: 80),
        ),
      );

      expect(fastest.commitsTurn, isTrue);
      expect(fastest.settleDuration.inMilliseconds, 320);
    },
  );

  test(
    'release policy keeps the fastest cancel above perceptible threshold',
    () {
      final cancel = resolvePageflipReleaseDecision(
        isForwardDirection: true,
        progress: 0.04,
        pageWidth: 398,
        velocityDx: 9000,
        dragStart: const Offset(560, 600),
        dragLatest: const Offset(552, 600),
        dragStartedAt: DateTime.now().subtract(
          const Duration(milliseconds: 80),
        ),
      );

      expect(cancel.commitsTurn, isFalse);
      expect(cancel.settleDuration.inMilliseconds, 220);
    },
  );
}
