// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-003
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-004
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-005
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-006
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-007
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-008
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-009
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-010
// readiness_case: circle_group_membership_apply_join_circle_group_app_api
// readiness_case: circle_group_membership_list_circle_group_memberships_app_api
// readiness_case: circle_group_membership_get_my_circle_group_membership_app_api
// readiness_case: circle_group_membership_leave_circle_group_app_api
// readiness_case: circle_group_membership_approve_circle_group_member_app_api
// readiness_case: circle_group_membership_reject_circle_group_member_app_api
// readiness_case: circle_group_membership_remove_circle_group_member_app_api
// readiness_case: circle_group_membership_update_circle_group_member_role_app_api

/// CircleGroupMembership operation-level production API source contract.
///
/// This runner acquires every actor and parent object through public commands,
/// then uses Generated clients through production Remote composition only. It
/// proves GWT-003..010 owner contracts; it does not close GWT-001/GWT-002 Chat
/// binding, Inbox, realtime, reclaim, DLQ, or health terminal requirements.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/circle_api_contract_harness.dart';
import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

void main() {
  test(
    'all group-membership operations converge through a real production process',
    () async {
      final harnesses = <CircleApiContractHarness>[];
      addTearDown(() async {
        for (final harness in harnesses.reversed) {
          await harness.close();
        }
      });

      Future<CircleApiContractHarness> createHarness() async {
        final harness = await CircleApiContractHarness.create();
        harnesses.add(harness);
        return harness;
      }

      final owner = await createHarness();
      final approvedMember = await createHarness();
      final rejectedMember = await createHarness();
      final leavingMember = await createHarness();
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();

      await owner.loginDisposableAccount('group-membership-owner-$suffix');
      final approvedPersonaId = await _loginPersona(
        approvedMember,
        'group-membership-approved-$suffix',
      );
      final rejectedPersonaId = await _loginPersona(
        rejectedMember,
        'group-membership-rejected-$suffix',
      );
      final leavingPersonaId = await _loginPersona(
        leavingMember,
        'group-membership-leaving-$suffix',
      );

      final circle = await owner.withIdempotencyKey(
        'group-membership-parent-$suffix',
        () => owner.lifecycle.createCircle(
          CreateCircleCommand(
            name: 'Group membership contract $suffix',
            category: 'community',
          ),
        ),
      );
      final circleId = circle.circleId;
      addTearDown(() async {
        await owner.withIdempotencyKey(
          'group-membership-parent-cleanup-$circleId',
          () => owner.lifecycle.archiveCircle(
            ArchiveCircleCommand(circleId: circleId),
          ),
        );
      });

      final group = await owner.withIdempotencyKey(
        'group-membership-group-$suffix',
        () => owner.groupCommands.create(
          CreateCircleGroupCommand(
            circleId: circleId,
            groupType: CircleGroupType.selfBuilt,
            name: 'Membership group $suffix',
            visibility: CircleGroupVisibility.private,
            joinPolicy: CircleGroupJoinPolicy.applyOnly,
            storageEnabled: false,
            noticeEnabled: false,
          ),
        ),
      );
      final groupId = group.groupId;
      addTearDown(() async {
        await owner.withIdempotencyKey(
          'group-membership-group-cleanup-$groupId',
          () => owner.groupCommands.archive(
            ArchiveCircleGroupCommand(circleId: circleId, groupId: groupId),
          ),
        );
      });

      for (final actor
          in <
            ({CircleApiContractHarness harness, String personaId, String label})
          >[
            (
              harness: approvedMember,
              personaId: approvedPersonaId,
              label: 'approved',
            ),
            (
              harness: rejectedMember,
              personaId: rejectedPersonaId,
              label: 'rejected',
            ),
            (
              harness: leavingMember,
              personaId: leavingPersonaId,
              label: 'leaving',
            ),
          ]) {
        final command = ApplyCircleGroupMembershipCommand(
          circleId: circleId,
          groupId: groupId,
        );
        final replay = await _replayCommand(
          actor.harness,
          'group-membership-apply-${actor.label}-$suffix',
          () => actor.harness.groupMembershipCommands.apply(command),
        );
        expect(replay.first.state, CircleGroupMembershipState.pending);
        expect(replay.replayed.membershipId, replay.first.membershipId);
        await _expectMyMembership(
          actor.harness,
          circleId: circleId,
          groupId: groupId,
          personaId: actor.personaId,
          state: CircleGroupMembershipState.pending,
          role: CircleGroupMembershipRole.member,
        );
      }

      final pendingPages = await _readTwoRosterPages(
        owner,
        circleId: circleId,
        groupId: groupId,
        state: CircleGroupMembershipState.pending,
      );
      expect(
        pendingPages.expand((page) => page.items).map((item) => item.personaId),
        contains(approvedPersonaId),
      );

      final approved = await _replayCommand(
        owner,
        'group-membership-approve-approved-$suffix',
        () => owner.groupMembershipCommands.approve(
          DecideCircleGroupMembershipCommand(
            circleId: circleId,
            groupId: groupId,
            personaId: approvedPersonaId,
          ),
        ),
      );
      expect(approved.first.state, CircleGroupMembershipState.active);
      await _expectMyMembership(
        approvedMember,
        circleId: circleId,
        groupId: groupId,
        personaId: approvedPersonaId,
        state: CircleGroupMembershipState.active,
        role: CircleGroupMembershipRole.member,
      );

      final roleUpdated = await _replayCommand(
        owner,
        'group-membership-role-$suffix',
        () => owner.groupMembershipCommands.updateRole(
          UpdateCircleGroupMembershipRoleCommand(
            circleId: circleId,
            groupId: groupId,
            personaId: approvedPersonaId,
            role: CircleGroupMembershipRole.manager,
          ),
        ),
      );
      expect(roleUpdated.first.role, CircleGroupMembershipRole.manager);
      await _expectMyMembership(
        approvedMember,
        circleId: circleId,
        groupId: groupId,
        personaId: approvedPersonaId,
        state: CircleGroupMembershipState.active,
        role: CircleGroupMembershipRole.manager,
      );

      final leavingApproved = await _replayCommand(
        owner,
        'group-membership-approve-leaving-$suffix',
        () => owner.groupMembershipCommands.approve(
          DecideCircleGroupMembershipCommand(
            circleId: circleId,
            groupId: groupId,
            personaId: leavingPersonaId,
          ),
        ),
      );
      expect(leavingApproved.first.state, CircleGroupMembershipState.active);
      await _expectMyMembership(
        leavingMember,
        circleId: circleId,
        groupId: groupId,
        personaId: leavingPersonaId,
        state: CircleGroupMembershipState.active,
        role: CircleGroupMembershipRole.member,
      );

      final activePages = await _readTwoRosterPages(
        owner,
        circleId: circleId,
        groupId: groupId,
        state: CircleGroupMembershipState.active,
      );
      final activeIds = activePages
          .expand((page) => page.items)
          .map((item) => item.membershipId)
          .toSet();
      expect(activeIds, hasLength(2));

      final rejected = await _replayCommand(
        owner,
        'group-membership-reject-$suffix',
        () => owner.groupMembershipCommands.reject(
          DecideCircleGroupMembershipCommand(
            circleId: circleId,
            groupId: groupId,
            personaId: rejectedPersonaId,
          ),
        ),
      );
      expect(rejected.first.state, CircleGroupMembershipState.rejected);
      await _expectMyMembership(
        rejectedMember,
        circleId: circleId,
        groupId: groupId,
        personaId: rejectedPersonaId,
        state: CircleGroupMembershipState.rejected,
        role: CircleGroupMembershipRole.member,
      );

      final removed = await _replayCommand(
        owner,
        'group-membership-remove-$suffix',
        () => owner.groupMembershipCommands.remove(
          RemoveCircleGroupMembershipCommand(
            circleId: circleId,
            groupId: groupId,
            personaId: approvedPersonaId,
          ),
        ),
      );
      expect(removed.first.state, CircleGroupMembershipState.removed);
      await _expectMyMembership(
        approvedMember,
        circleId: circleId,
        groupId: groupId,
        personaId: approvedPersonaId,
        state: CircleGroupMembershipState.removed,
        role: CircleGroupMembershipRole.manager,
      );

      final left = await _replayCommand(
        leavingMember,
        'group-membership-leave-$suffix',
        () => leavingMember.groupMembershipCommands.leave(
          LeaveCircleGroupMembershipCommand(
            circleId: circleId,
            groupId: groupId,
          ),
        ),
      );
      expect(left.first.state, CircleGroupMembershipState.left);
      await _expectMyMembership(
        leavingMember,
        circleId: circleId,
        groupId: groupId,
        personaId: leavingPersonaId,
        state: CircleGroupMembershipState.left,
        role: CircleGroupMembershipRole.member,
      );

      await _expectExactSuccessfulTelemetry(<CircleApiContractHarness>[
        owner,
        approvedMember,
        rejectedMember,
        leavingMember,
      ]);

      final unauthenticated = await createHarness();
      await _expectCanonicalUnauthenticatedFailures(
        unauthenticated,
        circleId: circleId,
        groupId: groupId,
        targetPersonaId: approvedPersonaId,
      );
      await _expectMyMembership(
        approvedMember,
        circleId: circleId,
        groupId: groupId,
        personaId: approvedPersonaId,
        state: CircleGroupMembershipState.removed,
        role: CircleGroupMembershipRole.manager,
      );
      await _expectMyMembership(
        rejectedMember,
        circleId: circleId,
        groupId: groupId,
        personaId: rejectedPersonaId,
        state: CircleGroupMembershipState.rejected,
        role: CircleGroupMembershipRole.member,
      );
      await _expectMyMembership(
        leavingMember,
        circleId: circleId,
        groupId: groupId,
        personaId: leavingPersonaId,
        state: CircleGroupMembershipState.left,
        role: CircleGroupMembershipRole.member,
      );
    },
  );
}

Future<String> _loginPersona(
  CircleApiContractHarness harness,
  String purpose,
) async {
  final session = await harness.loginDisposableAccount(purpose);
  final personaId = session.activePersona?.personaId;
  expect(personaId, isNotNull);
  expect(personaId, isNotEmpty);
  return personaId!;
}

Future<
  ({
    CircleGroupMembershipCommandResult first,
    CircleGroupMembershipCommandResult replayed,
  })
>
_replayCommand(
  CircleApiContractHarness harness,
  String idempotencyKey,
  Future<CircleGroupMembershipCommandResult> Function() operation,
) async {
  final first = await harness.withIdempotencyKey(idempotencyKey, operation);
  final replayed = await harness.withIdempotencyKey(idempotencyKey, operation);
  expect(first.idempotentReplay, isFalse);
  expect(replayed.idempotentReplay, isTrue);
  expect(replayed.membershipId, first.membershipId);
  expect(replayed.version, first.version);
  expect(replayed.state, first.state);
  expect(replayed.role, first.role);
  return (first: first, replayed: replayed);
}

Future<void> _expectMyMembership(
  CircleApiContractHarness harness, {
  required String circleId,
  required String groupId,
  required String personaId,
  required CircleGroupMembershipState state,
  required CircleGroupMembershipRole role,
}) async {
  final membership = await harness.groupMembershipQueries.getMy(
    MyCircleGroupMembershipQuery(circleId: circleId, groupId: groupId),
  );
  expect(membership.membershipId, isNotEmpty);
  expect(membership.personaId, personaId);
  expect(membership.circleId, circleId);
  expect(membership.groupId, groupId);
  expect(membership.version, greaterThan(0));
  expect(membership.state, state);
  expect(membership.role, role);
}

Future<List<CircleGroupMembershipPageSlice>> _readTwoRosterPages(
  CircleApiContractHarness owner, {
  required String circleId,
  required String groupId,
  required CircleGroupMembershipState state,
}) async {
  final first = await owner.groupMembershipQueries.list(
    CircleGroupMembershipListQuery(
      circleId: circleId,
      groupId: groupId,
      state: state,
      limit: 1,
    ),
  );
  expect(first.items, hasLength(1));
  expect(first.items.single.state, state);
  expect(first.cursor, isNotNull);
  expect(first.cursor, isNotEmpty);
  final second = await owner.groupMembershipQueries.list(
    CircleGroupMembershipListQuery(
      circleId: circleId,
      groupId: groupId,
      state: state,
      cursor: first.cursor,
      limit: 1,
    ),
  );
  expect(second.items, hasLength(1));
  expect(second.items.single.state, state);
  expect(
    second.items.single.membershipId,
    isNot(first.items.single.membershipId),
  );
  return <CircleGroupMembershipPageSlice>[first, second];
}

const Map<String, int> _expectedSuccessfulTelemetryCounts = <String, int>{
  AppCloudOperationIds.circleCircleGroupMembershipApplyJoinCircleGroup: 6,
  AppCloudOperationIds.circleCircleGroupMembershipListCircleGroupMemberships: 4,
  AppCloudOperationIds.circleCircleGroupMembershipGetMyCircleGroupMembership: 9,
  AppCloudOperationIds.circleCircleGroupMembershipLeaveCircleGroup: 2,
  AppCloudOperationIds.circleCircleGroupMembershipApproveCircleGroupMember: 4,
  AppCloudOperationIds.circleCircleGroupMembershipRejectCircleGroupMember: 2,
  AppCloudOperationIds.circleCircleGroupMembershipRemoveCircleGroupMember: 2,
  AppCloudOperationIds.circleCircleGroupMembershipUpdateCircleGroupMemberRole:
      2,
};

Future<void> _expectExactSuccessfulTelemetry(
  List<CircleApiContractHarness> harnesses,
) async {
  final events = <ProductionCloudOperationTelemetryEvent>[];
  for (final harness in harnesses) {
    events.addAll(await harness.telemetry.waitForEvents(minimumCount: 1));
  }
  final membershipEvents = events
      .where(
        (event) => _expectedSuccessfulTelemetryCounts.containsKey(
          event.canonicalOperationId,
        ),
      )
      .toList(growable: false);
  for (final entry in _expectedSuccessfulTelemetryCounts.entries) {
    final operationEvents = membershipEvents
        .where((event) => event.canonicalOperationId == entry.key)
        .toList(growable: false);
    expect(operationEvents, hasLength(entry.value));
    expect(operationEvents.every((event) => event.succeeded), isTrue);
    expect(
      operationEvents.every(
        (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
      ),
      isTrue,
    );
  }
}

typedef _FailureCall = ({
  String operationId,
  Future<Object?> Function() invoke,
});

Future<void> _expectCanonicalUnauthenticatedFailures(
  CircleApiContractHarness unauthenticated, {
  required String circleId,
  required String groupId,
  required String targetPersonaId,
}) async {
  final calls = <_FailureCall>[
    (
      operationId:
          AppCloudOperationIds.circleCircleGroupMembershipApplyJoinCircleGroup,
      invoke: () => unauthenticated.withIdempotencyKey(
        'unauthenticated-apply',
        () => unauthenticated.groupMembershipCommands.apply(
          ApplyCircleGroupMembershipCommand(
            circleId: circleId,
            groupId: groupId,
          ),
        ),
      ),
    ),
    (
      operationId: AppCloudOperationIds
          .circleCircleGroupMembershipListCircleGroupMemberships,
      invoke: () => unauthenticated.groupMembershipQueries.list(
        CircleGroupMembershipListQuery(
          circleId: circleId,
          groupId: groupId,
          limit: 1,
        ),
      ),
    ),
    (
      operationId: AppCloudOperationIds
          .circleCircleGroupMembershipGetMyCircleGroupMembership,
      invoke: () => unauthenticated.groupMembershipQueries.getMy(
        MyCircleGroupMembershipQuery(circleId: circleId, groupId: groupId),
      ),
    ),
    (
      operationId:
          AppCloudOperationIds.circleCircleGroupMembershipLeaveCircleGroup,
      invoke: () => unauthenticated.withIdempotencyKey(
        'unauthenticated-leave',
        () => unauthenticated.groupMembershipCommands.leave(
          LeaveCircleGroupMembershipCommand(
            circleId: circleId,
            groupId: groupId,
          ),
        ),
      ),
    ),
    (
      operationId: AppCloudOperationIds
          .circleCircleGroupMembershipApproveCircleGroupMember,
      invoke: () => unauthenticated.withIdempotencyKey(
        'unauthenticated-approve',
        () => unauthenticated.groupMembershipCommands.approve(
          DecideCircleGroupMembershipCommand(
            circleId: circleId,
            groupId: groupId,
            personaId: targetPersonaId,
          ),
        ),
      ),
    ),
    (
      operationId: AppCloudOperationIds
          .circleCircleGroupMembershipRejectCircleGroupMember,
      invoke: () => unauthenticated.withIdempotencyKey(
        'unauthenticated-reject',
        () => unauthenticated.groupMembershipCommands.reject(
          DecideCircleGroupMembershipCommand(
            circleId: circleId,
            groupId: groupId,
            personaId: targetPersonaId,
          ),
        ),
      ),
    ),
    (
      operationId: AppCloudOperationIds
          .circleCircleGroupMembershipRemoveCircleGroupMember,
      invoke: () => unauthenticated.withIdempotencyKey(
        'unauthenticated-remove',
        () => unauthenticated.groupMembershipCommands.remove(
          RemoveCircleGroupMembershipCommand(
            circleId: circleId,
            groupId: groupId,
            personaId: targetPersonaId,
          ),
        ),
      ),
    ),
    (
      operationId: AppCloudOperationIds
          .circleCircleGroupMembershipUpdateCircleGroupMemberRole,
      invoke: () => unauthenticated.withIdempotencyKey(
        'unauthenticated-role',
        () => unauthenticated.groupMembershipCommands.updateRole(
          UpdateCircleGroupMembershipRoleCommand(
            circleId: circleId,
            groupId: groupId,
            personaId: targetPersonaId,
            role: CircleGroupMembershipRole.manager,
          ),
        ),
      ),
    ),
  ];

  for (final call in calls) {
    await expectLater(
      call.invoke(),
      throwsA(
        isA<CloudException>()
            .having((error) => error.statusCode, 'statusCode', anyOf(401, 403))
            .having(
              (error) => error.code,
              'code',
              matches(
                RegExp(r'^[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[A-Za-z0-9_]+$'),
              ),
            )
            .having(
              (error) => error.sourceOperationId,
              'sourceOperationId',
              call.operationId,
            ),
      ),
    );
  }

  final telemetry = await unauthenticated.telemetry.waitForEvents(
    minimumCount: calls.length,
  );
  final failed = telemetry
      .where(
        (event) =>
            calls.any((call) => call.operationId == event.canonicalOperationId),
      )
      .toList(growable: false);
  expect(failed, hasLength(calls.length));
  expect(failed.every((event) => !event.succeeded), isTrue);
  expect(
    failed.every(
      (event) =>
          (event.statusCode == 401 || event.statusCode == 403) &&
          event.requestId.isNotEmpty &&
          event.traceId.isNotEmpty,
    ),
    isTrue,
  );
}
