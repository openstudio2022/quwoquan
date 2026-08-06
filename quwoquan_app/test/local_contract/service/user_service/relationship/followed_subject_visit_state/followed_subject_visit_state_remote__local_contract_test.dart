// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
// readiness_case: followed_subject_visit_state_mark_followed_subject_visited_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/user_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/user_service/profile_projection/following_subject/following_subject_typed_double.dart';

void main() {
  group('FollowedSubjectVisitState writer', () {
    test('location command and result use the canonical subject kind', () {
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
      'production composition preserves one request id for body and header replay',
      () async {
        final executor = _RecordingExecutor(
          response: <String, Object?>{
            'subjectId': 'circle-1',
            'subjectType': 'circle',
            'lastVisitedAt': '2026-07-20T01:00:00Z',
            'hasUnreadChanges': false,
          },
        );
        final writer =
            UserProductionComposition.followedSubjectVisitStateWriter(
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

        final first = await writer.markFollowedSubjectVisited(command);
        final replay = await writer.markFollowedSubjectVisited(command);

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

    test('typed ports clear unread query projection after visit', () async {
      final facet = InMemoryFollowingSubjectFacet();
      final before = await facet.listFollowingSubjects(
        ListFollowingSubjectsQuery(limit: 20),
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
        ListFollowingSubjectsQuery(limit: 20),
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
    });
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
    bodies.add(payload.body);
    return responseDecoder(response);
  }
}
