import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_delegate.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_notifier.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

import '../../../support/fixtures/chat/fixture_realtime_connection_delegate.dart';

void main() {
  test('app lifecycle reuses the explicitly composed realtime delegate', () {
    var delegateBuildCount = 0;
    final container = ProviderContainer(
      overrides: [
        realtimeConnectionManagerProvider.overrideWith(
          () => RealtimeConnectionNotifier(
            delegateFactory:
                ({
                  required ref,
                  required onStateChanged,
                  required currentUserIdResolver,
                }) {
                  delegateBuildCount++;
                  return FixtureRealtimeConnectionDelegate(
                    read: ref.read,
                    invalidate: ref.invalidate,
                    onStateChanged: onStateChanged,
                  );
                },
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    final notifier = container.read(realtimeConnectionManagerProvider.notifier);
    notifier.onAppForeground();
    notifier.onEnterConversation('unknown_conversation');
    expect(
      container.read(realtimeConnectionManagerProvider),
      TransportState.active,
    );
    expect(delegateBuildCount, 1);

    notifier.onAppForeground();

    expect(delegateBuildCount, 1);
    expect(
      container.read(realtimeConnectionManagerProvider),
      TransportState.active,
    );
  });
}
