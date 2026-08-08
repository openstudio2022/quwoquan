// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-003
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-004
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-005
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-006
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-007
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-008
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-009
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-010
// readiness_case: circle_group_membership_apply_join_circle_group_app_local
// readiness_case: circle_group_membership_list_circle_group_memberships_app_local
// readiness_case: circle_group_membership_get_my_circle_group_membership_app_local
// readiness_case: circle_group_membership_leave_circle_group_app_local
// readiness_case: circle_group_membership_approve_circle_group_member_app_local
// readiness_case: circle_group_membership_reject_circle_group_member_app_local
// readiness_case: circle_group_membership_remove_circle_group_member_app_local
// readiness_case: circle_group_membership_update_circle_group_member_role_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/adapters/group_membership_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

void main() {
  group('RemoteCircleGroupMembershipFacet generated HTTP contract', () {
    test(
      'commands preserve exact wire, typed receipts, and same-intent replay',
      () async {
        final log = <CapturedRemoteApiPathRequest>[];
        final attempts = <String, int>{};
        final remote = _remote(
          log,
          responseFor: (request) {
            final operationId = request.headers['X-Client-Operation-Id'];
            if (operationId == null) {
              throw StateError('missing operation identity');
            }
            final attempt = (attempts[operationId] ?? 0) + 1;
            attempts[operationId] = attempt;
            return remoteApiPathJsonResponse(
              _commandResult(operationId, replayed: attempt > 1),
            );
          },
        );
        final calls = _commandCalls(remote);

        for (final call in calls) {
          final first = await call.invoke();
          final replay = await call.invoke();

          expect(first.membershipId, call.membershipId);
          expect(first.state, call.state);
          expect(first.role, call.role);
          expect(first.version, call.version);
          expect(first.idempotentReplay, isFalse);
          expect(replay.membershipId, first.membershipId);
          expect(replay.state, first.state);
          expect(replay.role, first.role);
          expect(replay.version, first.version);
          expect(replay.idempotentReplay, isTrue);
        }

        expect(log, hasLength(calls.length * 2));
        for (var index = 0; index < calls.length; index += 1) {
          final call = calls[index];
          for (final request in <CapturedRemoteApiPathRequest>[
            log[index * 2],
            log[index * 2 + 1],
          ]) {
            _expectCommand(
              request,
              method: call.method,
              path: call.path,
              operationId: call.operationId,
              pageId: call.pageId,
              body: call.body,
            );
          }
          expect(
            log[index * 2].headers['Idempotency-Key'],
            log[index * 2 + 1].headers['Idempotency-Key'],
          );
        }
      },
    );

    test(
      'queries preserve exact wire and decode nonempty typed slices',
      () async {
        final log = <CapturedRemoteApiPathRequest>[];
        final remote = _remote(log, responseFor: _successResponse);

        final page = await remote.list(
          CircleGroupMembershipListQuery(
            circleId: 'circle-1',
            groupId: 'group-1',
            state: CircleGroupMembershipState.active,
            cursor: 'membership-cursor',
            limit: 7,
          ),
        );
        final mine = await remote.getMy(
          MyCircleGroupMembershipQuery(
            circleId: 'circle-1',
            groupId: 'group-1',
          ),
        );

        _expectQuery(
          log[0],
          path: '/circles/circle-1/groups/group-1/memberships',
          operationId: AppCloudOperationIds
              .circleCircleGroupMembershipListCircleGroupMemberships,
          pageId: CircleRequestPageIds.listCircleGroupMemberships,
          query: const <String, String>{
            'state': 'active',
            'cursor': 'membership-cursor',
            'limit': '7',
          },
        );
        _expectQuery(
          log[1],
          path: '/circles/circle-1/groups/group-1/memberships/self',
          operationId: AppCloudOperationIds
              .circleCircleGroupMembershipGetMyCircleGroupMembership,
          pageId: CircleRequestPageIds.getMyCircleGroupMembership,
        );

        expect(page.items, hasLength(1));
        expect(page.items.single.membershipId, 'membership-list');
        expect(page.items.single.personaId, 'persona-member');
        expect(page.items.single.state, CircleGroupMembershipState.active);
        expect(page.cursor, 'membership-next');
        expect(mine.membershipId, 'membership-self');
        expect(mine.personaId, 'persona-actor');
        expect(mine.role, CircleGroupMembershipRole.member);
        expect(mine.state, CircleGroupMembershipState.active);
      },
    );

    test(
      'canonical failures remain operation-bound CloudException values',
      () async {
        final log = <CapturedRemoteApiPathRequest>[];
        final remote = _remote(log, responseFor: _canonicalFailureResponse);
        final calls = _allOperationCalls(remote);

        for (final call in calls) {
          await expectLater(
            call.invoke(),
            throwsA(
              isA<CloudException>()
                  .having((error) => error.code, 'code', call.failureCode)
                  .having(
                    (error) => error.sourceOperationId,
                    'sourceOperationId',
                    call.operationId,
                  ),
            ),
          );
        }

        expect(log, hasLength(calls.length));
        for (var index = 0; index < calls.length; index += 1) {
          expect(
            log[index].headers['X-Client-Operation-Id'],
            calls[index].operationId,
          );
        }
      },
    );

    test('all operation decoders reject malformed success bodies', () async {
      final log = <CapturedRemoteApiPathRequest>[];
      final remote = _remote(
        log,
        responseFor: (_) => remoteApiPathJsonResponse(const <String, Object?>{
          'unexpected': 'shape',
        }),
      );
      final calls = _allOperationCalls(remote);

      for (final call in calls) {
        await expectLater(
          call.invoke(),
          throwsA(
            isA<CloudException>().having(
              (error) => error.sourceOperationId,
              'sourceOperationId',
              call.operationId,
            ),
          ),
        );
      }

      expect(log, hasLength(calls.length));
    });

    test('required command idempotency fails closed before HTTP', () async {
      final log = <CapturedRemoteApiPathRequest>[];
      final remote = _remote(
        log,
        responseFor: _successResponse,
        contextFactory: _missingIdempotencyContext,
      );

      for (final call in _commandCalls(remote)) {
        await expectLater(
          call.invoke(),
          throwsA(
            isA<CloudException>()
                .having(
                  (error) => error.type,
                  'type',
                  CloudErrorType.invalidResponse,
                )
                .having(
                  (error) => error.code,
                  'code',
                  'APP.CONTRACT.invalid_response',
                ),
          ),
        );
      }

      expect(log, isEmpty);
    });
  });
}

typedef _CommandCall = ({
  String method,
  String path,
  String operationId,
  String pageId,
  Map<String, Object?> body,
  String membershipId,
  CircleGroupMembershipState state,
  CircleGroupMembershipRole role,
  int version,
  Future<CircleGroupMembershipCommandResult> Function() invoke,
});

typedef _OperationCall = ({
  String operationId,
  String failureCode,
  Future<Object?> Function() invoke,
});

List<_CommandCall> _commandCalls(
  RemoteCircleGroupMembershipFacet remote,
) => <_CommandCall>[
  (
    method: 'POST',
    path: '/circles/circle-1/groups/group-1/memberships',
    operationId:
        AppCloudOperationIds.circleCircleGroupMembershipApplyJoinCircleGroup,
    pageId: CircleRequestPageIds.applyJoinCircleGroup,
    body: const <String, Object?>{},
    membershipId: 'membership-apply',
    state: CircleGroupMembershipState.pending,
    role: CircleGroupMembershipRole.member,
    version: 2,
    invoke: () => remote.apply(
      ApplyCircleGroupMembershipCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
      ),
    ),
  ),
  (
    method: 'DELETE',
    path: '/circles/circle-1/groups/group-1/memberships/self',
    operationId:
        AppCloudOperationIds.circleCircleGroupMembershipLeaveCircleGroup,
    pageId: CircleRequestPageIds.leaveCircleGroup,
    body: const <String, Object?>{},
    membershipId: 'membership-leave',
    state: CircleGroupMembershipState.left,
    role: CircleGroupMembershipRole.member,
    version: 3,
    invoke: () => remote.leave(
      LeaveCircleGroupMembershipCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
      ),
    ),
  ),
  (
    method: 'POST',
    path: '/circles/circle-1/groups/group-1/memberships/persona-target:approve',
    operationId: AppCloudOperationIds
        .circleCircleGroupMembershipApproveCircleGroupMember,
    pageId: CircleRequestPageIds.approveCircleGroupMember,
    body: const <String, Object?>{},
    membershipId: 'membership-approve',
    state: CircleGroupMembershipState.active,
    role: CircleGroupMembershipRole.member,
    version: 4,
    invoke: () => remote.approve(
      DecideCircleGroupMembershipCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
        personaId: 'persona-target',
      ),
    ),
  ),
  (
    method: 'POST',
    path: '/circles/circle-1/groups/group-1/memberships/persona-target:reject',
    operationId:
        AppCloudOperationIds.circleCircleGroupMembershipRejectCircleGroupMember,
    pageId: CircleRequestPageIds.rejectCircleGroupMember,
    body: const <String, Object?>{},
    membershipId: 'membership-reject',
    state: CircleGroupMembershipState.rejected,
    role: CircleGroupMembershipRole.member,
    version: 5,
    invoke: () => remote.reject(
      DecideCircleGroupMembershipCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
        personaId: 'persona-target',
      ),
    ),
  ),
  (
    method: 'DELETE',
    path: '/circles/circle-1/groups/group-1/memberships/persona-target',
    operationId:
        AppCloudOperationIds.circleCircleGroupMembershipRemoveCircleGroupMember,
    pageId: CircleRequestPageIds.removeCircleGroupMember,
    body: const <String, Object?>{},
    membershipId: 'membership-remove',
    state: CircleGroupMembershipState.removed,
    role: CircleGroupMembershipRole.member,
    version: 6,
    invoke: () => remote.remove(
      RemoveCircleGroupMembershipCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
        personaId: 'persona-target',
      ),
    ),
  ),
  (
    method: 'PATCH',
    path: '/circles/circle-1/groups/group-1/memberships/persona-target/role',
    operationId: AppCloudOperationIds
        .circleCircleGroupMembershipUpdateCircleGroupMemberRole,
    pageId: CircleRequestPageIds.updateCircleGroupMemberRole,
    body: const <String, Object?>{'role': 'manager'},
    membershipId: 'membership-role',
    state: CircleGroupMembershipState.active,
    role: CircleGroupMembershipRole.manager,
    version: 7,
    invoke: () => remote.updateRole(
      UpdateCircleGroupMembershipRoleCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
        personaId: 'persona-target',
        role: CircleGroupMembershipRole.manager,
      ),
    ),
  ),
];

List<_OperationCall> _allOperationCalls(
  RemoteCircleGroupMembershipFacet remote,
) => <_OperationCall>[
  (
    operationId:
        AppCloudOperationIds.circleCircleGroupMembershipApplyJoinCircleGroup,
    failureCode: 'CIRCLE.USER.group_membership_full',
    invoke: () => remote.apply(
      ApplyCircleGroupMembershipCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
      ),
    ),
  ),
  (
    operationId: AppCloudOperationIds
        .circleCircleGroupMembershipListCircleGroupMemberships,
    failureCode: 'CIRCLE.USER.permission_denied',
    invoke: () => remote.list(
      CircleGroupMembershipListQuery(
        circleId: 'circle-1',
        groupId: 'group-1',
        state: CircleGroupMembershipState.active,
        cursor: 'membership-cursor',
        limit: 7,
      ),
    ),
  ),
  (
    operationId: AppCloudOperationIds
        .circleCircleGroupMembershipGetMyCircleGroupMembership,
    failureCode: 'CIRCLE.USER.group_membership_not_found',
    invoke: () => remote.getMy(
      MyCircleGroupMembershipQuery(circleId: 'circle-1', groupId: 'group-1'),
    ),
  ),
  (
    operationId:
        AppCloudOperationIds.circleCircleGroupMembershipLeaveCircleGroup,
    failureCode: 'CIRCLE.USER.group_membership_owner_cannot_leave',
    invoke: () => remote.leave(
      LeaveCircleGroupMembershipCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
      ),
    ),
  ),
  (
    operationId: AppCloudOperationIds
        .circleCircleGroupMembershipApproveCircleGroupMember,
    failureCode: 'CIRCLE.USER.group_membership_state_conflict',
    invoke: () => remote.approve(
      DecideCircleGroupMembershipCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
        personaId: 'persona-target',
      ),
    ),
  ),
  (
    operationId:
        AppCloudOperationIds.circleCircleGroupMembershipRejectCircleGroupMember,
    failureCode: 'CIRCLE.USER.group_membership_state_conflict',
    invoke: () => remote.reject(
      DecideCircleGroupMembershipCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
        personaId: 'persona-target',
      ),
    ),
  ),
  (
    operationId:
        AppCloudOperationIds.circleCircleGroupMembershipRemoveCircleGroupMember,
    failureCode: 'CIRCLE.USER.group_membership_owner_cannot_remove',
    invoke: () => remote.remove(
      RemoveCircleGroupMembershipCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
        personaId: 'persona-target',
      ),
    ),
  ),
  (
    operationId: AppCloudOperationIds
        .circleCircleGroupMembershipUpdateCircleGroupMemberRole,
    failureCode: 'CIRCLE.USER.group_membership_role_invalid',
    invoke: () => remote.updateRole(
      UpdateCircleGroupMembershipRoleCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
        personaId: 'persona-target',
        role: CircleGroupMembershipRole.manager,
      ),
    ),
  ),
];

RemoteCircleGroupMembershipFacet _remote(
  List<CapturedRemoteApiPathRequest> log, {
  required RemoteApiPathResponseFactory responseFor,
  CircleGroupMembershipInvocationContextFactory contextFactory = _context,
}) => RemoteCircleGroupMembershipFacet(
  client: buildRemoteApiPathOperationClient(log, responseFor: responseFor),
  invocationContext: contextFactory,
);

CloudOperationInvocationContext _context(
  String clientPageId, {
  required bool command,
}) => CloudOperationInvocationContext(
  surfaceId: 'circleDetail',
  routeId: 'circleDetail',
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(
    accountId: 'account-actor',
    personaId: 'persona-actor',
  ),
  idempotencyKey: command ? '$clientPageId-intent' : null,
);

CloudOperationInvocationContext _missingIdempotencyContext(
  String clientPageId, {
  required bool command,
}) => CloudOperationInvocationContext(
  surfaceId: 'circleDetail',
  routeId: 'circleDetail',
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(
    accountId: 'account-actor',
    personaId: 'persona-actor',
  ),
);

http.Response _successResponse(http.Request request) {
  final operationId = request.headers['X-Client-Operation-Id'];
  final body = switch (operationId) {
    AppCloudOperationIds
        .circleCircleGroupMembershipListCircleGroupMemberships =>
      <String, Object?>{
        'items': <Object?>[
          _membershipSlice(
            membershipId: 'membership-list',
            personaId: 'persona-member',
          ),
        ],
        'cursor': 'membership-next',
      },
    AppCloudOperationIds
        .circleCircleGroupMembershipGetMyCircleGroupMembership =>
      _membershipSlice(
        membershipId: 'membership-self',
        personaId: 'persona-actor',
      ),
    _ => _commandResult(operationId ?? '', replayed: false),
  };
  return remoteApiPathJsonResponse(body);
}

http.Response _canonicalFailureResponse(http.Request request) {
  final operationId = request.headers['X-Client-Operation-Id'];
  final failure = switch (operationId) {
    AppCloudOperationIds.circleCircleGroupMembershipApplyJoinCircleGroup => (
      code: 'CIRCLE.USER.group_membership_full',
      statusCode: 409,
    ),
    AppCloudOperationIds
        .circleCircleGroupMembershipListCircleGroupMemberships =>
      (code: 'CIRCLE.USER.permission_denied', statusCode: 403),
    AppCloudOperationIds
        .circleCircleGroupMembershipGetMyCircleGroupMembership =>
      (code: 'CIRCLE.USER.group_membership_not_found', statusCode: 404),
    AppCloudOperationIds.circleCircleGroupMembershipLeaveCircleGroup => (
      code: 'CIRCLE.USER.group_membership_owner_cannot_leave',
      statusCode: 409,
    ),
    AppCloudOperationIds.circleCircleGroupMembershipApproveCircleGroupMember =>
      (code: 'CIRCLE.USER.group_membership_state_conflict', statusCode: 409),
    AppCloudOperationIds.circleCircleGroupMembershipRejectCircleGroupMember => (
      code: 'CIRCLE.USER.group_membership_state_conflict',
      statusCode: 409,
    ),
    AppCloudOperationIds.circleCircleGroupMembershipRemoveCircleGroupMember => (
      code: 'CIRCLE.USER.group_membership_owner_cannot_remove',
      statusCode: 409,
    ),
    AppCloudOperationIds
        .circleCircleGroupMembershipUpdateCircleGroupMemberRole =>
      (code: 'CIRCLE.USER.group_membership_role_invalid', statusCode: 400),
    _ => throw StateError('unexpected operation: $operationId'),
  };
  return remoteApiPathJsonResponse(<String, Object?>{
    'code': failure.code,
    'message': 'canonical membership failure',
  }, statusCode: failure.statusCode);
}

Map<String, Object?> _commandResult(
  String operationId, {
  required bool replayed,
}) {
  final result = switch (operationId) {
    AppCloudOperationIds.circleCircleGroupMembershipApplyJoinCircleGroup => (
      id: 'membership-apply',
      state: 'pending',
      role: 'member',
      version: 2,
    ),
    AppCloudOperationIds.circleCircleGroupMembershipLeaveCircleGroup => (
      id: 'membership-leave',
      state: 'left',
      role: 'member',
      version: 3,
    ),
    AppCloudOperationIds.circleCircleGroupMembershipApproveCircleGroupMember =>
      (id: 'membership-approve', state: 'active', role: 'member', version: 4),
    AppCloudOperationIds.circleCircleGroupMembershipRejectCircleGroupMember => (
      id: 'membership-reject',
      state: 'rejected',
      role: 'member',
      version: 5,
    ),
    AppCloudOperationIds.circleCircleGroupMembershipRemoveCircleGroupMember => (
      id: 'membership-remove',
      state: 'removed',
      role: 'member',
      version: 6,
    ),
    AppCloudOperationIds
        .circleCircleGroupMembershipUpdateCircleGroupMemberRole =>
      (id: 'membership-role', state: 'active', role: 'manager', version: 7),
    _ => throw StateError('unexpected command operation: $operationId'),
  };
  return <String, Object?>{
    'membershipId': result.id,
    'version': result.version,
    'role': result.role,
    'state': result.state,
    'idempotentReplay': replayed,
  };
}

Map<String, Object?> _membershipSlice({
  required String membershipId,
  required String personaId,
}) => <String, Object?>{
  'membershipId': membershipId,
  'version': 8,
  'groupId': 'group-1',
  'circleId': 'circle-1',
  'personaId': personaId,
  'role': 'member',
  'state': 'active',
  'joinedAt': '2026-08-09T08:00:00Z',
  'leftAt': null,
  'decidedAt': '2026-08-09T08:01:00Z',
  'createdAt': '2026-08-09T08:00:00Z',
  'updatedAt': '2026-08-09T08:01:00Z',
};

void _expectQuery(
  CapturedRemoteApiPathRequest request, {
  required String path,
  required String operationId,
  required String pageId,
  Map<String, String> query = const <String, String>{},
}) {
  expect(request.method, 'GET');
  expect(request.path, path);
  expect(request.query, query);
  expect(request.body, isEmpty);
  expect(request.headers['Authorization'], 'Bearer integration-contract-token');
  expect(request.headers.containsKey('Idempotency-Key'), isFalse);
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: pageId,
    surfaceId: 'circleDetail',
    operationId: operationId,
  );
}

void _expectCommand(
  CapturedRemoteApiPathRequest request, {
  required String method,
  required String path,
  required String operationId,
  required String pageId,
  required Map<String, Object?> body,
}) {
  expect(request.method, method);
  expect(request.path, path);
  expect(request.query, isEmpty);
  expect(request.body, body);
  expect(request.headers['Authorization'], 'Bearer integration-contract-token');
  expect(request.headers['Idempotency-Key'], '$pageId-intent');
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: pageId,
    surfaceId: 'circleDetail',
    operationId: operationId,
  );
}
