// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';

import '../../../support/runtime/patrol_acceptance_session.dart';

void main() {
  group('Patrol acceptance session contract', () {
    tearDown(resetPatrolAcceptanceSessionForTest);

    test(
      'preserves the real owner and persona as distinct actor identities',
      () {
        final session = buildPatrolAcceptanceSession(
          accessToken: 'access-real',
          refreshToken: 'refresh-real',
          ownerId: 'owner-real',
          personaId: 'persona-real',
        );

        expect(session.isAuthenticated, isTrue);
        expect(session.ownerId, 'owner-real');
        expect(session.activePersonaId, 'persona-real');
        expect(session.accessToken, 'access-real');
        expect(session.refreshToken, 'refresh-real');
      },
    );

    test(
      'public video canary uses a guest session without fixture credentials',
      () {
        final session = buildPatrolAnonymousPublicVideoSession();

        expect(session.isAuthenticated, isFalse);
        expect(session.status, AuthSessionStatus.guest);
        expect(session.accessToken, isEmpty);
        expect(session.activePersonaId, isEmpty);
      },
    );

    test(
      'unauthenticated auth entry mounts a guest session without credentials',
      () {
        final session = buildPatrolUnauthenticatedAuthEntrySession();

        expect(session.isAuthenticated, isFalse);
        expect(session.status, AuthSessionStatus.guest);
        expect(session.accessToken, isEmpty);
        expect(session.refreshToken, isEmpty);
        expect(session.ownerId, isEmpty);
        expect(session.activePersonaId, isEmpty);
        expect(session.installId, isNotEmpty);
      },
    );

    test('host runner installs a complete runtime session before launch', () {
      final session = installPatrolAcceptanceSessionForRunner(
        accessToken: 'runtime-access',
        refreshToken: 'runtime-refresh',
        ownerId: 'runtime-owner',
        personaId: 'runtime-persona',
      );

      expect(session.isAuthenticated, isTrue);
      expect(session.accessToken, 'runtime-access');
      expect(session.refreshToken, 'runtime-refresh');
      expect(session.ownerId, 'runtime-owner');
      expect(session.activePersonaId, 'runtime-persona');
    });

    test('host runner installs one typed conversation without changing actor identity', () {
      final session = installPatrolAcceptanceSessionForRunner(
        accessToken: 'runtime-access',
        refreshToken: 'runtime-refresh',
        ownerId: 'runtime-owner',
        personaId: 'runtime-persona',
      );

      final conversation = installPatrolTestDataConversationForRunner(
        conversationId: ' conversation-live ',
        initialMessageIds: const [' message-a ', 'message-b'],
      );

      expect(conversation.conversationId, 'conversation-live');
      expect(conversation.initialMessageIds, ['message-a', 'message-b']);
      expect(patrolRunnerInstalledTestDataConversation, same(conversation));
      expect(requirePatrolTestDataConversationForRunner(), same(conversation));
      expect(patrolRunnerInstalledAcceptanceSession, same(session));
      expect(
        () => conversation.initialMessageIds.add('message-c'),
        throwsUnsupportedError,
      );
    });

    for (final invalid in <({String conversationId, List<String> messages})>[
      (conversationId: '', messages: const ['message-a']),
      (conversationId: 'conversation-a', messages: const []),
      (conversationId: 'conversation-a', messages: const ['']),
      (
        conversationId: 'conversation-a',
        messages: const ['message-a', ' message-a '],
      ),
    ]) {
      test('rejects incomplete or duplicate typed conversation handoff', () {
        installPatrolAcceptanceSessionForRunner(
          accessToken: 'runtime-access',
          refreshToken: 'runtime-refresh',
          ownerId: 'runtime-owner',
          personaId: 'runtime-persona',
        );
        expect(
          () => installPatrolTestDataConversationForRunner(
            conversationId: invalid.conversationId,
            initialMessageIds: invalid.messages,
          ),
          throwsStateError,
        );
        expect(patrolRunnerInstalledTestDataConversation, isNull);
      });
    }

    test(
      'command actor resolves from authenticated session before projection',
      () {
        final container = ProviderContainer(
          overrides: [
            authSessionControllerProvider.overrideWith(
              _PatrolContractAuthSession.new,
            ),
          ],
        );
        addTearDown(container.dispose);

        expect(container.read(resolvedActivePersonaIdProvider), 'persona-live');
      },
    );

    for (final missing in const <String>[
      'accessToken',
      'refreshToken',
      'ownerId',
      'personaId',
    ]) {
      test('rejects a missing $missing instead of installing a fallback', () {
        expect(
          () => buildPatrolAcceptanceSession(
            accessToken: missing == 'accessToken' ? '' : 'access-real',
            refreshToken: missing == 'refreshToken' ? '' : 'refresh-real',
            ownerId: missing == 'ownerId' ? '' : 'owner-real',
            personaId: missing == 'personaId' ? '' : 'persona-real',
          ),
          throwsStateError,
        );
      });
    }
  });
}

final class _PatrolContractAuthSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'access-live',
    refreshToken: 'refresh-live',
    ownerId: 'owner-live',
    activePersonaId: 'persona-live',
    accountState: 'active',
  );
}
