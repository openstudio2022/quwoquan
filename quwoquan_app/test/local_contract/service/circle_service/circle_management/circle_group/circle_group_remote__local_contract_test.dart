// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-011
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-012
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-003
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-004
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-005
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-006
// readiness_case: circle_group_archive_circle_group_app_local
// readiness_case: circle_group_create_circle_group_app_local
// readiness_case: circle_group_get_circle_group_app_local
// readiness_case: circle_group_list_circle_groups_app_local
// readiness_case: circle_group_search_circle_groups_app_local
// readiness_case: circle_group_update_circle_group_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/di/circle_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group/application/public/circle_group_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

typedef _CircleGroupFacets = ({
  CircleGroupCommands commands,
  CircleGroupQueries queries,
});

typedef _OperationCall = ({
  String operationId,
  bool command,
  Future<Object?> Function(_CircleGroupFacets facets) invoke,
});

void main() {
  group('circle.circle_group production Remote generated contract', () {
    test('queries preserve exact wire and stable typed pagination', () async {
      final log = <CapturedRemoteApiPathRequest>[];
      final facets = _facets(log, responseFor: _querySuccessResponse);

      final listFirst = await facets.queries.list(
        CircleGroupListQuery(
          circleId: 'circle-1',
          groupType: CircleGroupType.orgNode,
          visibility: CircleGroupVisibility.private,
          parentGroupId: 'parent-1',
          nodeType: OrganizationNodeType.department,
          limit: 2,
        ),
      );
      final listSecond = await facets.queries.list(
        CircleGroupListQuery(
          circleId: 'circle-1',
          groupType: CircleGroupType.orgNode,
          visibility: CircleGroupVisibility.private,
          parentGroupId: 'parent-1',
          nodeType: OrganizationNodeType.department,
          cursor: listFirst.cursor,
          limit: 2,
        ),
      );
      final searchFirst = await facets.queries.search(
        CircleGroupSearchQuery(
          circleId: 'circle-1',
          query: '摄影',
          visibility: CircleGroupVisibility.public,
          groupType: CircleGroupType.selfBuilt,
          limit: 3,
        ),
      );
      final searchSecond = await facets.queries.search(
        CircleGroupSearchQuery(
          circleId: 'circle-1',
          query: '摄影',
          visibility: CircleGroupVisibility.public,
          groupType: CircleGroupType.selfBuilt,
          cursor: searchFirst.cursor,
          limit: 3,
        ),
      );
      final group = await facets.queries.get(
        CircleGroupQuery(circleId: 'circle-1', groupId: 'group-owner'),
      );

      _expectQuery(
        log[0],
        operationId: AppCloudOperationIds.circleCircleGroupListCircleGroups,
        clientPageId: CircleRequestPageIds.listCircleGroups,
        pathParameters: const <String, String>{'circleId': 'circle-1'},
        query: const <String, String>{
          'groupType': 'org_node',
          'visibility': 'private',
          'parentGroupId': 'parent-1',
          'nodeType': 'department',
          'limit': '2',
        },
      );
      _expectQuery(
        log[1],
        operationId: AppCloudOperationIds.circleCircleGroupListCircleGroups,
        clientPageId: CircleRequestPageIds.listCircleGroups,
        pathParameters: const <String, String>{'circleId': 'circle-1'},
        query: const <String, String>{
          'groupType': 'org_node',
          'visibility': 'private',
          'parentGroupId': 'parent-1',
          'nodeType': 'department',
          'cursor': 'list-next',
          'limit': '2',
        },
      );
      _expectQuery(
        log[2],
        operationId: AppCloudOperationIds.circleCircleGroupSearchCircleGroups,
        clientPageId: CircleRequestPageIds.searchCircleGroups,
        pathParameters: const <String, String>{'circleId': 'circle-1'},
        query: const <String, String>{
          'query': '摄影',
          'visibility': 'public',
          'groupType': 'self_built',
          'limit': '3',
        },
      );
      _expectQuery(
        log[3],
        operationId: AppCloudOperationIds.circleCircleGroupSearchCircleGroups,
        clientPageId: CircleRequestPageIds.searchCircleGroups,
        pathParameters: const <String, String>{'circleId': 'circle-1'},
        query: const <String, String>{
          'query': '摄影',
          'visibility': 'public',
          'groupType': 'self_built',
          'cursor': 'search-next',
          'limit': '3',
        },
      );
      _expectQuery(
        log[4],
        operationId: AppCloudOperationIds.circleCircleGroupGetCircleGroup,
        clientPageId: CircleRequestPageIds.getCircleGroup,
        pathParameters: const <String, String>{
          'circleId': 'circle-1',
          'groupId': 'group-owner',
        },
      );

      expect(listFirst.items.single.groupId, 'group-list-1');
      expect(listFirst.cursor, 'list-next');
      expect(listSecond.items.single.groupId, 'group-list-2');
      expect(listSecond.cursor, isNull);
      expect(<String>{
        ...listFirst.items.map((item) => item.groupId),
        ...listSecond.items.map((item) => item.groupId),
      }, hasLength(2));
      expect(searchFirst.items.single.groupId, 'group-search-1');
      expect(searchSecond.items.single.groupId, 'group-search-2');
      expect(searchSecond.cursor, isNull);
      expect(group.groupId, 'group-owner');
      expect(group.version, 7);
      expect(group.circleId, 'circle-1');
      expect(group.conversationId, 'conversation-owner');
      expect(group.status, CircleGroupStatus.active);
    });

    test('commands preserve exact wire and same-intent replay', () async {
      final log = <CapturedRemoteApiPathRequest>[];
      final responseCounts = <String, int>{};
      var ownerVersion = 7;
      var ownerStatus = 'active';
      final facets = _facets(
        log,
        responseFor: (request) {
          final operationId = request.headers['X-Client-Operation-Id']!;
          if (operationId ==
              AppCloudOperationIds.circleCircleGroupGetCircleGroup) {
            final groupId = request.url.pathSegments.last;
            return remoteApiPathJsonResponse(
              _groupSlice(
                groupId: groupId,
                version: groupId == 'group-created' ? 1 : ownerVersion,
                status: groupId == 'group-created' ? 'active' : ownerStatus,
                conversationId: groupId == 'group-owner'
                    ? 'conversation-owner'
                    : null,
              ),
            );
          }
          final count = (responseCounts[operationId] ?? 0) + 1;
          responseCounts[operationId] = count;
          if (count == 1 &&
              operationId ==
                  AppCloudOperationIds.circleCircleGroupUpdateCircleGroup) {
            ownerVersion = 8;
          }
          if (count == 1 &&
              operationId ==
                  AppCloudOperationIds.circleCircleGroupArchiveCircleGroup) {
            ownerVersion = 9;
            ownerStatus = 'archived';
          }
          return remoteApiPathJsonResponse(
            _commandResult(operationId, idempotentReplay: count.isEven),
          );
        },
      );
      final create = CreateCircleGroupCommand(
        circleId: 'circle-1',
        parentGroupId: 'parent-1',
        groupType: CircleGroupType.orgNode,
        nodeType: OrganizationNodeType.department,
        name: '摄影组织群',
        description: '权威 CircleGroup',
        visibility: CircleGroupVisibility.private,
        joinPolicy: CircleGroupJoinPolicy.inviteOnly,
        storageEnabled: true,
        noticeEnabled: false,
      );
      final update = UpdateCircleGroupCommand(
        circleId: 'circle-1',
        groupId: 'group-owner',
        expectedVersion: 7,
        parentGroupId: 'parent-2',
        nodeType: OrganizationNodeType.team,
        name: '摄影组织群二期',
        description: '权威更新',
        visibility: CircleGroupVisibility.public,
        joinPolicy: CircleGroupJoinPolicy.applyOnly,
        storageEnabled: false,
        noticeEnabled: true,
      );
      final archive = ArchiveCircleGroupCommand(
        circleId: 'circle-1',
        groupId: 'group-owner',
      );

      final created = await facets.commands.create(create);
      final createdReplay = await facets.commands.create(create);
      final createdReadback = await facets.queries.get(
        CircleGroupQuery(circleId: 'circle-1', groupId: 'group-created'),
      );
      final updated = await facets.commands.update(update);
      final updatedReplay = await facets.commands.update(update);
      final updatedReadback = await facets.queries.get(
        CircleGroupQuery(circleId: 'circle-1', groupId: 'group-owner'),
      );
      final archived = await facets.commands.archive(archive);
      final archivedReplay = await facets.commands.archive(archive);
      final archivedReadback = await facets.queries.get(
        CircleGroupQuery(circleId: 'circle-1', groupId: 'group-owner'),
      );

      final createRequests = _requestsFor(
        log,
        AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
      );
      final updateRequests = _requestsFor(
        log,
        AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
      );
      final archiveRequests = _requestsFor(
        log,
        AppCloudOperationIds.circleCircleGroupArchiveCircleGroup,
      );
      final readbackRequests = _requestsFor(
        log,
        AppCloudOperationIds.circleCircleGroupGetCircleGroup,
      );
      for (final request in createRequests) {
        _expectCommand(
          request,
          operationId: AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
          clientPageId: CircleRequestPageIds.createCircleGroup,
          method: 'POST',
          pathParameters: const <String, String>{'circleId': 'circle-1'},
          body: const <String, Object?>{
            'parentGroupId': 'parent-1',
            'groupType': 'org_node',
            'nodeType': 'department',
            'name': '摄影组织群',
            'description': '权威 CircleGroup',
            'visibility': 'private',
            'joinPolicy': 'invite_only',
            'storageEnabled': true,
            'noticeEnabled': false,
          },
        );
      }
      for (final request in updateRequests) {
        _expectCommand(
          request,
          operationId: AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
          clientPageId: CircleRequestPageIds.updateCircleGroup,
          method: 'PATCH',
          pathParameters: const <String, String>{
            'circleId': 'circle-1',
            'groupId': 'group-owner',
          },
          extraHeaders: const <String, String>{'If-Match': '"7"'},
          body: const <String, Object?>{
            'parentGroupId': 'parent-2',
            'nodeType': 'team',
            'name': '摄影组织群二期',
            'description': '权威更新',
            'visibility': 'public',
            'joinPolicy': 'apply_only',
            'storageEnabled': false,
            'noticeEnabled': true,
          },
        );
      }
      for (final request in archiveRequests) {
        _expectCommand(
          request,
          operationId: AppCloudOperationIds.circleCircleGroupArchiveCircleGroup,
          clientPageId: CircleRequestPageIds.archiveCircleGroup,
          method: 'DELETE',
          pathParameters: const <String, String>{
            'circleId': 'circle-1',
            'groupId': 'group-owner',
          },
        );
      }
      for (final request in readbackRequests) {
        _expectQuery(
          request,
          operationId: AppCloudOperationIds.circleCircleGroupGetCircleGroup,
          clientPageId: CircleRequestPageIds.getCircleGroup,
          pathParameters: <String, String>{
            'circleId': 'circle-1',
            'groupId': request.path.endsWith('/group-created')
                ? 'group-created'
                : 'group-owner',
          },
        );
      }

      expect(createRequests, hasLength(2));
      expect(updateRequests, hasLength(2));
      expect(archiveRequests, hasLength(2));
      expect(readbackRequests, hasLength(3));
      expect(created.groupId, 'group-created');
      expect(created.idempotentReplay, isFalse);
      expect(createdReplay.groupId, created.groupId);
      expect(createdReplay.version, created.version);
      expect(createdReplay.idempotentReplay, isTrue);
      expect(createdReadback.groupId, created.groupId);
      expect(createdReadback.version, created.version);
      expect(createdReadback.status, created.status);
      expect(updated.groupId, 'group-owner');
      expect(updated.version, 8);
      expect(updatedReplay.version, updated.version);
      expect(updatedReplay.idempotentReplay, isTrue);
      expect(updatedReadback.groupId, updated.groupId);
      expect(updatedReadback.version, updated.version);
      expect(updatedReadback.status, updated.status);
      expect(archived.status, CircleGroupStatus.archived);
      expect(archived.version, 9);
      expect(archivedReplay.version, archived.version);
      expect(archivedReplay.idempotentReplay, isTrue);
      expect(archivedReadback.groupId, archived.groupId);
      expect(archivedReadback.version, archived.version);
      expect(archivedReadback.status, archived.status);
    });

    test('BOLA failures remain canonical and operation-bound', () async {
      final log = <CapturedRemoteApiPathRequest>[];
      final facets = _facets(
        log,
        responseFor: (request) {
          final operationId = request.headers['X-Client-Operation-Id']!;
          final command = _commandOperationIds.contains(operationId);
          return remoteApiPathJsonResponse(<String, Object?>{
            'code': command
                ? 'CIRCLE.USER.permission_denied'
                : 'CIRCLE.USER.not_member',
            'message': 'canonical circle group authorization failure',
          }, statusCode: 403);
        },
      );

      for (final call in _operationCalls) {
        await expectLater(
          call.invoke(facets),
          throwsA(
            isA<CloudException>()
                .having(
                  (error) => error.code,
                  'code',
                  call.command
                      ? 'CIRCLE.USER.permission_denied'
                      : 'CIRCLE.USER.not_member',
                )
                .having(
                  (error) => error.sourceOperationId,
                  'sourceOperationId',
                  call.operationId,
                ),
          ),
        );
      }
      for (final call in _operationCalls) {
        expect(_requestsFor(log, call.operationId), hasLength(1));
      }
    });

    test('transient command failures retry the same intent only', () async {
      final log = <CapturedRemoteApiPathRequest>[];
      final facets = _facets(
        log,
        responseFor: (_) => remoteApiPathJsonResponse(const <String, Object?>{
          'code': 'CIRCLE.SYSTEM.group_storage_write_failed',
          'message': 'circle group storage unavailable',
        }, statusCode: 503),
      );

      for (final call in _operationCalls.where((call) => call.command)) {
        await expectLater(
          call.invoke(facets),
          throwsA(
            isA<CloudException>()
                .having(
                  (error) => error.code,
                  'code',
                  'CIRCLE.SYSTEM.group_storage_write_failed',
                )
                .having(
                  (error) => error.sourceOperationId,
                  'sourceOperationId',
                  call.operationId,
                ),
          ),
        );
        final attempts = _requestsFor(log, call.operationId);
        expect(attempts, hasLength(2));
        expect(attempts[0].headers['Idempotency-Key'], isNotEmpty);
        expect(
          attempts[1].headers['Idempotency-Key'],
          attempts[0].headers['Idempotency-Key'],
        );
      }
    });

    test(
      'malformed successful responses fail closed for every shape',
      () async {
        final log = <CapturedRemoteApiPathRequest>[];
        final facets = _facets(
          log,
          responseFor: (request) {
            final operationId = request.headers['X-Client-Operation-Id']!;
            final body = switch (operationId) {
              AppCloudOperationIds.circleCircleGroupListCircleGroups ||
              AppCloudOperationIds.circleCircleGroupSearchCircleGroups =>
                const <String, Object?>{'cursor': 'malformed-next'},
              AppCloudOperationIds.circleCircleGroupGetCircleGroup =>
                _groupSlice(groupId: 'group-malformed')..remove('version'),
              _ => <String, Object?>{
                ..._commandResult(operationId, idempotentReplay: false),
              }..remove('idempotentReplay'),
            };
            return remoteApiPathJsonResponse(body);
          },
        );

        for (final call in _operationCalls) {
          await expectLater(
            call.invoke(facets),
            throwsA(isA<CloudException>()),
          );
        }
        for (final call in _operationCalls) {
          expect(_requestsFor(log, call.operationId), isNotEmpty);
        }
      },
    );
  });
}

const _commandOperationIds = <String>{
  AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
  AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
  AppCloudOperationIds.circleCircleGroupArchiveCircleGroup,
};

final _operationCalls = <_OperationCall>[
  (
    operationId: AppCloudOperationIds.circleCircleGroupListCircleGroups,
    command: false,
    invoke: (facets) => facets.queries.list(
      CircleGroupListQuery(circleId: 'circle-1', limit: 2),
    ),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleGroupSearchCircleGroups,
    command: false,
    invoke: (facets) => facets.queries.search(
      CircleGroupSearchQuery(circleId: 'circle-1', query: '摄影', limit: 2),
    ),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
    command: true,
    invoke: (facets) => facets.commands.create(
      CreateCircleGroupCommand(
        circleId: 'circle-1',
        groupType: CircleGroupType.selfBuilt,
        name: '远行同好',
        visibility: CircleGroupVisibility.private,
        joinPolicy: CircleGroupJoinPolicy.applyOnly,
        storageEnabled: true,
        noticeEnabled: false,
      ),
    ),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleGroupGetCircleGroup,
    command: false,
    invoke: (facets) => facets.queries.get(
      CircleGroupQuery(circleId: 'circle-1', groupId: 'group-owner'),
    ),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleGroupUpdateCircleGroup,
    command: true,
    invoke: (facets) => facets.commands.update(
      UpdateCircleGroupCommand(
        circleId: 'circle-1',
        groupId: 'group-owner',
        expectedVersion: 7,
        name: '远行同好二期',
      ),
    ),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleGroupArchiveCircleGroup,
    command: true,
    invoke: (facets) => facets.commands.archive(
      ArchiveCircleGroupCommand(circleId: 'circle-1', groupId: 'group-owner'),
    ),
  ),
];

_CircleGroupFacets _facets(
  List<CapturedRemoteApiPathRequest> log, {
  required RemoteApiPathResponseFactory responseFor,
}) {
  final client = buildRemoteApiPathOperationClient(
    log,
    responseFor: responseFor,
  );
  return (
    commands: CircleProductionComposition.generatedAdapter<CircleGroupCommands>(
      CircleProductionAdapter.group,
      client: client,
      invocationContext: _context,
    ),
    queries: CircleProductionComposition.generatedAdapter<CircleGroupQueries>(
      CircleProductionAdapter.group,
      client: client,
      invocationContext: _context,
    ),
  );
}

CloudOperationInvocationContext _context(
  String clientPageId, {
  required bool command,
}) => CloudOperationInvocationContext(
  surfaceId: AppUiSurfaces.circleDetail.id,
  routeId: AppUiSurfaces.circleDetail.routeId,
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(
    accountId: 'account-actor',
    personaId: 'persona-actor',
  ),
  idempotencyKey: command ? '$clientPageId-intent' : null,
);

void _expectQuery(
  CapturedRemoteApiPathRequest request, {
  required String operationId,
  required String clientPageId,
  required Map<String, String> pathParameters,
  Map<String, String> query = const <String, String>{},
}) {
  expect(request.method, 'GET');
  expect(
    request.path,
    canonicalRemoteApiPath(operationId, pathParameters: pathParameters),
  );
  expect(request.query, query);
  expect(request.body, isEmpty);
  expect(request.headers['Authorization'], 'Bearer integration-contract-token');
  expect(request.headers.containsKey('Idempotency-Key'), isFalse);
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: clientPageId,
    surfaceId: AppUiSurfaces.circleDetail.id,
    operationId: operationId,
  );
}

void _expectCommand(
  CapturedRemoteApiPathRequest request, {
  required String operationId,
  required String clientPageId,
  required String method,
  required Map<String, String> pathParameters,
  Map<String, String> extraHeaders = const <String, String>{},
  Map<String, Object?> body = const <String, Object?>{},
}) {
  expect(request.method, method);
  expect(
    request.path,
    canonicalRemoteApiPath(operationId, pathParameters: pathParameters),
  );
  expect(request.query, isEmpty);
  expect(request.body, body);
  expect(request.headers['Authorization'], 'Bearer integration-contract-token');
  expect(request.headers['Idempotency-Key'], '$clientPageId-intent');
  for (final entry in extraHeaders.entries) {
    expect(request.headers[entry.key], entry.value);
  }
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: clientPageId,
    surfaceId: AppUiSurfaces.circleDetail.id,
    operationId: operationId,
  );
}

List<CapturedRemoteApiPathRequest> _requestsFor(
  List<CapturedRemoteApiPathRequest> log,
  String operationId,
) => log
    .where((request) => request.headers['X-Client-Operation-Id'] == operationId)
    .toList(growable: false);

http.Response _querySuccessResponse(http.Request request) {
  final operationId = request.headers['X-Client-Operation-Id'];
  final cursor = request.url.queryParameters['cursor'];
  final body = switch (operationId) {
    AppCloudOperationIds.circleCircleGroupListCircleGroups => <String, Object?>{
      'items': <Object?>[
        _groupSlice(
          groupId: cursor == null ? 'group-list-1' : 'group-list-2',
          groupType: 'org_node',
          nodeType: 'department',
          visibility: 'private',
        ),
      ],
      if (cursor == null) 'cursor': 'list-next',
    },
    AppCloudOperationIds.circleCircleGroupSearchCircleGroups =>
      <String, Object?>{
        'items': <Object?>[
          _groupSlice(
            groupId: cursor == null ? 'group-search-1' : 'group-search-2',
            visibility: 'public',
          ),
        ],
        if (cursor == null) 'cursor': 'search-next',
      },
    AppCloudOperationIds.circleCircleGroupGetCircleGroup => _groupSlice(
      groupId: 'group-owner',
      version: 7,
      conversationId: 'conversation-owner',
    ),
    _ => throw StateError('unexpected CircleGroup query: $operationId'),
  };
  return remoteApiPathJsonResponse(body);
}

Map<String, Object?> _commandResult(
  String operationId, {
  required bool idempotentReplay,
}) => <String, Object?>{
  'groupId':
      operationId == AppCloudOperationIds.circleCircleGroupCreateCircleGroup
      ? 'group-created'
      : 'group-owner',
  'version': switch (operationId) {
    AppCloudOperationIds.circleCircleGroupCreateCircleGroup => 1,
    AppCloudOperationIds.circleCircleGroupUpdateCircleGroup => 8,
    AppCloudOperationIds.circleCircleGroupArchiveCircleGroup => 9,
    _ => throw StateError('unexpected CircleGroup command: $operationId'),
  },
  'status':
      operationId == AppCloudOperationIds.circleCircleGroupArchiveCircleGroup
      ? 'archived'
      : 'active',
  'idempotentReplay': idempotentReplay,
};

Map<String, Object?> _groupSlice({
  required String groupId,
  int version = 4,
  String groupType = 'self_built',
  String? nodeType,
  String visibility = 'private',
  String? conversationId,
  String status = 'active',
}) => <String, Object?>{
  'groupId': groupId,
  'version': version,
  'circleId': 'circle-1',
  'parentGroupId': 'parent-1',
  'groupType': groupType,
  'nodeType': ?nodeType,
  'name': '权威 CircleGroup $groupId',
  'description': 'owner reader projection',
  'visibility': visibility,
  'joinPolicy': 'apply_only',
  'conversationId': ?conversationId,
  'storageEnabled': true,
  'noticeEnabled': false,
  'isDefaultPublicGroup': false,
  'status': status,
  'memberCount': 3,
  'createdAt': '2026-08-09T01:00:00Z',
  'updatedAt': '2026-08-09T02:00:00Z',
};
