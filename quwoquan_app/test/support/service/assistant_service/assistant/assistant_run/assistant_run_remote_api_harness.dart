import 'dart:io';

import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_session_run_facade.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_presentation_capability_catalog.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/assistant_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:uuid/uuid.dart';

import '../../../../runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _definedRuntimeEnvironment = String.fromEnvironment('APP_RUNTIME_ENV');
const _definedGatewayBaseUrl = String.fromEnvironment('CLOUD_GATEWAY_BASE_URL');
const _definedAccessToken = String.fromEnvironment('TEST_AUTH_TOKEN');
const _definedPersonaId = String.fromEnvironment('TEST_PERSONA_ID');

final class AssistantRunRemoteApiHarness {
  AssistantRunRemoteApiHarness._({
    required this.environment,
    required this.personaId,
    required this._httpClient,
    required this.telemetry,
    required this.composition,
  });

  static Future<AssistantRunRemoteApiHarness> fromEnvironment({
    Set<CloudEnvironment> allowedEnvironments = const {
      CloudEnvironment.beta,
      CloudEnvironment.gamma,
    },
  }) async {
    final environmentName = _readInput(
      'APP_RUNTIME_ENV',
      _definedRuntimeEnvironment,
    );
    final environment = CloudEnvironment.values.where(
      (candidate) => candidate.name == environmentName,
    );
    if (environment.isEmpty ||
        !allowedEnvironments.contains(environment.single)) {
      throw StateError(
        'Assistant Remote API integration requires APP_RUNTIME_ENV in '
        '${allowedEnvironments.map((item) => item.name).join(', ')}.',
      );
    }

    final gatewayText = _readInput(
      'CLOUD_GATEWAY_BASE_URL',
      _definedGatewayBaseUrl,
    );
    final gateway = Uri.tryParse(gatewayText);
    if (gateway == null ||
        !gateway.isAbsolute ||
        gateway.host.isEmpty ||
        (gateway.scheme != 'http' && gateway.scheme != 'https')) {
      throw StateError(
        'Assistant Remote API integration requires an injected absolute '
        'HTTP(S) CLOUD_GATEWAY_BASE_URL.',
      );
    }

    final accessToken = _readInput('TEST_AUTH_TOKEN', _definedAccessToken);
    final personaId = _readInput('TEST_PERSONA_ID', _definedPersonaId);
    if (accessToken.isEmpty || personaId.isEmpty) {
      throw StateError(
        'Assistant Remote API integration requires TEST_AUTH_TOKEN and '
        'TEST_PERSONA_ID from the candidate-bound nonprod identity pool.',
      );
    }

    final httpClient = CloudHttpClient(
      authTokenProvider: _EnvironmentAuthTokenProvider(accessToken),
    );
    final clientContext = _AssistantApiClientContext(environmentName);
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    final generatedClient = buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: clientContext,
      telemetrySink: telemetry.sink,
      environment: CloudRuntimeEnvironment(
        environment: environment.single,
        gatewayBaseUri: gateway,
      ),
    );
    final composition = AssistantProductionComposition.sessionRunFacade(
      client: generatedClient,
      presentationCapabilities: _presentationCapabilities,
      invocationContext:
          (clientPageId, {idempotencyKey, networkSurface = false}) =>
              CloudOperationInvocationContext(
                surfaceId: AppUiSurfaces.personalAssistantDialog.id,
                routeId: AppUiSurfaces.personalAssistantDialog.routeId,
                clientPageId: clientPageId,
                actor: CloudOperationActorContext(
                  personaId: personaId,
                  deviceActorId: 'assistant-api-integration-device',
                ),
                idempotencyKey: idempotencyKey,
              ),
    );
    return AssistantRunRemoteApiHarness._(
      environment: environment.single,
      personaId: personaId,
      httpClient: httpClient,
      telemetry: telemetry,
      composition: composition,
    );
  }

  final CloudEnvironment environment;
  final String personaId;
  final CloudHttpClient _httpClient;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final AssistantSessionRunComposition composition;

  Future<AssistantRemoteRunResult> execute(
    String prompt, {
    String? sessionId,
  }) async {
    final requestIdentity = const Uuid().v4();
    final resolvedSessionId =
        sessionId ??
        (await composition.createAssistantSession(
          summary: prompt,
          clientRequestId: 'session-$requestIdentity',
        )).sessionId;
    final run = await composition.startAssistantRun(
      sessionId: resolvedSessionId,
      text: prompt,
      clientRequestId: 'run-$requestIdentity',
    );
    final events = <AssistantStreamEventWire>[];
    await for (final event
        in composition
            .watchAssistantRunEvents(runId: run.runId)
            .timeout(const Duration(minutes: 3))) {
      events.add(event);
      if (_isTerminal(event.eventType)) {
        break;
      }
    }
    if (events.isEmpty || !_isTerminal(events.last.eventType)) {
      throw StateError(
        'Assistant Remote stream ended without a terminal event for '
        '${run.runId}.',
      );
    }
    final terminalRun = await composition.getAssistantRun(runId: run.runId);
    final snapshot = terminalRun.terminalSnapshot;
    if (snapshot == null) {
      throw StateError(
        'Assistant Remote run ${run.runId} has no terminal snapshot.',
      );
    }
    return AssistantRemoteRunResult(
      sessionId: resolvedSessionId,
      run: terminalRun,
      snapshot: snapshot,
      events: List<AssistantStreamEventWire>.unmodifiable(events),
    );
  }

  Future<void> close() async {
    try {
      await telemetry.waitForEvents(minimumCount: 1);
    } finally {
      _httpClient.close();
      await telemetry.dispose();
    }
  }
}

final class AssistantRemoteRunResult {
  AssistantRemoteRunResult({
    required this.sessionId,
    required this.run,
    required this.snapshot,
    required this.events,
  });

  final String sessionId;
  final AssistantRunEnvelopeWire run;
  final AssistantRunTerminalSnapshotView snapshot;
  final List<AssistantStreamEventWire> events;

  String get answer => snapshot.answerText.trim();

  List<String> get eventTypes =>
      events.map((event) => event.eventType.wireName).toList(growable: false);

  List<AssistantRunVisibleReferenceView> get acceptedReferences => snapshot
      .processes
      .expand((process) => process.acceptedReferences)
      .toList(growable: false);

  int get searchedDocumentCount => snapshot.processes.fold<int>(
    0,
    (total, process) => total + process.searchedDocumentCount,
  );

  int get acceptedDocumentCount => snapshot.processes.fold<int>(
    0,
    (total, process) => total + process.acceptedDocumentCount,
  );

  Set<String> get selectedSkillIds => snapshot.processes
      .map((process) => process.skillId.trim())
      .where((value) => value.isNotEmpty)
      .toSet();

  Set<String> get toolNames =>
      <String>{for (final event in events) _toolNameForEvent(event.payload)}
        ..remove('');
}

String _readInput(String name, String compileTimeValue) {
  final defined = compileTimeValue.trim();
  if (defined.isNotEmpty) return defined;
  return Platform.environment[name]?.trim() ?? '';
}

AssistantPresentationCapabilitySnapshot _presentationCapabilities(
  AssistantPresentationSurfacePolicy surfacePolicy,
) {
  return AssistantPresentationCapabilitySnapshot(
    surfacePolicy: surfacePolicy,
    viewportClass: AssistantPresentationViewportClass.standard,
    platform: 'api-integration',
    darkTheme: false,
    textScale: 1,
    reducedMotion: false,
    offline: false,
    mediaEnabled: true,
    actionsEnabled: true,
  );
}

String _toolNameForEvent(Map<String, dynamic> payload) {
  final direct = payload['toolName']?.toString().trim() ?? '';
  if (direct.isNotEmpty) return direct;
  final toolCall = payload['toolCall'];
  if (toolCall is Map) {
    return toolCall['toolName']?.toString().trim() ?? '';
  }
  final process = payload['process'];
  if (process is Map) {
    return process['toolName']?.toString().trim() ?? '';
  }
  return '';
}

bool _isTerminal(AssistantStreamEventType eventType) => switch (eventType) {
  AssistantStreamEventType.completed ||
  AssistantStreamEventType.failed ||
  AssistantStreamEventType.cancelled => true,
  _ => false,
};

final class _EnvironmentAuthTokenProvider implements CloudAuthTokenProvider {
  const _EnvironmentAuthTokenProvider(this.token);

  final String token;

  @override
  Future<String?> getAccessToken() async => token;
}

final class _AssistantApiClientContext implements CloudClientContextProvider {
  const _AssistantApiClientContext(this.environment);

  final String environment;

  @override
  CloudClientContextSnapshot snapshot() => CloudClientContextSnapshot(
    sessionId: 'assistant-$environment-api-integration',
    deviceActorId: 'assistant-api-integration-device',
    platform: 'test',
    appVersion: 'api-integration',
    locale: 'zh-CN',
  );
}
