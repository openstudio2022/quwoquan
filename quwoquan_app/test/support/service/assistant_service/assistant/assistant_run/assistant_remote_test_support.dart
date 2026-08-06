import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_presentation_capability_catalog.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class AssistantRecordingCommandClient extends http.BaseClient {
  AssistantRecordingCommandClient(this._responses);

  final List<Map<String, Object?>> _responses;
  final List<http.Request> requests = <http.Request>[];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    if (request is! http.Request) {
      throw StateError(
        'assistant command transport requires HTTP request body',
      );
    }
    requests.add(request);
    if (_responses.isEmpty) {
      throw StateError('unexpected assistant command request');
    }
    final response = _responses.removeAt(0);
    return http.StreamedResponse(
      Stream<List<int>>.value(utf8.encode(jsonEncode(response))),
      201,
      request: request,
      headers: const <String, String>{'content-type': 'application/json'},
    );
  }
}

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

AssistantPresentationCapabilitySnapshot
assistantRemoteTestPresentationCapabilities(
  AssistantPresentationSurfacePolicy surfacePolicy,
) {
  return AssistantPresentationCapabilitySnapshot(
    surfacePolicy: surfacePolicy,
    viewportClass: AssistantPresentationViewportClass.standard,
    platform: 'ios',
    darkTheme: false,
    textScale: 1.2,
    reducedMotion: true,
    offline: false,
    mediaEnabled: true,
    actionsEnabled: true,
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
