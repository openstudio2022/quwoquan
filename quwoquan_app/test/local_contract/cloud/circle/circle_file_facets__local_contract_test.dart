import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/remote/circle/file/file_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'CircleFile Remote maps create to the operation-specific generated ABI',
    () async {
      final executor = _RecordingExecutor(response: _commandResult());
      final contexts = <CloudOperationInvocationContext>[];
      final remote = RemoteCircleFileFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId, {required command}) {
          final context = CloudOperationInvocationContext(
            surfaceId: 'circleDetail',
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
            idempotencyKey: command ? 'idem-1' : null,
          );
          contexts.add(context);
          return context;
        },
      );

      final result = await remote.create(
        CreateCircleFileCommand(
          circleId: 'circle-1',
          parentFolderId: 'folder-1',
          name: 'contract.pdf',
          fileType: CircleFileType.file,
          assetId: 'asset-1',
        ),
      );

      expect(result.fileId, 'file-1');
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.circleCircleFileCreateCircleFile,
      );
      expect(executor.pathParameters, <String, String>{'circleId': 'circle-1'});
      expect(executor.body, <String, Object?>{
        'parentFolderId': 'folder-1',
        'name': 'contract.pdf',
        'fileType': 'file',
        'assetId': 'asset-1',
      });
      expect(executor.body, isNot(contains('personaId')));
      expect(executor.body, isNot(contains('objectKey')));
      expect(contexts.single.idempotencyKey, 'idem-1');
    },
  );

  test('CircleFile list returns a strict typed Reader slice', () async {
    final executor = _RecordingExecutor(
      response: <String, Object?>{
        'items': <Object?>[_fileSlice()],
        'cursor': 'file-1',
      },
    );
    final remote = RemoteCircleFileFacet(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: (clientPageId, {required command}) =>
          CloudOperationInvocationContext(
            surfaceId: 'circleDetail',
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
          ),
    );

    final page = await remote.list(
      CircleFileListQuery(
        circleId: 'circle-1',
        parentFolderId: 'folder-1',
        limit: 25,
      ),
    );

    expect(page.items.single.assetId, 'asset-1');
    expect(page.nextCursor, 'file-1');
    expect(executor.queryParameters, <String, String>{
      'parentFolderId': 'folder-1',
      'limit': '25',
    });
    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.circleCircleFileListCircleFiles,
    );
  });

  test(
    'CircleFile contracts reject child aliases, storage keys and invalid ownership',
    () {
      expect(
        () => CreateCircleFileCommand(
          circleId: 'circle-1',
          name: 'missing-asset.pdf',
          fileType: CircleFileType.file,
        ),
        throwsArgumentError,
      );
      expect(
        () => CreateCircleFileCommand(
          circleId: 'circle-1',
          name: 'folder',
          fileType: CircleFileType.folder,
          assetId: 'asset-1',
        ),
        throwsArgumentError,
      );
      expect(
        () => decodeCircleFileSlice(
          _fileSlice()..['objectKey'] = 'forbidden/storage/key',
        ),
        throwsFormatException,
      );
      expect(
        () => decodeCircleFileSlice(
          _fileSlice()
            ..remove('uploaderPersonaId')
            ..['uploaderId'] = 'unexpected-user',
        ),
        throwsFormatException,
      );
    },
  );

  test('CircleFile mutations carry optimistic version only in If-Match', () {
    final update = encodeUpdateCircleFileCommand(
      UpdateCircleFileCommand(
        circleId: 'circle-1',
        fileId: 'file-1',
        expectedVersion: 7,
        name: 'renamed.pdf',
      ),
    );
    expect(update.headers, <String, String>{'If-Match': '"7"'});
    expect(update.body, <String, Object?>{'name': 'renamed.pdf'});

    final delete = encodeDeleteCircleFileCommand(
      DeleteCircleFileCommand(
        circleId: 'circle-1',
        fileId: 'file-1',
        expectedVersion: 8,
      ),
    );
    expect(delete.headers, <String, String>{'If-Match': '"8"'});
    expect(delete.body, isNull);
  });
}

Map<String, Object?> _commandResult() => <String, Object?>{
  'fileId': 'file-1',
  'version': 1,
  'status': 'active',
  'idempotentReplay': false,
};

Map<String, Object?> _fileSlice() => <String, Object?>{
  'fileId': 'file-1',
  'version': 1,
  'circleId': 'circle-1',
  'groupId': null,
  'parentFolderId': 'folder-1',
  'name': 'contract.pdf',
  'fileType': 'file',
  'assetId': 'asset-1',
  'mimeType': 'application/pdf',
  'sizeBytes': 1024,
  'uploaderPersonaId': 'persona-1',
  'status': 'active',
  'createdAt': '2026-07-14T01:00:00Z',
  'updatedAt': '2026-07-14T01:00:00Z',
};

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
