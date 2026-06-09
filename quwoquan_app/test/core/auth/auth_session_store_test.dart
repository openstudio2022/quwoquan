import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    FlutterSecureStorage.setMockInitialValues(<String, String>{});
  });

  test('saveLoginResult persists tokens and active persona', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());
    final result = AuthLoginResultDto.fromMap(<String, dynamic>{
      'accessToken': 'access-1',
      'refreshToken': 'refresh-1',
      'ownerId': 'owner-1',
      'activeSub': <String, dynamic>{'subAccountId': 'sub-1'},
      'subAccountCount': 1,
      'accountState': 'active',
      'identityOrigin': 'phone',
    });

    await store.saveLoginResult(result);
    final stored = await store.read();

    expect(stored.accessToken, 'access-1');
    expect(stored.refreshToken, 'refresh-1');
    expect(stored.ownerId, 'owner-1');
    expect(stored.activeSubAccountId, 'sub-1');
    expect(stored.manualLoggedOut, isFalse);
  });

  test(
    'saveLoginResult persists remembered login method and masked account',
    () async {
      final store = AuthSessionStore(
        secureStorage: const FlutterSecureStorage(),
      );
      final result = AuthLoginResultDto.fromMap(<String, dynamic>{
        'accessToken': 'access-2',
        'refreshToken': 'refresh-2',
        'ownerId': 'owner-2',
        'activeSub': <String, dynamic>{'subAccountId': 'sub-2'},
        'subAccountCount': 1,
        'accountState': 'active',
        'identityOrigin': 'phone',
      });

      await store.saveLoginResult(
        result,
        rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
        rememberedLoginMaskedIdentifier: '138****3909',
      );
      final stored = await store.read();

      expect(stored.rememberedLoginMethod, AuthRememberedLoginMethod.phoneOtp);
      expect(stored.rememberedLoginMaskedIdentifier, '138****3909');
    },
  );

  test('clearSession records manual logout prompt state', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());

    await store.clearSession(manualLogout: true);
    final stored = await store.read();

    expect(stored.accessToken, isEmpty);
    expect(stored.refreshToken, isEmpty);
    expect(stored.manualLoggedOut, isTrue);
    expect(stored.launchPromptDismissed, isFalse);
  });
}
