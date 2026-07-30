import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

const _ownerId = 'owner-homepage-cold-start';
const _personaId = 'persona-homepage-cold-start';

void main() {
  test('已认证会话在 persona profile 水合前即可满足主页查询 actor 契约', () {
    final container = ProviderContainer(
      overrides: [
        authSessionControllerProvider.overrideWith(
          _ColdStartAuthenticatedSession.new,
        ),
      ],
    );
    addTearDown(container.dispose);

    final actor = container.read(homepageQueryActorContextProvider);

    expect(actor.accountId, _ownerId);
    expect(actor.personaId, _personaId);
  });
}

final class _ColdStartAuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'homepage-cold-start-token',
    refreshToken: 'homepage-cold-start-refresh-token',
    ownerId: _ownerId,
    activePersonaId: _personaId,
    accountState: 'active',
    installId: 'homepage-cold-start-install',
  );
}
