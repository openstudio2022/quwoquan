import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/user/auth_repository.dart';

const String _defaultNicknameSample = '新同学_260622_6698692';
final RegExp _defaultNicknamePattern = RegExp(r'^新同学_\d{6}_\d{7}$');

class _StubCloudHttpClient extends CloudHttpClient {
  _StubCloudHttpClient({this.onPostJson, this.onDeleteJson})
    : super(client: http.Client());

  final Future<CloudHttpDecodedJson> Function(
    Uri uri,
    Map<String, String> headers,
    CloudJsonMap body,
  )?
  onPostJson;

  final Future<CloudHttpDecodedJson> Function(
    Uri uri,
    Map<String, String> headers,
  )?
  onDeleteJson;

  @override
  Future<CloudHttpDecodedJson> postJson(
    Uri uri, {
    required Map<String, String> headers,
    required CloudJsonMap body,
  }) async {
    final handler = onPostJson;
    if (handler == null) {
      throw UnimplementedError('onPostJson is not configured');
    }
    return handler(uri, headers, body);
  }

  @override
  Future<CloudHttpDecodedJson> deleteJson(
    Uri uri, {
    required Map<String, String> headers,
  }) async {
    final handler = onDeleteJson;
    if (handler == null) {
      throw UnimplementedError('onDeleteJson is not configured');
    }
    return handler(uri, headers);
  }
}

void main() {
  group('RemoteAuthRepository 契约', () {
    test('手机号登录透传 deviceId/platform 并命中 metadata path', () async {
      final client = _StubCloudHttpClient(
        onPostJson: (uri, headers, body) async {
          expect(uri.path, UserApiMetadata.loginWithPhonePath);
          expect(
            headers['X-Client-Page-Id'],
            UserRequestPageIds.loginWithPhone,
          );
          expect(body['phone'], '+8618013813909');
          expect(body['otpCode'], '123456');
          expect(body['deviceId'], 'install-id-1');
          expect(body['platform'], 'ios');
          expect(body['appVersion'], '1.2.3');
          expect(body['agreementVersion'], '2026-06');
          expect(body['privacyVersion'], '2026-06');
          expect(body['credentialType'], isNull);
          expect(body['credentialKey'], isNull);
          return <String, dynamic>{
            'accessToken': 'token-1',
            'refreshToken': 'refresh-1',
            'ownerId': 'owner-1',
            'activeSub': <String, dynamic>{'subAccountId': 'sub-1'},
            'subAccountCount': 1,
            'accountState': 'active',
            'identityOrigin': 'phone',
          };
        },
      );
      final repo = RemoteAuthRepository(
        httpClient: client,
        baseUrl: 'https://gateway.example.com',
      );

      final result = await repo.login(
        credentialType: 'phone',
        credentialKey: '+8618013813909',
        otpCode: '123456',
        displayLabel: '138****3909',
        deviceId: 'install-id-1',
        platform: 'ios',
        appVersion: '1.2.3',
        agreementVersion: '2026-06',
        privacyVersion: '2026-06',
      );

      expect(result.ownerId, 'owner-1');
      expect(result.refreshToken, 'refresh-1');
    });

    test('SendOtp 透传设备上下文并解析结构化发码响应', () async {
      final client = _StubCloudHttpClient(
        onPostJson: (uri, headers, body) async {
          expect(uri.path, UserApiMetadata.sendOtpPath);
          expect(headers['X-Client-Page-Id'], UserRequestPageIds.sendOtp);
          expect(body['phone'], '+8618013813909');
          expect(body['deviceId'], 'install-id-otp');
          expect(body['platform'], 'ios');
          expect(body['appVersion'], '1.2.3');
          expect(body['sourceOperation'], 'LoginPhoneOtp');
          return <String, dynamic>{
            'maskedPhone': '180****3909',
            'expiresInSeconds': 300,
            'deliveryStatus': 'queued',
            'requestId': 'otp-request-1',
            'challengeId': 'otp-challenge-1',
            'retryAfterSeconds': 60,
            'debugCode': '123456',
          };
        },
      );
      final repo = RemoteAuthRepository(
        httpClient: client,
        baseUrl: 'https://gateway.example.com',
      );

      final result = await repo.sendOtp(
        phone: '+8618013813909',
        deviceId: 'install-id-otp',
        platform: 'ios',
        appVersion: '1.2.3',
        sourceOperation: 'LoginPhoneOtp',
      );

      expect(result.maskedPhone, '180****3909');
      expect(result.retryAfterSeconds, 60);
      expect(result.requestId, 'otp-request-1');
      expect(result.challengeId, 'otp-challenge-1');
    });

    test('一键登录 hint 命中 metadata path 并解析账号摘要', () async {
      final client = _StubCloudHttpClient(
        onPostJson: (uri, headers, body) async {
          expect(uri.path, UserApiMetadata.resolveOneTapLoginHintPath);
          expect(
            headers['X-Client-Page-Id'],
            UserRequestPageIds.resolveOneTapLoginHint,
          );
          expect(body['vendor'], 'cmcc');
          expect(body['carrierToken'], 'carrier-token');
          expect(body['deviceId'], 'install-id-hint');
          expect(body['platform'], 'ios');
          expect(body['appVersion'], '1.2.3');
          return <String, dynamic>{
            'state': 'registered',
            'maskedPhone': '138****3909',
            'registered': true,
            'accountHint': <String, dynamic>{
              'displayName': _defaultNicknameSample,
              'avatarUrl': '',
              'maskedPhone': '138****3909',
              'identityOrigin': 'phone',
            },
            'expiresInSeconds': 60,
            'providerRequestId': 'provider-request-1',
          };
        },
      );
      final repo = RemoteAuthRepository(
        httpClient: client,
        baseUrl: 'https://gateway.example.com',
      );

      final result = await repo.resolveOneTapLoginHint(
        vendor: 'cmcc',
        carrierToken: 'carrier-token',
        deviceId: 'install-id-hint',
        platform: 'ios',
        appVersion: '1.2.3',
      );

      expect(result.state, 'registered');
      expect(result.registered, isTrue);
      expect(
        result.accountHint?['displayName'],
        matches(_defaultNicknamePattern),
      );
    });

    test('一键登录透传协议版本和 appVersion 并解析 accountHint', () async {
      final client = _StubCloudHttpClient(
        onPostJson: (uri, headers, body) async {
          expect(uri.path, UserApiMetadata.loginOneTapPath);
          expect(headers['X-Client-Page-Id'], UserRequestPageIds.loginOneTap);
          expect(body['vendor'], 'cmcc');
          expect(body['carrierToken'], 'carrier-token-login');
          expect(body['deviceId'], 'install-id-login');
          expect(body['platform'], 'android');
          expect(body['appVersion'], '1.2.3');
          expect(body['agreementVersion'], '2026-06');
          expect(body['privacyVersion'], '2026-06');
          return <String, dynamic>{
            'accessToken': 'token-one-tap',
            'refreshToken': 'refresh-one-tap',
            'ownerId': 'owner-one-tap',
            'activeSub': <String, dynamic>{'subAccountId': 'sub-one-tap'},
            'subAccountCount': 1,
            'accountState': 'active',
            'identityOrigin': 'phone',
            'accountHint': <String, dynamic>{
              'displayName': _defaultNicknameSample,
              'maskedPhone': '138****3909',
            },
          };
        },
      );
      final repo = RemoteAuthRepository(
        httpClient: client,
        baseUrl: 'https://gateway.example.com',
      );

      final result = await repo.loginOneTap(
        vendor: 'cmcc',
        carrierToken: 'carrier-token-login',
        deviceId: 'install-id-login',
        platform: 'android',
        appVersion: '1.2.3',
        agreementVersion: '2026-06',
        privacyVersion: '2026-06',
      );

      expect(result.ownerId, 'owner-one-tap');
      expect(result.accountHint?['maskedPhone'], '138****3909');
    });

    test('logout 请求命中 metadata path 并透传 refreshToken/deviceId', () async {
      final client = _StubCloudHttpClient(
        onPostJson: (uri, headers, body) async {
          expect(uri.path, UserApiMetadata.logoutPath);
          expect(headers['X-Client-Page-Id'], UserRequestPageIds.logout);
          expect(body['refreshToken'], 'refresh-2');
          expect(body['deviceId'], 'install-id-2');
          return <String, dynamic>{'status': 'ok'};
        },
      );
      final repo = RemoteAuthRepository(
        httpClient: client,
        baseUrl: 'https://gateway.example.com',
      );

      await repo.logout(refreshToken: 'refresh-2', deviceId: 'install-id-2');
    });

    test('微信登录命中 metadata path 并透传授权码', () async {
      final client = _StubCloudHttpClient(
        onPostJson: (uri, headers, body) async {
          expect(uri.path, UserApiMetadata.loginWithWechatPath);
          expect(
            headers['X-Client-Page-Id'],
            UserRequestPageIds.loginWithWechat,
          );
          expect(body['wechatCode'], 'wx-auth-code');
          expect(body['deviceId'], 'install-id-3');
          expect(body['platform'], 'android');
          return <String, dynamic>{
            'accessToken': 'token-wechat',
            'refreshToken': 'refresh-wechat',
            'ownerId': 'owner-wechat',
            'activeSub': <String, dynamic>{'subAccountId': 'sub-wechat'},
            'subAccountCount': 1,
            'accountState': 'active',
            'identityOrigin': 'wechat',
          };
        },
      );
      final repo = RemoteAuthRepository(
        httpClient: client,
        baseUrl: 'https://gateway.example.com',
      );

      final result = await repo.loginWechat(
        wechatCode: 'wx-auth-code',
        deviceId: 'install-id-3',
        platform: 'android',
      );

      expect(result.ownerId, 'owner-wechat');
      expect(result.identityOrigin, 'wechat');
    });

    test('支付宝登录命中 metadata path 并透传 authCode', () async {
      final client = _StubCloudHttpClient(
        onPostJson: (uri, headers, body) async {
          expect(uri.path, UserApiMetadata.loginWithAlipayPath);
          expect(
            headers['X-Client-Page-Id'],
            UserRequestPageIds.loginWithAlipay,
          );
          expect(body['alipayAuthCode'], 'alipay-auth-code');
          expect(body['deviceId'], 'install-id-alipay');
          expect(body['platform'], 'android');
          return <String, dynamic>{
            'accessToken': 'token-alipay',
            'refreshToken': 'refresh-alipay',
            'ownerId': 'owner-alipay',
            'activeSub': <String, dynamic>{'subAccountId': 'sub-alipay'},
            'subAccountCount': 1,
            'accountState': 'active',
            'identityOrigin': 'alipay',
          };
        },
      );
      final repo = RemoteAuthRepository(
        httpClient: client,
        baseUrl: 'https://gateway.example.com',
      );

      final result = await repo.loginAlipay(
        alipayAuthCode: 'alipay-auth-code',
        deviceId: 'install-id-alipay',
        platform: 'android',
      );

      expect(result.ownerId, 'owner-alipay');
      expect(result.identityOrigin, 'alipay');
    });

    test('QQ 登录命中 metadata path 并透传 authCode', () async {
      final client = _StubCloudHttpClient(
        onPostJson: (uri, headers, body) async {
          expect(uri.path, UserApiMetadata.loginWithQqPath);
          expect(headers['X-Client-Page-Id'], UserRequestPageIds.loginWithQq);
          expect(body['qqAuthCode'], 'qq-auth-code');
          expect(body['deviceId'], 'install-id-qq');
          expect(body['platform'], 'ios');
          return <String, dynamic>{
            'accessToken': 'token-qq',
            'refreshToken': 'refresh-qq',
            'ownerId': 'owner-qq',
            'activeSub': <String, dynamic>{'subAccountId': 'sub-qq'},
            'subAccountCount': 1,
            'accountState': 'active',
            'identityOrigin': 'qq',
          };
        },
      );
      final repo = RemoteAuthRepository(
        httpClient: client,
        baseUrl: 'https://gateway.example.com',
      );

      final result = await repo.loginQq(
        qqAuthCode: 'qq-auth-code',
        deviceId: 'install-id-qq',
        platform: 'ios',
      );

      expect(result.ownerId, 'owner-qq');
      expect(result.identityOrigin, 'qq');
    });

    test('Apple 登录命中 metadata path 并透传 id token', () async {
      final client = _StubCloudHttpClient(
        onPostJson: (uri, headers, body) async {
          expect(uri.path, UserApiMetadata.loginWithApplePath);
          expect(
            headers['X-Client-Page-Id'],
            UserRequestPageIds.loginWithApple,
          );
          expect(body['appleIdToken'], 'apple-id-token');
          expect(body['deviceId'], 'install-id-4');
          expect(body['platform'], 'ios');
          return <String, dynamic>{
            'accessToken': 'token-apple',
            'refreshToken': 'refresh-apple',
            'ownerId': 'owner-apple',
            'activeSub': <String, dynamic>{'subAccountId': 'sub-apple'},
            'subAccountCount': 1,
            'accountState': 'active',
            'identityOrigin': 'apple',
          };
        },
      );
      final repo = RemoteAuthRepository(
        httpClient: client,
        baseUrl: 'https://gateway.example.com',
      );

      final result = await repo.loginApple(
        appleIdToken: 'apple-id-token',
        deviceId: 'install-id-4',
        platform: 'ios',
      );

      expect(result.ownerId, 'owner-apple');
      expect(result.identityOrigin, 'apple');
    });

    test('passkey 登录命中 metadata path 并透传 assertion', () async {
      final client = _StubCloudHttpClient(
        onPostJson: (uri, headers, body) async {
          expect(uri.path, UserApiMetadata.loginWithPasskeyPath);
          expect(
            headers['X-Client-Page-Id'],
            UserRequestPageIds.loginWithPasskey,
          );
          expect(body['passkeyAssertion'], 'passkey-assertion');
          expect(body['deviceId'], 'install-id-5');
          expect(body['platform'], 'android');
          expect(body['displayLabel'], 'zhaoyx@example.com');
          return <String, dynamic>{
            'accessToken': 'token-passkey',
            'refreshToken': 'refresh-passkey',
            'ownerId': 'owner-passkey',
            'activeSub': <String, dynamic>{'subAccountId': 'sub-passkey'},
            'subAccountCount': 1,
            'accountState': 'active',
            'identityOrigin': 'passkey',
          };
        },
      );
      final repo = RemoteAuthRepository(
        httpClient: client,
        baseUrl: 'https://gateway.example.com',
      );

      final result = await repo.loginPasskey(
        passkeyAssertion: 'passkey-assertion',
        deviceId: 'install-id-5',
        platform: 'android',
        displayLabel: 'zhaoyx@example.com',
      );

      expect(result.ownerId, 'owner-passkey');
      expect(result.identityOrigin, 'passkey');
    });
  });
}
