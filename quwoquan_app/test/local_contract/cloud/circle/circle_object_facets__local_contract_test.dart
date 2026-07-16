import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'CircleMembership commands use operation-specific generated ABI',
    () async {
      final executor = _CircleRecordingExecutor(response: _commandResult());
      final client = GeneratedCloudOperationClient(executor);
      const context = CloudOperationInvocationContext(
        surfaceId: 'circleDetail',
        clientPageId: 'circle.join',
        actor: CloudOperationActorContext(personaId: 'persona-1'),
        idempotencyKey: 'idem-1',
      );

      final result = await client.circleCircleMembershipJoinCircle(
        JoinCircleMembershipCommand(circleId: 'circle-1'),
        context: context,
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.circleCircleMembershipJoinCircle,
      );
      expect(executor.pathParameters, <String, String>{'circleId': 'circle-1'});
      expect(executor.body, isNull);
      expect(result.role, CircleMembershipRole.member);
      expect(result.state, CircleMembershipState.active);
    },
  );

  test('LeaveCircle version is encoded only as validated If-Match', () {
    final payload = encodeLeaveCircleMembershipCommand(
      LeaveCircleMembershipCommand(circleId: 'circle-1', expectedVersion: 7),
    );

    expect(payload.pathParameters, <String, String>{'circleId': 'circle-1'});
    expect(payload.headers, <String, String>{'If-Match': '"7"'});
    expect(payload.body, isNull);
  });

  test(
    'CircleMembership self query strictly decodes persona identity',
    () async {
      final executor = _CircleRecordingExecutor(response: _membership());
      final client = GeneratedCloudOperationClient(executor);

      final membership = await client
          .circleCircleMembershipGetMyCircleMembership(
            MyCircleMembershipQuery(circleId: 'circle-1'),
            context: const CloudOperationInvocationContext(
              surfaceId: 'circleDetail',
              clientPageId: 'circle.members.self',
              actor: CloudOperationActorContext(personaId: 'persona-1'),
            ),
          );

      expect(membership.personaId, 'persona-1');
      expect(membership.version, 7);
      expect(executor.body, isNull);
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.circleCircleMembershipGetMyCircleMembership,
      );
    },
  );

  test('CircleMembership decoder rejects userId alias and unknown fields', () {
    final alias = _membership()
      ..remove('personaId')
      ..['userId'] = 'persona-1';
    expect(() => decodeCircleMembershipSlice(alias), throwsFormatException);

    final unknown = _membership()..['displayName'] = 'compat alias';
    expect(() => decodeCircleMembershipSlice(unknown), throwsFormatException);
  });

  test(
    'CircleBehaviorFact body cannot carry actor or session metadata',
    () async {
      final executor = _CircleRecordingExecutor();
      final client = GeneratedCloudOperationClient(executor);

      await client.circleCircleBehaviorFactReportCircleBehavior(
        AppendCircleBehaviorFactCommand(
          circleId: 'circle-1',
          eventType: CircleBehaviorEventType.impression,
        ),
        context: const CloudOperationInvocationContext(
          surfaceId: 'circleDetail',
          clientPageId: 'circle.behaviors.report',
          actor: CloudOperationActorContext(personaId: 'persona-1'),
          idempotencyKey: 'behavior-1',
        ),
      );

      expect(executor.body, <String, Object?>{
        'circleId': 'circle-1',
        'eventType': 'impression',
      });
      expect(executor.body, isNot(contains('personaId')));
      expect(executor.body, isNot(contains('sessionId')));
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.circleCircleBehaviorFactReportCircleBehavior,
      );
    },
  );

  test(
    'CircleGroup create uses generated typed ABI without actor fields',
    () async {
      final executor = _CircleRecordingExecutor(
        response: _groupCommandResult(),
      );
      final client = GeneratedCloudOperationClient(executor);

      final result = await client.circleCircleGroupCreateCircleGroup(
        CreateCircleGroupCommand(
          circleId: 'circle-1',
          groupType: CircleGroupType.selfBuilt,
          name: '远行同好',
          visibility: CircleGroupVisibility.private,
          joinPolicy: CircleGroupJoinPolicy.applyOnly,
          storageEnabled: true,
          noticeEnabled: false,
        ),
        context: const CloudOperationInvocationContext(
          surfaceId: 'circleDetail',
          clientPageId: 'circle.group.create',
          actor: CloudOperationActorContext(personaId: 'persona-1'),
          idempotencyKey: 'group-create-1',
        ),
      );

      expect(result.groupId, 'group-1');
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
      );
      expect(executor.body, isNot(contains('personaId')));
      expect(executor.body, isNot(contains('circleId')));
      expect(executor.pathParameters, <String, String>{'circleId': 'circle-1'});
    },
  );

  test('CircleGroup update/archive carry version only through If-Match', () {
    final update = encodeUpdateCircleGroupCommand(
      UpdateCircleGroupCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
        expectedVersion: 7,
        name: '更新名称',
      ),
    );
    expect(update.headers, <String, String>{'If-Match': '"7"'});
    expect(update.body, <String, Object?>{'name': '更新名称'});

    final archive = encodeArchiveCircleGroupCommand(
      ArchiveCircleGroupCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
        expectedVersion: 8,
      ),
    );
    expect(archive.headers, <String, String>{'If-Match': '"8"'});
    expect(archive.body, isNull);
  });

  test('CircleGroup Reader rejects aggregate storage and audit aliases', () {
    expect(decodeCircleGroupSlice(_groupSlice()).groupId, 'group-1');
    expect(
      () => decodeCircleGroupSlice(_groupSlice()..['_id'] = 'group-1'),
      throwsFormatException,
    );
    expect(
      () => decodeCircleGroupSlice(
        _groupSlice()..['createdByPersonaId'] = 'persona-1',
      ),
      throwsFormatException,
    );
  });

  test('CircleGroupMembership commands use generated typed ABI', () async {
    final executor = _CircleRecordingExecutor(
      response: _groupMembershipCommandResult(),
    );
    final client = GeneratedCloudOperationClient(executor);

    final result = await client
        .circleCircleGroupMembershipApproveCircleGroupMember(
          DecideCircleGroupMembershipCommand(
            circleId: 'circle-1',
            groupId: 'group-1',
            personaId: 'persona-2',
            expectedVersion: 4,
          ),
          context: const CloudOperationInvocationContext(
            surfaceId: 'circleDetail',
            clientPageId: 'circle.group.members.approve',
            actor: CloudOperationActorContext(personaId: 'persona-owner'),
            idempotencyKey: 'approve-1',
          ),
        );

    expect(result.state, CircleGroupMembershipState.active);
    expect(executor.pathParameters, <String, String>{
      'circleId': 'circle-1',
      'groupId': 'group-1',
      'personaId': 'persona-2',
    });
    expect(executor.headers, <String, String>{'If-Match': '"4"'});
    expect(executor.body, isNull);
    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.circleCircleGroupMembershipApproveCircleGroupMember,
    );
  });

  test('CircleGroupMembership Reader rejects userId and decision actor', () {
    expect(
      decodeCircleGroupMembershipSlice(_groupMembershipSlice()).personaId,
      'persona-2',
    );
    expect(
      () => decodeCircleGroupMembershipSlice(
        _groupMembershipSlice()
          ..remove('personaId')
          ..['userId'] = 'persona-2',
      ),
      throwsFormatException,
    );
    expect(
      () => decodeCircleGroupMembershipSlice(
        _groupMembershipSlice()..['decidedByPersonaId'] = 'persona-owner',
      ),
      throwsFormatException,
    );
  });
}

Map<String, Object?> _commandResult() => <String, Object?>{
  'membershipId': 'membership-1',
  'version': 7,
  'state': 'active',
  'role': 'member',
  'idempotentReplay': false,
};

Map<String, Object?> _membership() => <String, Object?>{
  'membershipId': 'membership-1',
  'version': 7,
  'circleId': 'circle-1',
  'personaId': 'persona-1',
  'role': 'member',
  'state': 'active',
  'joinedAt': '2026-07-14T01:00:00Z',
  'leftAt': '0001-01-01T00:00:00Z',
  'lastActiveAt': '2026-07-14T01:00:00Z',
  'contribution': 0,
  'createdAt': '2026-07-14T01:00:00Z',
  'updatedAt': '2026-07-14T01:00:00Z',
};

Map<String, Object?> _groupCommandResult() => <String, Object?>{
  'groupId': 'group-1',
  'version': 1,
  'status': 'active',
  'idempotentReplay': false,
};

Map<String, Object?> _groupSlice() => <String, Object?>{
  'groupId': 'group-1',
  'version': 1,
  'circleId': 'circle-1',
  'groupType': 'self_built',
  'name': '远行同好',
  'visibility': 'private',
  'joinPolicy': 'apply_only',
  'storageEnabled': true,
  'noticeEnabled': false,
  'isDefaultPublicGroup': false,
  'status': 'active',
  'memberCount': 0,
  'createdAt': '2026-07-14T01:00:00Z',
  'updatedAt': '2026-07-14T01:00:00Z',
};

Map<String, Object?> _groupMembershipCommandResult() => <String, Object?>{
  'membershipId': 'group-membership-1',
  'version': 5,
  'role': 'member',
  'state': 'active',
  'idempotentReplay': false,
};

Map<String, Object?> _groupMembershipSlice() => <String, Object?>{
  'membershipId': 'group-membership-1',
  'version': 5,
  'groupId': 'group-1',
  'circleId': 'circle-1',
  'personaId': 'persona-2',
  'role': 'member',
  'state': 'active',
  'joinedAt': '2026-07-14T01:00:00Z',
  'leftAt': null,
  'decidedAt': '2026-07-14T01:00:00Z',
  'createdAt': '2026-07-14T00:00:00Z',
  'updatedAt': '2026-07-14T01:00:00Z',
};

final class _CircleRecordingExecutor implements CloudOperationExecutor {
  _CircleRecordingExecutor({this.response});

  final Object? response;
  CloudOperationContract? operation;
  Map<String, String> pathParameters = const <String, String>{};
  Map<String, String> queryParameters = const <String, String>{};
  Map<String, String> headers = const <String, String>{};
  Object? body;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    final payload = requestEncoder();
    pathParameters = payload.pathParameters;
    queryParameters = payload.queryParameters;
    headers = payload.headers;
    body = payload.body;
    return responseDecoder(response);
  }
}
