import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

GeneratedCloudOperationClient buildAssistantRemoteTestOperationClient(
  CloudHttpClient httpClient,
) {
  return buildGeneratedCloudOperationClient(
    httpClient: httpClient,
    clientContextProvider: const _AssistantRemoteTestClientContext(),
    telemetrySink: const _AssistantRemoteTestTelemetrySink(),
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.gamma,
      gatewayBaseUri: Uri.parse('https://assistant.test'),
    ),
  );
}

final class AssistantRemoteTestAuthTokenProvider
    implements CloudAuthTokenProvider {
  const AssistantRemoteTestAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'assistant-test-token';
}

CloudOperationInvocationContext assistantRemoteTestInvocationContext(
  String clientPageId, {
  String? idempotencyKey,
  bool networkSurface = false,
}) {
  return CloudOperationInvocationContext(
    surfaceId: networkSurface
        ? AppUiSurfaces.globalSearchNetworkResults.id
        : AppUiSurfaces.personalAssistantDialog.id,
    routeId: networkSurface
        ? AppUiSurfaces.globalSearchNetworkResults.routeId
        : AppUiSurfaces.personalAssistantDialog.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(
      accountId: 'assistant-test-account',
      personaId: 'assistant-test-persona',
    ),
    idempotencyKey: idempotencyKey,
  );
}

final class _AssistantRemoteTestClientContext
    implements CloudClientContextProvider {
  const _AssistantRemoteTestClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'assistant-remote-test-session',
      platform: 'ios',
      appVersion: 'test',
      locale: 'zh-CN',
    );
  }
}

final class _AssistantRemoteTestTelemetrySink
    implements CloudOperationTelemetrySink {
  const _AssistantRemoteTestTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}
