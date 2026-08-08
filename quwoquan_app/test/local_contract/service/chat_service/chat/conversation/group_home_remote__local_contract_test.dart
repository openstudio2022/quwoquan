// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/group-home-chat-info-contract/spec.md#gwt-001
// readiness_case: conversation_get_group_home_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/errors/runtime_failure_fixtures.dart';

void main() {
  test(
    'GetGroupHome only reads the canonical typed GroupHome source',
    () async {
      final executor = _RecordingExecutor(response: _groupHomeWire);
      final remote = RemoteChatConversationQuery(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      final home = await remote.getGroupHome(
        ChatGetGroupHomeQuery(conversationId: 'conversation-1'),
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.chatConversationGetGroupHome,
      );
      expect(executor.operation?.method, 'GET');
      expect(
        executor.operation?.pathTemplate,
        '/chat/groups/{conversationId}/home',
      );
      expect(executor.payload?.pathParameters, <String, String>{
        'conversationId': 'conversation-1',
      });
      expect(executor.payload?.queryParameters, isEmpty);
      expect(executor.payload?.body, isNull);
      expect(home.conversationId, 'conversation-1');
      expect(home.title, '契约群聊');
      expect(home.memberCount, 2);
      expect(home.accessMode, ConversationAccessMode.active);
      expect(home.postingPolicy, ConversationPostingPolicy.memberChat);
      expect(home.capabilities, <String>['members', 'files']);
    },
  );

  test('GetGroupHome preserves the canonical not-found failure', () async {
    final remote = RemoteChatConversationQuery(
      client: GeneratedCloudOperationClient(
        _RejectingExecutor(
          CloudException(
            type: CloudErrorType.notFound,
            message: 'conversation not found',
            statusCode: 404,
            code: 'CHAT.USER.conversation_not_found',
            runtimeFailure: testRuntimeFailure(
              code: 'CHAT.USER.conversation_not_found',
              kind: RuntimeFailureKind.notFound,
            ),
          ),
        ),
      ),
      invocationContext: _context,
    );

    await expectLater(
      remote.getGroupHome(
        ChatGetGroupHomeQuery(conversationId: 'missing-conversation'),
      ),
      throwsA(
        isA<CloudException>()
            .having((error) => error.statusCode, 'statusCode', 404)
            .having(
              (error) => error.code,
              'code',
              'CHAT.USER.conversation_not_found',
            ),
      ),
    );
  });
}

CloudOperationInvocationContext _context(String clientPageId) {
  return CloudOperationInvocationContext(
    surfaceId: 'chat-group-home-contract',
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(
      accountId: 'account-1',
      personaId: 'persona-1',
    ),
  );
}

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({required this.response});

  final Object? response;
  CloudOperationContract? operation;
  CloudOperationRequestPayload? payload;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    payload = requestEncoder();
    return responseDecoder(response);
  }
}

final class _RejectingExecutor implements CloudOperationExecutor {
  const _RejectingExecutor(this.error);

  final CloudException error;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    requestEncoder();
    throw error;
  }
}

const Map<String, Object?> _groupHomeWire = <String, Object?>{
  'conversationId': 'conversation-1',
  'title': '契约群聊',
  'avatarUrl': 'https://cdn.example/conversation-1.png',
  'groupAvatarVersion': 2,
  'circleId': '',
  'circleGroupId': '',
  'gatheringId': '',
  'entityId': '',
  'sourceEntityTitle': '',
  'sourceCircleTitle': '',
  'memberCount': 2,
  'announcement': '周末集合',
  'capabilities': <String>['members', 'files'],
  'originType': 'ad_hoc_group',
  'accessMode': 'active',
  'postingPolicy': 'member_chat',
  'canManageMembers': true,
  'canDissolve': true,
};
