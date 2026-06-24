import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';

void main() {
  group('photo publish payload media refs', () {
    test('图片发布先上传本地图片并用远端引用替换 mediaUrls 和 coverUrl', () async {
      final repository = _RecordingContentRepository();
      final fileStorage = _MemoryFileStorageGateway(<String, List<int>>{
        '/tmp/a.jpg': <int>[1, 2, 3],
        '/tmp/b.png': <int>[4, 5, 6],
      });
      final uploads = <_UploadCall>[];
      final state =
          CreateEditorState.initial(
            editorKind: CreateEditorKind.media,
          ).copyWith(
            mediaKind: CreateMediaKind.images,
            imagePaths: <String>[
              '/tmp/a.jpg',
              'https://cdn.quwoquan.test/existing.jpg',
              '/tmp/b.png',
            ],
            title: '图片作品',
          );

      final prepared = await buildCreatePostPayloadWithRemoteImageMedia(
        repository: repository,
        fileStorageGateway: fileStorage,
        state: state,
        uploadObject: (uri, bytes, {required contentType}) async {
          uploads.add(_UploadCall(uri, bytes, contentType));
        },
      );

      expect(repository.initMediaTypes, <String>['image', 'image']);
      expect(uploads.map((call) => call.uri.toString()).toList(), <String>[
        'https://upload.quwoquan.test/session_1',
        'https://upload.quwoquan.test/session_2',
      ]);
      expect(uploads.map((call) => call.contentType).toList(), <String>[
        'image/jpeg',
        'image/png',
      ]);
      expect(prepared.mediaAssetIds, <String>['asset_1', 'asset_2']);
      expect(prepared.payload['mediaUrls'], <String>[
        'https://cdn.quwoquan.test/asset_1.jpg',
        'https://cdn.quwoquan.test/existing.jpg',
        'https://cdn.quwoquan.test/asset_2.jpg',
      ]);
      expect(
        prepared.payload['coverUrl'],
        'https://cdn.quwoquan.test/asset_1.jpg',
      );
      expect(
        (prepared.payload['mediaUrls'] as List<String>).join('|'),
        isNot(contains('/tmp/')),
      );
    });

    test('本地图片上传失败会 abort 当前 upload session 且不产出半成品 payload', () async {
      final repository = _RecordingContentRepository();
      final fileStorage = _MemoryFileStorageGateway(<String, List<int>>{
        '/tmp/a.jpg': <int>[1, 2, 3],
      });
      final state =
          CreateEditorState.initial(
            editorKind: CreateEditorKind.media,
          ).copyWith(
            mediaKind: CreateMediaKind.images,
            imagePaths: <String>['/tmp/a.jpg'],
          );

      await expectLater(
        buildCreatePostPayloadWithRemoteImageMedia(
          repository: repository,
          fileStorageGateway: fileStorage,
          state: state,
          uploadObject: (uri, bytes, {required contentType}) async {
            throw StateError('upload failed');
          },
        ),
        throwsStateError,
      );

      expect(repository.abortedSessions, <String>['session_1']);
      expect(repository.completedSessions, isEmpty);
    });
  });
}

class _UploadCall {
  const _UploadCall(this.uri, this.bytes, this.contentType);

  final Uri uri;
  final List<int> bytes;
  final String contentType;
}

class _RecordingContentRepository extends MockContentRepository {
  final List<String> initMediaTypes = <String>[];
  final List<String> completedSessions = <String>[];
  final List<String> abortedSessions = <String>[];

  @override
  Future<ContentMediaInitUploadResponseDto> initMediaUpload({
    String mediaType = 'image',
    String assetScope = 'draft',
  }) async {
    initMediaTypes.add(mediaType);
    final index = initMediaTypes.length;
    return ContentMediaInitUploadResponseDto(
      sessionId: 'session_$index',
      mediaId: 'asset_$index',
      uploadUrl: 'https://upload.quwoquan.test/session_$index',
      presignUrl: 'https://upload.quwoquan.test/session_$index',
    );
  }

  @override
  Future<ContentMediaCompleteUploadResponseDto> completeMediaUpload({
    required String sessionId,
  }) async {
    completedSessions.add(sessionId);
    final index = completedSessions.length;
    return ContentMediaCompleteUploadResponseDto(
      sessionId: sessionId,
      status: 'ready',
      cdnUrl: 'https://cdn.quwoquan.test/asset_$index.jpg',
      assetId: 'asset_$index',
    );
  }

  @override
  Future<void> abortMediaUpload({required String sessionId}) async {
    abortedSessions.add(sessionId);
  }
}

class _MemoryFileStorageGateway implements FileStorageGateway {
  const _MemoryFileStorageGateway(this.bytesByPath);

  final Map<String, List<int>> bytesByPath;

  @override
  bool get isSupported => true;

  @override
  Future<String> applicationSupportPath() async => '/tmp/support';

  @override
  Future<String> temporaryPath() async => '/tmp';

  @override
  Future<bool> exists(String path) async => bytesByPath.containsKey(path);

  @override
  Future<void> writeAsString(String path, String contents) async {}

  @override
  Future<String> readAsString(String path) async => '';

  @override
  Future<List<int>> readAsBytes(String path) async => bytesByPath[path]!;

  @override
  Future<void> writeAsBytes(String path, List<int> bytes) async {}

  @override
  Future<void> delete(String path) async {}

  @override
  Future<void> ensureDirectory(String path) async {}

  @override
  Future<List<FileSystemEntry>> listDirectory(String path) async =>
      const <FileSystemEntry>[];
}
