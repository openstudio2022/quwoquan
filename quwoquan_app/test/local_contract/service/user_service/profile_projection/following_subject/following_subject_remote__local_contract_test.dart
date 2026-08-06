// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
// readiness_case: following_subject_list_following_subjects_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/user_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('FollowingSubject reader', () {
    test('FollowSubjectKind has one strict canonical wire vocabulary', () {
      expect(FollowSubjectKind.values.map((kind) => kind.wireName), <String>[
        'persona',
        'homepage',
        'circle',
        'location',
      ]);
      expect(
        FollowSubjectKind.fromWire('location', 'FollowSubjectKind'),
        FollowSubjectKind.location,
      );
      expect(
        () => FollowSubjectKind.fromWire('user', 'FollowSubjectKind'),
        throwsFormatException,
      );

      final generatedProjection = FollowingSubjectItemView(
        subjectId: 'location-west-sichuan',
        subjectType: FollowSubjectKind.location,
        displayName: '川西',
        targetRouteId: 'location_detail',
        targetObjectId: 'location-west-sichuan',
        followedAt: DateTime.utc(2026, 7, 29),
        unreadChangeCount: 0,
        hasUnreadChanges: false,
      );
      expect(generatedProjection.subjectType, FollowSubjectKind.location);
    });

    test('location query uses the canonical subject kind', () {
      final query =
          encodeUserFollowingSubjectListFollowingSubjectsGeneratedRequest(
            ListFollowingSubjectsQuery(
              subjectType: FollowSubjectKind.location,
            ),
          );

      expect(query.queryParameters['subjectType'], 'location');
    });

    test(
      'production composition uses generated client without idempotency',
      () async {
        final executor = _RecordingExecutor(
          response: <String, Object?>{
            'items': <Object?>[
              <String, Object?>{
                'subjectId': 'circle-1',
                'subjectType': 'circle',
                'displayName': '摄影圈',
                'targetRouteId': 'circle_detail',
                'targetObjectId': 'circle-1',
                'followedAt': '2026-07-20T00:00:00Z',
                'unreadChangeCount': 2,
                'hasUnreadChanges': true,
              },
            ],
          },
        );
        final reader = UserProductionComposition.followingSubjectReader(
          client: GeneratedCloudOperationClient(executor),
          invocationContext: _invocationContext,
        );

        final slice = await reader.listFollowingSubjects(
          ListFollowingSubjectsQuery(
            subjectType: FollowSubjectKind.circle,
          ),
        );

        expect(slice.items.single.subjectId, 'circle-1');
        expect(
          executor.operation?.canonicalOperationId,
          AppCloudOperationIds.userFollowingSubjectListFollowingSubjects,
        );
        expect(executor.queryParameters, <String, String>{
          'limit': '20',
          'subjectType': 'circle',
        });
        expect(executor.contexts.single.idempotencyKey, isNull);
      },
    );
  });
}

CloudOperationInvocationContext _invocationContext(
  String clientPageId, {
  String? idempotencyKey,
}) {
  return CloudOperationInvocationContext(
    surfaceId: 'home_feed',
    routeId: '/home',
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-current'),
    idempotencyKey: idempotencyKey,
  );
}

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({required this.response});

  final Object? response;
  CloudOperationContract? operation;
  final List<CloudOperationInvocationContext> contexts =
      <CloudOperationInvocationContext>[];
  Map<String, String> queryParameters = const <String, String>{};

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    contexts.add(context);
    queryParameters = requestEncoder().queryParameters;
    return responseDecoder(response);
  }
}
