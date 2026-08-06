// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/external-inbound-deeplink-routing/spec.md#gwt-001
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/navigation/app_router_module.dart';

void main() {
  tearDown(resetAppRouterLibraryLoaderForTesting);

  test(
    'Router deferred load records failure then permits a new retry attempt',
    () async {
      expect(isAppRouterLibraryLoaded, isFalse);

      overrideAppRouterLibraryLoaderForTesting(
        () =>
            Future<void>.error(StateError('simulated deferred router failure')),
      );
      await expectLater(
        ensureAppRouterLibraryLoaded(),
        throwsA(isA<StateError>()),
      );
      expect(appRouterLibraryLastLoadError, isA<StateError>());
      final failedAttempt = appRouterLibraryLoadAttempt;

      overrideAppRouterLibraryLoaderForTesting(() => Future<void>.value());
      await ensureAppRouterLibraryLoaded(retry: true);

      expect(isAppRouterLibraryLoaded, isTrue);
      expect(appRouterLibraryLoadAttempt, greaterThan(failedAttempt));
    },
  );

  test('Router deferred future 永久 pending 时超时后的 retry 不会复用旧 attempt', () async {
    final pending = Completer<void>();
    overrideAppRouterLibraryLoaderForTesting(() => pending.future);

    await expectLater(
      ensureAppRouterLibraryLoaded().timeout(const Duration(milliseconds: 5)),
      throwsA(isA<TimeoutException>()),
    );
    final stalledAttempt = appRouterLibraryLoadAttempt;

    overrideAppRouterLibraryLoaderForTesting(() => Future<void>.value());
    await ensureAppRouterLibraryLoaded(retry: true);

    expect(isAppRouterLibraryLoaded, isTrue);
    expect(appRouterLibraryLoadAttempt, greaterThan(stalledAttempt));
    pending.complete();
    await Future<void>.delayed(Duration.zero);
    expect(isAppRouterLibraryLoaded, isTrue);
  });
}
