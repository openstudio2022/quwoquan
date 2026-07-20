import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  const context = CloudOperationInvocationContext(
    surfaceId: 'addContact',
    clientPageId: 'contact.contract',
    actor: CloudOperationActorContext(personaId: 'persona-current'),
  );

  test('GreetingRequest generated client 编解码 typed command/result', () async {
    final executor = _RecordingExecutor(
      response: _greetingRecord(status: 'pending'),
    );
    final client = GeneratedCloudOperationClient(executor);

    final result = await client.userGreetingRequestSendGreetingRequest(
      SendGreetingCommand(
        targetSubAccountId: 'persona-target',
        requestMessage: '你好',
      ),
      context: context,
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.userGreetingRequestSendGreetingRequest,
    );
    expect(executor.body, <String, Object?>{
      'targetSubAccountId': 'persona-target',
      'requestMessage': '你好',
      'source': 'profile',
    });
    expect(result.status, 'pending');
  });

  test('ContactDiscovery generated client 只上传哈希列表', () async {
    final executor = _RecordingExecutor(
      response: <String, Object?>{
        'id': 'discovery-1',
        'status': 'completed',
        'matchedSubAccountIds': <Object?>[],
        'matchCount': 0,
        'matches': <Object?>[],
      },
    );
    final client = GeneratedCloudOperationClient(executor);

    final result = await client.userContactDiscoveryInitiateContactDiscovery(
      InitiateContactDiscoveryCommand(
        hashedPhones: const <String>[
          'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        ],
      ),
      context: context,
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.userContactDiscoveryInitiateContactDiscovery,
    );
    expect(executor.body, <String, Object?>{
      'hashedPhones': const <String>[
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      ],
    });
    expect(result.matches, isEmpty);
  });

  test('RelationshipCapability generated client 保留 16 个能力位', () async {
    final executor = _RecordingExecutor(
      response: <String, Object?>{
        'viewerSubAccountId': 'persona-current',
        'targetSubAccountId': 'persona-target',
        'relationState': 'mutual',
        'canFollow': false,
        'canUnfollow': true,
        'canFollowBack': false,
        'canGreet': false,
        'canOpenConversation': true,
        'canCreateDirectConversation': true,
        'canSendMessage': true,
        'hasPendingGreeting': false,
        'hasFormalConversation': true,
        'canStartVoiceCall': true,
        'canStartVideoCall': true,
        'isBlocked': false,
        'isBlockedBy': false,
      },
    );
    final client = GeneratedCloudOperationClient(executor);

    final result = await client
        .userPersonaRelationshipGetRelationshipCapability(
          GetRelationshipCapabilityQuery(targetSubAccountId: 'persona-target'),
          context: context,
        );

    expect(executor.pathParameters, <String, String>{
      'subAccountId': 'persona-target',
    });
    expect(result.relationState, 'mutual');
    expect(result.canStartVideoCall, isTrue);
  });

  test('FollowingSubject query 与访问水位均走 generated client', () async {
    final listExecutor = _RecordingExecutor(
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
    final listClient = GeneratedCloudOperationClient(listExecutor);
    final slice = await listClient.userFollowingSubjectListFollowingSubjects(
      const ListFollowingSubjectsQuery(subjectType: 'circle'),
      context: context,
    );

    expect(slice.items.single.subjectId, 'circle-1');
    expect(listExecutor.queryParameters['subjectType'], 'circle');

    final visitExecutor = _RecordingExecutor(
      response: <String, Object?>{
        'subjectId': 'circle-1',
        'subjectType': 'circle',
        'lastVisitedAt': '2026-07-20T01:00:00Z',
        'hasUnreadChanges': false,
      },
    );
    final visitClient = GeneratedCloudOperationClient(visitExecutor);
    final visit = await visitClient
        .userFollowedSubjectVisitStateMarkFollowedSubjectVisited(
          MarkFollowedSubjectVisitedCommand(
            subjectId: 'circle-1',
            subjectType: 'circle',
            visitedAt: DateTime.utc(2026, 7, 20, 1),
          ),
          context: context,
        );
    expect(visit.hasUnreadChanges, isFalse);
    expect(visitExecutor.pathParameters['subjectId'], 'circle-1');
  });
}

Map<String, Object?> _greetingRecord({required String status}) {
  return <String, Object?>{
    'id': 'greeting-1',
    'requesterSubAccountId': 'persona-current',
    'targetSubAccountId': 'persona-target',
    'requestMessage': '你好',
    'status': status,
    'source': 'profile',
    'createdAt': '2026-07-20T00:00:00Z',
    'updatedAt': '2026-07-20T00:00:00Z',
  };
}

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({required this.response});

  final Object? response;
  CloudOperationContract? operation;
  Map<String, String> pathParameters = const <String, String>{};
  Map<String, String> queryParameters = const <String, String>{};
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
    body = payload.body;
    return responseDecoder(response);
  }
}
