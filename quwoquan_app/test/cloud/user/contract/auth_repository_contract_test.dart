import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/user/auth_repository.dart';

class _StubCloudHttpClient extends CloudHttpClient {
  _StubCloudHttpClient({
    this.onPostJson,
    this.onDeleteJson,
  }) : super(client: http.Client());

  final Future<CloudHttpDecodedJson> Function(
    Uri uri,
    Map<String, String> headers,
    CloudJsonMap body,
  )? onPostJson;

  final Future<CloudHttpDecodedJson> Function(
    Uri uri,
    Map<String, String> headers,
  )? onDeleteJson;

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
          expect(headers['X-Client-Page-Id'], UserRequestPageIds.loginWithPhone);
          expect(body['phone'], '+8618013813909');
          expect(body['otpCode'], '123456');
          expect(body['deviceId'], 'install-id-1');
          expect(body['platform'], 'ios');
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
      );

      expect(result.ownerId, 'owner-1');
      expect(result.refreshToken, 'refresh-1');
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
