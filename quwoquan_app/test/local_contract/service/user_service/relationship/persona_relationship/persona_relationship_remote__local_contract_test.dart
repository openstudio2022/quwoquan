// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
// readiness_case: persona_relationship_block_user_app_local
// readiness_case: persona_relationship_get_relationship_capability_app_local
// readiness_case: persona_relationship_list_blocked_users_app_local
// readiness_case: persona_relationship_unblock_user_app_local

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/adapters/persona_relationship_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('RemotePersonaRelationshipFacet generated HTTP contract', () {
    test(
      'block/list/capability/unblock keep exact wire and stable command intents',
      () async {
        final captured = <http.Request>[];
        var blockResponses = 0;
        var unblockResponses = 0;
        var generatedKeys = 0;
        final facet = RemotePersonaRelationshipFacet(
          client: _client((request) {
            captured.add(request);
            final operationId = request.headers['X-Client-Operation-Id'];
            return switch (operationId) {
              AppCloudOperationIds.userPersonaRelationshipBlockUser =>
                _blockResult(
                  targetPersonaId: ++blockResponses == 1
                      ? 'persona-mismatch'
                      : 'persona-target',
                  blocked: true,
                  replay: blockResponses > 1,
                ),
              AppCloudOperationIds.userPersonaRelationshipListBlockedUsers =>
                _blockedPage(),
              AppCloudOperationIds
                  .userPersonaRelationshipGetRelationshipCapability =>
                _capability(),
              AppCloudOperationIds.userPersonaRelationshipUnblockUser =>
                _blockResult(
                  targetPersonaId: 'persona-target',
                  blocked: ++unblockResponses == 1,
                  replay: unblockResponses > 1,
                ),
              _ => throw StateError('unexpected operation: $operationId'),
            };
          }),
          invocationContext: _context,
          idempotencyKeyFactory: () {
            generatedKeys += 1;
            return generatedKeys == 1
                ? 'block-intent-contract'
                : 'unblock-intent-contract';
          },
        );

        final blockCommand = BlockUserCommand(
          targetPersonaId: ' persona-target ',
        );
        await expectLater(facet.blockUser(blockCommand), _invalidResponse());
        final blocked = await facet.blockUser(blockCommand);
        final page = await facet.listBlockedUsers(
          ListBlockedUsersQuery(cursor: 'cursor-1', limit: 2),
        );
        final capability = await facet.getRelationshipCapability(
          GetRelationshipCapabilityQuery(targetPersonaId: ' persona-target '),
        );
        final unblockCommand = UnblockUserCommand(
          targetPersonaId: ' persona-target ',
        );
        await expectLater(
          facet.unblockUser(unblockCommand),
          _invalidResponse(),
        );
        final unblocked = await facet.unblockUser(unblockCommand);

        expect(blocked.targetPersonaId, 'persona-target');
        expect(blocked.blocked, isTrue);
        expect(blocked.idempotentReplay, isTrue);
        expect(page.items.single.targetPersonaId, 'persona-target');
        expect(page.items.single.displayName, 'Target Persona');
        expect(page.nextCursor, 'cursor-2');
        expect(capability.viewerPersonaId, 'persona-viewer');
        expect(capability.targetPersonaId, 'persona-target');
        expect(capability.isBlocked, isTrue);
        expect(unblocked.targetPersonaId, 'persona-target');
        expect(unblocked.blocked, isFalse);
        expect(unblocked.idempotentReplay, isTrue);
        expect(generatedKeys, 2);

        _expectCommand(
          captured[0],
          method: 'POST',
          operationId: AppCloudOperationIds.userPersonaRelationshipBlockUser,
          idempotencyKey: 'block-intent-contract',
        );
        _expectCommand(
          captured[1],
          method: 'POST',
          operationId: AppCloudOperationIds.userPersonaRelationshipBlockUser,
          idempotencyKey: 'block-intent-contract',
        );
        _expectQuery(
          captured[2],
          path: '/user/blocked',
          operationId:
              AppCloudOperationIds.userPersonaRelationshipListBlockedUsers,
          query: const <String, String>{'cursor': 'cursor-1', 'limit': '2'},
        );
        _expectQuery(
          captured[3],
          path: '/user/personas/persona-target/relationship/capability',
          operationId: AppCloudOperationIds
              .userPersonaRelationshipGetRelationshipCapability,
        );
        _expectCommand(
          captured[4],
          method: 'DELETE',
          operationId: AppCloudOperationIds.userPersonaRelationshipUnblockUser,
          idempotencyKey: 'unblock-intent-contract',
        );
        _expectCommand(
          captured[5],
          method: 'DELETE',
          operationId: AppCloudOperationIds.userPersonaRelationshipUnblockUser,
          idempotencyKey: 'unblock-intent-contract',
        );
      },
    );

    test(
      'blank command metadata and missing persona fail before transport',
      () async {
        final captured = <http.Request>[];
        final explicitFacet = RemotePersonaRelationshipFacet(
          client: _client((request) {
            captured.add(request);
            return _blockResult(
              targetPersonaId: 'persona-target',
              blocked: true,
            );
          }),
          invocationContext: _context,
        );

        expect(
          () => BlockUserCommand(targetPersonaId: '  '),
          throwsArgumentError,
        );
        await expectLater(
          explicitFacet.blockUserWithIntent(
            BlockUserCommand(targetPersonaId: 'persona-target'),
            idempotencyKey: '  ',
          ),
          _invalidResponse(),
        );

        final missingActorFacet = RemotePersonaRelationshipFacet(
          client: _client((request) {
            captured.add(request);
            return _blockResult(
              targetPersonaId: 'persona-target',
              blocked: true,
            );
          }),
          invocationContext: (clientPageId) => CloudOperationInvocationContext(
            surfaceId: 'blockedUsers',
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(accountId: 'account-1'),
          ),
        );
        await expectLater(
          missingActorFacet.blockUser(
            BlockUserCommand(targetPersonaId: 'persona-target'),
          ),
          _invalidResponse(),
        );
        expect(captured, isEmpty);
      },
    );

    test('blank or mismatched typed projections fail closed', () async {
      final captured = <http.Request>[];
      final facet = RemotePersonaRelationshipFacet(
        client: _client((request) {
          captured.add(request);
          return switch (request.headers['X-Client-Operation-Id']) {
            AppCloudOperationIds.userPersonaRelationshipListBlockedUsers =>
              <String, Object?>{
                'items': <Object?>[
                  <String, Object?>{
                    'targetPersonaId': '',
                    'displayName': 'Target Persona',
                    'userHandle': 'target',
                    'avatarUrl': null,
                    'blockedAt': '2026-08-08T08:00:00Z',
                  },
                ],
                'nextCursor': null,
              },
            AppCloudOperationIds
                .userPersonaRelationshipGetRelationshipCapability =>
              _capability(targetPersonaId: 'persona-mismatch'),
            _ => throw StateError('unexpected operation'),
          };
        }),
        invocationContext: _context,
      );

      await expectLater(
        facet.listBlockedUsers(ListBlockedUsersQuery()),
        _invalidResponse(),
      );
      await expectLater(
        facet.getRelationshipCapability(
          GetRelationshipCapabilityQuery(targetPersonaId: 'persona-target'),
        ),
        _invalidResponse(),
      );
      expect(captured, hasLength(2));
    });

    test(
      'canonical transport failure propagates without an empty fallback',
      () async {
        final facet = RemotePersonaRelationshipFacet(
          client: _client((_) => const <String, Object?>{}, statusCode: 503),
          invocationContext: _context,
        );

        await expectLater(
          facet.listBlockedUsers(ListBlockedUsersQuery()),
          throwsA(
            isA<CloudException>().having(
              (error) => error.statusCode,
              'statusCode',
              503,
            ),
          ),
        );
      },
    );
  });
}

Matcher _invalidResponse() => throwsA(
  isA<CloudException>().having(
    (error) => error.type,
    'type',
    CloudErrorType.invalidResponse,
  ),
);

void _expectCommand(
  http.Request request, {
  required String method,
  required String operationId,
  required String idempotencyKey,
}) {
  expect(request.method, method);
  expect(request.url.path, '/user/personas/persona-target/block');
  expect(request.url.queryParameters, isEmpty);
  expect(request.headers['X-Client-Operation-Id'], operationId);
  expect(
    request.headers['authorization'],
    'Bearer relationship-contract-token',
  );
  expect(request.headers['Idempotency-Key'], idempotencyKey);
  expect(request.body, isEmpty);
}

void _expectQuery(
  http.Request request, {
  required String path,
  required String operationId,
  Map<String, String> query = const <String, String>{},
}) {
  expect(request.method, 'GET');
  expect(request.url.path, path);
  expect(request.url.queryParameters, query);
  expect(request.headers['X-Client-Operation-Id'], operationId);
  expect(
    request.headers['authorization'],
    'Bearer relationship-contract-token',
  );
  expect(request.headers.containsKey('Idempotency-Key'), isFalse);
  expect(request.body, isEmpty);
}

Map<String, Object?> _blockResult({
  required String targetPersonaId,
  required bool blocked,
  bool replay = false,
}) => <String, Object?>{
  'targetPersonaId': targetPersonaId,
  'blocked': blocked,
  'idempotentReplay': replay,
  'updatedAt': '2026-08-08T08:00:00Z',
};

Map<String, Object?> _blockedPage() => <String, Object?>{
  'items': <Object?>[
    <String, Object?>{
      'targetPersonaId': 'persona-target',
      'displayName': 'Target Persona',
      'userHandle': 'target',
      'avatarUrl': 'https://cdn.example.com/avatar.jpg',
      'blockedAt': '2026-08-08T08:00:00Z',
    },
  ],
  'nextCursor': 'cursor-2',
};

Map<String, Object?> _capability({String targetPersonaId = 'persona-target'}) =>
    <String, Object?>{
      'viewerPersonaId': 'persona-viewer',
      'targetPersonaId': targetPersonaId,
      'relationState': 'not_following',
      'canFollow': false,
      'canUnfollow': false,
      'canFollowBack': false,
      'canGreet': false,
      'canOpenConversation': false,
      'canCreateDirectConversation': false,
      'canSendMessage': false,
      'hasPendingGreeting': false,
      'hasFormalConversation': false,
      'canStartVoiceCall': false,
      'canStartVideoCall': false,
      'isBlocked': true,
      'isBlockedBy': false,
    };

GeneratedCloudOperationClient _client(
  Map<String, Object?> Function(http.Request request) responseFor, {
  int statusCode = 200,
}) {
  return buildGeneratedCloudOperationClient(
    httpClient: CloudHttpClient(
      client: MockClient((request) async {
        return http.Response(
          jsonEncode(responseFor(request)),
          statusCode,
          headers: const <String, String>{'content-type': 'application/json'},
        );
      }),
      authTokenProvider: const _RelationshipTokenProvider(),
    ),
    clientContextProvider: const _RelationshipClientContext(),
    telemetrySink: const _NoopTelemetrySink(),
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.alpha,
      gatewayBaseUri: Uri.parse('https://test-gateway.example.com'),
    ),
  );
}

CloudOperationInvocationContext _context(String clientPageId) {
  final capability =
      clientPageId == UserRequestPageIds.getRelationshipCapability;
  final command =
      clientPageId == UserRequestPageIds.blockUser ||
      clientPageId == UserRequestPageIds.unblockUser;
  return CloudOperationInvocationContext(
    surfaceId: capability ? 'addContactConfirm' : 'blockedUsers',
    routeId: capability ? 'addContactConfirm' : 'blockedUsers',
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(
      accountId: 'account-1',
      personaId: 'persona-viewer',
    ),
    idempotencyKey: command ? 'transient-factory-key' : null,
  );
}

final class _RelationshipClientContext implements CloudClientContextProvider {
  const _RelationshipClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'relationship-contract-session',
      deviceActorId: 'relationship-contract-device',
      platform: 'test',
      appVersion: 'test',
      locale: 'zh-CN',
    );
  }
}

final class _NoopTelemetrySink implements CloudOperationTelemetrySink {
  const _NoopTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}

final class _RelationshipTokenProvider implements CloudAuthTokenProvider {
  const _RelationshipTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'relationship-contract-token';
}
