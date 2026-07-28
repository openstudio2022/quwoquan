// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/learning-event-ingestion/spec.md#gwt-001
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_learning_fact_remote.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:uuid/uuid.dart';

import '../../../support/recording_cloud_operation_telemetry_sink.dart';

const _gatewayUrl = String.fromEnvironment(
  'CLOUD_GATEWAY_BASE_URL',
  defaultValue: '',
);
const _definedAccessToken = String.fromEnvironment('TEST_AUTH_TOKEN');
const _personaId = String.fromEnvironment('TEST_PERSONA_ID');
const _definedEvidencePath = String.fromEnvironment(
  'ASSISTANT_LEARNING_REMOTE_EVIDENCE_PATH',
);
final _accessToken = _definedAccessToken.trim().isNotEmpty
    ? _definedAccessToken
    : Platform.environment['TEST_AUTH_TOKEN']?.trim() ?? '';
final _evidencePath = _definedEvidencePath.trim().isNotEmpty
    ? _definedEvidencePath
    : Platform.environment['ASSISTANT_LEARNING_REMOTE_EVIDENCE_PATH']?.trim() ??
          '';

final class _GammaAssistantClientContext implements CloudClientContextProvider {
  const _GammaAssistantClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'gamma-assistant-learning-api-integration',
      deviceActorId: 'gamma-assistant-learning-device',
      platform: 'test',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}

void main() {
  setUpAll(() {
    if (_accessToken.isEmpty) {
      fail(
        'Assistant learning Remote API verification requires TEST_AUTH_TOKEN. '
        'Use the local Gamma acceptance-session issuer.',
      );
    }
    if (_personaId.trim().isEmpty) {
      fail(
        'Assistant learning Remote API verification requires TEST_PERSONA_ID. '
        'Use the local Gamma acceptance-session issuer.',
      );
    }
  });

  test(
    'generated learning Remote round-trips one durable fact identity',
    () async {
      final httpClient = _buildGammaHttpClient();
      final telemetry = RecordingCloudOperationTelemetrySink();
      addTearDown(httpClient.close);
      final conversationFacet = RemoteAssistantRepository(
        httpClient: httpClient,
        consentActorScope: 'gamma-assistant-learning-api-integration',
      );
      final generatedClient = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: const _GammaAssistantClientContext(),
        telemetrySink: telemetry,
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse(_gatewayUrl),
        ),
      );
      final learningFacet = RemoteAssistantLearningFactAppendAdapter(
        client: generatedClient,
        invocationContext: (clientPageId, {required idempotencyKey}) =>
            CloudOperationInvocationContext(
              surfaceId: AppUiSurfaces.personalAssistantDialog.id,
              routeId: AppUiSurfaces.personalAssistantDialog.routeId,
              clientPageId: clientPageId,
              actor: const CloudOperationActorContext(
                personaId: _personaId,
                deviceActorId: 'gamma-assistant-learning-device',
              ),
              idempotencyKey: idempotencyKey,
            ),
      );

      final identity = const Uuid().v4();
      final conversation = await conversationFacet.createAssistantConversation(
        summary: 'Gamma learning verification',
        clientRequestId: 'conversation-$identity',
      );
      final run = await conversationFacet.startAssistantRun(
        conversationId: conversation.conversationId,
        text: '请给出一句简短的商用验证回复',
        clientRequestId: 'run-$identity',
      );
      final request = AppendAssistantLearningFactRequest(
        eventId: 'learning-$identity',
        eventVersion: 1,
        factType: AssistantLearningFactType.userFeedback,
        assistantTurnId: run.turnId,
        referralSource: AssistantReferralSource.assistantConversation,
        domainId: 'assistant',
        feedbackType: FeedbackType.useful,
        queryText: '该原始文本只能留在受控事实中',
        trainingEligible: false,
        occurredAt: DateTime.now().toUtc().toIso8601String(),
      );

      final first = await learningFacet.appendUserFact(request: request);
      final replay = await learningFacet.appendUserFact(request: request);

      expect(conversation.conversationId, isNotEmpty);
      expect(run.turnId, isNotEmpty);
      expect(first.accepted, isTrue);
      expect(first.deduplicated, isFalse);
      expect(first.payloadDigest, isNotEmpty);
      expect(replay.accepted, isTrue);
      expect(replay.deduplicated, isTrue);
      expect(replay.appendSequence, first.appendSequence);
      expect(replay.payloadDigest, first.payloadDigest);
      expect(telemetry.events, hasLength(2));
      expect(telemetry.events.every((event) => event.succeeded), isTrue);

      await _writeRemoteEvidence(<String, Object?>{
        'schema': 'assistant-learning-remote-api-evidence-v1',
        'status': 'passed',
        'conversationId': conversation.conversationId,
        'turnId': run.turnId,
        'eventId': first.eventId,
        'eventVersion': first.eventVersion,
        'appendSequence': first.appendSequence,
        'payloadDigest': first.payloadDigest,
        'replayDeduplicated': replay.deduplicated,
        'operations': telemetry.events
            .map(
              (event) => <String, Object?>{
                'operationId': event.canonicalOperationId,
                'requestId': event.requestId,
                'traceId': event.traceId,
                'succeeded': event.succeeded,
              },
            )
            .toList(growable: false),
      });
    },
  );
}

Future<void> _writeRemoteEvidence(Map<String, Object?> evidence) async {
  if (_evidencePath.isEmpty) return;
  final output = File(_evidencePath);
  await output.parent.create(recursive: true);
  await output.writeAsString('${jsonEncode(evidence)}\n');
}

CloudHttpClient _buildGammaHttpClient() => CloudHttpClient(
  authTokenProvider: _StaticTokenProvider(_accessToken),
);

final class _StaticTokenProvider implements CloudAuthTokenProvider {
  const _StaticTokenProvider(this.token);

  final String token;

  @override
  Future<String?> getAccessToken() async => token;
}
