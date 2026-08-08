// spec_ref: specs/feature-tree/circle-community/circle-management-and-stats/spec.md#sit-002
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/member-role-permission/spec.md#gwt-002
// readiness_case: circle_membership_approve_circle_member_app_local
// readiness_case: circle_membership_get_my_circle_membership_app_local
// readiness_case: circle_membership_join_circle_app_local
// readiness_case: circle_membership_leave_circle_app_local
// readiness_case: circle_membership_list_circle_memberships_app_local
// readiness_case: circle_membership_list_pending_circle_memberships_app_local
// readiness_case: circle_membership_list_persona_circles_app_local
// readiness_case: circle_membership_reject_circle_member_app_local
// readiness_case: circle_membership_update_circle_membership_role_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/adapters/membership_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

void main() {
  group('RemoteCircleMembershipFacet generated HTTP contract', () {
    test(
      'queries preserve exact wire and decode canonical projections',
      () async {
        final log = <CapturedRemoteApiPathRequest>[];
        final remote = _remote(log, responseFor: _successResponse);

        final personaCircles = await remote.listPersonaCircles(
          PersonaCircleListQuery(
            personaId: 'persona-target',
            query: '摄影',
            cursor: 'persona-cursor',
            limit: 7,
          ),
        );
        final mine = await remote.getMyMembership(
          MyCircleMembershipQuery(circleId: 'circle-1'),
        );
        final roster = await remote.listMemberships(
          CircleMembershipListQuery(
            circleId: 'circle-1',
            cursor: 'roster-cursor',
            limit: 11,
          ),
        );
        final pending = await remote.listPendingMemberships(
          PendingCircleMembershipListQuery(
            circleId: 'circle-1',
            cursor: 'pending-cursor',
            limit: 13,
          ),
        );

        _expectQuery(
          log[0],
          path: '/personas/persona-target/circles',
          operationId:
              AppCloudOperationIds.circleCircleMembershipListPersonaCircles,
          pageId: CircleRequestPageIds.listPersonaCircles,
          surfaceId: 'userProfile',
          query: const <String, String>{
            'cursor': 'persona-cursor',
            'limit': '7',
            'query': '摄影',
          },
        );
        _expectQuery(
          log[1],
          path: '/circles/circle-1/memberships/self',
          operationId:
              AppCloudOperationIds.circleCircleMembershipGetMyCircleMembership,
          pageId: CircleRequestPageIds.getMyCircleMembership,
          surfaceId: 'circleDetail',
        );
        _expectQuery(
          log[2],
          path: '/circles/circle-1/memberships',
          operationId:
              AppCloudOperationIds.circleCircleMembershipListCircleMemberships,
          pageId: CircleRequestPageIds.listCircleMemberships,
          surfaceId: 'circleDetail',
          query: const <String, String>{
            'cursor': 'roster-cursor',
            'limit': '11',
          },
        );
        _expectQuery(
          log[3],
          path: '/circles/circle-1/memberships/pending',
          operationId: AppCloudOperationIds
              .circleCircleMembershipListPendingCircleMemberships,
          pageId: CircleRequestPageIds.listPendingCircleMemberships,
          surfaceId: 'circleStats',
          query: const <String, String>{
            'cursor': 'pending-cursor',
            'limit': '13',
          },
        );

        expect(personaCircles.items.single.circleId, 'circle-1');
        expect(personaCircles.items.single.status, CircleStatus.active);
        expect(
          personaCircles.items.single.joinPolicy,
          CircleJoinPolicy.approval,
        );
        expect(mine.membershipId, 'membership-self');
        expect(mine.personaId, 'persona-actor');
        expect(mine.state, CircleMembershipState.active);
        expect(roster.items.single.personaId, 'persona-member');
        expect(roster.cursor, 'roster-next');
        expect(pending.items.single.personaId, 'persona-pending');
        expect(pending.items.single.state, CircleMembershipState.pending);
        expect(pending.cursor, 'pending-next');
      },
    );

    test(
      'commands preserve exact wire, intent identity and typed receipts',
      () async {
        final log = <CapturedRemoteApiPathRequest>[];
        final remote = _remote(log, responseFor: _successResponse);

        final joined = await remote.join(
          JoinCircleMembershipCommand(circleId: 'circle-1'),
        );
        final left = await remote.leave(
          LeaveCircleMembershipCommand(circleId: 'circle-1'),
        );
        final approved = await remote.approveWithClientRequestId(
          DecideCircleMembershipCommand(
            circleId: 'circle-1',
            personaId: 'persona-pending',
          ),
          clientRequestId: 'approve-intent',
        );
        final rejected = await remote.rejectWithClientRequestId(
          DecideCircleMembershipCommand(
            circleId: 'circle-1',
            personaId: 'persona-rejected',
          ),
          clientRequestId: 'reject-intent',
        );
        final updated = await remote.updateRole(
          UpdateCircleMembershipRoleCommand(
            circleId: 'circle-1',
            personaId: 'persona-member',
            role: CircleMemberRole.admin,
          ),
        );

        _expectCommand(
          log[0],
          method: 'POST',
          path: '/circles/circle-1/memberships',
          operationId: AppCloudOperationIds.circleCircleMembershipJoinCircle,
          pageId: CircleRequestPageIds.joinCircle,
          surfaceId: 'circleDetail',
          idempotencyKey: 'circle.join-intent',
        );
        _expectCommand(
          log[1],
          method: 'DELETE',
          path: '/circles/circle-1/memberships/self',
          operationId: AppCloudOperationIds.circleCircleMembershipLeaveCircle,
          pageId: CircleRequestPageIds.leaveCircle,
          surfaceId: 'circleDetail',
          idempotencyKey: 'circle.leave-intent',
        );
        _expectCommand(
          log[2],
          method: 'POST',
          path: '/circles/circle-1/memberships/persona-pending:approve',
          operationId:
              AppCloudOperationIds.circleCircleMembershipApproveCircleMember,
          pageId: CircleRequestPageIds.approveCircleMember,
          surfaceId: 'circleStats',
          idempotencyKey: 'approve-intent',
        );
        _expectCommand(
          log[3],
          method: 'POST',
          path: '/circles/circle-1/memberships/persona-rejected:reject',
          operationId:
              AppCloudOperationIds.circleCircleMembershipRejectCircleMember,
          pageId: CircleRequestPageIds.rejectCircleMember,
          surfaceId: 'circleStats',
          idempotencyKey: 'reject-intent',
        );
        _expectCommand(
          log[4],
          method: 'PATCH',
          path: '/circles/circle-1/memberships/persona-member/role',
          operationId: AppCloudOperationIds
              .circleCircleMembershipUpdateCircleMembershipRole,
          pageId: CircleRequestPageIds.updateCircleMembershipRole,
          surfaceId: 'circleStats',
          idempotencyKey: 'circle.members.updateRole-intent',
          body: const <String, Object?>{'role': 'admin'},
        );

        expect(joined.membershipId, 'membership-join');
        expect(joined.state, CircleMembershipState.active);
        expect(left.membershipId, 'membership-leave');
        expect(left.state, CircleMembershipState.left);
        expect(approved.membershipId, 'membership-approve');
        expect(approved.state, CircleMembershipState.active);
        expect(rejected.membershipId, 'membership-reject');
        expect(rejected.state, CircleMembershipState.rejected);
        expect(updated.membershipId, 'membership-role');
        expect(updated.role, CircleMemberRole.admin);
        expect(updated.version, 9);
      },
    );

    test(
      'canonical failures remain operation-bound CloudException values',
      () async {
        final log = <CapturedRemoteApiPathRequest>[];
        final remote = _remote(
          log,
          responseFor: (_) => remoteApiPathJsonResponse(const <String, Object?>{
            'code': 'CIRCLE.SYSTEM.membership_storage_write_failed',
            'message': 'membership storage unavailable',
          }, statusCode: 503),
        );
        final calls =
            <({String operationId, Future<Object?> Function() invoke})>[
              (
                operationId: AppCloudOperationIds
                    .circleCircleMembershipListPersonaCircles,
                invoke: () => remote.listPersonaCircles(
                  PersonaCircleListQuery(personaId: 'persona-target'),
                ),
              ),
              (
                operationId: AppCloudOperationIds
                    .circleCircleMembershipGetMyCircleMembership,
                invoke: () => remote.getMyMembership(
                  MyCircleMembershipQuery(circleId: 'circle-1'),
                ),
              ),
              (
                operationId: AppCloudOperationIds
                    .circleCircleMembershipListCircleMemberships,
                invoke: () => remote.listMemberships(
                  CircleMembershipListQuery(circleId: 'circle-1'),
                ),
              ),
              (
                operationId: AppCloudOperationIds
                    .circleCircleMembershipListPendingCircleMemberships,
                invoke: () => remote.listPendingMemberships(
                  PendingCircleMembershipListQuery(circleId: 'circle-1'),
                ),
              ),
              (
                operationId:
                    AppCloudOperationIds.circleCircleMembershipJoinCircle,
                invoke: () => remote.join(
                  JoinCircleMembershipCommand(circleId: 'circle-1'),
                ),
              ),
              (
                operationId:
                    AppCloudOperationIds.circleCircleMembershipLeaveCircle,
                invoke: () => remote.leave(
                  LeaveCircleMembershipCommand(circleId: 'circle-1'),
                ),
              ),
              (
                operationId: AppCloudOperationIds
                    .circleCircleMembershipApproveCircleMember,
                invoke: () => remote.approveWithClientRequestId(
                  DecideCircleMembershipCommand(
                    circleId: 'circle-1',
                    personaId: 'persona-pending',
                  ),
                  clientRequestId: 'approve-failure-intent',
                ),
              ),
              (
                operationId: AppCloudOperationIds
                    .circleCircleMembershipRejectCircleMember,
                invoke: () => remote.rejectWithClientRequestId(
                  DecideCircleMembershipCommand(
                    circleId: 'circle-1',
                    personaId: 'persona-pending',
                  ),
                  clientRequestId: 'reject-failure-intent',
                ),
              ),
              (
                operationId: AppCloudOperationIds
                    .circleCircleMembershipUpdateCircleMembershipRole,
                invoke: () => remote.updateRole(
                  UpdateCircleMembershipRoleCommand(
                    circleId: 'circle-1',
                    personaId: 'persona-member',
                    role: CircleMemberRole.admin,
                  ),
                ),
              ),
            ];

        for (final call in calls) {
          await expectLater(
            call.invoke(),
            throwsA(
              isA<CloudException>()
                  .having(
                    (error) => error.code,
                    'code',
                    'CIRCLE.SYSTEM.membership_storage_write_failed',
                  )
                  .having(
                    (error) => error.sourceOperationId,
                    'sourceOperationId',
                    call.operationId,
                  ),
            ),
          );
        }
        final commandOperations = <String>{
          AppCloudOperationIds.circleCircleMembershipJoinCircle,
          AppCloudOperationIds.circleCircleMembershipLeaveCircle,
          AppCloudOperationIds.circleCircleMembershipApproveCircleMember,
          AppCloudOperationIds.circleCircleMembershipRejectCircleMember,
          AppCloudOperationIds.circleCircleMembershipUpdateCircleMembershipRole,
        };
        for (final call in calls) {
          final attempts = log
              .where(
                (request) =>
                    request.headers['X-Client-Operation-Id'] ==
                    call.operationId,
              )
              .length;
          expect(
            attempts,
            commandOperations.contains(call.operationId) ? 2 : 1,
          );
        }
      },
    );

    test(
      'moderation rejects missing caller-bound idempotency before HTTP',
      () async {
        final log = <CapturedRemoteApiPathRequest>[];
        final remote = _remote(
          log,
          responseFor: _successResponse,
          contextFactory: _legacyContext,
        );

        expect(
          () => remote.approveWithClientRequestId(
            DecideCircleMembershipCommand(
              circleId: 'circle-1',
              personaId: 'persona-pending',
            ),
            clientRequestId: 'approve-intent',
          ),
          throwsA(isA<StateError>()),
        );
        expect(log, isEmpty);
      },
    );
  });
}

RemoteCircleMembershipFacet _remote(
  List<CapturedRemoteApiPathRequest> log, {
  required RemoteApiPathResponseFactory responseFor,
  Object contextFactory = _context,
}) => RemoteCircleMembershipFacet(
  client: buildRemoteApiPathOperationClient(log, responseFor: responseFor),
  invocationContext: contextFactory,
);

CloudOperationInvocationContext _context(
  String clientPageId, {
  required bool command,
  String? idempotencyKey,
}) => CloudOperationInvocationContext(
  surfaceId: _surfaceFor(clientPageId),
  routeId: _surfaceFor(clientPageId),
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(
    accountId: 'account-actor',
    personaId: 'persona-actor',
  ),
  idempotencyKey: command ? idempotencyKey ?? '$clientPageId-intent' : null,
);

CloudOperationInvocationContext _legacyContext(
  String clientPageId, {
  required bool command,
}) => CloudOperationInvocationContext(
  surfaceId: _surfaceFor(clientPageId),
  routeId: _surfaceFor(clientPageId),
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(
    accountId: 'account-actor',
    personaId: 'persona-actor',
  ),
  idempotencyKey: command ? '$clientPageId-intent' : null,
);

String _surfaceFor(String clientPageId) => switch (clientPageId) {
  CircleRequestPageIds.listPersonaCircles => 'userProfile',
  CircleRequestPageIds.listPendingCircleMemberships ||
  CircleRequestPageIds.approveCircleMember ||
  CircleRequestPageIds.rejectCircleMember ||
  CircleRequestPageIds.updateCircleMembershipRole => 'circleStats',
  _ => 'circleDetail',
};

http.Response _successResponse(http.Request request) {
  final operationId = request.headers['X-Client-Operation-Id'];
  final body = switch (operationId) {
    AppCloudOperationIds.circleCircleMembershipListPersonaCircles =>
      _personaCirclePage,
    AppCloudOperationIds.circleCircleMembershipGetMyCircleMembership =>
      _membershipSlice(
        membershipId: 'membership-self',
        personaId: 'persona-actor',
        state: 'active',
      ),
    AppCloudOperationIds.circleCircleMembershipListCircleMemberships =>
      <String, Object?>{
        'items': <Object?>[
          _membershipSlice(
            membershipId: 'membership-member',
            personaId: 'persona-member',
            state: 'active',
          ),
        ],
        'cursor': 'roster-next',
      },
    AppCloudOperationIds.circleCircleMembershipListPendingCircleMemberships =>
      <String, Object?>{
        'items': <Object?>[
          _membershipSlice(
            membershipId: 'membership-pending',
            personaId: 'persona-pending',
            state: 'pending',
          ),
        ],
        'cursor': 'pending-next',
      },
    AppCloudOperationIds.circleCircleMembershipJoinCircle => _commandResult(
      membershipId: 'membership-join',
      state: 'active',
      role: 'member',
      version: 2,
    ),
    AppCloudOperationIds.circleCircleMembershipLeaveCircle => _commandResult(
      membershipId: 'membership-leave',
      state: 'left',
      role: 'member',
      version: 3,
    ),
    AppCloudOperationIds.circleCircleMembershipApproveCircleMember =>
      _commandResult(
        membershipId: 'membership-approve',
        state: 'active',
        role: 'member',
        version: 7,
      ),
    AppCloudOperationIds.circleCircleMembershipRejectCircleMember =>
      _commandResult(
        membershipId: 'membership-reject',
        state: 'rejected',
        role: 'member',
        version: 8,
      ),
    AppCloudOperationIds.circleCircleMembershipUpdateCircleMembershipRole =>
      _commandResult(
        membershipId: 'membership-role',
        state: 'active',
        role: 'admin',
        version: 9,
      ),
    _ => throw StateError('unexpected operation: $operationId'),
  };
  return remoteApiPathJsonResponse(body);
}

Map<String, Object?> _commandResult({
  required String membershipId,
  required String state,
  required String role,
  required int version,
}) => <String, Object?>{
  'membershipId': membershipId,
  'version': version,
  'state': state,
  'role': role,
  'idempotentReplay': false,
};

Map<String, Object?> _membershipSlice({
  required String membershipId,
  required String personaId,
  required String state,
}) => <String, Object?>{
  'membershipId': membershipId,
  'version': 6,
  'circleId': 'circle-1',
  'personaId': personaId,
  'role': 'member',
  'state': state,
  'joinedAt': '2026-08-08T08:00:00Z',
  'leftAt': null,
  'lastActiveAt': '2026-08-08T09:00:00Z',
  'contribution': 12,
  'createdAt': '2026-08-08T08:00:00Z',
  'updatedAt': '2026-08-08T09:00:00Z',
};

const Map<String, Object?> _personaCirclePage = <String, Object?>{
  'items': <Object?>[
    <String, Object?>{
      'circleId': 'circle-1',
      'name': '摄影同行圈',
      'description': '真实 typed Circle projection',
      'ownerPersonaId': 'persona-owner',
      'category': 'travel',
      'subCategory': 'photography',
      'tags': <String>['travel', 'photography'],
      'memberCount': 42,
      'postCount': 18,
      'weeklyActiveCount': 9,
      'status': 'active',
      'visibility': 'public',
      'joinPolicy': 'approval',
      'kind': 'interest',
      'displaySubjectType': 'circle',
      'followEnabled': true,
      'createdAt': '2026-08-08T08:00:00Z',
      'updatedAt': '2026-08-08T09:00:00Z',
    },
  ],
  'cursor': 'persona-next',
};

void _expectQuery(
  CapturedRemoteApiPathRequest request, {
  required String path,
  required String operationId,
  required String pageId,
  required String surfaceId,
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
    surfaceId: surfaceId,
    operationId: operationId,
  );
}

void _expectCommand(
  CapturedRemoteApiPathRequest request, {
  required String method,
  required String path,
  required String operationId,
  required String pageId,
  required String surfaceId,
  required String idempotencyKey,
  Map<String, Object?> body = const <String, Object?>{},
}) {
  expect(request.method, method);
  expect(request.path, path);
  expect(request.query, isEmpty);
  expect(request.body, body);
  expect(request.headers['Authorization'], 'Bearer integration-contract-token');
  expect(request.headers['Idempotency-Key'], idempotencyKey);
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: pageId,
    surfaceId: surfaceId,
    operationId: operationId,
  );
}
