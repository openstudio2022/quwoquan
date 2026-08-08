import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/domain/realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_notifier.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';

import '../../../../../support/service/realtime_gateway/realtime/connection/connection_typed_double.dart';

void main() {
  test('application notifier only consumes the typed delegate factory', () {
    final source = File(
      'lib/service/realtime_gateway/realtime/connection/application/'
      'realtime_connection_notifier.dart',
    ).readAsStringSync();

    expect(source, contains('required this._delegateFactory'));
    expect(
      source,
      contains('final RealtimeConnectionDelegateFactory _delegateFactory'),
    );
    expect(source, isNot(contains('/adapters/')));
    expect(source, isNot(contains('RemoteRealtimeConnectionDelegate')));
    expect(source, isNot(contains('operationGatewayResolver')));
  });

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
