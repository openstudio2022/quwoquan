import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String _defaultNicknameSample = '新同学_260622_6698692';
final RegExp _defaultNicknamePattern = RegExp(r'^新同学_\d{6}_\d{7}$');

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    FlutterSecureStorage.setMockInitialValues(<String, String>{});
  });

  test('saveLoginGrant persists tokens and active persona', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());
    final result = decodeAuthSessionGrant(<String, dynamic>{
      'accessToken': 'access-1',
      'refreshToken': 'refresh-1',
      'ownerId': 'owner-1',
      'activePersona': <String, dynamic>{'personaId': 'sub-1'},
      'personaCount': 1,
      'accountState': 'active',
      'identityOrigin': 'phone',
    });

    await store.saveLoginGrant(result);
    final stored = await store.read();

    expect(stored.accessToken, 'access-1');
    expect(stored.refreshToken, 'refresh-1');
    expect(stored.ownerId, 'owner-1');
    expect(stored.activePersonaId, 'sub-1');
    expect(stored.manualLoggedOut, isFalse);
  });

  test(
    'saveLoginGrant persists remembered login method and masked account',
    () async {
      final store = AuthSessionStore(
        secureStorage: const FlutterSecureStorage(),
      );
      final result = decodeAuthSessionGrant(<String, dynamic>{
        'accessToken': 'access-2',
        'refreshToken': 'refresh-2',
        'ownerId': 'owner-2',
        'activePersona': <String, dynamic>{'personaId': 'sub-2'},
        'personaCount': 1,
        'accountState': 'active',
        'identityOrigin': 'phone',
        'accountHint': <String, dynamic>{
          'displayName': _defaultNicknameSample,
          'nicknameCustomized': false,
          'avatarUrl': 'https://cdn.example.com/avatar.png',
          'maskedPhone': '138****3909',
        },
      });

      await store.saveLoginGrant(
        result,
        rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      );
      final stored = await store.read();

      expect(stored.rememberedLoginMethod, AuthRememberedLoginMethod.phoneOtp);
      expect(stored.rememberedLoginMaskedIdentifier, '138****3909');
      expect(stored.rememberedDisplayName, matches(_defaultNicknamePattern));
      expect(stored.rememberedAvatarUrl, 'https://cdn.example.com/avatar.png');
      expect(stored.rememberedNicknameCustomized, isFalse);
    },
  );

  test('malformed nicknameCustomized cannot grant customized status', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'auth.remembered_nickname_customized': 'true',
    });
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());

    final stored = await store.read();

    expect(stored.rememberedNicknameCustomized, isFalse);
  });

  test('read restores the canonical active persona key', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'auth.active_persona_id': 'persona-current',
    });
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());

    final stored = await store.read();
    final preferences = await SharedPreferences.getInstance();

    expect(stored.activePersonaId, 'persona-current');
    expect(preferences.getString('auth.active_persona_id'), 'persona-current');
  });

  test('active refresh token is never reinterpreted as quick login', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'auth.account_state': 'active',
      'auth.manual_logged_out': true,
    });
    FlutterSecureStorage.setMockInitialValues(<String, String>{
      'auth.refresh_token': 'active-refresh',
    });
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());

    final stored = await store.read();

    expect(stored.refreshToken, 'active-refresh');
    expect(stored.rememberedRefreshToken, isEmpty);
    expect(stored.quickLoginRefreshToken, isEmpty);
    expect(stored.hasValidQuickLoginCredential, isFalse);
  });

  test('quick login requires its canonical explicit expiry', () async {
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    SharedPreferences.setMockInitialValues(<String, Object>{
      'auth.manual_logged_out': true,
      'auth.last_refresh_at_epoch_ms': nowMs,
      'auth.session_remember_ttl_seconds': 2592000,
    });
    FlutterSecureStorage.setMockInitialValues(<String, String>{
      'auth.remembered_refresh_token': 'remembered-refresh',
    });
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());

    final stored = await store.read();

    expect(stored.quickLoginRefreshToken, 'remembered-refresh');
    expect(stored.quickLoginExpiresAtEpochMs, 0);
    expect(stored.hasValidQuickLoginCredential, isFalse);
  });

  test('clearSession records manual logout prompt state', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());

    await store.clearSession(manualLogout: true);
    final stored = await store.read();

    expect(stored.accessToken, isEmpty);
    expect(stored.refreshToken, isEmpty);
    expect(stored.manualLoggedOut, isTrue);
    expect(stored.launchPromptDismissed, isFalse);
  });

  test(
    'softLogout keeps refresh credential and records quick-login expiry',
    () async {
      final store = AuthSessionStore(
        secureStorage: const FlutterSecureStorage(),
      );
      await store.saveLoginGrant(
        decodeAuthSessionGrant(<String, dynamic>{
          'accessToken': 'access-soft',
          'refreshToken': 'refresh-soft',
          'ownerId': 'owner-soft',
          'accountState': 'active',
          'identityOrigin': 'phone',
          'accountHint': <String, dynamic>{
            'displayName': '趣友A',
            'nicknameCustomized': true,
            'maskedPhone': '138****0001',
          },
        }),
        rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      );

      await store.softLogout();
      final stored = await store.read();

      // 软退出：失效活跃会话（删 accessToken），但保留快速登录凭证与账号摘要。
      expect(stored.accessToken, isEmpty);
      expect(stored.refreshToken, isEmpty);
      expect(stored.rememberedRefreshToken, 'refresh-soft');
      expect(stored.quickLoginRefreshToken, 'refresh-soft');
      expect(stored.ownerId, 'owner-soft');
      expect(stored.rememberedDisplayName, '趣友A');
      expect(stored.rememberedNicknameCustomized, isTrue);
      expect(stored.rememberedLoginMaskedIdentifier, '138****0001');
      expect(stored.manualLoggedOut, isTrue);
      expect(stored.quickLoginExpiresAtEpochMs, greaterThan(0));
      expect(stored.hasValidQuickLoginCredential, isTrue);
    },
  );

  test('softLogout uses cloud-issued remember TTL for expiry', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());
    await store.saveLoginGrant(
      decodeAuthSessionGrant(<String, dynamic>{
        'accessToken': 'access-ttl',
        'refreshToken': 'refresh-ttl',
        'ownerId': 'owner-ttl',
        'sessionRememberTtlSeconds': 600,
      }),
    );

    final before = DateTime.now().millisecondsSinceEpoch;
    await store.softLogout();
    final stored = await store.read();

    // 过期戳应约为 now + 600s（云端下发 TTL），允许少量执行耗时偏差。
    final expectedMax = before + 600 * 1000 + 5000;
    expect(stored.quickLoginExpiresAtEpochMs, lessThanOrEqualTo(expectedMax));
    expect(
      stored.quickLoginExpiresAtEpochMs,
      greaterThan(before + 600 * 1000 - 5000),
    );
  });

  test(
    'hardLogout (clearSession) wipes credentials and account summary',
    () async {
      final store = AuthSessionStore(
        secureStorage: const FlutterSecureStorage(),
      );
      await store.saveLoginGrant(
        decodeAuthSessionGrant(<String, dynamic>{
          'accessToken': 'access-hard',
          'refreshToken': 'refresh-hard',
          'ownerId': 'owner-hard',
          'identityOrigin': 'phone',
          'accountHint': <String, dynamic>{
            'displayName': '趣友Hard',
            'nicknameCustomized': true,
            'avatarUrl': 'https://cdn.example.com/avatar-hard.png',
            'maskedPhone': '138****0002',
          },
        }),
        rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      );

      await store.clearSession(manualLogout: true);
      final stored = await store.read();

      expect(stored.refreshToken, isEmpty);
      expect(stored.quickLoginExpiresAtEpochMs, 0);
      expect(stored.hasValidQuickLoginCredential, isFalse);
      expect(stored.rememberedLoginMethod, AuthRememberedLoginMethod.unknown);
      expect(stored.rememberedLoginMaskedIdentifier, isEmpty);
      expect(stored.rememberedDisplayName, isEmpty);
      expect(stored.rememberedAvatarUrl, isEmpty);
      expect(stored.rememberedNicknameCustomized, isFalse);
    },
  );

  test(
    'expired session clears credentials but preserves account summary',
    () async {
      final store = AuthSessionStore(
        secureStorage: const FlutterSecureStorage(),
      );
      await store.saveLoginGrant(
        decodeAuthSessionGrant(<String, dynamic>{
          'accessToken': 'access-expired',
          'refreshToken': 'refresh-expired',
          'ownerId': 'owner-expired',
          'identityOrigin': 'phone',
          'accountHint': <String, dynamic>{
            'displayName': '趣友Expired',
            'nicknameCustomized': true,
            'avatarUrl': 'https://cdn.example.com/avatar-expired.png',
            'maskedPhone': '138****0003',
          },
        }),
        rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      );

      await store.clearSession(manualLogout: false);
      final stored = await store.read();

      expect(stored.refreshToken, isEmpty);
      expect(stored.rememberedLoginMethod, AuthRememberedLoginMethod.phoneOtp);
      expect(stored.rememberedLoginMaskedIdentifier, '138****0003');
      expect(stored.rememberedDisplayName, '趣友Expired');
      expect(stored.rememberedAvatarUrl, contains('avatar-expired.png'));
      expect(stored.rememberedNicknameCustomized, isTrue);
    },
  );

  test(
    'refresh accountHint replaces summary and explicit empty avatar',
    () async {
      final store = AuthSessionStore(
        secureStorage: const FlutterSecureStorage(),
      );
      await store.saveLoginGrant(
        decodeAuthSessionGrant(<String, dynamic>{
          'accessToken': 'access-old',
          'refreshToken': 'refresh-old',
          'ownerId': 'owner-refresh',
          'identityOrigin': 'phone',
          'accountHint': <String, dynamic>{
            'displayName': '旧昵称',
            'nicknameCustomized': true,
            'avatarUrl': 'https://cdn.example.com/avatar-old.png',
            'maskedPhone': '138****0004',
          },
        }),
        rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      );

      await store.saveRefreshedAccountHint(
        const AccountHintSnapshot(
          displayName: '系统默认昵称',
          nicknameCustomized: false,
          avatarUrl: '',
          avatarAssetId: '',
          maskedPhone: '138****0005',
          identityOrigin: 'phone',
        ),
      );
      final refreshed = await store.read();

      expect(refreshed.rememberedDisplayName, '系统默认昵称');
      expect(refreshed.rememberedNicknameCustomized, isFalse);
      expect(refreshed.rememberedAvatarUrl, isEmpty);
      expect(refreshed.rememberedLoginMaskedIdentifier, '138****0005');

      await store.saveRefreshedAccountHint(null);
      final unchanged = await store.read();
      expect(unchanged.rememberedDisplayName, '系统默认昵称');
      expect(unchanged.rememberedLoginMaskedIdentifier, '138****0005');
    },
  );

  test('saveLoginGrant(phoneOtp) 记住完整手机号，软退出保留供自动预填', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());
    await store.saveLoginGrant(
      decodeAuthSessionGrant(<String, dynamic>{
        'accessToken': 'access-phone',
        'refreshToken': 'refresh-phone',
        'ownerId': 'owner-phone',
        'identityOrigin': 'phone',
      }),
      rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      rememberedLoginMaskedIdentifier: '180****9016',
      rememberedLoginIdentifier: '18000009016',
    );

    final afterLogin = await store.read();
    expect(afterLogin.rememberedLoginIdentifier, '18000009016');

    // 软退出保留完整号（过期后再登录可自动预填 + 自动发码）。
    await store.softLogout();
    final afterSoft = await store.read();
    expect(afterSoft.rememberedLoginIdentifier, '18000009016');
    expect(afterSoft.rememberedLoginMaskedIdentifier, '180****9016');
  });

  test('彻底退出清除本机完整手机号', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());
    await store.saveLoginGrant(
      decodeAuthSessionGrant(<String, dynamic>{
        'accessToken': 'access-phone',
        'refreshToken': 'refresh-phone',
        'ownerId': 'owner-phone',
        'identityOrigin': 'phone',
      }),
      rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      rememberedLoginMaskedIdentifier: '180****9016',
      rememberedLoginIdentifier: '18000009016',
    );

    await store.clearSession(manualLogout: true);
    final stored = await store.read();
    expect(stored.rememberedLoginIdentifier, isEmpty);
  });

  test('非手机号登录方式不持有完整手机号', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());
    await store.saveLoginGrant(
      decodeAuthSessionGrant(<String, dynamic>{
        'accessToken': 'access-wechat',
        'refreshToken': 'refresh-wechat',
        'ownerId': 'owner-wechat',
        'identityOrigin': 'wechat',
      }),
      rememberedLoginMethod: AuthRememberedLoginMethod.wechat,
      rememberedLoginIdentifier: '18000009016',
    );

    final stored = await store.read();
    expect(stored.rememberedLoginIdentifier, isEmpty);
  });
}
