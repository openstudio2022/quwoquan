// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// readiness_case: chat_inbox_view_list_inbox_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/adapters/chat_inbox_remote.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'ListInbox only delegates to its object generated typed operation',
    () async {
      final executor = _RecordingExecutor(
        response: <String, Object?>{
          'items': <Object?>[_inboxWire],
          'nextCursor': 'next-keyset-token',
        },
      );
      final query = RemoteChatInboxQuery(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      final page = await query.listInbox(
        ChatListInboxQuery(
          cursor: 'current-keyset-token',
          // canonical ChatListInboxQuery.maximumLimit == 50，取上界断言分页边界。
          limit: ChatListInboxQuery.maximumLimit,
        ),
      );

      expect(executor.callCount, 1);
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.chatChatInboxViewListInbox,
      );
      expect(executor.operation?.method, 'GET');
      expect(executor.operation?.pathTemplate, '/chat/inbox');
      expect(executor.context?.surfaceId, AppUiSurfaces.chatList.id);
      expect(executor.context?.clientPageId, ChatRequestPageIds.listInbox);
      expect(executor.queryParameters, <String, String>{
        'cursor': 'current-keyset-token',
        'limit': '50',
      });
      expect(executor.pathParameters, isEmpty);
      expect(executor.body, isNull);
      expect(page.items.single.id, 'conversation-1');
      expect(page.items.single.unreadCount, 2);
      expect(page.nextCursor, 'next-keyset-token');
    },
  );
}

CloudOperationInvocationContext _context(String clientPageId) {
  return CloudOperationInvocationContext(
    surfaceId: AppUiSurfaces.chatList.id,
    routeId: AppUiSurfaces.chatList.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-1'),
  );
}

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({required this.response});

  final Object? response;
  int callCount = 0;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
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
    callCount += 1;
    this.operation = operation;
    this.context = context;
    final payload = requestEncoder();
    pathParameters = payload.pathParameters;
    queryParameters = payload.queryParameters;
    body = payload.body;
    return responseDecoder(response);
  }
}

const Map<String, Object?> _inboxWire = <String, Object?>{
  'id': 'conversation-1',
  'type': 'direct',
  'title': '小趣',
  'avatarUrl': '',
  'groupAvatarVersion': 0,
  'lastMessagePreview': '你好',
  'lastMessageType': 'text',
  'lastMessageTime': '2026-07-21T08:00:00Z',
  'lastSeq': 9,
  'unreadCount': 2,
  'mentionUnreadCount': 0,
  'muted': false,
  'pinned': false,
  'circleId': null,
};
