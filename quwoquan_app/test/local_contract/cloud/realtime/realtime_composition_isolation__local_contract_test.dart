import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_delegate.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_notifier.dart';
import 'package:quwoquan_app/core/di/app_data_source_mode.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

import '../../../support/fixtures/chat/fixture_realtime_connection_delegate.dart';

void main() {
  test('runtime mode changes cannot rebuild or replace realtime delegate', () {
    var delegateBuildCount = 0;
    final container = ProviderContainer(
      overrides: [
        appDataSourceModeProvider.overrideWith(_SwitchableModeNotifier.new),
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

    container
        .read(appDataSourceModeProvider.notifier)
        .setMode(AppDataSourceMode.remote);

    expect(delegateBuildCount, 1);
    expect(
      container.read(realtimeConnectionManagerProvider),
      TransportState.active,
    );
  });
}

/// Test-only switch proves realtime no longer observes the removed mode signal.
final class _SwitchableModeNotifier extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.mock;

  @override
  void setMode(AppDataSourceMode mode) {
    state = mode;
  }
}
