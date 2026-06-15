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
        'accountHint': <String, dynamic>{
          'displayName': '趣友3909',
          'avatarUrl': 'https://cdn.example.com/avatar.png',
          'maskedPhone': '138****3909',
        },
      });

      await store.saveLoginResult(
        result,
        rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      );
      final stored = await store.read();

      expect(stored.rememberedLoginMethod, AuthRememberedLoginMethod.phoneOtp);
      expect(stored.rememberedLoginMaskedIdentifier, '138****3909');
      expect(stored.rememberedDisplayName, '趣友3909');
      expect(stored.rememberedAvatarUrl, 'https://cdn.example.com/avatar.png');
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

  test(
    'softLogout keeps refresh credential and records quick-login expiry',
    () async {
      final store = AuthSessionStore(
        secureStorage: const FlutterSecureStorage(),
      );
      await store.saveLoginResult(
        AuthLoginResultDto.fromMap(<String, dynamic>{
          'accessToken': 'access-soft',
          'refreshToken': 'refresh-soft',
          'ownerId': 'owner-soft',
          'accountState': 'active',
          'identityOrigin': 'phone',
          'accountHint': <String, dynamic>{
            'displayName': '趣友A',
            'maskedPhone': '138****0001',
          },
        }),
        rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      );

      await store.softLogout();
      final stored = await store.read();

      // 软退出：失效活跃会话（删 accessToken），但保留快速登录凭证与账号摘要。
      expect(stored.accessToken, isEmpty);
      expect(stored.refreshToken, 'refresh-soft');
      expect(stored.ownerId, 'owner-soft');
      expect(stored.rememberedDisplayName, '趣友A');
      expect(stored.rememberedLoginMaskedIdentifier, '138****0001');
      expect(stored.manualLoggedOut, isTrue);
      expect(stored.quickLoginExpiresAtEpochMs, greaterThan(0));
      expect(stored.hasValidQuickLoginCredential, isTrue);
    },
  );

  test('softLogout uses cloud-issued remember TTL for expiry', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());
    await store.saveLoginResult(
      AuthLoginResultDto.fromMap(<String, dynamic>{
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

  test('hardLogout (clearSession) wipes refresh credential', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());
    await store.saveLoginResult(
      AuthLoginResultDto.fromMap(<String, dynamic>{
        'accessToken': 'access-hard',
        'refreshToken': 'refresh-hard',
        'ownerId': 'owner-hard',
      }),
    );

    await store.clearSession(manualLogout: true);
    final stored = await store.read();

    expect(stored.refreshToken, isEmpty);
    expect(stored.quickLoginExpiresAtEpochMs, 0);
    expect(stored.hasValidQuickLoginCredential, isFalse);
  });

  test(
    'saveLoginResult(phoneOtp) 记住完整手机号，软退出保留供自动预填',
    () async {
      final store = AuthSessionStore(
        secureStorage: const FlutterSecureStorage(),
      );
      await store.saveLoginResult(
        AuthLoginResultDto.fromMap(<String, dynamic>{
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
    },
  );

  test('彻底退出清除本机完整手机号', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());
    await store.saveLoginResult(
      AuthLoginResultDto.fromMap(<String, dynamic>{
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
    await store.saveLoginResult(
      AuthLoginResultDto.fromMap(<String, dynamic>{
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
