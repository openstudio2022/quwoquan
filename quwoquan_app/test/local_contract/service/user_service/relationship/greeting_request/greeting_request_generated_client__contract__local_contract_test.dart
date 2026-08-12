// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/greeting-request-inbox-and-upgrade/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/greeting-intersection-context/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/greeting-intersection-context/spec.md#gwt-002
// readiness_case: greeting_request_send_greeting_request_app_local
// readiness_case: greeting_request_list_greeting_inbox_app_local
// readiness_case: greeting_request_list_greeting_outbox_app_local
// readiness_case: greeting_request_reply_greeting_request_app_local
// readiness_case: greeting_request_ignore_greeting_request_app_local
// readiness_case: greeting_request_cancel_greeting_request_app_local

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/relationship/greeting_request/adapters/greeting_request_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

void main() {
  group('RemoteGreetingRequestFacet SendGreetingRequest HTTP contract', () {
    test('有效 intersectionRef 只上传 typed 引用并消费云侧冻结摘要', () async {
      final requests = <CapturedRemoteApiPathRequest>[];
      final remote = _remote(
        requests,
        idempotencyKey: 'greeting-valid-intersection-intent',
        responseFor: (_) => remoteApiPathJsonResponse(
          _greetingRecord(
            intersectionRef: _intersectionRefWire(),
            intersectionSnapshot: _intersectionSnapshotWire(),
          ),
        ),
      );

      final result = await remote.sendGreeting(
        SendGreetingCommand(
          targetPersonaId: ' persona-target ',
          requestMessage: ' 认识一下 ',
          source: ' recommendation ',
          intersectionRef: _intersectionRef(),
        ),
      );

      expect(result.status, GreetingRequestStatus.pending);
      expect(result.intersectionRef?.intersectionId, 'intersection-1');
      expect(result.intersectionSnapshot?.primaryText, '我们都去过同一处机位');
      expect(result.intersectionSnapshot?.dimension, 'co_visited_entity');
      expect(requests, hasLength(1));
      _expectSendRequest(
        requests.single,
        idempotencyKey: 'greeting-valid-intersection-intent',
        attempt: 1,
        body: <String, Object?>{
          'targetPersonaId': 'persona-target',
          'requestMessage': '认识一下',
          'source': 'recommendation',
          'intersectionRef': _intersectionRefWire(),
        },
      );
      expect(requests.single.body.toString(), isNot(contains('primaryText')));
    });

    test('失效 intersectionRef 仍解码为无伪造摘要的普通问候', () async {
      final requests = <CapturedRemoteApiPathRequest>[];
      final remote = _remote(
        requests,
        idempotencyKey: 'greeting-stale-intersection-intent',
        responseFor: (_) => remoteApiPathJsonResponse(
          _greetingRecord(intersectionRef: _intersectionRefWire()),
        ),
      );

      final result = await remote.sendGreeting(
        SendGreetingCommand(
          targetPersonaId: 'persona-target',
          requestMessage: '你好',
          source: 'recommendation',
          intersectionRef: _intersectionRef(),
        ),
      );

      expect(result.status, GreetingRequestStatus.pending);
      expect(result.intersectionRef?.intersectionId, 'intersection-1');
      expect(result.intersectionSnapshot, isNull);
      _expectSendRequest(
        requests.single,
        idempotencyKey: 'greeting-stale-intersection-intent',
        attempt: 1,
        body: <String, Object?>{
          'targetPersonaId': 'persona-target',
          'requestMessage': '你好',
          'source': 'recommendation',
          'intersectionRef': _intersectionRefWire(),
        },
      );
    });

    test('503 自动重试复用同一 command 幂等键并返回 typed record', () async {
      final requests = <CapturedRemoteApiPathRequest>[];
      var attempts = 0;
      final remote = _remote(
        requests,
        idempotencyKey: 'greeting-retry-intent',
        responseFor: (_) {
          attempts += 1;
          if (attempts == 1) {
            return http.Response(
              jsonEncode(<String, Object?>{
                'code': UserErrorCode.internalError.code,
                'message': 'user dependency unavailable',
              }),
              503,
              headers: const <String, String>{
                'content-type': 'application/json',
                'retry-after': '0',
              },
            );
          }
          return remoteApiPathJsonResponse(_greetingRecord());
        },
      );

      final result = await remote.sendGreeting(
        SendGreetingCommand(targetPersonaId: 'persona-target'),
      );

      expect(result.id, 'greeting-1');
      expect(requests, hasLength(2));
      _expectSendRequest(
        requests[0],
        idempotencyKey: 'greeting-retry-intent',
        attempt: 1,
        body: const <String, Object?>{
          'targetPersonaId': 'persona-target',
          'source': 'profile',
        },
      );
      _expectSendRequest(
        requests[1],
        idempotencyKey: 'greeting-retry-intent',
        attempt: 2,
        body: const <String, Object?>{
          'targetPersonaId': 'persona-target',
          'source': 'profile',
        },
      );
    });

    test('canonical failure 保留 typed code 且不合成 pending record', () async {
      final requests = <CapturedRemoteApiPathRequest>[];
      final remote = _remote(
        requests,
        idempotencyKey: 'greeting-blocked-intent',
        responseFor: (_) => remoteApiPathJsonResponse(<String, Object?>{
          'code': UserErrorCode.greetingTargetBlockedSender.code,
          'message': 'recipient does not accept greetings',
          'requestId': 'request-greeting-blocked',
          'traceId': 'trace-greeting-blocked',
        }, statusCode: UserErrorCode.greetingTargetBlockedSender.httpStatus),
      );

      await expectLater(
        remote.sendGreeting(
          SendGreetingCommand(targetPersonaId: 'persona-target'),
        ),
        throwsA(
          isA<CloudException>()
              .having(
                (error) => error.code,
                'code',
                UserErrorCode.greetingTargetBlockedSender.code,
              )
              .having(
                (error) => error.statusCode,
                'statusCode',
                UserErrorCode.greetingTargetBlockedSender.httpStatus,
              )
              .having(
                (error) => error.sourceOperationId,
                'sourceOperationId',
                AppCloudOperationIds.userGreetingRequestSendGreetingRequest,
              ),
        ),
      );
      expect(requests, hasLength(1));
      _expectSendRequest(
        requests.single,
        idempotencyKey: 'greeting-blocked-intent',
        attempt: 1,
        body: const <String, Object?>{
          'targetPersonaId': 'persona-target',
          'source': 'profile',
        },
      );
    });

    test(
      'inbox/outbox 与 reply/ignore/cancel 逐项绑定 canonical Remote operation',
      () async {
        final requests = <CapturedRemoteApiPathRequest>[];
        final remote = _remote(
          requests,
          idempotencyKey: 'greeting-lifecycle-intent',
          responseFor: (request) {
            if (request.url.path.endsWith('/inbox') ||
                request.url.path.endsWith('/outbox')) {
              return remoteApiPathJsonResponse(<String, Object?>{
                'items': <Object?>[_greetingRecord()],
                'nextCursor': 'cursor-next',
              });
            }
            if (request.url.path.endsWith('/reply')) {
              return remoteApiPathJsonResponse(
                _greetingRecord(
                  status: 'replied',
                  promotedConversationId: 'conversation-1',
                  decisionAt: '2026-08-09T08:01:00Z',
                ),
              );
            }
            if (request.url.path.endsWith('/ignore')) {
              return remoteApiPathJsonResponse(
                _greetingRecord(
                  status: 'ignored',
                  decisionAt: '2026-08-09T08:01:00Z',
                ),
              );
            }
            return remoteApiPathJsonResponse(
              _greetingRecord(
                status: 'cancelled',
                decisionAt: '2026-08-09T08:01:00Z',
              ),
            );
          },
        );

        final inbox = await remote.listGreetingInbox(
          ListGreetingRequestsQuery(
            status: 'pending',
            cursor: 'cursor-inbox',
            limit: 12,
          ),
        );
        final outbox = await remote.listGreetingOutbox(
          ListGreetingRequestsQuery(status: 'pending', limit: 13),
        );
        final replied = await remote.replyGreeting(
          ReplyGreetingCommand(requestId: 'greeting-1'),
        );
        final ignored = await remote.ignoreGreeting(
          IgnoreGreetingCommand(requestId: 'greeting-1'),
        );
        final cancelled = await remote.cancelGreeting(
          CancelGreetingCommand(requestId: 'greeting-1'),
        );

        expect(inbox.items.single.id, 'greeting-1');
        expect(inbox.nextCursor, 'cursor-next');
        expect(outbox.items.single.id, 'greeting-1');
        expect(replied.status, GreetingRequestStatus.replied);
        expect(replied.promotedConversationId, 'conversation-1');
        expect(ignored.status, GreetingRequestStatus.ignored);
        expect(cancelled.status, GreetingRequestStatus.cancelled);

        expect(requests, hasLength(5));
        _expectLifecycleRequest(
          requests[0],
          operationId:
              AppCloudOperationIds.userGreetingRequestListGreetingInbox,
          clientPageId: UserRequestPageIds.listGreetingInbox,
          method: 'GET',
          path: canonicalRemoteApiPath(
            AppCloudOperationIds.userGreetingRequestListGreetingInbox,
          ),
          query: const <String, String>{
            'status': 'pending',
            'cursor': 'cursor-inbox',
            'limit': '12',
          },
          expectsIdempotencyKey: false,
        );
        _expectLifecycleRequest(
          requests[1],
          operationId:
              AppCloudOperationIds.userGreetingRequestListGreetingOutbox,
          clientPageId: UserRequestPageIds.listGreetingOutbox,
          method: 'GET',
          path: canonicalRemoteApiPath(
            AppCloudOperationIds.userGreetingRequestListGreetingOutbox,
          ),
          query: const <String, String>{'status': 'pending', 'limit': '13'},
          expectsIdempotencyKey: false,
        );
        _expectLifecycleRequest(
          requests[2],
          operationId:
              AppCloudOperationIds.userGreetingRequestReplyGreetingRequest,
          clientPageId: UserRequestPageIds.replyGreetingRequest,
          method: 'POST',
          path: canonicalRemoteApiPath(
            AppCloudOperationIds.userGreetingRequestReplyGreetingRequest,
            pathParameters: const <String, String>{'requestId': 'greeting-1'},
          ),
        );
        _expectLifecycleRequest(
          requests[3],
          operationId:
              AppCloudOperationIds.userGreetingRequestIgnoreGreetingRequest,
          clientPageId: UserRequestPageIds.ignoreGreetingRequest,
          method: 'POST',
          path: canonicalRemoteApiPath(
            AppCloudOperationIds.userGreetingRequestIgnoreGreetingRequest,
            pathParameters: const <String, String>{'requestId': 'greeting-1'},
          ),
        );
        _expectLifecycleRequest(
          requests[4],
          operationId:
              AppCloudOperationIds.userGreetingRequestCancelGreetingRequest,
          clientPageId: UserRequestPageIds.cancelGreetingRequest,
          method: 'DELETE',
          path: canonicalRemoteApiPath(
            AppCloudOperationIds.userGreetingRequestCancelGreetingRequest,
            pathParameters: const <String, String>{'requestId': 'greeting-1'},
          ),
        );
      },
    );

    test('caller-bound intent key 逐字透传到三个终态 command', () async {
      final requests = <CapturedRemoteApiPathRequest>[];
      final remote = _remote(
        requests,
        idempotencyKey: 'fallback-intent-must-not-be-used',
        responseFor: (request) {
          if (request.url.path.endsWith('/reply')) {
            return remoteApiPathJsonResponse(
              _greetingRecord(
                status: 'replied',
                promotedConversationId: 'conversation-1',
                decisionAt: '2026-08-09T08:01:00Z',
              ),
            );
          }
          if (request.url.path.endsWith('/ignore')) {
            return remoteApiPathJsonResponse(
              _greetingRecord(
                status: 'ignored',
                decisionAt: '2026-08-09T08:01:00Z',
              ),
            );
          }
          return remoteApiPathJsonResponse(
            _greetingRecord(
              status: 'cancelled',
              decisionAt: '2026-08-09T08:01:00Z',
            ),
          );
        },
      );

      await remote.replyGreetingWithIntent(
        ReplyGreetingCommand(requestId: 'greeting-1'),
        idempotencyKey: 'reply-stable-intent',
      );
      await remote.ignoreGreetingWithIntent(
        IgnoreGreetingCommand(requestId: 'greeting-1'),
        idempotencyKey: 'ignore-stable-intent',
      );
      await remote.cancelGreetingWithIntent(
        CancelGreetingCommand(requestId: 'greeting-1'),
        idempotencyKey: 'cancel-stable-intent',
      );

      expect(
        requests.map((request) => request.headers['Idempotency-Key']),
        const <String>[
          'reply-stable-intent',
          'ignore-stable-intent',
          'cancel-stable-intent',
        ],
      );
    });
  });
}

RemoteGreetingRequestFacet _remote(
  List<CapturedRemoteApiPathRequest> requests, {
  required String idempotencyKey,
  required RemoteApiPathResponseFactory responseFor,
}) {
  final fallbackIdempotencyKey = idempotencyKey;
  return RemoteGreetingRequestFacet(
    client: buildRemoteApiPathOperationClient(
      requests,
      responseFor: responseFor,
    ),
    invocationContext: (clientPageId, {String? idempotencyKey}) {
      final surface = clientPageId == UserRequestPageIds.sendGreetingRequest
          ? AppUiSurfaces.userProfile
          : AppUiSurfaces.greetingInbox;
      return CloudOperationInvocationContext(
        surfaceId: surface.id,
        routeId: surface.routeId,
        clientPageId: clientPageId,
        idempotencyKey:
            clientPageId == UserRequestPageIds.listGreetingInbox ||
                clientPageId == UserRequestPageIds.listGreetingOutbox
            ? null
            : idempotencyKey ?? fallbackIdempotencyKey,
        actor: const CloudOperationActorContext(
          accountId: 'account-1',
          personaId: 'persona-viewer',
        ),
      );
    },
  );
}

GreetingIntersectionRef _intersectionRef() => const GreetingIntersectionRef(
  intersectionId: 'intersection-1',
  evidenceId: 'evidence-1',
  sourceRef: 'coVisitedEntity',
  objectTypeRef: 'entity.homepage',
  objectId: 'homepage-1',
);

Map<String, Object?> _intersectionRefWire() => <String, Object?>{
  'intersectionId': 'intersection-1',
  'evidenceId': 'evidence-1',
  'sourceRef': 'coVisitedEntity',
  'objectTypeRef': 'entity.homepage',
  'objectId': 'homepage-1',
};

Map<String, Object?> _intersectionSnapshotWire() => <String, Object?>{
  ..._intersectionRefWire(),
  'primaryText': '我们都去过同一处机位',
  'dimension': 'co_visited_entity',
  'resolvedAt': '2026-08-09T08:00:00Z',
};

Map<String, Object?> _greetingRecord({
  Map<String, Object?>? intersectionRef,
  Map<String, Object?>? intersectionSnapshot,
  String status = 'pending',
  String? promotedConversationId,
  String? decisionAt,
}) {
  final record = <String, Object?>{
    'id': 'greeting-1',
    'requesterPersonaId': 'persona-viewer',
    'targetPersonaId': 'persona-target',
    'requestMessage': '你好',
    'status': status,
    'source': intersectionRef == null ? 'profile' : 'recommendation',
    'promotedConversationId': promotedConversationId,
    'expireAt': '2026-08-12T08:00:00Z',
    'decisionAt': decisionAt,
    'createdAt': '2026-08-09T08:00:00Z',
    'updatedAt': '2026-08-09T08:00:00Z',
  };
  if (intersectionRef != null) {
    record['intersectionRef'] = intersectionRef;
  }
  if (intersectionSnapshot != null) {
    record['intersectionSnapshot'] = intersectionSnapshot;
  }
  return record;
}

void _expectLifecycleRequest(
  CapturedRemoteApiPathRequest request, {
  required String operationId,
  required String clientPageId,
  required String method,
  required String path,
  Map<String, String> query = const <String, String>{},
  bool expectsIdempotencyKey = true,
}) {
  expect(request.method, method);
  expect(request.path, path);
  expect(request.query, query);
  expect(request.body, isEmpty);
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: clientPageId,
    surfaceId: AppUiSurfaces.greetingInbox.id,
    operationId: operationId,
  );
  expect(request.headers['Authorization'], 'Bearer integration-contract-token');
  expect(
    request.headers['Idempotency-Key'],
    expectsIdempotencyKey ? 'greeting-lifecycle-intent' : isNull,
  );
  expect(request.headers['X-Client-Persona-Id'], 'persona-viewer');
}

void _expectSendRequest(
  CapturedRemoteApiPathRequest request, {
  required String idempotencyKey,
  required int attempt,
  required Map<String, Object?> body,
}) {
  const operationId =
      AppCloudOperationIds.userGreetingRequestSendGreetingRequest;
  expect(request.method, 'POST');
  expect(request.path, canonicalRemoteApiPath(operationId));
  expect(request.query, isEmpty);
  expect(request.body, body);
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: UserRequestPageIds.sendGreetingRequest,
    surfaceId: AppUiSurfaces.userProfile.id,
    operationId: operationId,
  );
  expect(request.headers['Authorization'], 'Bearer integration-contract-token');
  expect(request.headers['Idempotency-Key'], idempotencyKey);
  expect(request.headers['X-Client-Attempt'], '$attempt');
  expect(request.headers['X-Client-Persona-Id'], 'persona-viewer');
}
