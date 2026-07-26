import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/core/di/cloud_http_client_provider.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show accountSessionLoginCommandWriterProvider;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('anonymous bootstrap allows a cold mobile TLS handshake', () {
    final contract =
        appCloudOperationContracts[AppCloudOperationIds
            .userAccountSessionLoginAnonymous]!;

    expect(contract.timeoutMilliseconds, 10000);
    expect(contract.maxAttempts, 2);
  });

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
        overrides: [cloudHttpClientProvider.overrideWithValue(httpClient)],
      );
      addTearDown(container.dispose);

      final result = await container
          .read(accountSessionLoginCommandWriterProvider)
          .loginAnonymous(
            LoginAnonymousCommand(
              installId: 'patrol-install',
              deviceFingerprintHash: 'patrol-fingerprint',
              platform: 'ios',
              appVersion: 'local-e2e',
            ),
          );

      expect(captured.url.path, UserApiMetadata.loginAnonymousPath);
      expect(captured.headers.containsKey('authorization'), isFalse);
      expect(result.ownerId, 'anonymous-owner');
      expect(result.activeSub?.subAccountId, 'anonymous-persona');
    },
  );
}
