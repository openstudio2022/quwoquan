// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-002
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-003
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-005
// readiness_case: assistant_run_start_assistant_run_app_local
// readiness_case: assistant_run_get_assistant_run_app_local
// readiness_case: assistant_run_pause_assistant_run_app_local
// readiness_case: assistant_run_resume_assistant_run_app_local
// readiness_case: assistant_run_steer_assistant_run_app_local
// readiness_case: assistant_run_cancel_assistant_run_app_local
// readiness_case: assistant_run_approve_assistant_tool_use_app_local
// readiness_case: assistant_run_submit_device_action_receipt_app_local
// readiness_case: assistant_run_stream_assistant_run_events_app_local
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/di/assistant_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/generated/assistant/assistant_errors.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_remote_test_support.dart';

void main() {
  test(
    'StartAssistantRun and GetAssistantRun use exact generated wire',
    () async {
      final transport = _AssistantRunTransport();
      final httpClient = CloudHttpClient(
        client: transport,
        authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
      );
      addTearDown(httpClient.close);
      final remote = AssistantProductionComposition.sessionRunFacade(
        client: buildAssistantRemoteTestOperationClient(httpClient),
        invocationContext: assistantRemoteTestInvocationContext,
        presentationCapabilities: assistantRemoteTestPresentationCapabilities,
      );

      final started = await remote.startAssistantRun(
        sessionId: 'session-1',
        text: '  plan tomorrow  ',
        clientRequestId: 'start-request-1',
        intersectionEvidenceRefs: const <AssistantIntersectionEvidenceRef>[
          AssistantIntersectionEvidenceRef(
            intersectionId: 'intersection-1',
            evidenceId: 'snapshot-1',
            sourceRef: 'same_school',
            objectTypeRef: 'content.post',
            objectId: 'post-1',
          ),
        ],
      );
      final loaded = await remote.getAssistantRun(runId: '  run-1  ');

      expect(started.runId, 'run-1');
      expect(started.sessionId, 'session-1');
      expect(started.status, 'queued');
      expect(loaded.status, 'running');
      expect(loaded.revision, 2);
      expect(loaded.streamState.resumeToken, 'resume-2');

      final start = transport.requestFor(
        AppCloudOperationIds.assistantAssistantRunStartAssistantRun,
      );
      expect(start.method, 'POST');
      expect(start.url.path, '/assistant/sessions/session-1/runs');
      expect(start.url.queryParameters, isEmpty);
      _expectHeaders(
        start,
        operation: AppCloudOperationIds.assistantAssistantRunStartAssistantRun,
        pageId: AssistantRequestPageIds.startAssistantRun,
        idempotencyKey: 'start-request-1',
      );
      expect(jsonDecode(_requestBody(start)), <String, Object?>{
        'clientRequestId': 'start-request-1',
        'intent': <String, Object?>{
          'kind': 'answer',
          'answer': <String, Object?>{'text': 'plan tomorrow'},
        },
        'contextSnapshot': <String, Object?>{
          'intersectionEvidenceRefs': <Object?>[
            <String, Object?>{
              'intersectionId': 'intersection-1',
              'evidenceId': 'snapshot-1',
              'sourceRef': 'same_school',
              'objectTypeRef': 'content.post',
              'objectId': 'post-1',
            },
          ],
        },
        'surfaceCapabilities': <String, Object?>{
          'surfaceId': AppUiSurfaces.personalAssistantDialog.id,
          'supportedNodeKinds': _personalAssistantNodeKinds,
          'supportedActionIntents': <String>['ApproveTool'],
          'viewportClass': 'standard',
          'platform': 'ios',
          'theme': 'light',
          'textScale': 1.2,
          'reducedMotion': true,
          'offline': false,
        },
      });

      final get = transport.requestFor(
        AppCloudOperationIds.assistantAssistantRunGetAssistantRun,
      );
      expect(get.method, 'GET');
      expect(get.url.path, '/assistant/runs/run-1');
      expect(get.url.queryParameters, isEmpty);
      expect(_requestBody(get), isEmpty);
      _expectHeaders(
        get,
        operation: AppCloudOperationIds.assistantAssistantRunGetAssistantRun,
        pageId: AssistantRequestPageIds.getAssistantRun,
      );
    },
  );

  test(
    'pause resume steer and cancel preserve command identity and body',
    () async {
      final transport = _AssistantRunTransport();
      final httpClient = CloudHttpClient(
        client: transport,
        authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
      );
      addTearDown(httpClient.close);
      final remote = AssistantProductionComposition.sessionRunFacade(
        client: buildAssistantRemoteTestOperationClient(httpClient),
        invocationContext: assistantRemoteTestInvocationContext,
        presentationCapabilities: assistantRemoteTestPresentationCapabilities,
      );

      final paused = await remote.pauseAssistantRun(
        runId: 'run-1',
        commandRequestId: 'pause-request-1',
        reason: '  waiting for input  ',
      );
      final resumed = await remote.resumeAssistantRun(
        runId: 'run-1',
        commandRequestId: 'resume-request-1',
      );
      final steered = await remote.steerAssistantRun(
        runId: 'run-1',
        commandRequestId: 'steer-request-1',
        instruction: 'prefer the direct train',
      );
      final cancelled = await remote.cancelAssistantRun(
        runId: 'run-1',
        commandRequestId: 'cancel-request-1',
      );

      expect(paused.status, 'paused');
      expect(resumed.status, 'running');
      expect(steered.goal, 'prefer the direct train');
      expect(cancelled.status, 'cancelled');

      _expectCommand(
        transport,
        operation: AppCloudOperationIds.assistantAssistantRunPauseAssistantRun,
        pageId: AssistantRequestPageIds.pauseAssistantRun,
        path: '/assistant/runs/run-1/pause',
        idempotencyKey: 'pause-request-1',
        body: const <String, Object?>{'reason': 'waiting for input'},
      );
      _expectCommand(
        transport,
        operation: AppCloudOperationIds.assistantAssistantRunResumeAssistantRun,
        pageId: AssistantRequestPageIds.resumeAssistantRun,
        path: '/assistant/runs/run-1/resume',
        idempotencyKey: 'resume-request-1',
      );
      _expectCommand(
        transport,
        operation: AppCloudOperationIds.assistantAssistantRunSteerAssistantRun,
        pageId: AssistantRequestPageIds.steerAssistantRun,
        path: '/assistant/runs/run-1/steer',
        idempotencyKey: 'steer-request-1',
        body: const <String, Object?>{'instruction': 'prefer the direct train'},
      );
      _expectCommand(
        transport,
        operation: AppCloudOperationIds.assistantAssistantRunCancelAssistantRun,
        pageId: AssistantRequestPageIds.cancelAssistantRun,
        path: '/assistant/runs/run-1/cancel',
        idempotencyKey: 'cancel-request-1',
      );
    },
  );

  test('tool approval and device receipt remain two typed operations', () async {
    final transport = _AssistantRunTransport();
    final httpClient = CloudHttpClient(
      client: transport,
      authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
    );
    addTearDown(httpClient.close);
    final remote = AssistantProductionComposition.sessionRunFacade(
      client: buildAssistantRemoteTestOperationClient(httpClient),
      invocationContext: assistantRemoteTestInvocationContext,
      presentationCapabilities: assistantRemoteTestPresentationCapabilities,
    );

    final approval = await remote.approveAssistantToolUse(
      runId: 'run-1',
      toolInvocationId: 'tool-1',
      commandRequestId: 'approval-request-1',
      decision: 'approved',
      approvalPermit: 'approval-permit-1',
      installationId: 'installation-1',
      deviceId: 'device-1',
    );
    final receipt = AssistantDeviceActionExecutionReceipt(
      installationId: 'installation-1',
      deviceId: 'device-1',
      capability: 'calendar_create_reminder',
      inputDigest:
          'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      permit: 'device-permit-1',
      idempotencyKey: 'device-effect-1',
      outcome: 'completed',
      executedAt: DateTime.utc(2026, 8, 8, 12),
      deviceObjectId: 'calendar-event-1',
    );
    final continued = await remote.submitDeviceActionReceipt(
      runId: 'run-1',
      toolInvocationId: 'tool-1',
      commandRequestId: 'receipt-request-1',
      receipt: receipt,
    );

    expect(approval.runId, 'run-1');
    expect(approval.state, 'approved');
    expect(approval.deviceActionPermit?.toolInvocationId, 'tool-1');
    expect(approval.deviceActionPermit?.capability, 'calendar_create_reminder');
    expect(continued.status, 'running');
    expect(continued.revision, 8);

    _expectCommand(
      transport,
      operation:
          AppCloudOperationIds.assistantAssistantRunApproveAssistantToolUse,
      pageId: AssistantRequestPageIds.approveAssistantToolUse,
      path: '/assistant/runs/run-1/tool-invocations/tool-1/approval',
      idempotencyKey: 'approval-request-1',
      body: const <String, Object?>{
        'decision': 'approved',
        'approvalPermit': 'approval-permit-1',
        'installationId': 'installation-1',
        'deviceId': 'device-1',
      },
    );
    _expectCommand(
      transport,
      operation:
          AppCloudOperationIds.assistantAssistantRunSubmitDeviceActionReceipt,
      pageId: AssistantRequestPageIds.submitDeviceActionReceipt,
      path:
          '/assistant/runs/run-1/tool-invocations/tool-1/device-action-receipt',
      idempotencyKey: 'receipt-request-1',
      body: const <String, Object?>{
        'receipt': <String, Object?>{
          'installationId': 'installation-1',
          'deviceId': 'device-1',
          'capability': 'calendar_create_reminder',
          'inputDigest':
              'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
          'permit': 'device-permit-1',
          'idempotencyKey': 'device-effect-1',
          'outcome': 'completed',
          'executedAt': '2026-08-08T12:00:00.000Z',
          'deviceObjectId': 'calendar-event-1',
        },
      },
    );
  });

  test(
    'StreamAssistantRunEvents uses generated SSE descriptor and decode',
    () async {
      final transport = _AssistantRunTransport();
      final httpClient = CloudHttpClient(
        client: transport,
        authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
      );
      addTearDown(httpClient.close);
      final remote = AssistantProductionComposition.sessionRunFacade(
        client: buildAssistantRemoteTestOperationClient(httpClient),
        invocationContext: assistantRemoteTestInvocationContext,
        presentationCapabilities: assistantRemoteTestPresentationCapabilities,
      );

      final events = await remote
          .watchAssistantRunEvents(
            runId: '  run-1  ',
            lastEventId: '  resume-7  ',
          )
          .toList();

      expect(events, hasLength(1));
      expect(events.single.eventId, 'business-event-8');
      expect(events.single.seq, 8);
      expect(events.single.eventType, AssistantStreamEventType.completed);
      expect(events.single.payload, <String, Object?>{
        'status': 'completed',
        'finalAnswer': 'done',
      });

      final stream = transport.requestFor(
        AppCloudOperationIds.assistantAssistantRunStreamAssistantRunEvents,
      );
      expect(stream.method, 'GET');
      expect(stream.url.path, '/assistant/runs/run-1/events');
      expect(stream.url.queryParameters, <String, String>{
        'resumeToken': 'resume-7',
      });
      expect(_requestBody(stream), isEmpty);
      _expectHeaders(
        stream,
        operation:
            AppCloudOperationIds.assistantAssistantRunStreamAssistantRunEvents,
        pageId: AssistantRequestPageIds.streamAssistantRunEvents,
      );
      expect(stream.headers['Accept'], 'text/event-stream');
      expect(stream.headers['Last-Event-ID'], isNull);
    },
  );

  test('invalid identity and canonical state conflict fail closed', () async {
    final transport = _AssistantRunTransport(
      failureOperation:
          AppCloudOperationIds.assistantAssistantRunPauseAssistantRun,
    );
    final httpClient = CloudHttpClient(
      client: transport,
      authTokenProvider: const AssistantRemoteTestAuthTokenProvider(),
    );
    addTearDown(httpClient.close);
    final remote = AssistantProductionComposition.sessionRunFacade(
      client: buildAssistantRemoteTestOperationClient(httpClient),
      invocationContext: assistantRemoteTestInvocationContext,
      presentationCapabilities: assistantRemoteTestPresentationCapabilities,
    );

    expect(() => remote.getAssistantRun(runId: '  '), throwsArgumentError);
    expect(
      () => remote.watchAssistantRunEvents(runId: '  '),
      throwsArgumentError,
    );
    await expectLater(
      remote.pauseAssistantRun(
        runId: 'run-1',
        commandRequestId: 'pause-conflict-1',
      ),
      throwsA(
        isA<CloudException>()
            .having((error) => error.statusCode, 'statusCode', 409)
            .having(
              (error) => error.code,
              'code',
              AssistantErrorCode.runStateConflict.code,
            ),
      ),
    );
    expect(transport.requests, hasLength(1));
  });
}

const List<String> _personalAssistantNodeKinds = <String>[
  'card',
  'column',
  'row',
  'grid',
  'list',
  'carousel',
  'markdown',
  'text',
  'icon',
  'badge',
  'divider',
  'stat',
  'key_value',
  'entity_reference',
  'source_reference',
  'timeline',
  'route_map',
  'comparison_table',
  'source_list',
  'callout',
  'media',
  'media_gallery',
  'action_group',
  'choice_chips',
  'date_time_input',
  'confirmation_card',
];

void _expectCommand(
  _AssistantRunTransport transport, {
  required String operation,
  required String pageId,
  required String path,
  required String idempotencyKey,
  Map<String, Object?>? body,
}) {
  final request = transport.requestFor(operation);
  expect(request.method, 'POST');
  expect(request.url.path, path);
  expect(request.url.queryParameters, isEmpty);
  _expectHeaders(
    request,
    operation: operation,
    pageId: pageId,
    idempotencyKey: idempotencyKey,
  );
  if (body == null) {
    expect(_requestBody(request), isEmpty);
  } else {
    expect(jsonDecode(_requestBody(request)), body);
  }
}

void _expectHeaders(
  http.BaseRequest request, {
  required String operation,
  required String pageId,
  String? idempotencyKey,
}) {
  expect(request.headers['Authorization'], 'Bearer assistant-test-token');
  expect(request.headers['X-Client-Operation-Id'], operation);
  expect(request.headers['X-Client-Page-Id'], pageId);
  expect(
    request.headers['X-Client-Surface-Id'],
    AppUiSurfaces.personalAssistantDialog.id,
  );
  expect(
    request.headers['X-Client-Route-Id'],
    AppUiSurfaces.personalAssistantDialog.routeId,
  );
  expect(
    request.headers['X-Client-Session-Id'],
    'assistant-remote-test-session',
  );
  expect(request.headers['Idempotency-Key'], idempotencyKey);
}

String _requestBody(http.BaseRequest request) {
  if (request is! http.Request) {
    throw StateError('generated JSON operation did not use an HTTP request');
  }
  return request.body;
}

final class _AssistantRunTransport extends http.BaseClient {
  _AssistantRunTransport({this.failureOperation});

  final String? failureOperation;
  final List<http.BaseRequest> requests = <http.BaseRequest>[];

  http.BaseRequest requestFor(String operation) => requests.singleWhere(
    (request) => request.headers['X-Client-Operation-Id'] == operation,
  );

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requests.add(request);
    final operation = request.headers['X-Client-Operation-Id'];
    if (operation == failureOperation) {
      return _json(request, <String, Object?>{
        'code': AssistantErrorCode.runStateConflict.code,
      }, statusCode: 409);
    }
    return switch (operation) {
      AppCloudOperationIds.assistantAssistantRunStartAssistantRun => _json(
        request,
        _runEnvelope(status: 'queued', revision: 1),
        statusCode: 201,
      ),
      AppCloudOperationIds.assistantAssistantRunGetAssistantRun => _json(
        request,
        _runEnvelope(status: 'running', revision: 2),
      ),
      AppCloudOperationIds.assistantAssistantRunPauseAssistantRun => _json(
        request,
        _runEnvelope(status: 'paused', revision: 3),
      ),
      AppCloudOperationIds.assistantAssistantRunResumeAssistantRun => _json(
        request,
        _runEnvelope(status: 'running', revision: 4),
      ),
      AppCloudOperationIds.assistantAssistantRunSteerAssistantRun => _json(
        request,
        _runEnvelope(
          status: 'running',
          revision: 5,
          goal: 'prefer the direct train',
        ),
      ),
      AppCloudOperationIds.assistantAssistantRunCancelAssistantRun => _json(
        request,
        _runEnvelope(status: 'cancelled', revision: 6),
      ),
      AppCloudOperationIds.assistantAssistantRunApproveAssistantToolUse =>
        _json(request, _approval()),
      AppCloudOperationIds.assistantAssistantRunSubmitDeviceActionReceipt =>
        _json(request, _runEnvelope(status: 'running', revision: 8)),
      AppCloudOperationIds.assistantAssistantRunStreamAssistantRunEvents =>
        _sse(request),
      _ => throw StateError('unexpected AssistantRun operation: $operation'),
    };
  }

  Map<String, Object?> _runEnvelope({
    required String status,
    required int revision,
    String goal = 'plan tomorrow',
  }) => <String, Object?>{
    'runId': 'run-1',
    'sessionId': 'session-1',
    'status': status,
    'reasoningProfile': 'balanced',
    'goal': goal,
    'traceId': 'trace-run-1',
    'revision': revision,
    'streamState': <String, Object?>{
      'lastSeq': revision,
      'completed': status == 'cancelled',
      'resumeToken': 'resume-$revision',
    },
    'createdAt': '2026-08-08T12:00:00Z',
    if (status == 'cancelled') 'completedAt': '2026-08-08T12:00:10Z',
  };

  Map<String, Object?> _approval() => const <String, Object?>{
    'runId': 'run-1',
    'state': 'approved',
    'deviceActionPermit': <String, Object?>{
      'runId': 'run-1',
      'toolInvocationId': 'tool-1',
      'installationId': 'installation-1',
      'deviceId': 'device-1',
      'capability': 'calendar_create_reminder',
      'inputDigest':
          'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'idempotencyKey': 'device-effect-1',
      'approvalRef': 'approval-1',
      'expiresAt': '2026-08-08T12:05:00Z',
      'permit': 'device-permit-1',
    },
  };

  http.StreamedResponse _sse(http.BaseRequest request) {
    final event = <String, Object?>{
      'schema': 'assistant_stream_event',
      'eventId': 'business-event-8',
      'sessionId': 'session-1',
      'runId': 'run-1',
      'seq': 8,
      'eventType': 'completed',
      'traceId': 'trace-run-1',
      'payload': const <String, Object?>{
        'status': 'completed',
        'finalAnswer': 'done',
      },
      'createdAt': '2026-08-08T12:00:08Z',
    };
    final body =
        'id: resume-8\n'
        'event: completed\n'
        'data: ${jsonEncode(event)}\n\n';
    return http.StreamedResponse(
      Stream<List<int>>.value(utf8.encode(body)),
      200,
      request: request,
      headers: const <String, String>{'content-type': 'text/event-stream'},
    );
  }

  http.StreamedResponse _json(
    http.BaseRequest request,
    Map<String, Object?> body, {
    int statusCode = 200,
  }) => http.StreamedResponse(
    Stream<List<int>>.value(utf8.encode(jsonEncode(body))),
    statusCode,
    request: request,
    headers: const <String, String>{'content-type': 'application/json'},
  );
}
