import 'dart:convert';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/di/cloud_http_client_provider.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart'
    show
        accountSessionLoginCommandWriterProvider,
        cloudRuntimeEnvironmentProvider;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/runtime/remote_api_path_test_harness.dart';

void main() {
  test('anonymous bootstrap allows a cold mobile TLS handshake', () {
    final contract =
        appCloudOperationContracts[AppCloudOperationIds
            .userAccountSessionLoginAnonymous]!;

    expect(contract.timeoutMilliseconds, 10000);
    expect(contract.maxAttempts, 2);
  });

  test('Patrol Remote setup 仅按结构化恢复语义重放同一匿名登录命令', () {
    final direct = File('test/support/runtime/patrol/patrol_test_support.dart');
    final source =
        (direct.existsSync()
                ? direct
                : File(
                    'quwoquan_app/test/support/runtime/patrol/'
                    'patrol_test_support.dart',
                  ))
            .readAsStringSync();
    final commandIndex = source.indexOf(
      'final command = LoginAnonymousCommand(',
    );
    final loopIndex = source.indexOf(
      'attempt <= _patrolAnonymousLoginSetupAttempts',
    );

    expect(source, contains('_patrolAnonymousLoginSetupAttempts = 3'));
    expect(source, contains('const Duration(seconds: 45)'));
    expect(source, contains('runtimeFailure.recovery.action'));
    expect(source, contains('.loginAnonymous(command)'));
    expect(commandIndex, greaterThanOrEqualTo(0));
    expect(loopIndex, greaterThan(commandIndex));
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
              'activePersona': <String, String>{
                'personaId': 'anonymous-persona',
              },
              'accountState': 'anonymous',
              'identityOrigin': 'anonymous_device',
              'logicalShard': 0,
              'anonymousRetentionPolicy': 'retained',
              'personaCount': 1,
              'sessionRememberTtlSeconds': 2592000,
            }),
            200,
          );
        }),
      );
      final container = ProviderContainer(
        overrides: [
          unauthenticatedCloudHttpClientProvider.overrideWithValue(httpClient),
          cloudRuntimeEnvironmentProvider.overrideWithValue(
            CloudRuntimeEnvironment(
              environment: CloudEnvironment.alpha,
              gatewayBaseUri: Uri.parse('https://api.alpha.quwoquan.com'),
            ),
          ),
        ],
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

      expect(
        captured.url.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.userAccountSessionLoginAnonymous,
        ),
      );
      expect(captured.headers.containsKey('authorization'), isFalse);
      expect(result.ownerId, 'anonymous-owner');
      expect(result.activePersona?.personaId, 'anonymous-persona');
    },
  );
}
