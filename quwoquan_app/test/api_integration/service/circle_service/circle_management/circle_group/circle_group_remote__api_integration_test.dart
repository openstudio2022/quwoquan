// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-003
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-004
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-005
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-006
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-011
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-012
// readiness_case: circle_group_list_circle_groups_app_api
// readiness_case: circle_group_search_circle_groups_app_api
// readiness_case: circle_group_create_circle_group_app_api
// readiness_case: circle_group_get_circle_group_app_api
// readiness_case: circle_group_update_circle_group_app_api
// readiness_case: circle_group_archive_circle_group_app_api

/// CircleGroup operation-level production API source contract.
///
/// Every actor and parent object is acquired through public commands. The test
/// uses Generated clients through production Remote composition, proves only
/// GWT-003..006/GWT-011..012, and does not close the cross-service Chat binding,
/// Inbox, realtime, reclaim, DLQ, or health requirements in GWT-001/GWT-002.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/circle_api_contract_harness.dart';
import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiContractBaseUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');

const _groupOperationIds = <String>{
  AppCloudOperationIds.circleCircleGroupListCircleGroups,
  AppCloudOperationIds.circleCircleGroupSearchCircleGroups,
  AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
  AppCloudOperationIds.circleCircleGroupGetCircleGroup,
  AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
  AppCloudOperationIds.circleCircleGroupArchiveCircleGroup,
};

void main() {
  test(
    'all CircleGroup operations converge through a real production process',
    () async {
      _requireGammaCandidate();
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
      final outsider = await createHarness();
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final ownerPersonaId = await _loginPersona(
        owner,
        'circle-group-owner-$suffix',
      );
      await _loginPersona(outsider, 'circle-group-outsider-$suffix');
      final telemetry = _TelemetryLedger();

      final circle = await owner.withIdempotencyKey(
        'circle-group-parent-$suffix',
        () => owner.lifecycle.createCircle(
          CreateCircleCommand(
            name: 'CircleGroup API contract $suffix',
            category: 'community',
          ),
        ),
      );
      final circleId = circle.circleId;
      addTearDown(() async {
        await owner.withIdempotencyKey(
          'circle-group-parent-cleanup-$circleId',
          () => owner.lifecycle.archiveCircle(
            ArchiveCircleCommand(circleId: circleId),
          ),
        );
      });
      void registerGroupCleanup(String groupId) {
        addTearDown(() async {
          await owner.withIdempotencyKey(
            'circle-group-cleanup-$groupId',
            () => owner.groupCommands.archive(
              ArchiveCircleGroupCommand(circleId: circleId, groupId: groupId),
            ),
          );
        });
      }

      final parent = await telemetry.observe(
        AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
        () => owner.withIdempotencyKey(
          'circle-group-parent-node-$suffix',
          () => owner.groupCommands.create(
            CreateCircleGroupCommand(
              circleId: circleId,
              groupType: CircleGroupType.orgNode,
              nodeType: OrganizationNodeType.department,
              name: 'Contract parent $suffix',
              visibility: CircleGroupVisibility.private,
              joinPolicy: CircleGroupJoinPolicy.inviteOnly,
              storageEnabled: false,
              noticeEnabled: false,
            ),
          ),
        ),
      );
      registerGroupCleanup(parent.groupId);
      final createKey = 'circle-group-create-$suffix';
      final childACommand = CreateCircleGroupCommand(
        circleId: circleId,
        parentGroupId: parent.groupId,
        groupType: CircleGroupType.orgNode,
        nodeType: OrganizationNodeType.team,
        name: 'Contract branch $suffix A',
        description: 'authoritative branch A',
        visibility: CircleGroupVisibility.private,
        joinPolicy: CircleGroupJoinPolicy.applyOnly,
        storageEnabled: true,
        noticeEnabled: true,
      );
      final childA = await telemetry.observe(
        AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
        () => owner.withIdempotencyKey(
          createKey,
          () => owner.groupCommands.create(childACommand),
        ),
      );
      registerGroupCleanup(childA.groupId);
      final childAReplay = await telemetry.observe(
        AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
        () => owner.withIdempotencyKey(
          createKey,
          () => owner.groupCommands.create(childACommand),
        ),
      );
      expect(childA.groupId, isNotEmpty);
      expect(childA.idempotentReplay, isFalse);
      expect(childAReplay.groupId, childA.groupId);
      expect(childAReplay.version, childA.version);
      expect(childAReplay.idempotentReplay, isTrue);

      await _expectCanonicalFailure(
        telemetry.observe(
          AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
          () => owner.withIdempotencyKey(
            createKey,
            () => owner.groupCommands.create(
              CreateCircleGroupCommand(
                circleId: circleId,
                parentGroupId: parent.groupId,
                groupType: CircleGroupType.orgNode,
                nodeType: OrganizationNodeType.team,
                name: 'Conflicting branch $suffix',
                visibility: CircleGroupVisibility.private,
                joinPolicy: CircleGroupJoinPolicy.applyOnly,
                storageEnabled: true,
                noticeEnabled: true,
              ),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
        codes: const <String>{'CIRCLE.USER.group_idempotency_conflict'},
        statusCodes: const <int>{409},
      );

      final childB = await telemetry.observe(
        AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
        () => owner.withIdempotencyKey(
          'circle-group-create-b-$suffix',
          () => owner.groupCommands.create(
            CreateCircleGroupCommand(
              circleId: circleId,
              parentGroupId: parent.groupId,
              groupType: CircleGroupType.orgNode,
              nodeType: OrganizationNodeType.team,
              name: 'Contract branch $suffix B',
              description: 'authoritative branch B',
              visibility: CircleGroupVisibility.private,
              joinPolicy: CircleGroupJoinPolicy.applyOnly,
              storageEnabled: true,
              noticeEnabled: true,
            ),
          ),
        ),
      );
      registerGroupCleanup(childB.groupId);
      expect(<String>{childA.groupId, childB.groupId}, hasLength(2));

      for (final groupId in <String>[childA.groupId, childB.groupId]) {
        await _waitForGroupOwner(
          owner,
          circleId: circleId,
          groupId: groupId,
          personaId: ownerPersonaId,
        );
      }

      final createdReadback = await telemetry.observe(
        AppCloudOperationIds.circleCircleGroupGetCircleGroup,
        () => owner.groupQueries.get(
          CircleGroupQuery(circleId: circleId, groupId: childA.groupId),
        ),
      );
      _expectAuthoritativeGroup(
        createdReadback,
        circleId: circleId,
        groupId: childA.groupId,
        parentGroupId: parent.groupId,
        name: 'Contract branch $suffix A',
        description: 'authoritative branch A',
        status: CircleGroupStatus.active,
      );
      expect(createdReadback.version, childA.version);

      final listed = await _readTwoListPages(
        telemetry,
        owner,
        circleId: circleId,
        parentGroupId: parent.groupId,
      );
      expect(
        listed.expand((page) => page.items).map((item) => item.groupId).toSet(),
        <String>{childA.groupId, childB.groupId},
      );
      final searched = await _readTwoSearchPages(
        telemetry,
        owner,
        circleId: circleId,
        query: 'Contract branch $suffix',
      );
      expect(
        searched
            .expand((page) => page.items)
            .map((item) => item.groupId)
            .toSet(),
        <String>{childA.groupId, childB.groupId},
      );

      final outsiderCalls =
          <({String operationId, Future<Object?> Function() invoke})>[
            (
              operationId:
                  AppCloudOperationIds.circleCircleGroupListCircleGroups,
              invoke: () => telemetry.observe(
                AppCloudOperationIds.circleCircleGroupListCircleGroups,
                () => outsider.groupQueries.list(
                  CircleGroupListQuery(circleId: circleId, limit: 1),
                ),
              ),
            ),
            (
              operationId:
                  AppCloudOperationIds.circleCircleGroupSearchCircleGroups,
              invoke: () => telemetry.observe(
                AppCloudOperationIds.circleCircleGroupSearchCircleGroups,
                () => outsider.groupQueries.search(
                  CircleGroupSearchQuery(
                    circleId: circleId,
                    query: 'Contract branch $suffix',
                    limit: 1,
                  ),
                ),
              ),
            ),
            (
              operationId: AppCloudOperationIds.circleCircleGroupGetCircleGroup,
              invoke: () => telemetry.observe(
                AppCloudOperationIds.circleCircleGroupGetCircleGroup,
                () => outsider.groupQueries.get(
                  CircleGroupQuery(circleId: circleId, groupId: childA.groupId),
                ),
              ),
            ),
            (
              operationId:
                  AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
              invoke: () => telemetry.observe(
                AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
                () => outsider.withIdempotencyKey(
                  'circle-group-outsider-create-$suffix',
                  () => outsider.groupCommands.create(
                    CreateCircleGroupCommand(
                      circleId: circleId,
                      groupType: CircleGroupType.selfBuilt,
                      name: 'Forbidden group $suffix',
                      visibility: CircleGroupVisibility.private,
                      joinPolicy: CircleGroupJoinPolicy.applyOnly,
                      storageEnabled: false,
                      noticeEnabled: false,
                    ),
                  ),
                ),
              ),
            ),
            (
              operationId:
                  AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
              invoke: () => telemetry.observe(
                AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
                () => outsider.withIdempotencyKey(
                  'circle-group-outsider-update-$suffix',
                  () => outsider.groupCommands.update(
                    UpdateCircleGroupCommand(
                      circleId: circleId,
                      groupId: childA.groupId,
                      expectedVersion: createdReadback.version,
                      description: 'forbidden update',
                    ),
                  ),
                ),
              ),
            ),
            (
              operationId:
                  AppCloudOperationIds.circleCircleGroupArchiveCircleGroup,
              invoke: () => telemetry.observe(
                AppCloudOperationIds.circleCircleGroupArchiveCircleGroup,
                () => outsider.withIdempotencyKey(
                  'circle-group-outsider-archive-$suffix',
                  () => outsider.groupCommands.archive(
                    ArchiveCircleGroupCommand(
                      circleId: circleId,
                      groupId: childA.groupId,
                    ),
                  ),
                ),
              ),
            ),
          ];
      for (final call in outsiderCalls) {
        await _expectCanonicalFailure(
          call.invoke(),
          operationId: call.operationId,
          codes: const <String>{
            'CIRCLE.USER.not_member',
            'CIRCLE.USER.permission_denied',
          },
          statusCodes: const <int>{403},
        );
      }

      final updateKey = 'circle-group-update-${childA.groupId}';
      final updateCommand = UpdateCircleGroupCommand(
        circleId: circleId,
        groupId: childA.groupId,
        expectedVersion: createdReadback.version,
        description: 'authoritative branch A updated',
        noticeEnabled: false,
      );
      final updated = await telemetry.observe(
        AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
        () => owner.withIdempotencyKey(
          updateKey,
          () => owner.groupCommands.update(updateCommand),
        ),
      );
      final updatedReplay = await telemetry.observe(
        AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
        () => owner.withIdempotencyKey(
          updateKey,
          () => owner.groupCommands.update(updateCommand),
        ),
      );
      expect(updated.version, greaterThan(createdReadback.version));
      expect(updated.idempotentReplay, isFalse);
      expect(updatedReplay.groupId, updated.groupId);
      expect(updatedReplay.version, updated.version);
      expect(updatedReplay.idempotentReplay, isTrue);

      await _expectCanonicalFailure(
        telemetry.observe(
          AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
          () => owner.withIdempotencyKey(
            updateKey,
            () => owner.groupCommands.update(
              UpdateCircleGroupCommand(
                circleId: circleId,
                groupId: childA.groupId,
                expectedVersion: createdReadback.version,
                description: 'conflicting update',
              ),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
        codes: const <String>{'CIRCLE.USER.group_idempotency_conflict'},
        statusCodes: const <int>{409},
      );
      await _expectCanonicalFailure(
        telemetry.observe(
          AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
          () => owner.withIdempotencyKey(
            'circle-group-stale-update-$suffix',
            () => owner.groupCommands.update(
              UpdateCircleGroupCommand(
                circleId: circleId,
                groupId: childA.groupId,
                expectedVersion: createdReadback.version,
                description: 'stale update',
              ),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
        codes: const <String>{'CIRCLE.USER.group_version_conflict'},
        statusCodes: const <int>{409},
      );
      await _expectCanonicalFailure(
        telemetry.observe(
          AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
          () => owner.withIdempotencyKey(
            'circle-group-parent-cycle-$suffix',
            () => owner.groupCommands.update(
              UpdateCircleGroupCommand(
                circleId: circleId,
                groupId: childA.groupId,
                expectedVersion: updated.version,
                parentGroupId: childA.groupId,
              ),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
        codes: const <String>{'CIRCLE.USER.group_parent_invalid'},
        statusCodes: const <int>{409},
      );

      final updatedReadback = await telemetry.observe(
        AppCloudOperationIds.circleCircleGroupGetCircleGroup,
        () => owner.groupQueries.get(
          CircleGroupQuery(circleId: circleId, groupId: childA.groupId),
        ),
      );
      _expectAuthoritativeGroup(
        updatedReadback,
        circleId: circleId,
        groupId: childA.groupId,
        parentGroupId: parent.groupId,
        name: 'Contract branch $suffix A',
        description: 'authoritative branch A updated',
        status: CircleGroupStatus.active,
      );
      expect(updatedReadback.version, updated.version);
      expect(updatedReadback.noticeEnabled, isFalse);

      final archiveKey = 'circle-group-archive-${childA.groupId}';
      final archiveCommand = ArchiveCircleGroupCommand(
        circleId: circleId,
        groupId: childA.groupId,
      );
      final archived = await telemetry.observe(
        AppCloudOperationIds.circleCircleGroupArchiveCircleGroup,
        () => owner.withIdempotencyKey(
          archiveKey,
          () => owner.groupCommands.archive(archiveCommand),
        ),
      );
      final archivedReplay = await telemetry.observe(
        AppCloudOperationIds.circleCircleGroupArchiveCircleGroup,
        () => owner.withIdempotencyKey(
          archiveKey,
          () => owner.groupCommands.archive(archiveCommand),
        ),
      );
      expect(archived.status, CircleGroupStatus.archived);
      expect(archived.idempotentReplay, isFalse);
      expect(archivedReplay.groupId, archived.groupId);
      expect(archivedReplay.version, archived.version);
      expect(archivedReplay.idempotentReplay, isTrue);

      await _expectCanonicalFailure(
        telemetry.observe(
          AppCloudOperationIds.circleCircleGroupArchiveCircleGroup,
          () => owner.withIdempotencyKey(
            archiveKey,
            () => owner.groupCommands.archive(
              ArchiveCircleGroupCommand(
                circleId: circleId,
                groupId: childB.groupId,
              ),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.circleCircleGroupArchiveCircleGroup,
        codes: const <String>{'CIRCLE.USER.group_idempotency_conflict'},
        statusCodes: const <int>{409},
      );
      final archivedReadback = await telemetry.observe(
        AppCloudOperationIds.circleCircleGroupGetCircleGroup,
        () => owner.groupQueries.get(
          CircleGroupQuery(circleId: circleId, groupId: childA.groupId),
        ),
      );
      expect(archivedReadback.groupId, childA.groupId);
      expect(archivedReadback.version, archived.version);
      expect(archivedReadback.status, CircleGroupStatus.archived);
      final childBReadback = await telemetry.observe(
        AppCloudOperationIds.circleCircleGroupGetCircleGroup,
        () => owner.groupQueries.get(
          CircleGroupQuery(circleId: circleId, groupId: childB.groupId),
        ),
      );
      expect(childBReadback.groupId, childB.groupId);
      expect(childBReadback.status, CircleGroupStatus.active);

      await _expectCanonicalFailure(
        telemetry.observe(
          AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
          () => owner.withIdempotencyKey(
            'circle-group-update-archived-$suffix',
            () => owner.groupCommands.update(
              UpdateCircleGroupCommand(
                circleId: circleId,
                groupId: childA.groupId,
                expectedVersion: archived.version,
                description: 'must remain archived',
              ),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
        codes: const <String>{'CIRCLE.USER.group_archived'},
        statusCodes: const <int>{409},
      );
      final finalArchivedReadback = await telemetry.observe(
        AppCloudOperationIds.circleCircleGroupGetCircleGroup,
        () => owner.groupQueries.get(
          CircleGroupQuery(circleId: circleId, groupId: childA.groupId),
        ),
      );
      expect(finalArchivedReadback.version, archived.version);
      expect(finalArchivedReadback.status, CircleGroupStatus.archived);

      await telemetry.expectExactEvidence(harnesses);
    },
  );
}

void _requireGammaCandidate() {
  if (_apiContractBaseUrl.isEmpty) {
    throw StateError('L3: API_CONTRACT_BASE_URL not set');
  }
  if (_apiContractEnv != 'gamma') {
    throw StateError('CircleGroup App API contract requires gamma candidate');
  }
  final baseUri = Uri.tryParse(_apiContractBaseUrl);
  if (baseUri == null ||
      baseUri.scheme != 'https' ||
      !baseUri.hasAuthority ||
      baseUri.host != 'api.gamma.quwoquan.com') {
    throw StateError(
      'CircleGroup App API contract requires the canonical Gamma HTTPS endpoint',
    );
  }
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

Future<void> _waitForGroupOwner(
  CircleApiContractHarness owner, {
  required String circleId,
  required String groupId,
  required String personaId,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 15));
  while (DateTime.now().isBefore(deadline)) {
    try {
      final membership = await owner.groupMembershipQueries.getMy(
        MyCircleGroupMembershipQuery(circleId: circleId, groupId: groupId),
      );
      if (membership.personaId == personaId &&
          membership.role == CircleGroupMembershipRole.owner &&
          membership.state == CircleGroupMembershipState.active) {
        return;
      }
      throw StateError(
        'CircleGroup owner membership has an unexpected authoritative state',
      );
    } on CloudException catch (error) {
      if (error.code != 'CIRCLE.USER.group_membership_not_found') {
        rethrow;
      }
    }
    await Future<void>.delayed(const Duration(milliseconds: 200));
  }
  throw StateError(
    'CircleGroup owner membership did not converge through the public reader',
  );
}

Future<List<CircleGroupPageSlice>> _readTwoListPages(
  _TelemetryLedger telemetry,
  CircleApiContractHarness owner, {
  required String circleId,
  required String parentGroupId,
}) async {
  final first = await telemetry.observe(
    AppCloudOperationIds.circleCircleGroupListCircleGroups,
    () => owner.groupQueries.list(
      CircleGroupListQuery(
        circleId: circleId,
        groupType: CircleGroupType.orgNode,
        visibility: CircleGroupVisibility.private,
        parentGroupId: parentGroupId,
        nodeType: OrganizationNodeType.team,
        limit: 1,
      ),
    ),
  );
  expect(first.items, hasLength(1));
  expect(first.cursor, isNotNull);
  expect(first.cursor, isNotEmpty);
  final second = await telemetry.observe(
    AppCloudOperationIds.circleCircleGroupListCircleGroups,
    () => owner.groupQueries.list(
      CircleGroupListQuery(
        circleId: circleId,
        groupType: CircleGroupType.orgNode,
        visibility: CircleGroupVisibility.private,
        parentGroupId: parentGroupId,
        nodeType: OrganizationNodeType.team,
        cursor: first.cursor,
        limit: 1,
      ),
    ),
  );
  expect(second.items, hasLength(1));
  expect(second.items.single.groupId, isNot(first.items.single.groupId));
  for (final item in <CircleGroupSlice>[...first.items, ...second.items]) {
    expect(item.circleId, circleId);
    expect(item.parentGroupId, parentGroupId);
    expect(item.groupType, CircleGroupType.orgNode);
    expect(item.nodeType, OrganizationNodeType.team);
    expect(item.visibility, CircleGroupVisibility.private);
    expect(item.status, CircleGroupStatus.active);
    expect(item.version, greaterThan(0));
  }
  return <CircleGroupPageSlice>[first, second];
}

Future<List<CircleGroupPageSlice>> _readTwoSearchPages(
  _TelemetryLedger telemetry,
  CircleApiContractHarness owner, {
  required String circleId,
  required String query,
}) async {
  final first = await telemetry.observe(
    AppCloudOperationIds.circleCircleGroupSearchCircleGroups,
    () => owner.groupQueries.search(
      CircleGroupSearchQuery(
        circleId: circleId,
        query: query,
        visibility: CircleGroupVisibility.private,
        groupType: CircleGroupType.orgNode,
        limit: 1,
      ),
    ),
  );
  expect(first.items, hasLength(1));
  expect(first.cursor, isNotNull);
  expect(first.cursor, isNotEmpty);
  final second = await telemetry.observe(
    AppCloudOperationIds.circleCircleGroupSearchCircleGroups,
    () => owner.groupQueries.search(
      CircleGroupSearchQuery(
        circleId: circleId,
        query: query,
        visibility: CircleGroupVisibility.private,
        groupType: CircleGroupType.orgNode,
        cursor: first.cursor,
        limit: 1,
      ),
    ),
  );
  expect(second.items, hasLength(1));
  expect(second.items.single.groupId, isNot(first.items.single.groupId));
  for (final item in <CircleGroupSlice>[...first.items, ...second.items]) {
    expect(item.circleId, circleId);
    expect(item.name, contains(query));
    expect(item.groupType, CircleGroupType.orgNode);
    expect(item.visibility, CircleGroupVisibility.private);
    expect(item.status, CircleGroupStatus.active);
    expect(item.version, greaterThan(0));
  }
  return <CircleGroupPageSlice>[first, second];
}

void _expectAuthoritativeGroup(
  CircleGroupSlice group, {
  required String circleId,
  required String groupId,
  required String parentGroupId,
  required String name,
  required String description,
  required CircleGroupStatus status,
}) {
  expect(group.groupId, groupId);
  expect(group.version, greaterThan(0));
  expect(group.circleId, circleId);
  expect(group.parentGroupId, parentGroupId);
  expect(group.groupType, CircleGroupType.orgNode);
  expect(group.nodeType, OrganizationNodeType.team);
  expect(group.name, name);
  expect(group.description, description);
  expect(group.visibility, CircleGroupVisibility.private);
  expect(group.joinPolicy, CircleGroupJoinPolicy.applyOnly);
  expect(group.storageEnabled, isTrue);
  expect(group.isDefaultPublicGroup, isFalse);
  expect(group.status, status);
  expect(group.memberCount, greaterThanOrEqualTo(0));
  expect(group.createdAt.isUtc, isTrue);
  expect(group.updatedAt.isUtc, isTrue);
}

Future<void> _expectCanonicalFailure(
  Future<Object?> call, {
  required String operationId,
  required Set<String> codes,
  required Set<int> statusCodes,
}) async {
  await expectLater(
    call,
    throwsA(
      isA<CloudException>()
          .having((error) => error.code, 'code', isIn(codes))
          .having((error) => error.statusCode, 'statusCode', isIn(statusCodes))
          .having(
            (error) => error.sourceOperationId,
            'sourceOperationId',
            operationId,
          )
          .having((error) => error.requestId, 'requestId', isNotEmpty)
          .having((error) => error.traceId, 'traceId', isNotEmpty),
    ),
  );
}

final class _TelemetryLedger {
  final Map<String, int> _success = <String, int>{};
  final Map<String, int> _failure = <String, int>{};

  Future<T> observe<T>(
    String operationId,
    Future<T> Function() operation,
  ) async {
    try {
      final value = await operation();
      _success.update(operationId, (count) => count + 1, ifAbsent: () => 1);
      return value;
    } catch (_) {
      _failure.update(operationId, (count) => count + 1, ifAbsent: () => 1);
      rethrow;
    }
  }

  Future<void> expectExactEvidence(
    List<CircleApiContractHarness> harnesses,
  ) async {
    final events = <ProductionCloudOperationTelemetryEvent>[];
    for (final harness in harnesses) {
      events.addAll(await harness.telemetry.waitForEvents(minimumCount: 1));
    }
    final groupEvents = events
        .where(
          (event) => _groupOperationIds.contains(event.canonicalOperationId),
        )
        .toList(growable: false);
    expect(
      groupEvents.map((event) => event.canonicalOperationId).toSet(),
      _groupOperationIds,
    );
    for (final operationId in _groupOperationIds) {
      final operationEvents = groupEvents
          .where((event) => event.canonicalOperationId == operationId)
          .toList(growable: false);
      final succeeded = operationEvents
          .where((event) => event.succeeded)
          .toList(growable: false);
      final failed = operationEvents
          .where((event) => !event.succeeded)
          .toList(growable: false);
      expect(succeeded, hasLength(_success[operationId] ?? 0));
      expect(failed, hasLength(_failure[operationId] ?? 0));
      expect(
        operationEvents.every(
          (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
        ),
        isTrue,
      );
      expect(
        succeeded.every(
          (event) =>
              event.statusCode != null &&
              event.statusCode! >= 200 &&
              event.statusCode! < 300,
        ),
        isTrue,
      );
      expect(
        failed.every(
          (event) => event.statusCode != null && event.statusCode! >= 400,
        ),
        isTrue,
      );
    }
  }
}
