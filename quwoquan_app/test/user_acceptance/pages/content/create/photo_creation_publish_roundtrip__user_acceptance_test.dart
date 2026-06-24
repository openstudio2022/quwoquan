import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';

void main() {
  test('图片创作发布旅程保持选图顺序、远端引用、首图封面与 bind 顺序', () async {
    final repository = _JourneyContentRepository();
    final fileStorage = _JourneyFileStorageGateway(<String, List<int>>{
      '/tmp/first.jpg': <int>[1],
      '/tmp/second.jpg': <int>[2],
      '/tmp/third.jpg': <int>[3],
    });
    final state = CreateEditorState.initial(editorKind: CreateEditorKind.media)
        .copyWith(
          mediaKind: CreateMediaKind.images,
          imagePaths: <String>[
            '/tmp/second.jpg',
            '/tmp/first.jpg',
            '/tmp/third.jpg',
          ],
          body: '按用户拖动后的顺序发布。',
        );

    final prepared = await buildCreatePostPayloadWithRemoteImageMedia(
      repository: repository,
      fileStorageGateway: fileStorage,
      state: state,
      uploadObject: (uri, bytes, {required contentType}) async {},
    );
    await repository.bindMediaAssetsToPost(
      postId: 'post_photo_roundtrip',
      assetIds: prepared.mediaAssetIds,
    );

    expect(prepared.payload['contentType'], 'image');
    expect(prepared.payload['mediaUrls'], <String>[
      'https://cdn.quwoquan.test/second.jpg',
      'https://cdn.quwoquan.test/first.jpg',
      'https://cdn.quwoquan.test/third.jpg',
    ]);
    expect(
      prepared.payload['coverUrl'],
      'https://cdn.quwoquan.test/second.jpg',
    );
    expect(repository.boundAssetIds, <String>[
      'asset_second',
      'asset_first',
      'asset_third',
    ]);
  });
}

class _JourneyContentRepository extends MockContentRepository {
  final List<String> boundAssetIds = <String>[];
  final Map<String, String> _assetBySession = <String, String>{};

  @override
  Future<ContentMediaInitUploadResponseDto> initMediaUpload({
    String mediaType = 'image',
    String assetScope = 'draft',
  }) async {
    final index = _assetBySession.length;
    final assetName = <String>['second', 'first', 'third'][index];
    final sessionId = 'session_$assetName';
    _assetBySession[sessionId] = assetName;
    return ContentMediaInitUploadResponseDto(
      sessionId: sessionId,
      mediaId: 'asset_$assetName',
      uploadUrl: 'https://upload.quwoquan.test/$assetName',
      presignUrl: 'https://upload.quwoquan.test/$assetName',
    );
  }

  @override
  Future<ContentMediaCompleteUploadResponseDto> completeMediaUpload({
    required String sessionId,
  }) async {
    final assetName = _assetBySession[sessionId]!;
    return ContentMediaCompleteUploadResponseDto(
      sessionId: sessionId,
      status: 'ready',
      cdnUrl: 'https://cdn.quwoquan.test/$assetName.jpg',
      assetId: 'asset_$assetName',
    );
  }

  @override
  Future<void> bindMediaAssetsToPost({
    required String postId,
    required List<String> assetIds,
  }) async {
    boundAssetIds
      ..clear()
      ..addAll(assetIds);
  }
}

class _JourneyFileStorageGateway implements FileStorageGateway {
  const _JourneyFileStorageGateway(this.bytesByPath);

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
  Future<String> readAsString(String path) async => '';

  @override
  Future<void> writeAsString(String path, String contents) async {}

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
