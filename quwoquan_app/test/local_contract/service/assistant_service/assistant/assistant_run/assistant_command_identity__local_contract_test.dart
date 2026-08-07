// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-stream-protocol/spec.md#gwt-001
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_presentation_capability_catalog.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/di/assistant_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_remote_test_support.dart';

void main() {
  test(
    'assistant command body and Idempotency-Key share one stable identity',
    () async {
      final transport = AssistantRecordingCommandClient(<Map<String, Object?>>[
        <String, Object?>{
          'sessionId': 'session-1',
          'userId': 'user-1',
          'state': 'active',
          'activeTurnId': '',
          'lastTurnId': '',
          'summary': 'assistant test',
          'createdAt': '2026-07-24T09:00:00Z',
          'updatedAt': '2026-07-24T09:00:00Z',
        },
        <String, Object?>{
          'runId': 'run-1',
          'sessionId': 'session-1',
          'status': 'queued',
          'goal': 'help me plan today',
          'streamState': <String, Object?>{},
          'createdAt': '2026-07-24T09:00:01Z',
        },
      ]);
      final httpClient = CloudHttpClient(
        client: transport,
        authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
      );
      final repository = AssistantProductionComposition.sessionRunFacade(
        client: buildAssistantRemoteTestOperationClient(httpClient),
        invocationContext: assistantRemoteTestInvocationContext,
        presentationCapabilities: assistantRemoteTestPresentationCapabilities,
      );

      await repository.createAssistantSession(
        summary: 'assistant test',
        clientRequestId: 'session-intent-1',
      );
      await repository.startAssistantRun(
        sessionId: 'session-1',
        text: 'help me plan today',
        clientRequestId: 'run-intent-1',
      );

      expect(transport.requests, hasLength(2));
      final create = transport.requests[0];
      final createBody = jsonDecode(create.body) as Map<String, dynamic>;
      expect(create.headers['Idempotency-Key'], 'session-intent-1');
      expect(createBody['clientRequestId'], 'session-intent-1');
      expect(createBody['summary'], 'assistant test');
      expect(create.headers['X-Client-Page-Id'], isNotEmpty);
      expect(create.headers['X-Client-Session-Id'], isNotEmpty);
      expect(create.headers['X-Client-Surface-Id'], isNotEmpty);
      expect(create.headers['X-Client-Route-Id'], isNotEmpty);
      expect(create.headers['X-Client-Operation-Id'], isNotEmpty);
      expect(create.headers['X-Trace-Id'], startsWith('APP.'));

      final start = transport.requests[1];
      final startBody = jsonDecode(start.body) as Map<String, dynamic>;
      expect(start.headers['Idempotency-Key'], 'run-intent-1');
      expect(startBody['clientRequestId'], 'run-intent-1');
      expect(startBody['intent'], <String, dynamic>{
        'kind': 'answer',
        'answer': <String, dynamic>{'text': 'help me plan today'},
      });
      expect(
        startBody['surfaceCapabilities'],
        containsPair('surfaceId', AppUiSurfaces.personalAssistantDialog.id),
      );
      expect(
        (startBody['surfaceCapabilities'] as Map<String, dynamic>),
        allOf(
          containsPair('viewportClass', 'standard'),
          isNot(containsPair('viewportClass', 'any')),
          containsPair('platform', 'ios'),
          containsPair('theme', 'light'),
          containsPair('textScale', 1.2),
          containsPair('reducedMotion', true),
          containsPair('offline', false),
        ),
      );
      final nodeKinds =
          ((startBody['surfaceCapabilities']
                      as Map<String, dynamic>)['supportedNodeKinds']
                  as List<dynamic>)
              .cast<String>();
      expect(
        nodeKinds,
        containsAll(<String>[
          'markdown',
          'route_map',
          'comparison_table',
          'media',
          'confirmation_card',
        ]),
      );
      expect(start.headers['X-Client-Page-Id'], isNotEmpty);
      expect(start.headers['X-Client-Session-Id'], isNotEmpty);
      expect(start.headers['X-Client-Surface-Id'], isNotEmpty);
      expect(start.headers['X-Client-Route-Id'], isNotEmpty);
      expect(start.headers['X-Client-Operation-Id'], isNotEmpty);
      expect(start.headers['X-Trace-Id'], startsWith('APP.'));
    },
  );

  test('assistant command rejects an empty client request identity', () async {
    final transport = AssistantRecordingCommandClient(
      const <Map<String, Object?>>[],
    );
    final httpClient = CloudHttpClient(
      client: transport,
      authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
    );
    final repository = AssistantProductionComposition.sessionRunFacade(
      client: buildAssistantRemoteTestOperationClient(httpClient),
      invocationContext: assistantRemoteTestInvocationContext,
      presentationCapabilities: assistantRemoteTestPresentationCapabilities,
    );

    await expectLater(
      repository.createAssistantSession(clientRequestId: ' '),
      throwsArgumentError,
    );
    expect(transport.requests, isEmpty);
  });

  test(
    'offline capability snapshot strips media and actions before StartAssistantRun',
    () async {
      final transport = AssistantRecordingCommandClient(<Map<String, Object?>>[
        <String, Object?>{
          'runId': 'run-offline',
          'sessionId': 'session-offline',
          'status': 'queued',
          'goal': 'offline request',
          'streamState': <String, Object?>{},
          'createdAt': '2026-07-24T09:00:01Z',
        },
      ]);
      final httpClient = CloudHttpClient(
        client: transport,
        authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
      );
      final repository = AssistantProductionComposition.sessionRunFacade(
        client: buildAssistantRemoteTestOperationClient(httpClient),
        invocationContext: assistantRemoteTestInvocationContext,
        presentationCapabilities: (surfacePolicy) =>
            AssistantPresentationCapabilitySnapshot(
              surfacePolicy: surfacePolicy,
              viewportClass: AssistantPresentationViewportClass.compact,
              platform: 'android',
              darkTheme: true,
              textScale: 1.4,
              reducedMotion: true,
              offline: true,
              mediaEnabled: true,
              actionsEnabled: true,
            ),
      );

      await repository.startAssistantRun(
        sessionId: 'session-offline',
        text: 'offline request',
        clientRequestId: 'run-offline-request',
      );

      final body =
          jsonDecode(transport.requests.single.body) as Map<String, dynamic>;
      final capabilities = body['surfaceCapabilities'] as Map<String, dynamic>;
      final nodeKinds = (capabilities['supportedNodeKinds'] as List<dynamic>)
          .cast<String>();
      expect(capabilities, containsPair('offline', true));
      expect(capabilities, containsPair('viewportClass', 'compact'));
      expect(nodeKinds, containsAll(<String>['route_map', 'comparison_table']));
      expect(nodeKinds, isNot(contains('media')));
      expect(nodeKinds, isNot(contains('media_gallery')));
      expect(nodeKinds, isNot(contains('action_group')));
      expect(nodeKinds, isNot(contains('confirmation_card')));
    },
  );

  test(
    'run controls and tool actions all delegate to their generated operations',
    () async {
      final transport = AssistantRecordingCommandClient(<Map<String, Object?>>[
        <String, Object?>{
          'runId': 'run-control',
          'sessionId': 'session-control',
          'status': 'paused',
          'goal': 'pause the run',
          'streamState': <String, Object?>{},
          'createdAt': '2026-07-24T09:00:01Z',
        },
        <String, Object?>{'runId': 'run-control', 'state': 'approved'},
        <String, Object?>{
          'runId': 'run-control',
          'sessionId': 'session-control',
          'status': 'running',
          'goal': 'pause the run',
          'streamState': <String, Object?>{},
          'createdAt': '2026-07-24T09:00:01Z',
        },
      ]);
      final repository = AssistantProductionComposition.sessionRunFacade(
        client: buildAssistantRemoteTestOperationClient(
          CloudHttpClient(
            client: transport,
            authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
          ),
        ),
        invocationContext: assistantRemoteTestInvocationContext,
        presentationCapabilities: assistantRemoteTestPresentationCapabilities,
      );

      await repository.pauseAssistantRun(
        runId: 'run-control',
        commandRequestId: 'pause-control-1',
      );
      expect(
        transport.requests.single.headers['X-Client-Operation-Id'],
        AppCloudOperationIds.assistantAssistantRunPauseAssistantRun,
      );

      // 工具审批与设备动作回执已完成 generated handoff：两者都是真实 typed
      // 操作，各自携带自己的 operation id 与稳定 Idempotency-Key。
      final approval = await repository.approveAssistantToolUse(
        runId: 'run-control',
        toolInvocationId: 'tool-1',
        commandRequestId: 'approve-control-1',
        decision: 'approved',
        approvalPermit: 'permit-1',
      );
      expect(approval.runId, 'run-control');
      expect(approval.state, 'approved');
      expect(
        transport.requests[1].headers['X-Client-Operation-Id'],
        AppCloudOperationIds.assistantAssistantRunApproveAssistantToolUse,
      );
      expect(transport.requests[1].headers['Idempotency-Key'], 'approve-control-1');

      final receiptResult = await repository.submitDeviceActionReceipt(
        runId: 'run-control',
        toolInvocationId: 'tool-1',
        commandRequestId: 'receipt-control-1',
        receipt: AssistantDeviceActionExecutionReceipt(
          installationId: 'installation_test',
          deviceId: 'device_test',
          capability: 'calendar_create_reminder',
          inputDigest:
              'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          permit: 'permit-1',
          idempotencyKey: 'receipt-control-1',
          outcome: 'completed',
          executedAt: DateTime.utc(2026, 7, 24, 9, 1),
        ),
      );
      expect(receiptResult.runId, 'run-control');
      expect(
        transport.requests[2].headers['X-Client-Operation-Id'],
        AppCloudOperationIds.assistantAssistantRunSubmitDeviceActionReceipt,
      );
      expect(transport.requests[2].headers['Idempotency-Key'], 'receipt-control-1');
      expect(transport.requests, hasLength(3));
    },
  );
}
