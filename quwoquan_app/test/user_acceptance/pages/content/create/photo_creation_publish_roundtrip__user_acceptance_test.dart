import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/recording_content_media_facet.dart';

void main() {
  test('图片创作发布旅程保持选图顺序、远端引用、首图封面与 bind 顺序', () async {
    final media = RecordingContentMediaFacet();
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
      media: media,
      fileStorageGateway: fileStorage,
      state: state,
      uploadObject:
          (
            uri,
            bytes, {
            required contentType,
            required expectedSha256,
          }) async {},
    );
    await media.bindPostMediaAssets(
      BindContentPostMediaAssetsCommand(
        postId: 'post_photo_roundtrip',
        assetIds: prepared.mediaAssetIds,
      ),
    );

    expect(prepared.payload['contentType'], 'image');
    expect(prepared.payload['mediaUrls'], <String>[
      'https://cdn.quwoquan.test/image_asset_1.jpg',
      'https://cdn.quwoquan.test/image_asset_2.jpg',
      'https://cdn.quwoquan.test/image_asset_3.jpg',
    ]);
    expect(
      prepared.payload['coverUrl'],
      'https://cdn.quwoquan.test/image_asset_1.jpg',
    );
    expect(media.boundAssetIds, <String>[
      'image_asset_1',
      'image_asset_2',
      'image_asset_3',
    ]);
  });
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
