import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/testing/patrol_test_support.dart';

void main() {
  group('Patrol acceptance session contract', () {
    test(
      'preserves the real owner and persona as distinct actor identities',
      () {
        final session = buildPatrolAcceptanceSession(
          accessToken: 'access-real',
          refreshToken: 'refresh-real',
          ownerId: 'owner-real',
          subAccountId: 'persona-real',
        );

        expect(session.isAuthenticated, isTrue);
        expect(session.ownerId, 'owner-real');
        expect(session.activeSubAccountId, 'persona-real');
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
        expect(session.activeSubAccountId, isEmpty);
      },
    );

    for (final missing in const <String>[
      'accessToken',
      'refreshToken',
      'ownerId',
      'subAccountId',
    ]) {
      test('rejects a missing $missing instead of installing a fallback', () {
        expect(
          () => buildPatrolAcceptanceSession(
            accessToken: missing == 'accessToken' ? '' : 'access-real',
            refreshToken: missing == 'refreshToken' ? '' : 'refresh-real',
            ownerId: missing == 'ownerId' ? '' : 'owner-real',
            subAccountId: missing == 'subAccountId' ? '' : 'persona-real',
          ),
          throwsStateError,
        );
      });
    }
  });
}
