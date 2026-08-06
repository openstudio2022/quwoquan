import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import '../../../support/runtime/patrol/patrol_test_support.dart';

void main() {
  group('Patrol acceptance session contract', () {
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
