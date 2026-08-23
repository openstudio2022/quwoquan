// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-004
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-005
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-011
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-012
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-004
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-008
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-009
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-012
// readiness_case: gathering_cancel_gathering_app_local
// readiness_case: gathering_complete_gathering_app_local
// readiness_case: gathering_create_gathering_draft_app_local
// readiness_case: gathering_get_gathering_app_local
// readiness_case: gathering_join_open_gathering_app_local
// readiness_case: gathering_pause_gathering_admission_app_local
// readiness_case: gathering_review_gathering_application_app_local
// readiness_case: gathering_resume_gathering_admission_app_local

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/adapters/gathering_remote.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as cloud;

void main() {
  group('RemoteGatheringFacet generated HTTP contract', () {
    test(
      'CreateGatheringDraft preserves the full draft and replay identity',
      () async {
        final captured = <http.Request>[];
        var callCount = 0;
        final remote = _remote(captured, (_) {
          callCount += 1;
          return _commandResponse(
            version: 1,
            lifecycle: 'draft',
            roomBinding: 'pending',
            replayed: callCount > 1,
          );
        });
        final input = _createDraftInput();

        final first = await remote.createDraft(input);
        final replay = await remote.createDraft(input);

        for (final request in captured) {
          _expectCommandRequest(
            request,
            method: 'POST',
            path: '/gatherings',
            operationId:
                cloud.AppCloudOperationIds.circleGatheringCreateGatheringDraft,
            idempotencyKey: input.idempotencyKey,
            body: _createDraftBody,
          );
        }
        expect(first.gatheringId, 'gathering-1');
        expect(first.aggregateVersion, 1);
        expect(first.lifecycleStatus, GatheringLifecycleStatus.draft);
        expect(first.roomBindingStatus, GatheringRoomBindingStatus.pending);
        expect(first.idempotentReplay, isFalse);
        expect(replay.gatheringId, first.gatheringId);
        expect(replay.aggregateVersion, first.aggregateVersion);
        expect(replay.idempotentReplay, isTrue);
      },
    );

    test(
      'GetGathering uses private owner read and preserves access failure',
      () async {
        final captured = <http.Request>[];
        // 看板同时读活动主体与可选 Plan；此处 Plan 未创建，走 optional 缺席路径。
        final remote = _remote(captured, (request) {
          if (request.headers['X-Client-Operation-Id'] ==
              cloud.AppCloudOperationIds.circleGatheringPlanGetGatheringPlan) {
            return _failureResponse(
              statusCode: 404,
              code: 'CIRCLE.USER.gathering_plan_not_found',
            );
          }
          return _privateDetailResponse;
        });

        final detail = await remote.loadCircle('gathering-1');

        expect(captured, hasLength(2));
        _expectQueryRequest(
          captured.first,
          method: 'GET',
          path: '/gatherings/gathering-1',
          operationId: cloud.AppCloudOperationIds.circleGatheringGetGathering,
        );
        _expectQueryRequest(
          captured.last,
          method: 'GET',
          path: '/gatherings/gathering-1/plan',
          operationId:
              cloud.AppCloudOperationIds.circleGatheringPlanGetGatheringPlan,
        );
        expect(detail.activity.gatheringId, 'gathering-1');
        expect(detail.activity.title, 'Canonical Gathering');
        expect(detail.activity.placeLabel, 'Shanghai');
        expect(detail.participation.activeCount, 2);
        expect(detail.participation.remainingSeats, 2);
        // Plan 缺席不得拖垮活动主体读取，只把 Plan 区标记为未创建。
        expect(
          detail.plan.capability.unavailableReason,
          GatheringBoardCapabilityUnavailableReason.notConfigured,
        );

        final deniedRequests = <http.Request>[];
        final denied = _remote(
          deniedRequests,
          (_) => http.Response(
            jsonEncode(<String, Object?>{
              'code': 'CIRCLE.USER.gathering_access_revoked',
              'message': 'access revoked',
            }),
            403,
            headers: const <String, String>{'content-type': 'application/json'},
          ),
        );

        await expectLater(
          denied.loadCircle('gathering-1'),
          throwsA(
            isA<CloudException>()
                .having((error) => error.type, 'type', CloudErrorType.forbidden)
                .having(
                  (error) => error.sourceOperationId,
                  'sourceOperationId',
                  cloud.AppCloudOperationIds.circleGatheringGetGathering,
                ),
          ),
        );
        _expectQueryRequest(
          deniedRequests.single,
          method: 'GET',
          path: '/gatherings/gathering-1',
          operationId: cloud.AppCloudOperationIds.circleGatheringGetGathering,
        );
      },
    );

    test(
      'JoinOpenGathering creates one typed active participation receipt',
      () async {
        final captured = <http.Request>[];
        final remote = _remote(
          captured,
          (_) => _commandResponse(
            version: 4,
            lifecycle: 'published',
            roomBinding: 'ready',
            replayed: false,
            participationState: 'active',
            participationVersion: 3,
          ),
        );
        const input = GatheringParticipationCommandInput(
          idempotencyKey: 'gathering-join-intent',
          gatheringId: 'gathering-1',
          expectedGatheringVersion: 3,
          expectedParticipationVersion: 2,
        );

        final result = await remote.joinOpen(input);

        _expectCommandRequest(
          captured.single,
          method: 'POST',
          path: '/gatherings/gathering-1:join-open',
          operationId:
              cloud.AppCloudOperationIds.circleGatheringJoinOpenGathering,
          idempotencyKey: input.idempotencyKey,
          body: const <String, Object?>{
            'expectedGatheringVersion': 3,
            'expectedParticipationVersion': 2,
          },
        );
        expect(result.gatheringId, 'gathering-1');
        expect(result.participationState, GatheringParticipationState.active);
        expect(result.participationVersion, 3);
        expect(result.conversationId, 'conversation-1');

        final fullRequests = <http.Request>[];
        final full = _remote(
          fullRequests,
          (_) => _failureResponse(
            statusCode: 409,
            code: 'CIRCLE.USER.gathering_capacity_full',
          ),
        );
        await expectLater(
          full.joinOpen(input),
          throwsA(
            isA<CloudException>().having(
              (error) => error.code,
              'code',
              'CIRCLE.USER.gathering_capacity_full',
            ),
          ),
        );
        _expectCommandRequest(
          fullRequests.single,
          method: 'POST',
          path: '/gatherings/gathering-1:join-open',
          operationId:
              cloud.AppCloudOperationIds.circleGatheringJoinOpenGathering,
          idempotencyKey: input.idempotencyKey,
          body: const <String, Object?>{
            'expectedGatheringVersion': 3,
            'expectedParticipationVersion': 2,
          },
        );
      },
    );

    test(
      'WatchGatheringAvailability keeps aggregate and watch versions distinct',
      () async {
        final captured = <http.Request>[];
        var callCount = 0;
        final remote = _remote(captured, (_) {
          callCount += 1;
          return _commandResponse(
            version: 8,
            lifecycle: 'published',
            roomBinding: 'ready',
            replayed: callCount > 1,
          );
        });
        const input = GatheringAvailabilityWatchCommandInput(
          idempotencyKey: 'gathering-watch-availability-intent',
          gatheringId: 'gathering-1',
          expectedGatheringVersion: 7,
          expectedWatchVersion: 0,
        );

        final first = await remote.watchAvailability(input);
        final replay = await remote.watchAvailability(input);

        for (final request in captured) {
          _expectCommandRequest(
            request,
            method: 'POST',
            path: '/gatherings/gathering-1:watch-availability',
            operationId: cloud
                .AppCloudOperationIds
                .circleGatheringWatchGatheringAvailability,
            idempotencyKey: input.idempotencyKey,
            body: const <String, Object?>{
              'expectedGatheringVersion': 7,
              'expectedWatchVersion': 0,
            },
          );
        }
        expect(first.aggregateVersion, 8);
        expect(first.idempotentReplay, isFalse);
        expect(first.participationState, isNull);
        expect(first.participationVersion, isNull);
        expect(replay.aggregateVersion, first.aggregateVersion);
        expect(replay.idempotentReplay, isTrue);
      },
    );

    test(
      'ReviewGatheringApplication keeps approve and reject distinct',
      () async {
        final captured = <http.Request>[];
        final remote = _remote(captured, (request) {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          final approved = body['decision'] == 'approve';
          return _commandResponse(
            version: approved ? 5 : 6,
            lifecycle: 'published',
            roomBinding: 'ready',
            replayed: false,
            participationState: approved ? 'active' : 'closed',
            participationVersion: approved ? 4 : 5,
          );
        });
        const approve = GatheringReviewApplicationInput(
          idempotencyKey: 'gathering-review-approve-intent',
          gatheringId: 'gathering-1',
          participantPersonaId: 'persona-applicant',
          decision: GatheringApplicationDecision.approve,
          expectedGatheringVersion: 4,
          expectedParticipationVersion: 3,
          reasonRef: 'application-approved',
        );
        const reject = GatheringReviewApplicationInput(
          idempotencyKey: 'gathering-review-reject-intent',
          gatheringId: 'gathering-1',
          participantPersonaId: 'persona-applicant-2',
          decision: GatheringApplicationDecision.reject,
          expectedGatheringVersion: 5,
          expectedParticipationVersion: 4,
          reasonRef: 'application-rejected',
        );

        final approved = await remote.reviewApplication(approve);
        final rejected = await remote.reviewApplication(reject);

        _expectCommandRequest(
          captured[0],
          method: 'POST',
          path: '/gatherings/gathering-1:review-application',
          operationId: cloud
              .AppCloudOperationIds
              .circleGatheringReviewGatheringApplication,
          idempotencyKey: approve.idempotencyKey,
          body: const <String, Object?>{
            'participantPersonaId': 'persona-applicant',
            'decision': 'approve',
            'reasonRef': 'application-approved',
            'expectedGatheringVersion': 4,
            'expectedParticipationVersion': 3,
          },
        );
        _expectCommandRequest(
          captured[1],
          method: 'POST',
          path: '/gatherings/gathering-1:review-application',
          operationId: cloud
              .AppCloudOperationIds
              .circleGatheringReviewGatheringApplication,
          idempotencyKey: reject.idempotencyKey,
          body: const <String, Object?>{
            'participantPersonaId': 'persona-applicant-2',
            'decision': 'reject',
            'reasonRef': 'application-rejected',
            'expectedGatheringVersion': 5,
            'expectedParticipationVersion': 4,
          },
        );
        expect(approved.participationState, GatheringParticipationState.active);
        expect(rejected.participationState, GatheringParticipationState.closed);
        expect(approved.participationVersion, 4);
        expect(rejected.participationVersion, 5);

        final staleRequests = <http.Request>[];
        final stale = _remote(
          staleRequests,
          (_) => _failureResponse(
            statusCode: 409,
            code: 'CIRCLE.USER.gathering_version_conflict',
          ),
        );
        await expectLater(
          stale.reviewApplication(approve),
          throwsA(
            isA<CloudException>().having(
              (error) => error.code,
              'code',
              'CIRCLE.USER.gathering_version_conflict',
            ),
          ),
        );
        expect(staleRequests, hasLength(1));
      },
    );

    test(
      'PauseGatheringAdmission replays and reads back paused admission',
      () async {
        final captured = <http.Request>[];
        var commandCount = 0;
        final remote = _remote(captured, (request) {
          final operationId = request.headers['X-Client-Operation-Id'];
          if (operationId ==
              cloud
                  .AppCloudOperationIds
                  .circleGatheringPauseGatheringAdmission) {
            commandCount += 1;
            return _commandResponse(
              version: 8,
              lifecycle: 'published',
              roomBinding: 'ready',
              replayed: commandCount > 1,
            );
          }
          if (operationId ==
              cloud.AppCloudOperationIds.circleGatheringGetPublicGathering) {
            return _publicDetailResponse(
              aggregateVersion: 8,
              admissionState: 'paused',
              full: false,
            );
          }
          if (operationId ==
              cloud.AppCloudOperationIds.circleGatheringGetGathering) {
            return _privateDetailResponseFor(
              aggregateVersion: 8,
              admissionControlStatus: 'paused',
              admissionControlVersion: 4,
              admissionState: 'paused',
              full: false,
            );
          }
          throw StateError('unexpected operation $operationId');
        });
        const input = GatheringChangeAdmissionInput(
          idempotencyKey: 'gathering-pause-admission-intent',
          gatheringId: 'gathering-1',
          action: GatheringAdmissionControlAction.pause,
          reasonRef: 'host-maintenance',
          expectedGatheringVersion: 7,
          expectedAdmissionControlVersion: 3,
        );

        final first = await remote.changeAdmission(input);
        final replay = await remote.changeAdmission(input);
        final detail = await remote.getDetail(
          const GatheringDetailQuery(gatheringId: 'gathering-1'),
        );

        for (final request in captured.take(2)) {
          _expectCommandRequest(
            request,
            method: 'POST',
            path: '/gatherings/gathering-1:pause-admission',
            operationId: cloud
                .AppCloudOperationIds
                .circleGatheringPauseGatheringAdmission,
            idempotencyKey: input.idempotencyKey,
            body: const <String, Object?>{
              'reasonRef': 'host-maintenance',
              'expectedGatheringVersion': 7,
              'expectedAdmissionControlVersion': 3,
            },
          );
        }
        _expectQueryRequest(
          captured[2],
          method: 'GET',
          path: '/public/gatherings/gathering-1',
          operationId:
              cloud.AppCloudOperationIds.circleGatheringGetPublicGathering,
        );
        _expectQueryRequest(
          captured[3],
          method: 'GET',
          path: '/gatherings/gathering-1',
          operationId: cloud.AppCloudOperationIds.circleGatheringGetGathering,
        );
        expect(first.idempotentReplay, isFalse);
        expect(replay.idempotentReplay, isTrue);
        expect(
          detail?.publicDetail.admissionState,
          GatheringAdmissionState.paused,
        );
        expect(detail?.privateDetail?.admissionPaused, isTrue);
        expect(detail?.privateDetail?.admissionControlVersion, 4);

        await _expectAdmissionControlFailure(
          action: GatheringAdmissionControlAction.pause,
          operationId:
              cloud.AppCloudOperationIds.circleGatheringPauseGatheringAdmission,
          path: '/gatherings/gathering-1:pause-admission',
          expectedCode: 'CIRCLE.USER.gathering_admission_control_conflict',
        );
        await _expectAdmissionControlMalformedFailure(
          action: GatheringAdmissionControlAction.pause,
        );
      },
    );

    test(
      'ResumeGatheringAdmission replays but full readback stays closed',
      () async {
        final captured = <http.Request>[];
        var commandCount = 0;
        final remote = _remote(captured, (request) {
          final operationId = request.headers['X-Client-Operation-Id'];
          if (operationId ==
              cloud
                  .AppCloudOperationIds
                  .circleGatheringResumeGatheringAdmission) {
            commandCount += 1;
            return _commandResponse(
              version: 9,
              lifecycle: 'published',
              roomBinding: 'ready',
              replayed: commandCount > 1,
            );
          }
          if (operationId ==
              cloud.AppCloudOperationIds.circleGatheringGetPublicGathering) {
            return _publicDetailResponse(
              aggregateVersion: 9,
              admissionState: 'full',
              full: true,
            );
          }
          if (operationId ==
              cloud.AppCloudOperationIds.circleGatheringGetGathering) {
            return _privateDetailResponseFor(
              aggregateVersion: 9,
              admissionControlStatus: 'open',
              admissionControlVersion: 5,
              admissionState: 'full',
              full: true,
            );
          }
          throw StateError('unexpected operation $operationId');
        });
        const input = GatheringChangeAdmissionInput(
          idempotencyKey: 'gathering-resume-admission-intent',
          gatheringId: 'gathering-1',
          action: GatheringAdmissionControlAction.resume,
          reasonRef: 'host-resumed-admission',
          expectedGatheringVersion: 8,
          expectedAdmissionControlVersion: 4,
        );

        final first = await remote.changeAdmission(input);
        final replay = await remote.changeAdmission(input);
        final detail = await remote.getDetail(
          const GatheringDetailQuery(gatheringId: 'gathering-1'),
        );

        for (final request in captured.take(2)) {
          _expectCommandRequest(
            request,
            method: 'POST',
            path: '/gatherings/gathering-1:resume-admission',
            operationId: cloud
                .AppCloudOperationIds
                .circleGatheringResumeGatheringAdmission,
            idempotencyKey: input.idempotencyKey,
            body: const <String, Object?>{
              'reasonRef': 'host-resumed-admission',
              'expectedGatheringVersion': 8,
              'expectedAdmissionControlVersion': 4,
            },
          );
        }
        _expectQueryRequest(
          captured[2],
          method: 'GET',
          path: '/public/gatherings/gathering-1',
          operationId:
              cloud.AppCloudOperationIds.circleGatheringGetPublicGathering,
        );
        _expectQueryRequest(
          captured[3],
          method: 'GET',
          path: '/gatherings/gathering-1',
          operationId: cloud.AppCloudOperationIds.circleGatheringGetGathering,
        );
        expect(first.idempotentReplay, isFalse);
        expect(replay.idempotentReplay, isTrue);
        expect(
          detail?.publicDetail.admissionState,
          GatheringAdmissionState.full,
        );
        expect(
          detail?.publicDetail.primaryAction,
          GatheringPrimaryAction.watchAvailability,
        );
        expect(detail?.privateDetail?.admissionPaused, isFalse);
        expect(detail?.privateDetail?.admissionControlVersion, 5);

        await _expectAdmissionControlFailure(
          action: GatheringAdmissionControlAction.resume,
          operationId: cloud
              .AppCloudOperationIds
              .circleGatheringResumeGatheringAdmission,
          path: '/gatherings/gathering-1:resume-admission',
          expectedCode: 'CIRCLE.USER.gathering_admission_control_conflict',
        );
        await _expectAdmissionControlMalformedFailure(
          action: GatheringAdmissionControlAction.resume,
        );
      },
    );

    test(
      'CancelGathering and CompleteGathering remain distinct terminals',
      () async {
        final captured = <http.Request>[];
        final remote = _remote(captured, (request) {
          final operationId = request.headers['X-Client-Operation-Id'];
          final completing =
              operationId ==
              cloud.AppCloudOperationIds.circleGatheringCompleteGathering;
          return _commandResponse(
            version: completing ? 9 : 8,
            lifecycle: completing ? 'completed' : 'cancelled',
            roomBinding: 'ready',
            replayed: false,
            outcomeStatus: completing ? 'unverified' : null,
          );
        });
        const cancel = GatheringReasonCommandInput(
          idempotencyKey: 'gathering-cancel-intent',
          gatheringId: 'gathering-1',
          reasonRef: 'host-cancelled-before-start',
          expectedGatheringVersion: 7,
          evidenceRefs: <GatheringCanonicalObjectRef>[
            GatheringCanonicalObjectRef(
              objectTypeRef: 'circle.gathering_evidence',
              objectId: 'evidence-cancel-1',
            ),
          ],
        );
        const complete = GatheringOutcomeCommandInput(
          idempotencyKey: 'gathering-complete-intent',
          gatheringId: 'gathering-1',
          status: GatheringOutcomeStatus.unverified,
          expectedGatheringVersion: 8,
        );

        final cancelled = await remote.cancel(cancel);
        final completed = await remote.recordOutcome(complete);

        _expectCommandRequest(
          captured[0],
          method: 'POST',
          path: '/gatherings/gathering-1:cancel',
          operationId:
              cloud.AppCloudOperationIds.circleGatheringCancelGathering,
          idempotencyKey: cancel.idempotencyKey,
          body: const <String, Object?>{
            'reasonRef': 'host-cancelled-before-start',
            'evidenceRefs': <Object?>[
              <String, Object?>{
                'objectTypeRef': 'circle.gathering_evidence',
                'objectId': 'evidence-cancel-1',
              },
            ],
            'expectedGatheringVersion': 7,
          },
        );
        _expectCommandRequest(
          captured[1],
          method: 'POST',
          path: '/gatherings/gathering-1:complete',
          operationId:
              cloud.AppCloudOperationIds.circleGatheringCompleteGathering,
          idempotencyKey: complete.idempotencyKey,
          body: const <String, Object?>{'expectedGatheringVersion': 8},
        );
        expect(cancelled.lifecycleStatus, GatheringLifecycleStatus.cancelled);
        expect(cancelled.outcomeStatus, isNull);
        expect(completed.lifecycleStatus, GatheringLifecycleStatus.completed);
        expect(completed.outcomeStatus, GatheringOutcomeStatus.unverified);

        final lateCancelRequests = <http.Request>[];
        final lateCancel = _remote(
          lateCancelRequests,
          (_) => _failureResponse(
            statusCode: 409,
            code: 'CIRCLE.USER.gathering_cancellation_window_closed',
          ),
        );
        await expectLater(
          lateCancel.cancel(cancel),
          throwsA(
            isA<CloudException>().having(
              (error) => error.code,
              'code',
              'CIRCLE.USER.gathering_cancellation_window_closed',
            ),
          ),
        );
        expect(lateCancelRequests, hasLength(1));
      },
    );

    test(
      'generated command decoder rejects incomplete owner receipt',
      () async {
        final captured = <http.Request>[];
        final remote = _remote(
          captured,
          (_) => <String, Object?>{
            'gatheringId': 'gathering-1',
            'aggregateVersion': 4,
            'lifecycleStatus': 'published',
            'roomBindingStatus': 'ready',
            'idempotentReplay': false,
          },
        );

        await expectLater(
          remote.joinOpen(
            const GatheringParticipationCommandInput(
              idempotencyKey: 'gathering-invalid-receipt-intent',
              gatheringId: 'gathering-1',
              expectedGatheringVersion: 3,
              expectedParticipationVersion: 2,
            ),
          ),
          throwsA(isA<CloudException>()),
        );
        expect(captured, hasLength(1));
      },
    );
  });
}

Future<void> _expectAdmissionControlFailure({
  required GatheringAdmissionControlAction action,
  required String operationId,
  required String path,
  required String expectedCode,
}) async {
  final captured = <http.Request>[];
  final remote = _remote(
    captured,
    (_) => _failureResponse(statusCode: 409, code: expectedCode),
  );
  final input = GatheringChangeAdmissionInput(
    idempotencyKey: 'gathering-${action.name}-admission-stale-intent',
    gatheringId: 'gathering-1',
    action: action,
    reasonRef: 'stale-control-version',
    expectedGatheringVersion: 7,
    expectedAdmissionControlVersion: 2,
  );

  await expectLater(
    remote.changeAdmission(input),
    throwsA(
      isA<CloudException>()
          .having((error) => error.code, 'code', expectedCode)
          .having(
            (error) => error.sourceOperationId,
            'sourceOperationId',
            operationId,
          ),
    ),
  );
  _expectCommandRequest(
    captured.single,
    method: 'POST',
    path: path,
    operationId: operationId,
    idempotencyKey: input.idempotencyKey,
    body: const <String, Object?>{
      'reasonRef': 'stale-control-version',
      'expectedGatheringVersion': 7,
      'expectedAdmissionControlVersion': 2,
    },
  );
}

Future<void> _expectAdmissionControlMalformedFailure({
  required GatheringAdmissionControlAction action,
}) async {
  final captured = <http.Request>[];
  final remote = _remote(captured, (_) {
    return <String, Object?>{
      'gatheringId': 'gathering-1',
      'aggregateVersion': 8,
      'lifecycleStatus': 'published',
      'roomBindingStatus': 'ready',
      'idempotentReplay': false,
    };
  });

  await expectLater(
    remote.changeAdmission(
      GatheringChangeAdmissionInput(
        idempotencyKey: 'gathering-${action.name}-malformed-intent',
        gatheringId: 'gathering-1',
        action: action,
        reasonRef: 'malformed-response-check',
        expectedGatheringVersion: 7,
        expectedAdmissionControlVersion: 3,
      ),
    ),
    throwsA(isA<CloudException>()),
  );
  expect(captured, hasLength(1));
}

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
      authTokenProvider: const _GatheringTokenProvider(),
    ),
    clientContextProvider: const _GatheringClientContext(),
    telemetrySink: const _NoopTelemetrySink(),
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.gamma,
      gatewayBaseUri: Uri.parse('https://test-gateway.example.com'),
    ),
  );
  return RemoteGatheringFacet(client: client, invocationContext: _context);
}

cloud.CloudOperationInvocationContext _context(
  String clientPageId, {
  String? idempotencyKey,
}) {
  final create = clientPageId == CircleRequestPageIds.createGatheringDraft;
  final surface = create ? 'gatheringCreate' : 'gatheringDetail';
  return cloud.CloudOperationInvocationContext(
    surfaceId: surface,
    routeId: surface,
    clientPageId: clientPageId,
    actor: const cloud.CloudOperationActorContext(
      accountId: 'account-1',
      personaId: 'persona-1',
    ),
    idempotencyKey: idempotencyKey,
  );
}

void _expectCommandRequest(
  http.Request request, {
  required String method,
  required String path,
  required String operationId,
  required String idempotencyKey,
  required Map<String, Object?> body,
}) {
  expect(request.method, method);
  expect(request.url.path, path);
  expect(request.url.queryParameters, isEmpty);
  expect(request.headers['X-Client-Operation-Id'], operationId);
  expect(request.headers['authorization'], 'Bearer gathering-contract-token');
  expect(request.headers['Idempotency-Key'], idempotencyKey);
  expect(jsonDecode(request.body), body);
}

void _expectQueryRequest(
  http.Request request, {
  required String method,
  required String path,
  required String operationId,
}) {
  expect(request.method, method);
  expect(request.url.path, path);
  expect(request.url.queryParameters, isEmpty);
  expect(request.headers['X-Client-Operation-Id'], operationId);
  expect(request.headers['authorization'], 'Bearer gathering-contract-token');
  expect(request.headers.containsKey('Idempotency-Key'), isFalse);
  expect(request.body, isEmpty);
}

GatheringCreateDraftInput _createDraftInput() {
  return GatheringCreateDraftInput(
    idempotencyKey: 'gathering-create-intent',
    host: const GatheringHostInput(
      subjectKind: GatheringHostSubjectKind.persona,
      subjectId: 'host-persona',
      authorityEvidenceRef: 'persona:host-persona:self',
      authorityVersion: 7,
    ),
    creatorParticipates: true,
    purpose: const GatheringPurposeDraft(
      title: 'Canonical Gathering',
      summary: 'Typed draft summary',
      sourceRefs: <GatheringSourceRef>[
        GatheringSourceRef(
          objectRef: GatheringCanonicalObjectRef(
            objectTypeRef: 'content.post',
            objectId: 'post-1',
          ),
          routeId: 'post.detail',
          sourceDigest: 'source-digest-1',
        ),
      ],
      topicRefs: <String>['topic:travel-photography'],
      requirementRefs: <String>['requirement:bring-water'],
    ),
    schedule: GatheringScheduleDraft(
      timezone: 'Asia/Shanghai',
      startAt: DateTime.utc(2026, 8, 10, 2),
      endAt: DateTime.utc(2026, 8, 10, 5),
      admissionClosesAt: DateTime.utc(2026, 8, 10, 1),
    ),
    place: const GatheringPlaceDraft(
      mode: GatheringPlaceMode.physical,
      coarsePlaceLabel: 'Shanghai',
      exactMeetingPoint: 'Gate 1',
      onlineLocationRef: '',
    ),
    policy: const GatheringPolicyDraft(
      audience: GatheringAudiencePolicy.public,
      admission: GatheringAdmissionPolicy.open,
      maxParticipants: 4,
      disclosure: GatheringDisclosurePolicyDraft(
        time: GatheringTimeDisclosure.exact,
        place: GatheringPlaceDisclosure.afterJoin,
        roster: GatheringRosterDisclosure.countOnly,
      ),
      riskControlPolicyRef: 'risk-policy-1',
    ),
  );
}

const Map<String, Object?> _createDraftBody = <String, Object?>{
  'hostBinding': <String, Object?>{
    'hostSubjectKind': 'persona',
    'hostSubjectId': 'host-persona',
    'authorityEvidenceRef': 'persona:host-persona:self',
    'authorityVersion': 7,
  },
  'creatorParticipates': true,
  'purpose': <String, Object?>{
    'title': 'Canonical Gathering',
    'summary': 'Typed draft summary',
    'topicRefs': <Object?>['topic:travel-photography'],
    'requirementRefs': <Object?>['requirement:bring-water'],
    'sourceObjectRefs': <Object?>[
      <String, Object?>{
        'objectRef': <String, Object?>{
          'objectTypeRef': 'content.post',
          'objectId': 'post-1',
        },
        'routeId': 'post.detail',
        'sourceDigest': 'source-digest-1',
      },
    ],
    'costNotice': 'free',
  },
  'schedule': <String, Object?>{
    'timezone': 'Asia/Shanghai',
    'startAt': '2026-08-10T02:00:00.000Z',
    'endAt': '2026-08-10T05:00:00.000Z',
    'admissionClosesAt': '2026-08-10T01:00:00.000Z',
  },
  'place': <String, Object?>{
    'mode': 'physical',
    'coarsePlaceLabel': 'Shanghai',
    'exactMeetingPoint': 'Gate 1',
    'onlineLocationRef': '',
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
};

Map<String, Object?> _commandResponse({
  required int version,
  required String lifecycle,
  required String roomBinding,
  required bool replayed,
  String? participationState,
  int? participationVersion,
  String? outcomeStatus,
}) {
  return <String, Object?>{
    'gatheringId': 'gathering-1',
    'aggregateVersion': version,
    'lifecycleStatus': lifecycle,
    'participationState': ?participationState,
    'participationVersion': ?participationVersion,
    'currentGatheringRevisionId': 'gathering-revision-$version',
    'currentGatheringRevisionNumber': version,
    'outcomeStatus': ?outcomeStatus,
    'conversationId': 'conversation-1',
    'roomBindingStatus': roomBinding,
    'idempotentReplay': replayed,
  };
}

Map<String, Object?> _publicDetailResponse({
  required int aggregateVersion,
  required String admissionState,
  required bool full,
}) {
  final occupiedSeats = full ? 4 : 2;
  return <String, Object?>{
    'card': <String, Object?>{
      'gatheringId': 'gathering-1',
      'aggregateVersion': aggregateVersion,
      'cardDigest': 'gathering-card-$aggregateVersion',
      'host': const <String, Object?>{
        'hostSubjectKind': 'persona',
        'hostSubjectId': 'host-persona',
        'hostDigest': 'host-digest-1',
      },
      'purpose': const <String, Object?>{
        'title': 'Canonical Gathering',
        'summary': 'Public typed detail',
        'topicRefs': <Object?>['topic:travel-photography'],
        'requirementRefs': <Object?>['requirement:bring-water'],
        'costNotice': 'free',
      },
      'schedule': const <String, Object?>{
        'timezone': 'Asia/Shanghai',
        'startAt': '2026-08-10T02:00:00Z',
        'endAt': '2026-08-10T05:00:00Z',
      },
      'place': const <String, Object?>{
        'mode': 'physical',
        'coarsePlaceLabel': 'Shanghai',
      },
      'capacity': <String, Object?>{
        'maxParticipants': 4,
        'activeSeatCount': occupiedSeats,
        'invitedSeatHoldCount': 0,
        'occupiedSeats': occupiedSeats,
        'remainingSeats': 4 - occupiedSeats,
        'full': full,
      },
      'temporal': const <String, Object?>{
        'temporalPhase': 'upcoming',
        'evaluatedAt': '2026-08-08T02:00:00Z',
      },
      'admission': <String, Object?>{
        'admissionState': admissionState,
        'evaluatedAt': '2026-08-08T02:00:00Z',
      },
      'lifecycleStatus': 'published',
      'currentGatheringRevisionId': 'gathering-revision-$aggregateVersion',
      'currentGatheringRevisionNumber': aggregateVersion,
      'updatedAt': '2026-08-08T02:00:00Z',
    },
    'audiencePolicy': 'public',
    'admissionPolicy': 'open',
    'disclosurePolicy': const <String, Object?>{
      'timeDisclosure': 'exact',
      'placeDisclosure': 'after_join',
      'rosterDisclosure': 'count_only',
    },
    'revisions': <Object?>[
      <String, Object?>{
        'revisionId': 'gathering-revision-$aggregateVersion',
        'revisionNumber': aggregateVersion,
        'digest': 'revision-digest-$aggregateVersion',
        'materialChange': false,
        'createdAt': '2026-08-08T02:00:00Z',
      },
    ],
    'conversationId': 'conversation-1',
  };
}

Map<String, Object?> _privateDetailResponseFor({
  required int aggregateVersion,
  required String admissionControlStatus,
  required int admissionControlVersion,
  required String admissionState,
  required bool full,
}) {
  final occupiedSeats = full ? 4 : 2;
  return <String, Object?>{
    ..._privateDetailResponse,
    'aggregateVersion': aggregateVersion,
    'admissionControl': <String, Object?>{
      'status': admissionControlStatus,
      'version': admissionControlVersion,
    },
    'currentGatheringRevisionId': 'gathering-revision-$aggregateVersion',
    'currentGatheringRevisionNumber': aggregateVersion,
    'capacity': <String, Object?>{
      'maxParticipants': 4,
      'activeSeatCount': occupiedSeats,
      'invitedSeatHoldCount': 0,
      'occupiedSeats': occupiedSeats,
      'remainingSeats': 4 - occupiedSeats,
      'full': full,
    },
    'admission': <String, Object?>{
      'admissionState': admissionState,
      'evaluatedAt': '2026-08-08T02:00:00Z',
    },
  };
}

http.Response _failureResponse({
  required int statusCode,
  required String code,
}) {
  return http.Response(
    jsonEncode(<String, Object?>{'code': code, 'message': 'canonical failure'}),
    statusCode,
    headers: const <String, String>{'content-type': 'application/json'},
  );
}

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

final class _GatheringTokenProvider implements CloudAuthTokenProvider {
  const _GatheringTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'gathering-contract-token';
}

final class _GatheringClientContext implements CloudClientContextProvider {
  const _GatheringClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'gathering-contract-session',
      deviceActorId: 'gathering-contract-device',
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
