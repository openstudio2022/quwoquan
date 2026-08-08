// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-002
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-003
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-004
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-005
// readiness_case: circle_file_create_circle_file_app_local
// readiness_case: circle_file_delete_circle_file_app_local
// readiness_case: circle_file_get_circle_file_app_local
// readiness_case: circle_file_list_circle_files_app_local
// readiness_case: circle_file_update_circle_file_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_file/adapters/file_remote.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_file/application/public/circle_file_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

typedef _CircleFileFacets = ({
  CircleFileWriter writer,
  CircleFileReader reader,
});

typedef _OperationCall = ({
  String operationId,
  bool command,
  Future<Object?> Function(_CircleFileFacets facets) invoke,
});

void main() {
  group('circle.circle_file production Remote generated contract', () {
    test('queries preserve exact wire and stable typed pagination', () async {
      final log = <CapturedRemoteApiPathRequest>[];
      final facets = _facets(log, responseFor: _querySuccessResponse);

      final first = await facets.reader.list(
        CircleFileListQuery(
          circleId: 'circle-1',
          groupId: 'group-1',
          parentFolderId: 'folder-root',
          limit: 2,
        ),
      );
      final second = await facets.reader.list(
        CircleFileListQuery(
          circleId: 'circle-1',
          groupId: 'group-1',
          parentFolderId: 'folder-root',
          cursor: first.cursor,
          limit: 2,
        ),
      );
      final file = await facets.reader.get(
        CircleFileQuery(circleId: 'circle-1', fileId: 'file-owner'),
      );

      _expectQuery(
        log[0],
        operationId: AppCloudOperationIds.circleCircleFileListCircleFiles,
        clientPageId: CircleRequestPageIds.listCircleFiles,
        pathParameters: const <String, String>{'circleId': 'circle-1'},
        query: const <String, String>{
          'groupId': 'group-1',
          'parentFolderId': 'folder-root',
          'limit': '2',
        },
      );
      _expectQuery(
        log[1],
        operationId: AppCloudOperationIds.circleCircleFileListCircleFiles,
        clientPageId: CircleRequestPageIds.listCircleFiles,
        pathParameters: const <String, String>{'circleId': 'circle-1'},
        query: const <String, String>{
          'groupId': 'group-1',
          'parentFolderId': 'folder-root',
          'cursor': 'file-next',
          'limit': '2',
        },
      );
      _expectQuery(
        log[2],
        operationId: AppCloudOperationIds.circleCircleFileGetCircleFile,
        clientPageId: CircleRequestPageIds.getCircleFile,
        pathParameters: const <String, String>{
          'circleId': 'circle-1',
          'fileId': 'file-owner',
        },
      );

      expect(first.items.single.fileId, 'file-list-1');
      expect(first.cursor, 'file-next');
      expect(second.items.single.fileId, 'file-list-2');
      expect(second.cursor, isNull);
      expect(<String>{
        ...first.items.map((item) => item.fileId),
        ...second.items.map((item) => item.fileId),
      }, hasLength(2));
      expect(file.fileId, 'file-owner');
      expect(file.version, 7);
      expect(file.assetId, 'asset-owner');
      expect(file.uploaderPersonaId, 'persona-actor');
      expect(file.status, CircleFileStatus.active);
    });

    test('commands preserve exact wire, replay and fresh readback', () async {
      final log = <CapturedRemoteApiPathRequest>[];
      final responseCounts = <String, int>{};
      var ownerVersion = 7;
      var ownerName = 'owner.pdf';
      var ownerDeleted = false;
      final facets = _facets(
        log,
        responseFor: (request) {
          final operationId = request.headers['X-Client-Operation-Id']!;
          if (operationId ==
              AppCloudOperationIds.circleCircleFileGetCircleFile) {
            final fileId = request.url.pathSegments.last;
            if (fileId == 'file-owner' && ownerDeleted) {
              return remoteApiPathJsonResponse(const <String, Object?>{
                'code': 'CIRCLE.USER.file_not_found',
                'message': 'deleted file is no longer readable',
              }, statusCode: 404);
            }
            return remoteApiPathJsonResponse(
              _fileSlice(
                fileId: fileId,
                version: fileId == 'file-created' ? 1 : ownerVersion,
                name: fileId == 'file-created' ? 'created.pdf' : ownerName,
                assetId: fileId == 'file-created'
                    ? 'asset-created'
                    : 'asset-owner',
              ),
            );
          }
          final count = (responseCounts[operationId] ?? 0) + 1;
          responseCounts[operationId] = count;
          if (count == 1 &&
              operationId ==
                  AppCloudOperationIds.circleCircleFileUpdateCircleFile) {
            ownerVersion = 8;
            ownerName = 'renamed.pdf';
          }
          if (count == 1 &&
              operationId ==
                  AppCloudOperationIds.circleCircleFileDeleteCircleFile) {
            ownerVersion = 9;
            ownerDeleted = true;
          }
          return remoteApiPathJsonResponse(
            _commandResult(operationId, idempotentReplay: count.isEven),
          );
        },
      );
      final create = CreateCircleFileCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
        parentFolderId: 'folder-root',
        name: 'created.pdf',
        fileType: CircleFileType.file,
        assetId: 'asset-created',
      );
      final update = UpdateCircleFileCommand(
        circleId: 'circle-1',
        fileId: 'file-owner',
        expectedVersion: 7,
        parentFolderId: 'folder-next',
        name: 'renamed.pdf',
      );
      final delete = DeleteCircleFileCommand(
        circleId: 'circle-1',
        fileId: 'file-owner',
      );

      final created = await facets.writer.create(create);
      final createdReplay = await facets.writer.create(create);
      final createdReadback = await facets.reader.get(
        CircleFileQuery(circleId: 'circle-1', fileId: 'file-created'),
      );
      final updated = await facets.writer.update(update);
      final updatedReplay = await facets.writer.update(update);
      final updatedReadback = await facets.reader.get(
        CircleFileQuery(circleId: 'circle-1', fileId: 'file-owner'),
      );
      final deleted = await facets.writer.delete(delete);
      final deletedReplay = await facets.writer.delete(delete);
      await expectLater(
        facets.reader.get(
          CircleFileQuery(circleId: 'circle-1', fileId: 'file-owner'),
        ),
        throwsA(
          isA<CloudException>()
              .having(
                (error) => error.code,
                'code',
                'CIRCLE.USER.file_not_found',
              )
              .having(
                (error) => error.sourceOperationId,
                'sourceOperationId',
                AppCloudOperationIds.circleCircleFileGetCircleFile,
              ),
        ),
      );

      final createRequests = _requestsFor(
        log,
        AppCloudOperationIds.circleCircleFileCreateCircleFile,
      );
      final updateRequests = _requestsFor(
        log,
        AppCloudOperationIds.circleCircleFileUpdateCircleFile,
      );
      final deleteRequests = _requestsFor(
        log,
        AppCloudOperationIds.circleCircleFileDeleteCircleFile,
      );
      for (final request in createRequests) {
        _expectCommand(
          request,
          operationId: AppCloudOperationIds.circleCircleFileCreateCircleFile,
          clientPageId: CircleRequestPageIds.createCircleFile,
          method: 'POST',
          pathParameters: const <String, String>{'circleId': 'circle-1'},
          body: const <String, Object?>{
            'groupId': 'group-1',
            'parentFolderId': 'folder-root',
            'name': 'created.pdf',
            'fileType': 'file',
            'assetId': 'asset-created',
          },
        );
      }
      for (final request in updateRequests) {
        _expectCommand(
          request,
          operationId: AppCloudOperationIds.circleCircleFileUpdateCircleFile,
          clientPageId: CircleRequestPageIds.updateCircleFile,
          method: 'PATCH',
          pathParameters: const <String, String>{
            'circleId': 'circle-1',
            'fileId': 'file-owner',
          },
          extraHeaders: const <String, String>{'If-Match': '"7"'},
          body: const <String, Object?>{
            'parentFolderId': 'folder-next',
            'name': 'renamed.pdf',
          },
        );
      }
      for (final request in deleteRequests) {
        _expectCommand(
          request,
          operationId: AppCloudOperationIds.circleCircleFileDeleteCircleFile,
          clientPageId: CircleRequestPageIds.deleteCircleFile,
          method: 'DELETE',
          pathParameters: const <String, String>{
            'circleId': 'circle-1',
            'fileId': 'file-owner',
          },
        );
      }

      expect(createRequests, hasLength(2));
      expect(updateRequests, hasLength(2));
      expect(deleteRequests, hasLength(2));
      expect(created.fileId, 'file-created');
      expect(createdReplay.fileId, created.fileId);
      expect(createdReplay.idempotentReplay, isTrue);
      expect(createdReadback.fileId, created.fileId);
      expect(createdReadback.version, created.version);
      expect(updated.fileId, 'file-owner');
      expect(updated.version, 8);
      expect(updatedReplay.version, updated.version);
      expect(updatedReplay.idempotentReplay, isTrue);
      expect(updatedReadback.version, updated.version);
      expect(updatedReadback.name, 'renamed.pdf');
      expect(deleted.status, CircleFileStatus.deleted);
      expect(deleted.version, 9);
      expect(deletedReplay.version, deleted.version);
      expect(deletedReplay.idempotentReplay, isTrue);
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
            'message': 'canonical circle file authorization failure',
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
          'code': 'CIRCLE.SYSTEM.file_storage_write_failed',
          'message': 'circle file storage unavailable',
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
                  'CIRCLE.SYSTEM.file_storage_write_failed',
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
              AppCloudOperationIds.circleCircleFileListCircleFiles =>
                const <String, Object?>{'cursor': 'missing-items'},
              AppCloudOperationIds.circleCircleFileGetCircleFile => _fileSlice(
                fileId: 'file-malformed',
              )..remove('version'),
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
  AppCloudOperationIds.circleCircleFileCreateCircleFile,
  AppCloudOperationIds.circleCircleFileUpdateCircleFile,
  AppCloudOperationIds.circleCircleFileDeleteCircleFile,
};

final _operationCalls = <_OperationCall>[
  (
    operationId: AppCloudOperationIds.circleCircleFileListCircleFiles,
    command: false,
    invoke: (facets) =>
        facets.reader.list(CircleFileListQuery(circleId: 'circle-1', limit: 2)),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleFileGetCircleFile,
    command: false,
    invoke: (facets) => facets.reader.get(
      CircleFileQuery(circleId: 'circle-1', fileId: 'file-owner'),
    ),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleFileCreateCircleFile,
    command: true,
    invoke: (facets) => facets.writer.create(
      CreateCircleFileCommand(
        circleId: 'circle-1',
        name: 'created.pdf',
        fileType: CircleFileType.file,
        assetId: 'asset-created',
      ),
    ),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleFileUpdateCircleFile,
    command: true,
    invoke: (facets) => facets.writer.update(
      UpdateCircleFileCommand(
        circleId: 'circle-1',
        fileId: 'file-owner',
        expectedVersion: 7,
        name: 'renamed.pdf',
      ),
    ),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleFileDeleteCircleFile,
    command: true,
    invoke: (facets) => facets.writer.delete(
      DeleteCircleFileCommand(circleId: 'circle-1', fileId: 'file-owner'),
    ),
  ),
];

_CircleFileFacets _facets(
  List<CapturedRemoteApiPathRequest> log, {
  required RemoteApiPathResponseFactory responseFor,
}) {
  final remote = RemoteCircleFileFacet(
    client: buildRemoteApiPathOperationClient(log, responseFor: responseFor),
    invocationContext: _context,
  );
  return (writer: remote, reader: remote);
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
    AppCloudOperationIds.circleCircleFileListCircleFiles => <String, Object?>{
      'items': <Object?>[
        _fileSlice(fileId: cursor == null ? 'file-list-1' : 'file-list-2'),
      ],
      if (cursor == null) 'cursor': 'file-next',
    },
    AppCloudOperationIds.circleCircleFileGetCircleFile => _fileSlice(
      fileId: 'file-owner',
      version: 7,
      assetId: 'asset-owner',
    ),
    _ => throw StateError('unexpected CircleFile query: $operationId'),
  };
  return remoteApiPathJsonResponse(body);
}

Map<String, Object?> _commandResult(
  String operationId, {
  required bool idempotentReplay,
}) => <String, Object?>{
  'fileId': operationId == AppCloudOperationIds.circleCircleFileCreateCircleFile
      ? 'file-created'
      : 'file-owner',
  'version': switch (operationId) {
    AppCloudOperationIds.circleCircleFileCreateCircleFile => 1,
    AppCloudOperationIds.circleCircleFileUpdateCircleFile => 8,
    AppCloudOperationIds.circleCircleFileDeleteCircleFile => 9,
    _ => throw StateError('unexpected CircleFile command: $operationId'),
  },
  'status': operationId == AppCloudOperationIds.circleCircleFileDeleteCircleFile
      ? 'deleted'
      : 'active',
  'idempotentReplay': idempotentReplay,
};

Map<String, Object?> _fileSlice({
  required String fileId,
  int version = 4,
  String name = 'contract.pdf',
  String assetId = 'asset-owner',
}) => <String, Object?>{
  'fileId': fileId,
  'version': version,
  'circleId': 'circle-1',
  'groupId': 'group-1',
  'parentFolderId': 'folder-root',
  'name': name,
  'fileType': 'file',
  'assetId': assetId,
  'mimeType': 'application/pdf',
  'sizeBytes': 1024,
  'uploaderPersonaId': 'persona-actor',
  'status': 'active',
  'createdAt': '2026-08-09T01:00:00Z',
  'updatedAt': '2026-08-09T02:00:00Z',
};
