// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/conversation-list-source-switch/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/conversation-list-source-switch/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-settings/spec.md#gwt-003
// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-settings/spec.md#gwt-005
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-002
// readiness_case: conversation_list_conversation_timestamps_app_local
// readiness_case: conversation_batch_get_conversations_app_local
// readiness_case: conversation_update_group_governance_settings_app_local
// readiness_case: conversation_update_announcement_app_local
// readiness_case: conversation_dissolve_conversation_app_local
// readiness_case: conversation_get_gathering_chat_board_app_local

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/gathering_board_chat_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/observability/recording_cloud_operation_telemetry_sink.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

void main() {
  group('Conversation sync, governance and board production Remote', () {
    test('timestamp index keeps exact generated HTTP and typed data', () async {
      final harness = _Harness(
        (_) => remoteApiPathJsonResponse(<String, Object?>{
          'items': <Object?>[_timestampWire],
        }),
      );
      final remote = _query(harness);

      final index = await remote.listConversationTimestamps(
        const ChatListConversationTimestampsQuery(),
      );

      expect(index.items, hasLength(1));
      expect(index.items.single.conversationId, _conversationId);
      expect(index.items.single.unreadCount, 3);
      _expectRequest(
        harness.log.single,
        method: 'GET',
        path: '/chat/conversations/timestamps',
        operationId:
            AppCloudOperationIds.chatConversationListConversationTimestamps,
      );
      _expectTelemetry(
        harness,
        AppCloudOperationIds.chatConversationListConversationTimestamps,
        path: '/chat/conversations/timestamps',
        surfaceId: AppUiSurfaces.chatList.id,
      );
    });

    test(
      'batch query keeps member-scoped ids and typed conversations',
      () async {
        final harness = _Harness(
          (_) => remoteApiPathJsonResponse(<String, Object?>{
            'items': <Object?>[_conversationWire()],
          }),
        );
        final remote = _query(harness);

        final batch = await remote.batchGetConversations(
          ChatBatchGetConversationsQuery(
            conversationIds: const <String>[_conversationId, 'conversation-2'],
          ),
        );

        expect(batch.items.single.conversationId, _conversationId);
        expect(batch.items.single.status, 'active');
        _expectRequest(
          harness.log.single,
          method: 'POST',
          path: '/chat/conversations/batch',
          operationId:
              AppCloudOperationIds.chatConversationBatchGetConversations,
          body: const <String, Object?>{
            'ids': <Object?>[_conversationId, 'conversation-2'],
          },
        );
        _expectTelemetry(
          harness,
          AppCloudOperationIds.chatConversationBatchGetConversations,
          path: '/chat/conversations/batch',
          surfaceId: AppUiSurfaces.chatList.id,
        );
      },
    );

    test(
      'governance replay preserves intent and authoritative readback',
      () async {
        final harness = _Harness((request) {
          return switch (request.headers['X-Client-Operation-Id']) {
            AppCloudOperationIds
                .chatConversationUpdateGroupGovernanceSettings =>
              remoteApiPathJsonResponse(
                _conversationWire(nameEditableByAdminOnly: true),
              ),
            AppCloudOperationIds.chatConversationGetConversation =>
              remoteApiPathJsonResponse(
                _conversationWire(nameEditableByAdminOnly: true),
              ),
            AppCloudOperationIds.chatConversationGetGroupHome =>
              remoteApiPathJsonResponse(_groupHomeWire()),
            final operationId => throw StateError(
              'unexpected operation: $operationId',
            ),
          };
        });
        final writer = _writer(harness);
        final reader = _query(harness);
        final command = ChatUpdateGroupGovernanceSettingsCommand(
          conversationId: _conversationId,
          nameEditableByAdminOnly: true,
        );

        final first = await writer.updateGroupGovernanceSettings(
          command,
          idempotencyKey: _governanceIntent,
        );
        final replay = await writer.updateGroupGovernanceSettings(
          command,
          idempotencyKey: _governanceIntent,
        );
        final detail = await reader.getConversation(
          ChatGetConversationQuery(conversationId: _conversationId),
        );
        final home = await reader.getGroupHome(
          ChatGetGroupHomeQuery(conversationId: _conversationId),
        );

        expect(first.nameEditableByAdminOnly, isTrue);
        expect(replay.conversationId, first.conversationId);
        expect(replay.membersRosterRevision, first.membersRosterRevision);
        expect(detail.nameEditableByAdminOnly, isTrue);
        expect(home.canDissolve, isTrue);
        for (final request in harness.log.take(2)) {
          _expectRequest(
            request,
            method: 'PATCH',
            path: '/chat/conversations/$_conversationId/governance',
            operationId: AppCloudOperationIds
                .chatConversationUpdateGroupGovernanceSettings,
            idempotencyKey: _governanceIntent,
            body: const <String, Object?>{'nameEditableByAdminOnly': true},
          );
        }
        expect(
          harness.telemetry.events
              .where(
                (event) =>
                    event.canonicalOperationId ==
                    AppCloudOperationIds
                        .chatConversationUpdateGroupGovernanceSettings,
              )
              .length,
          2,
        );
      },
    );

    test(
      'announcement replay preserves intent and authoritative readback',
      () async {
        final harness = _Harness((request) {
          return switch (request.headers['X-Client-Operation-Id']) {
            AppCloudOperationIds.chatConversationUpdateAnnouncement =>
              remoteApiPathJsonResponse(
                _conversationWire(announcement: '集合时间改为九点'),
              ),
            AppCloudOperationIds.chatConversationGetConversation =>
              remoteApiPathJsonResponse(
                _conversationWire(announcement: '集合时间改为九点'),
              ),
            final operationId => throw StateError(
              'unexpected operation: $operationId',
            ),
          };
        });
        final writer = _writer(harness);
        final reader = _query(harness);
        final command = ChatUpdateAnnouncementCommand(
          conversationId: _conversationId,
          announcement: '集合时间改为九点',
        );

        final first = await writer.updateAnnouncement(
          command,
          idempotencyKey: _announcementIntent,
        );
        final replay = await writer.updateAnnouncement(
          command,
          idempotencyKey: _announcementIntent,
        );
        final detail = await reader.getConversation(
          ChatGetConversationQuery(conversationId: _conversationId),
        );

        expect(first.announcement, '集合时间改为九点');
        expect(replay.announcement, first.announcement);
        expect(replay.announcementUpdatedAt, first.announcementUpdatedAt);
        expect(detail.announcement, first.announcement);
        for (final request in harness.log.take(2)) {
          _expectRequest(
            request,
            method: 'PATCH',
            path: '/chat/conversations/$_conversationId/announcement',
            operationId:
                AppCloudOperationIds.chatConversationUpdateAnnouncement,
            idempotencyKey: _announcementIntent,
            body: const <String, Object?>{'announcement': '集合时间改为九点'},
          );
        }
      },
    );

    test(
      'dissolve replay reaches one terminal status and leaves the list',
      () async {
        final harness = _Harness((request) {
          return switch (request.headers['X-Client-Operation-Id']) {
            AppCloudOperationIds.chatConversationDissolveConversation =>
              remoteApiPathJsonResponse(const <String, Object?>{
                'status': 'dissolved',
              }),
            AppCloudOperationIds.chatConversationListConversations =>
              remoteApiPathJsonResponse(const <String, Object?>{
                'items': <Object?>[],
                'nextCursor': null,
              }),
            final operationId => throw StateError(
              'unexpected operation: $operationId',
            ),
          };
        });
        final writer = _writer(harness);
        final reader = _query(harness);
        final command = ChatDissolveConversationCommand(
          conversationId: _conversationId,
        );

        final first = await writer.dissolveConversation(
          command,
          idempotencyKey: _dissolveIntent,
        );
        final replay = await writer.dissolveConversation(
          command,
          idempotencyKey: _dissolveIntent,
        );
        final inbox = await reader.listConversations(
          const ChatListConversationsQuery(limit: 20),
        );

        expect(first.status, 'dissolved');
        expect(replay.status, first.status);
        expect(inbox.items, isEmpty);
        for (final request in harness.log.take(2)) {
          _expectRequest(
            request,
            method: 'DELETE',
            path: '/chat/conversations/$_conversationId',
            operationId:
                AppCloudOperationIds.chatConversationDissolveConversation,
            idempotencyKey: _dissolveIntent,
          );
        }
      },
    );

    test(
      'gathering board decodes owner slices without a second state source',
      () async {
        final harness = _Harness((_) => remoteApiPathJsonResponse(_boardWire));
        final remote = RemoteGatheringBoardChatReader(
          client: harness.client,
          invocationContext: _queryContext,
        );

        final board = await remote.loadChat(_conversationId);

        expect(board.access.gatheringId, 'gathering-1');
        expect(board.access.conversationId, _conversationId);
        expect(board.access.canPost, isTrue);
        expect(board.pinnedAnnouncement?.content, '集合时间已更新');
        expect(board.assets.single.mediaAssetId, 'media-1');
        _expectRequest(
          harness.log.single,
          method: 'GET',
          path: '/chat/gathering-conversations/$_conversationId/board',
          operationId:
              AppCloudOperationIds.chatConversationGetGatheringChatBoard,
        );
        _expectTelemetry(
          harness,
          AppCloudOperationIds.chatConversationGetGatheringChatBoard,
          path: '/chat/gathering-conversations/{conversationId}/board',
          surfaceId: AppUiSurfaces.gatheringBoard.id,
        );
      },
    );

    test(
      'canonical dependency failures remain typed and operation-bound',
      () async {
        final calls = <Future<Object?> Function(_Harness)>[
          (harness) => _query(harness).listConversationTimestamps(
            const ChatListConversationTimestampsQuery(),
          ),
          (harness) => _query(harness).batchGetConversations(
            ChatBatchGetConversationsQuery(
              conversationIds: const <String>[_conversationId],
            ),
          ),
          (harness) => _writer(harness).updateGroupGovernanceSettings(
            ChatUpdateGroupGovernanceSettingsCommand(
              conversationId: _conversationId,
              nameEditableByAdminOnly: true,
            ),
            idempotencyKey: _governanceIntent,
          ),
          (harness) => _writer(harness).dissolveConversation(
            ChatDissolveConversationCommand(conversationId: _conversationId),
            idempotencyKey: _dissolveIntent,
          ),
          (harness) => RemoteGatheringBoardChatReader(
            client: harness.client,
            invocationContext: _queryContext,
          ).loadChat(_conversationId),
        ];

        for (final call in calls) {
          final harness = _Harness(
            (_) => remoteApiPathJsonResponse(const <String, Object?>{
              'code': 'CHAT.SYSTEM.internal_error',
              'message': 'chat dependency unavailable',
            }, statusCode: 503),
          );
          await expectLater(
            call(harness),
            throwsA(
              isA<CloudException>()
                  .having((error) => error.statusCode, 'statusCode', 503)
                  .having(
                    (error) => error.code,
                    'code',
                    'CHAT.SYSTEM.internal_error',
                  ),
            ),
          );
          expect(harness.telemetry.events.last.succeeded, isFalse);
          expect(harness.telemetry.events.last.failureCode, isNotEmpty);
        }
      },
    );

    test(
      'generated decoders reject incomplete authoritative responses',
      () async {
        final malformedCalls = <Future<Object?> Function(_Harness)>[
          (harness) => _query(harness).listConversationTimestamps(
            const ChatListConversationTimestampsQuery(),
          ),
          (harness) => _query(harness).batchGetConversations(
            ChatBatchGetConversationsQuery(
              conversationIds: const <String>[_conversationId],
            ),
          ),
          (harness) => _writer(harness).updateGroupGovernanceSettings(
            ChatUpdateGroupGovernanceSettingsCommand(
              conversationId: _conversationId,
              nameEditableByAdminOnly: true,
            ),
            idempotencyKey: _governanceIntent,
          ),
          (harness) => _writer(harness).dissolveConversation(
            ChatDissolveConversationCommand(conversationId: _conversationId),
            idempotencyKey: _dissolveIntent,
          ),
          (harness) => RemoteGatheringBoardChatReader(
            client: harness.client,
            invocationContext: _queryContext,
          ).loadChat(_conversationId),
        ];

        for (final call in malformedCalls) {
          final harness = _Harness(
            (_) => remoteApiPathJsonResponse(const <String, Object?>{}),
          );
          await expectLater(call(harness), throwsA(isA<CloudException>()));
        }
      },
    );
  });
}

final class _Harness {
  _Harness(this.responseFor) {
    client = buildGeneratedCloudOperationClient(
      httpClient: CloudHttpClient(
        client: captureRemoteApiPathClient(log, responseFor: responseFor),
        authTokenProvider: const RemoteApiPathTestAuthTokenProvider(),
      ),
      clientContextProvider: const RemoteApiPathTestCloudClientContext(),
      telemetrySink: telemetry,
      environment: CloudRuntimeEnvironment(
        environment: CloudEnvironment.gamma,
        gatewayBaseUri: Uri.parse(remoteApiPathTestBaseUrl),
      ),
    );
  }

  final FutureOr<http.Response> Function(http.Request request) responseFor;
  final List<CapturedRemoteApiPathRequest> log =
      <CapturedRemoteApiPathRequest>[];
  final RecordingCloudOperationTelemetrySink telemetry =
      RecordingCloudOperationTelemetrySink();
  late final GeneratedCloudOperationClient client;
}

RemoteChatConversationQuery _query(_Harness harness) {
  return RemoteChatConversationQuery(
    client: harness.client,
    invocationContext: _queryContext,
  );
}

RemoteChatConversationCommandWriter _writer(_Harness harness) {
  return RemoteChatConversationCommandWriter(
    client: harness.client,
    invocationContext: _commandContext,
  );
}

CloudOperationInvocationContext _queryContext(String clientPageId) {
  final surface = switch (clientPageId) {
    ChatRequestPageIds.getConversation => AppUiSurfaces.chatManage,
    ChatRequestPageIds.getGroupHome => AppUiSurfaces.chatAnnouncement,
    ChatRequestPageIds.getGatheringChatBoard => AppUiSurfaces.gatheringBoard,
    _ => AppUiSurfaces.chatList,
  };
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-owner'),
  );
}

CloudOperationInvocationContext _commandContext(
  String clientPageId,
  String idempotencyKey,
) {
  final surface = clientPageId == ChatRequestPageIds.updateAnnouncement
      ? AppUiSurfaces.chatAnnouncement
      : AppUiSurfaces.chatManage;
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-owner'),
    idempotencyKey: idempotencyKey,
  );
}

void _expectRequest(
  CapturedRemoteApiPathRequest request, {
  required String method,
  required String path,
  required String operationId,
  Map<String, Object?> body = const <String, Object?>{},
  String? idempotencyKey,
}) {
  expect(request.method, method);
  expect(request.path, path);
  expect(request.query, isEmpty);
  expect(request.body, body);
  expect(request.headers['X-Client-Operation-Id'], operationId);
  expect(request.headers['Authorization'], 'Bearer integration-contract-token');
  if (idempotencyKey == null) {
    expect(request.headers.containsKey('Idempotency-Key'), isFalse);
  } else {
    expect(request.headers['Idempotency-Key'], idempotencyKey);
  }
}

void _expectTelemetry(
  _Harness harness,
  String operationId, {
  required String path,
  required String surfaceId,
}) {
  final event = harness.telemetry.events.single;
  expect(event.canonicalOperationId, operationId);
  expect(event.surfaceId, surfaceId);
  expect(event.method, isNotEmpty);
  expect(event.pathTemplate, path);
  expect(event.succeeded, isTrue);
  expect(event.attempt, 1);
}

Map<String, Object?> _conversationWire({
  bool nameEditableByAdminOnly = false,
  String announcement = '',
}) => <String, Object?>{
  'id': _conversationId,
  'conversationId': _conversationId,
  'type': 'group',
  'title': '契约群聊',
  'avatarUrl': 'https://cdn.example/conversation-1.png',
  'groupAvatarVersion': 1,
  'creatorId': 'persona-owner',
  'circleId': '',
  'circleGroupId': '',
  'gatheringId': '',
  'gatheringSourceVersion': 0,
  'gatheringSourceEventId': '',
  'intersectionFacts': <Object?>[],
  'accessMode': 'active',
  'postingPolicy': 'member_chat',
  'entityId': '',
  'originType': 'ad_hoc_group',
  'maxSeq': 8,
  'memberCount': 2,
  'membersRosterRevision': 3,
  'maxGroupSize': 500,
  'receiptEnabled': true,
  'announcement': announcement,
  'announcementUpdatedBy': announcement.isEmpty ? '' : 'persona-owner',
  'announcementUpdatedAt': '2026-08-09T06:00:00Z',
  'nameEditableByAdminOnly': nameEditableByAdminOnly,
  'lastMessageId': 'message-8',
  'lastMessagePreview': '最后一条消息',
  'lastMessageType': 'text',
  'lastMessageTime': '2026-08-09T06:00:00Z',
  'messageCount': 8,
  'status': 'active',
  'createdAt': '2026-08-08T06:00:00Z',
  'updatedAt': '2026-08-09T06:00:00Z',
};

Map<String, Object?> _groupHomeWire() => const <String, Object?>{
  'conversationId': _conversationId,
  'title': '契约群聊',
  'avatarUrl': 'https://cdn.example/conversation-1.png',
  'groupAvatarVersion': 1,
  'circleId': '',
  'circleGroupId': '',
  'gatheringId': '',
  'entityId': '',
  'sourceEntityTitle': '',
  'sourceCircleTitle': '',
  'memberCount': 2,
  'announcement': '',
  'capabilities': <String>['members', 'dissolve'],
  'originType': 'ad_hoc_group',
  'accessMode': 'active',
  'postingPolicy': 'member_chat',
  'canManageMembers': true,
  'canDissolve': true,
};

const Map<String, Object?> _timestampWire = <String, Object?>{
  'conversationId': _conversationId,
  'type': 'group',
  'updatedAt': '2026-08-09T06:00:00Z',
  'settingsUpdatedAt': '2026-08-09T05:59:00Z',
  'lastMessageAt': '2026-08-09T06:00:00Z',
  'lastMessageTime': '2026-08-09T06:00:00Z',
  'lastMessagePreview': '最后一条消息',
  'unreadCount': 3,
};

const Map<String, Object?> _boardWire = <String, Object?>{
  'access': <String, Object?>{
    'gatheringId': 'gathering-1',
    'conversationId': _conversationId,
    'accessMode': 'active',
    'postingPolicy': 'member_chat',
    'viewerRole': 'participant',
    'canPost': true,
  },
  'pinnedAnnouncement': <String, Object?>{
    'content': '集合时间已更新',
    'updatedBy': 'persona-owner',
    'updatedAt': '2026-08-09T06:00:00Z',
  },
  'assets': <Object?>[
    <String, Object?>{
      'messageId': 'message-asset-1',
      'seq': 9,
      'mediaAssetId': 'media-1',
      'messageType': 'image',
      'createdAt': '2026-08-09T06:01:00Z',
    },
  ],
};

const String _conversationId = 'conversation-1';
const String _governanceIntent = 'governance-intent-1';
const String _announcementIntent = 'announcement-intent-1';
const String _dissolveIntent = 'dissolve-intent-1';
