// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/profile_projection/following_subject_item_view_dto.g.dart';
import 'package:quwoquan_app/core/di/app_production_composition.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';

void main() {
  group('FollowingSubject object ports', () {
    test('FollowSubjectKind has one strict canonical wire vocabulary', () {
      expect(FollowSubjectKind.values.map((kind) => kind.wireName), <String>[
        'persona',
        'homepage',
        'circle',
        'location',
      ]);
      expect(FollowSubjectKind.fromWire('location'), FollowSubjectKind.location);
      expect(() => FollowSubjectKind.fromWire('user'), throwsFormatException);

      final generatedProjection = FollowingSubjectItemViewDto.fromMap(
        <String, dynamic>{
          'subjectId': 'location-west-sichuan',
          'subjectType': 'location',
          'displayName': '川西',
          'avatarUrl': '',
          'coverUrl': '',
          'subtitle': '',
          'targetRouteId': 'location_detail',
          'targetObjectId': 'location-west-sichuan',
          'followedAt': '2026-07-29T00:00:00Z',
          'lastVisitedAt': '',
          'latestChangedAt': '',
          'unreadChangeCount': 0,
          'hasUnreadChanges': false,
          'latestChangeReason': '',
        },
      );
      expect(generatedProjection.subjectType, FollowSubjectKind.location);
    });

    test('location uses the same kind in query, command, and response', () {
      final query =
          encodeUserFollowingSubjectListFollowingSubjectsGeneratedRequest(
            const ListFollowingSubjectsQuery(
              subjectType: FollowSubjectKind.location,
            ),
          );
      final command =
          encodeUserFollowedSubjectVisitStateMarkFollowedSubjectVisitedGeneratedRequest(
            MarkFollowedSubjectVisitedCommand(
              subjectId: 'location-west-sichuan',
              subjectType: FollowSubjectKind.location,
              visitedAt: DateTime.utc(2026, 7, 29),
            ),
          );
      final result = decodeFollowedSubjectVisitResult(<String, Object?>{
        'subjectId': 'location-west-sichuan',
        'subjectType': 'location',
        'lastVisitedAt': '2026-07-29T00:00:00Z',
        'hasUnreadChanges': false,
      });

      expect(query.queryParameters['subjectType'], 'location');
      expect(command.pathParameters, <String, String>{
        'subjectType': 'location',
        'subjectId': 'location-west-sichuan',
      });
      expect(command.body, <String, Object?>{
        'visitedAt': '2026-07-29T00:00:00.000Z',
      });
      expect(result.subjectType, FollowSubjectKind.location);
    });

    test(
      'production registry query uses generated client without idempotency',
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
        final facets = AppProductionComposition.followingSubjectFacets(
          client: GeneratedCloudOperationClient(executor),
          invocationContext: _invocationContext,
        );

        final slice = await facets.query.listFollowingSubjects(
          const ListFollowingSubjectsQuery(
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

    test(
      'production registry visit writer preserves one request id for body and header replay',
      () async {
        final executor = _RecordingExecutor(
          response: <String, Object?>{
            'subjectId': 'circle-1',
            'subjectType': 'circle',
            'lastVisitedAt': '2026-07-20T01:00:00Z',
            'hasUnreadChanges': false,
          },
        );
        final facets = AppProductionComposition.followingSubjectFacets(
          client: GeneratedCloudOperationClient(executor),
          invocationContext: _invocationContext,
        );
        final command = MarkFollowedSubjectVisitedCommand(
          subjectId: 'circle-1',
          subjectType: FollowSubjectKind.circle,
          visitedAt: DateTime.utc(2026, 7, 20, 1),
          clientRequestId: ' visit-contract-1 ',
        );
        final expectedBody = <String, Object?>{
          'visitedAt': '2026-07-20T01:00:00.000Z',
          'clientRequestId': 'visit-contract-1',
        };

        final first = await facets.visitWriter.markFollowedSubjectVisited(
          command,
        );
        final replay = await facets.visitWriter.markFollowedSubjectVisited(
          command,
        );

        expect(first.hasUnreadChanges, isFalse);
        expect(replay.hasUnreadChanges, isFalse);
        expect(
          executor.operation?.canonicalOperationId,
          AppCloudOperationIds
              .userFollowedSubjectVisitStateMarkFollowedSubjectVisited,
        );
        expect(executor.operation?.idempotency, 'required');
        expect(executor.pathParameters, <String, String>{
          'subjectType': 'circle',
          'subjectId': 'circle-1',
        });
        expect(
          executor.contexts.map((context) => context.idempotencyKey),
          <String?>['visit-contract-1', 'visit-contract-1'],
        );
        expect(executor.bodies, <Object?>[expectedBody, expectedBody]);
      },
    );

    test(
      'alpha typed facet clears unread query projection after visit',
      () async {
        final facet = AlphaFollowingSubjectFacet();
        final before = await facet.listFollowingSubjects(
          const ListFollowingSubjectsQuery(limit: 20),
        );
        final target = before.items.firstWhere((item) => item.hasUnreadChanges);
        final visitedAt = DateTime.utc(2026, 7, 20, 8);

        final result = await facet.markFollowedSubjectVisited(
          MarkFollowedSubjectVisitedCommand(
            subjectId: target.subjectId,
            subjectType: target.subjectType,
            visitedAt: visitedAt,
            clientRequestId: 'visit-contract-1',
          ),
        );
        final after = await facet.listFollowingSubjects(
          const ListFollowingSubjectsQuery(limit: 20),
        );
        final updated = after.items.firstWhere(
          (item) =>
              item.subjectId == target.subjectId &&
              item.subjectType == target.subjectType,
        );

        expect(result.hasUnreadChanges, isFalse);
        expect(updated.hasUnreadChanges, isFalse);
        expect(updated.unreadChangeCount, equals(0));
        expect(result.lastVisitedAt, visitedAt);
        expect(updated.lastVisitedAt, visitedAt);
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
  Map<String, String> pathParameters = const <String, String>{};
  Map<String, String> queryParameters = const <String, String>{};
  final List<Object?> bodies = <Object?>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    contexts.add(context);
    final payload = requestEncoder();
    pathParameters = payload.pathParameters;
    queryParameters = payload.queryParameters;
    bodies.add(payload.body);
    return responseDecoder(response);
  }
}
