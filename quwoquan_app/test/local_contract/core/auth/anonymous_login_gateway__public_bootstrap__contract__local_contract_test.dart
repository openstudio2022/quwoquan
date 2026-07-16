import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/core/di/cloud_http_client_provider.dart';
import 'package:quwoquan_app/core/di/login_dependencies.dart';

void main() {
  test(
    'anonymous bootstrap uses a public client without a bearer session',
    () async {
      late http.Request captured;
      final httpClient = CloudHttpClient(
        client: MockClient((request) async {
          captured = request;
          return http.Response(
            jsonEncode(<String, Object?>{
              'accessToken': 'anonymous-access',
              'refreshToken': 'anonymous-refresh',
              'ownerId': 'anonymous-owner',
              'activeSub': <String, String>{
                'subAccountId': 'anonymous-persona',
              },
              'accountState': 'anonymous',
              'identityOrigin': 'anonymous_device',
            }),
            200,
          );
        }),
      );
      final container = ProviderContainer(
        overrides: [
          unauthenticatedCloudHttpClientProvider.overrideWithValue(httpClient),
        ],
      );
      addTearDown(container.dispose);

      final result = await container
          .read(anonymousLoginGatewayProvider)
          .loginAnonymous(
            installId: 'patrol-install',
            deviceFingerprintHash: 'patrol-fingerprint',
            platform: 'ios',
            appVersion: 'local-e2e',
          );

      expect(captured.url.path, UserApiMetadata.loginAnonymousPath);
      expect(captured.headers.containsKey('authorization'), isFalse);
      expect(result.ownerId, 'anonymous-owner');
      expect(result.activeSub?['subAccountId'], 'anonymous-persona');
    },
  );
}
