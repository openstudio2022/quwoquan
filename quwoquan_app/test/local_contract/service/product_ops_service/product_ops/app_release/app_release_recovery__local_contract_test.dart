// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-002
// readiness_case: app_release_get_app_recovery_version_app_local
import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/app_release/adapters/remote_app_release_recovery_reader.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/app_release/application/app_release_recovery_reader.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_operation_gateway.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_runtime_binding.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_version_client.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'version client sends only platform and local version coordinates',
    () async {
      late Uri requested;
      late Map<String, String> requestedHeaders;
      final client = RecoveryVersionClient(
        gateway: _httpGateway(
          MockClient((request) async {
            requested = request.url;
            requestedHeaders = request.headers;
            return http.Response(
              '{"platform":"android",'
              '"latestVersion":"1.8.2","latestBuild":"18201",'
              '"minimumSupportedVersion":"1.8.0",'
              '"minimumSupportedBuild":"18000",'
              '"updateState":"available",'
              '"updateUrl":"https://cdn.quwoquan.com/download/android/latest.json",'
              '"recoveryUrl":"https://quwoquan.com/"}',
              200,
            );
          }),
        ),
      );

      final result = await client.fetch(
        binding: _binding(),
        platform: 'android',
        appVersion: '1.8.1',
        buildNumber: 18100,
      );

      expect(
        requested.path,
        appCloudOperationContracts[AppCloudOperationIds
                .opsAppReleaseGetAppRecoveryVersion]!
            .pathTemplate,
      );
      expect(requested.queryParameters, <String, String>{
        'platform': 'android',
        'appVersion': '1.8.1',
        'buildNumber': '18100',
      });
      expect(requestedHeaders['X-Client-Surface-Id'], AppUiSurfaces.welcome.id);
      expect(
        requestedHeaders['X-Client-Page-Id'],
        OpsRequestPageIds.getAppRecoveryVersion,
      );
      expect(
        requestedHeaders['X-Client-Operation-Id'],
        AppCloudOperationIds.opsAppReleaseGetAppRecoveryVersion,
      );
      expect(requestedHeaders.containsKey('X-Client-Route-Id'), isFalse);
      expect(result.latestBuild, 18201);
      expect(result.platform, RecoveryVersionPlatform.android);
      expect(result.updateChannel, RecoveryVersionChannel.nativeUpdate);
    },
  );

  test('remote reader maps platform minimum build and update state', () async {
    final reader = _remoteReader(
      MockClient(
        (_) async => http.Response(
          '{"platform":"android",'
          '"latestVersion":"1.8.2","latestBuild":"18201",'
          '"minimumSupportedVersion":"1.8.0",'
          '"minimumSupportedBuild":"18000",'
          '"updateState":"available",'
          '"updateUrl":"https://cdn.quwoquan.com/download/android/latest.json",'
          '"recoveryUrl":"https://quwoquan.com/"}',
          200,
        ),
      ),
    );

    final facts = await reader.read(
      const AppReleaseRecoveryQuery(
        platform: 'android',
        appVersion: '1.8.1',
        buildNumber: 18100,
      ),
    );

    expect(facts.platform, AppReleaseRecoveryPlatform.android);
    expect(facts.minimumSupportedVersion, '1.8.0');
    expect(facts.minimumSupportedBuild, 18000);
    expect(facts.updateState, AppReleaseUpdateState.available);
    expect(facts.updateChannel, AppReleaseRecoveryChannel.nativeUpdate);
  });

  test(
    'public iOS recovery preserves nullable native update channel',
    () async {
      final reader = _remoteReader(
        MockClient(
          (_) async => http.Response(
            '{"platform":"ios",'
            '"latestVersion":"1.8.2","latestBuild":"18201",'
            '"minimumSupportedVersion":"1.8.0",'
            '"minimumSupportedBuild":"18000",'
            '"updateState":"available",'
            '"updateUrl":null,'
            '"recoveryUrl":"https://quwoquan.com/ios"}',
            200,
          ),
        ),
      );

      final facts = await reader.read(
        const AppReleaseRecoveryQuery(
          platform: 'ios',
          appVersion: '1.8.1',
          buildNumber: 18100,
        ),
      );

      expect(facts.updateState, AppReleaseUpdateState.available);
      expect(facts.platform, AppReleaseRecoveryPlatform.ios);
      expect(facts.updateChannel, AppReleaseRecoveryChannel.webOnly);
      expect(facts.updateUrl, isNull);
      expect(facts.recoveryUrl, 'https://quwoquan.com/ios');
    },
  );

  test('Android and Web reject a missing native update channel', () async {
    for (final platform in <String>['android', 'web']) {
      final reader = _remoteReader(
        MockClient(
          (_) async => http.Response(
            '{"platform":"$platform",'
            '"latestVersion":"1.8.2","latestBuild":"18201",'
            '"minimumSupportedVersion":"1.8.0",'
            '"minimumSupportedBuild":"18000",'
            '"updateState":"available",'
            '"updateUrl":null,'
            '"recoveryUrl":"https://quwoquan.com/"}',
            200,
          ),
        ),
      );

      await expectLater(
        reader.read(
          AppReleaseRecoveryQuery(
            platform: platform,
            appVersion: '1.8.1',
            buildNumber: 18100,
          ),
        ),
        throwsFormatException,
      );
    }
  });

  test('public iOS rejects a native update channel', () async {
    final reader = _remoteReader(
      MockClient(
        (_) async => http.Response(
          '{"platform":"ios",'
          '"latestVersion":"1.8.2","latestBuild":"18201",'
          '"minimumSupportedVersion":"1.8.0",'
          '"minimumSupportedBuild":"18000",'
          '"updateState":"available",'
          '"updateUrl":"https://cdn.quwoquan.com/download/ios",'
          '"recoveryUrl":"https://quwoquan.com/ios"}',
          200,
        ),
      ),
    );

    await expectLater(
      reader.read(
        const AppReleaseRecoveryQuery(
          platform: 'ios',
          appVersion: '1.8.1',
          buildNumber: 18100,
        ),
      ),
      throwsFormatException,
    );
  });

  test(
    'version client rejects platform or channel discriminator loss',
    () async {
      for (final response in <RecoveryVersionResponse>[
        const RecoveryVersionResponse(
          platform: RecoveryVersionPlatform.ios,
          latestVersion: '1.8.2',
          latestBuild: 18201,
          minimumSupportedVersion: '1.8.0',
          minimumSupportedBuild: 18000,
          updateState: RecoveryUpdateState.available,
          updateChannel: RecoveryVersionChannel.webOnly,
          updateUrl: null,
          recoveryUrl: 'https://quwoquan.com/ios',
        ),
        const RecoveryVersionResponse(
          platform: RecoveryVersionPlatform.android,
          latestVersion: '1.8.2',
          latestBuild: 18201,
          minimumSupportedVersion: '1.8.0',
          minimumSupportedBuild: 18000,
          updateState: RecoveryUpdateState.available,
          updateChannel: RecoveryVersionChannel.nativeUpdate,
          updateUrl: null,
          recoveryUrl: 'https://quwoquan.com/',
        ),
      ]) {
        final client = RecoveryVersionClient(
          gateway: RecoveryOperationGateway(
            operations: _StaticVersionOperations(response),
          ),
        );
        await expectLater(
          client.fetch(
            binding: _binding(),
            platform: 'android',
            appVersion: '1.8.1',
            buildNumber: 18100,
          ),
          throwsFormatException,
        );
      }
    },
  );

  test(
    'version client rejects non-https origin and expanded response',
    () async {
      final client = RecoveryVersionClient(
        gateway: _httpGateway(
          MockClient(
            (_) async => http.Response(
              '{"platform":"android",'
              '"latestVersion":"1.8.2","latestBuild":"18201",'
              '"minimumSupportedVersion":"1.8.0",'
              '"minimumSupportedBuild":"18000",'
              '"updateState":"available",'
              '"updateUrl":"https://cdn.quwoquan.com/download/android/latest.json",'
              '"recoveryUrl":"https://quwoquan.com/",'
              '"diagnosticId":"forbidden"}',
              200,
            ),
          ),
        ),
      );
      expect(
        () => _binding(baseUrl: 'http://api.quwoquan.com'),
        throwsFormatException,
      );
      await expectLater(
        client.fetch(
          binding: _binding(),
          platform: 'android',
          appVersion: '1.8.1',
          buildNumber: 18100,
        ),
        throwsA(
          isA<CloudException>()
              .having(
                (error) => error.type,
                'type',
                CloudErrorType.invalidResponse,
              )
              .having(
                (error) => error.sourceOperationId,
                'sourceOperationId',
                AppCloudOperationIds.opsAppReleaseGetAppRecoveryVersion,
              ),
        ),
      );
    },
  );

  test('version client fails closed on non-2xx and malformed JSON', () async {
    for (final response in <http.Response>[
      http.Response('{"code":"unavailable"}', 503),
      http.Response('{not-json', 200),
      http.Response(
        '{"platform":"android",'
        '"latestVersion":"1.8.2","latestBuild":"0",'
        '"minimumSupportedVersion":"1.8.0",'
        '"minimumSupportedBuild":"18000",'
        '"updateState":"required",'
        '"updateUrl":"https://cdn.quwoquan.com/download/android/latest.json",'
        '"recoveryUrl":"https://quwoquan.com/"}',
        200,
      ),
      http.Response(
        '{"platform":"android",'
        '"latestVersion":"1.8.2","latestBuild":"18201",'
        '"minimumSupportedVersion":"1.8.0",'
        '"minimumSupportedBuild":"18000",'
        '"updateState":"none",'
        '"updateUrl":"https://cdn.quwoquan.com/download/android/latest.json",'
        '"recoveryUrl":"https://quwoquan.com/"}',
        200,
      ),
    ]) {
      final client = RecoveryVersionClient(
        gateway: _httpGateway(MockClient((_) async => response)),
      );
      await expectLater(
        client.fetch(
          binding: _binding(),
          platform: 'android',
          appVersion: '1.8.1',
          buildNumber: 18100,
        ),
        throwsA(anything),
      );
    }
  });

  test(
    'version client maps timeout and TLS failures through canonical error',
    () async {
      for (final failure in <Object>[
        TimeoutException('version timeout'),
        HandshakeException('certificate rejected'),
      ]) {
        final client = RecoveryVersionClient(
          gateway: _httpGateway(MockClient((_) async => throw failure)),
        );
        await expectLater(
          client.fetch(
            binding: _binding(),
            platform: 'ios',
            appVersion: '1.8.1',
            buildNumber: 18100,
          ),
          throwsA(
            isA<CloudException>().having(
              (error) => error.sourceOperationId,
              'sourceOperationId',
              AppCloudOperationIds.opsAppReleaseGetAppRecoveryVersion,
            ),
          ),
        );
      }
    },
  );
}

RecoveryOperationGateway _httpGateway(http.Client client) {
  return RecoveryOperationGateway(
    operations: _VersionOperations(_remoteReader(client)),
  );
}

AppReleaseRecoveryReader _remoteReader(http.Client client) {
  final generatedClient = buildGeneratedCloudOperationClient(
    httpClient: CloudHttpClient(client: client),
    clientContextProvider: const _RecoveryClientContextProvider(),
    telemetrySink: const _NoopTelemetrySink(),
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.alpha,
      gatewayBaseUri: _binding().recoveryOrigin,
    ),
  );
  return RemoteAppReleaseRecoveryReader(
    client: generatedClient,
    invocationContext: () => CloudOperationInvocationContext(
      // 恢复版本读面在 canonical 契约里只绑定 `welcome`。
      surfaceId: AppUiSurfaces.welcome.id,
      clientPageId: OpsRequestPageIds.getAppRecoveryVersion,
      actor: const CloudOperationActorContext(
        deviceActorId: 'recovery-device-actor',
      ),
    ),
  );
}

final class _VersionOperations implements RecoveryRuntimeOperations {
  const _VersionOperations(this.reader);

  final AppReleaseRecoveryReader reader;

  @override
  Future<RecoveryVersionResponse> getVersion(
    RecoveryVersionRequest request,
  ) async {
    final facts = await reader.read(
      AppReleaseRecoveryQuery(
        platform: request.platform,
        appVersion: request.appVersion,
        buildNumber: request.buildNumber,
      ),
    );
    return RecoveryVersionResponse(
      platform: switch (facts.platform) {
        AppReleaseRecoveryPlatform.android => RecoveryVersionPlatform.android,
        AppReleaseRecoveryPlatform.ios => RecoveryVersionPlatform.ios,
        AppReleaseRecoveryPlatform.web => RecoveryVersionPlatform.web,
      },
      latestVersion: facts.latestVersion,
      latestBuild: facts.latestBuild,
      minimumSupportedVersion: facts.minimumSupportedVersion,
      minimumSupportedBuild: facts.minimumSupportedBuild,
      updateState: switch (facts.updateState) {
        AppReleaseUpdateState.none => RecoveryUpdateState.none,
        AppReleaseUpdateState.available => RecoveryUpdateState.available,
        AppReleaseUpdateState.required => RecoveryUpdateState.required,
      },
      updateChannel: switch (facts.updateChannel) {
        AppReleaseRecoveryChannel.nativeUpdate =>
          RecoveryVersionChannel.nativeUpdate,
        AppReleaseRecoveryChannel.webOnly => RecoveryVersionChannel.webOnly,
      },
      updateUrl: facts.updateUrl,
      recoveryUrl: facts.recoveryUrl,
    );
  }

  @override
  Future<void> reportFailure(RecoveryFailurePayload payload) =>
      throw UnsupportedError('not used by version contract');
}

final class _StaticVersionOperations implements RecoveryRuntimeOperations {
  const _StaticVersionOperations(this.version);

  final RecoveryVersionResponse version;

  @override
  Future<RecoveryVersionResponse> getVersion(
    RecoveryVersionRequest request,
  ) async => version;

  @override
  Future<void> reportFailure(RecoveryFailurePayload payload) =>
      throw UnsupportedError('not used by version discriminator test');
}

RecoveryRuntimeBinding _binding({
  String baseUrl = 'https://api.quwoquan.com',
}) => RecoveryRuntimeBinding.fromLaunchManifest(
  environment: 'alpha',
  recoveryBaseUrl: baseUrl,
  runtimeConfigDigest: 'sha256:${'1' * 64}',
  effectiveLaunchManifestDigest: 'sha256:${'2' * 64}',
);

final class _RecoveryClientContextProvider
    implements CloudClientContextProvider {
  const _RecoveryClientContextProvider();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'recovery-version-contract',
      platform: 'android',
      appVersion: '1.8.1',
      locale: 'zh-CN',
      deviceActorId: 'recovery-device-actor',
    );
  }
}

final class _NoopTelemetrySink implements CloudOperationTelemetrySink {
  const _NoopTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}
