// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/circle_handlers.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  const handler = CircleRehearsalHandler();
  late MemoryRehearsalPersistence persistence;
  late AlphaRehearsalStore store;
  var ids = 0;
  setUp(() {
    persistence = MemoryRehearsalPersistence();
    store = AlphaRehearsalStore(
      persistence: persistence,
      idFactory: () => '${++ids}',
    );
  });
  Future<Map<String, Object?>> send(
    String op, {
    String actor = 'alice',
    Map<String, String> path = const {},
    Map<String, String> query = const {},
    Map<String, Object?> body = const {},
    AlphaRehearsalStore? using,
  }) async {
    final s = using ?? store;
    await s.ensureLoaded();
    final result = await handler.handle(
      RehearsalInvocation(
        operation: appCloudOperationContracts[op]!,
        payload: CloudOperationRequestPayload(
          pathParameters: path,
          queryParameters: query,
          body: body,
        ),
        context: CloudOperationInvocationContext(
          surfaceId: 'rehearsal',
          clientPageId: 'rehearsal',
          actor: CloudOperationActorContext(accountId: actor, personaId: actor),
        ),
        store: s,
        now: () => DateTime.utc(2026, 9, 13),
        nextId: s.nextId,
      ),
    );
    return result! as Map<String, Object?>;
  }

  Future<String> circle({String policy = 'open'}) async =>
      (await send(
            'circle.circle.CreateCircle',
            body: {'name': '本地圈', 'joinPolicy': policy},
          ))['circleId']!
          as String;
  Map<String, Object?> draft(String admission, int cap) => {
    'hostBinding': {
      'hostSubjectKind': 'persona',
      'hostSubjectId': 'alice',
      'authorityEvidenceRef': 'local',
      'authorityVersion': 1,
    },
    'creatorParticipates': true,
    'purpose': {
      'title': '活动',
      'topicRefs': <Object>[],
      'requirementRefs': <Object>[],
      'sourceObjectRefs': <Object>[],
      'costNotice': 'free',
    },
    'schedule': <String, Object?>{},
    'place': {'mode': 'physical'},
    'policySet': {
      'audiencePolicy': 'public',
      'admissionPolicy': admission,
      'capacityPolicy': {'maxParticipants': cap},
      'disclosurePolicy': {
        'timeDisclosure': 'exact',
        'placeDisclosure': 'coarse',
        'rosterDisclosure': 'count_only',
      },
      'applicationQuestions': <Object>[],
      'riskControlPolicyRef': 'local',
    },
  };

  test('circle/group/membership 分页权限与重启恢复', () async {
    final id = await circle(policy: 'approval');
    await expectLater(
      send(
        'circle.circle.UpdateCircle',
        actor: 'bob',
        path: {'circleId': id},
        body: {'name': 'x'},
      ),
      throwsA(
        isA<CloudException>().having(
          (e) => e.code,
          'code',
          'CIRCLE.USER.permission_denied',
        ),
      ),
    );
    expect(
      (await send(
        'circle.circle_membership.JoinCircle',
        actor: 'bob',
        path: {'circleId': id},
      ))['state'],
      'pending',
    );
    await send(
      'circle.circle_membership.ApproveCircleMember',
      path: {'circleId': id, 'personaId': 'bob'},
    );
    for (final name in ['一', '二', '三']) {
      await send(
        'circle.circle_group.CreateCircleGroup',
        actor: 'bob',
        path: {'circleId': id},
        body: {
          'name': name,
          'groupType': 'self_built',
          'visibility': 'private',
          'joinPolicy': 'apply_only',
          'storageEnabled': false,
          'noticeEnabled': true,
        },
      );
    }
    final first = await send(
      'circle.circle_group.ListCircleGroups',
      actor: 'bob',
      path: {'circleId': id},
      query: {'limit': '2'},
    );
    expect(first['items'], hasLength(2));
    expect(first['cursor'], isNotNull);
    expect(
      (await send(
        'circle.circle_group.ListCircleGroups',
        actor: 'bob',
        path: {'circleId': id},
        query: {'limit': '2', 'cursor': first['cursor']! as String},
      ))['items'],
      hasLength(1),
    );
    final restarted = AlphaRehearsalStore(
      persistence: persistence,
      idFactory: () => '${++ids}',
    );
    expect(
      (await send(
        'circle.circle.GetCircle',
        path: {'circleId': id},
        using: restarted,
      ))['name'],
      '本地圈',
    );
    expect(
      (await send(
        'circle.circle_membership.GetMyCircleMembership',
        actor: 'bob',
        path: {'circleId': id},
        using: restarted,
      ))['state'],
      'active',
    );
  });

  test('post placement 放置置顶精选移除真实读回', () async {
    final id = await circle();
    final placed = await send(
      'circle.circle_post_placement.PlacePostInCircle',
      path: {'circleId': id},
      body: {'postId': 'p1'},
    );
    final pid = placed['placementId']! as String;
    await send(
      'circle.circle_post_placement.PinCirclePost',
      path: {'circleId': id, 'placementId': pid},
      body: {'pinned': true},
    );
    await send(
      'circle.circle_post_placement.FeatureCirclePost',
      path: {'circleId': id, 'placementId': pid},
      body: {'featured': true},
    );
    final feed = await send(
      'circle.circle.GetCircleFeed',
      path: {'circleId': id},
      query: {'limit': '20', 'sort': 'latest'},
    );
    final item = (feed['items'] as List).single as Map;
    expect(item['pinned'], isTrue);
    expect(item['featured'], isTrue);
    await send(
      'circle.circle_post_placement.RemovePostFromCircle',
      path: {'circleId': id, 'placementId': pid},
    );
    expect(
      (await send(
        'circle.circle.GetCircleFeed',
        path: {'circleId': id},
        query: {'limit': '20', 'sort': 'latest'},
      ))['items'],
      isEmpty,
    );
  });

  test('gathering 申请容量暂停恢复完成和安全终止', () async {
    final made = await send(
      'circle.gathering.CreateGatheringDraft',
      body: draft('approval', 2),
    );
    final id = made['gatheringId']! as String;
    await send(
      'circle.gathering.PublishGathering',
      path: {'gatheringId': id},
      body: {'expectedGatheringVersion': 1},
    );
    await send(
      'circle.gathering.ApplyToGathering',
      actor: 'bob',
      path: {'gatheringId': id},
      body: {
        'expectedGatheringVersion': 2,
        'expectedParticipationVersion': 0,
        'answers': <Object>[],
      },
    );
    await send(
      'circle.gathering.ReviewGatheringApplication',
      path: {'gatheringId': id},
      body: {
        'participantPersonaId': 'bob',
        'decision': 'approve',
        'expectedGatheringVersion': 2,
        'expectedParticipationVersion': 1,
      },
    );
    await send(
      'circle.gathering.PauseGatheringAdmission',
      path: {'gatheringId': id},
      body: {
        'reasonRef': 'pause',
        'expectedGatheringVersion': 3,
        'expectedAdmissionControlVersion': 1,
      },
    );
    await expectLater(
      send(
        'circle.gathering.ApplyToGathering',
        actor: 'carol',
        path: {'gatheringId': id},
        body: {
          'expectedGatheringVersion': 4,
          'expectedParticipationVersion': 0,
          'answers': <Object>[],
        },
      ),
      throwsA(isA<CloudException>()),
    );
    await send(
      'circle.gathering.ResumeGatheringAdmission',
      path: {'gatheringId': id},
      body: {
        'expectedGatheringVersion': 4,
        'expectedAdmissionControlVersion': 2,
      },
    );
    await send(
      'circle.gathering.CompleteGathering',
      path: {'gatheringId': id},
      body: {'expectedGatheringVersion': 5},
    );
    expect(
      ((await send(
            'circle.gathering.GetPublicGathering',
            path: {'gatheringId': id},
          ))['card']
          as Map)['lifecycleStatus'],
      'completed',
    );
    final other =
        (await send(
              'circle.gathering.CreateGatheringDraft',
              body: draft('open', 3),
            ))['gatheringId']!
            as String;
    await store.commit(
      () => store.records.putIfAbsent(
        'circle.gathering_safety_authorities',
        () => {},
      )['safety'] = {'active': true},
    );
    expect(
      (await send(
        'circle.gathering.SafetyTerminateGathering',
        actor: 'safety',
        path: {'gatheringId': other},
        body: {
          'reasonRef': 'safety',
          'evidenceRefs': <Object>[],
          'expectedGatheringVersion': 1,
        },
      ))['outcomeStatus'],
      'safety_terminated',
    );
  });

  test('plan revision 分页且 watch 为可取消一次性 command 非流', () async {
    final made = await send(
      'circle.gathering.CreateGatheringDraft',
      body: draft('open', 5),
    );
    final id = made['gatheringId']! as String;
    await send(
      'circle.gathering.UpdateGathering',
      path: {'gatheringId': id},
      body: {...draft('open', 5), 'expectedGatheringVersion': 1},
    );
    final revisions = await send(
      'circle.gathering_plan.ListGatheringPlanRevisions',
      path: {'gatheringId': id},
      query: {'limit': '1'},
    );
    expect(revisions['nextCursor'], isNotNull);
    await send(
      'circle.gathering.PublishGathering',
      path: {'gatheringId': id},
      body: {'expectedGatheringVersion': 2},
    );
    final watched = await send(
      'circle.gathering.WatchGatheringAvailability',
      actor: 'bob',
      path: {'gatheringId': id},
      body: {'expectedGatheringVersion': 3, 'expectedWatchVersion': 0},
    );
    expect(watched['participationVersion'], 1);
    final inv = RehearsalInvocation(
      operation:
          appCloudOperationContracts['circle.gathering.WatchGatheringAvailability']!,
      payload: CloudOperationRequestPayload(
        pathParameters: {'gatheringId': id},
      ),
      context: const CloudOperationInvocationContext(
        surfaceId: 'r',
        clientPageId: 'r',
        actor: CloudOperationActorContext(personaId: 'bob'),
      ),
      store: store,
      now: DateTime.now,
      nextId: store.nextId,
    );
    expect(handler.stream(inv), isNull);
  });
}
