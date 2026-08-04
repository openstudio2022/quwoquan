import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/realtime/realtime/connection/domain/realtime_connection_delegate.dart';
import 'package:quwoquan_app/realtime/realtime/connection/presentation/realtime_connection_notifier.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

import '../../../../support/realtime/realtime/connection/connection_typed_double.dart';

void main() {
  test('app lifecycle reuses the explicitly composed realtime delegate', () {
    var delegateBuildCount = 0;
    final container = ProviderContainer(
      overrides: [
        authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
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

  test('guest foreground never starts bearer-required realtime transport', () {
    final container = ProviderContainer(
      overrides: [
        realtimeConnectionManagerProvider.overrideWith(
          () => RealtimeConnectionNotifier(
            delegateFactory:
                ({
                  required ref,
                  required onStateChanged,
                  required currentUserIdResolver,
                }) => FixtureRealtimeConnectionDelegate(
                  read: ref.read,
                  invalidate: ref.invalidate,
                  onStateChanged: onStateChanged,
                ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    final notifier = container.read(realtimeConnectionManagerProvider.notifier);
    notifier.onAppForeground();
    notifier.onEnterConversation('conversation-must-not-connect');

    expect(
      container.read(realtimeConnectionManagerProvider),
      TransportState.disconnected,
    );
  });
}

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'realtime-test-token',
    refreshToken: 'realtime-test-refresh-token',
    ownerId: 'realtime-test-owner',
    activePersonaId: 'realtime-test-persona',
    accountState: 'active',
    installId: 'realtime-test-install',
  );
}
