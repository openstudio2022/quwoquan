// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-plan-collaboration/spec.md#gwt-001
// readiness_case: gathering_plan_get_gathering_plan_app_local

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/adapters/gathering_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as cloud;

void main() {
  group('GetGatheringPlan App 读取契约', () {
    test('看板读取沿 canonical 只读 path 取回 current Revision', () async {
      final captured = <http.Request>[];
      final remote = _remote(captured, _planResponse);

      final board = await remote.loadCircle('gathering-1');

      final planRequest = captured.last;
      expect(planRequest.method, 'GET');
      expect(planRequest.url.path, '/gatherings/gathering-1/plan');
      expect(
        planRequest.headers['X-Client-Operation-Id'],
        cloud.AppCloudOperationIds.circleGatheringPlanGetGatheringPlan,
      );
      // 只读 query 不得携带幂等键，也不得带请求体。
      expect(planRequest.headers.containsKey('Idempotency-Key'), isFalse);
      expect(planRequest.body, isEmpty);

      expect(
        board.plan.capability.state,
        GatheringBoardCapabilityState.available,
      );
      expect(board.plan.items.single.title, '集合出发');
      expect(board.plan.capability.itemCount, 1);
    });

    test('Plan 未创建时看板只标记未配置，活动主体照常可读', () async {
      final board = await _boardWithPlanFailure(
        statusCode: 404,
        code: 'CIRCLE.USER.gathering_plan_not_found',
      );

      expect(board.activity.title, 'Canonical Gathering');
      expect(
        board.plan.capability.unavailableReason,
        GatheringBoardCapabilityUnavailableReason.notConfigured,
      );
    });

    test('越权读 Plan 时 fail-closed 到无权限，不伪装成未创建', () async {
      final board = await _boardWithPlanFailure(
        statusCode: 403,
        code: 'CIRCLE.USER.gathering_plan_permission_denied',
      );

      expect(
        board.plan.capability.unavailableReason,
        GatheringBoardCapabilityUnavailableReason.permissionDenied,
      );
    });

    test('Plan 存储失败时标记暂时不可用，不塌陷成空计划', () async {
      final board = await _boardWithPlanFailure(
        statusCode: 500,
        code: 'CIRCLE.SYSTEM.gathering_plan_storage_failed',
      );

      expect(
        board.plan.capability.unavailableReason,
        GatheringBoardCapabilityUnavailableReason.temporarilyUnavailable,
      );
      expect(board.plan.items, isEmpty);
    });
  });
}

Future<GatheringBoardCircleSlice> _boardWithPlanFailure({
  required int statusCode,
  required String code,
}) {
  final remote = _remote(<http.Request>[], (request) {
    if (_isPlanRequest(request)) {
      return http.Response(
        jsonEncode(<String, Object?>{'code': code, 'message': code}),
        statusCode,
        headers: const <String, String>{'content-type': 'application/json'},
      );
    }
    return _privateDetailResponse;
  });
  return remote.loadCircle('gathering-1');
}

bool _isPlanRequest(http.Request request) =>
    request.headers['X-Client-Operation-Id'] ==
    cloud.AppCloudOperationIds.circleGatheringPlanGetGatheringPlan;

Object _planResponse(http.Request request) =>
    _isPlanRequest(request) ? _gatheringPlanResponse : _privateDetailResponse;

RemoteGatheringFacet _remote(
  List<http.Request> captured,
  Object Function(http.Request request) responseFor,
) {
  final client = buildGeneratedCloudOperationClient(
    httpClient: CloudHttpClient(
      client: MockClient((request) async {
        captured.add(request);
        final response = responseFor(request);
        if (response is http.Response) {
          return response;
        }
        return http.Response(
          jsonEncode(response),
          200,
          headers: const <String, String>{'content-type': 'application/json'},
        );
      }),
      authTokenProvider: const _PlanTokenProvider(),
    ),
    clientContextProvider: const _PlanClientContext(),
    telemetrySink: const _NoopTelemetrySink(),
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.gamma,
      gatewayBaseUri: Uri.parse('https://test-gateway.example.com'),
    ),
  );
  return RemoteGatheringFacet(
    client: client,
    invocationContext: (String clientPageId, {String? idempotencyKey}) =>
        cloud.CloudOperationInvocationContext(
          surfaceId: 'gatheringBoard',
          routeId: 'gatheringBoard',
          clientPageId: clientPageId,
          actor: const cloud.CloudOperationActorContext(
            accountId: 'account-1',
            personaId: 'persona-1',
          ),
          idempotencyKey: idempotencyKey,
        ),
  );
}

const Map<String, Object?> _gatheringPlanResponse = <String, Object?>{
  'id': 'plan-1',
  'gatheringId': 'gathering-1',
  'version': 2,
  'currentRevisionId': 'plan-revision-1',
  'currentRevisionNumber': 1,
  'currentRevisionDigest': 'plan-digest-1',
  'revisions': <Object?>[
    <String, Object?>{
      'revisionId': 'plan-revision-1',
      'revisionNumber': 1,
      'baseRevisionNumber': 0,
      'baseRevisionDigest': 'plan-digest-0',
      'revisionDigest': 'plan-digest-1',
      'committedByPersonaId': 'host-persona',
      'items': <Object?>[
        <String, Object?>{
          'itemId': 'plan-item-1',
          'kind': 'agenda',
          'order': 1,
          'agenda': <String, Object?>{'content': '集合出发', 'durationMinutes': 45},
          'sourceRefs': <Object?>[],
        },
      ],
      'acknowledgementPolicy': <String, Object?>{'mode': 'none'},
      'affectedParticipationRefs': <Object?>[],
      'committedAt': '2026-08-09T01:00:00Z',
    },
  ],
  'proposals': <Object?>[],
  'acknowledgements': <Object?>[],
  'createdAt': '2026-08-09T01:00:00Z',
  'updatedAt': '2026-08-09T01:00:00Z',
};

const Map<String, Object?> _privateDetailResponse = <String, Object?>{
  'gatheringId': 'gathering-1',
  'aggregateVersion': 7,
  'createdByPersonaId': 'host-persona',
  'hostBinding': <String, Object?>{
    'hostSubjectKind': 'persona',
    'hostSubjectId': 'host-persona',
    'authorityEvidenceRef': 'persona:host-persona:self',
    'authorityVersion': 7,
  },
  'organizerAssignments': <Object?>[
    <String, Object?>{
      'personaId': 'host-persona',
      'role': 'primary_organizer',
      'authorityEvidenceRef': 'persona:host-persona:self',
      'authorityVersion': 7,
      'assignedAt': '2026-08-08T01:00:00Z',
      'version': 1,
    },
  ],
  'purpose': <String, Object?>{
    'title': 'Canonical Gathering',
    'summary': 'Private typed detail',
    'topicRefs': <Object?>['topic:travel-photography'],
    'requirementRefs': <Object?>['requirement:bring-water'],
    'sourceObjectRefs': <Object?>[],
    'costNotice': 'free',
  },
  'schedule': <String, Object?>{
    'timezone': 'Asia/Shanghai',
    'startAt': '2026-08-10T02:00:00Z',
    'endAt': '2026-08-10T05:00:00Z',
    'admissionClosesAt': '2026-08-10T01:00:00Z',
  },
  'place': <String, Object?>{
    'mode': 'physical',
    'coarsePlaceLabel': 'Shanghai',
    'exactMeetingPoint': 'Gate 1',
  },
  'policySet': <String, Object?>{
    'audiencePolicy': 'public',
    'admissionPolicy': 'open',
    'capacityPolicy': <String, Object?>{'maxParticipants': 4},
    'disclosurePolicy': <String, Object?>{
      'timeDisclosure': 'exact',
      'placeDisclosure': 'after_join',
      'rosterDisclosure': 'count_only',
    },
    'applicationQuestions': <Object?>[],
    'riskControlPolicyRef': 'risk-policy-1',
  },
  'admissionControl': <String, Object?>{'status': 'open', 'version': 3},
  'lifecycleStatus': 'published',
  'conversationId': 'conversation-1',
  'roomBindingStatus': 'ready',
  'currentGatheringRevisionId': 'gathering-revision-7',
  'currentGatheringRevisionNumber': 7,
  'capacity': <String, Object?>{
    'maxParticipants': 4,
    'activeSeatCount': 2,
    'invitedSeatHoldCount': 0,
    'occupiedSeats': 2,
    'remainingSeats': 2,
    'full': false,
  },
  'temporal': <String, Object?>{
    'temporalPhase': 'upcoming',
    'evaluatedAt': '2026-08-08T02:00:00Z',
  },
  'admission': <String, Object?>{
    'admissionState': 'accepting',
    'evaluatedAt': '2026-08-08T02:00:00Z',
  },
  'createdAt': '2026-08-08T01:00:00Z',
  'updatedAt': '2026-08-08T02:00:00Z',
};

final class _PlanTokenProvider implements CloudAuthTokenProvider {
  const _PlanTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'gathering-plan-contract-token';
}

final class _PlanClientContext implements CloudClientContextProvider {
  const _PlanClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'gathering-plan-contract-session',
      deviceActorId: 'gathering-plan-contract-device',
      platform: 'test',
      appVersion: 'test',
      locale: 'zh-CN',
    );
  }
}

final class _NoopTelemetrySink implements CloudOperationTelemetrySink {
  const _NoopTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}
