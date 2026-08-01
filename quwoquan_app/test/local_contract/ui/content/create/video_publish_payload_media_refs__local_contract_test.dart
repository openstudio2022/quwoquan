import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';

import '../../../../support/recording_content_media_facet.dart';
import '../../../../support/recording_content_post_publication_writer.dart';

void main() {
  test('录制视频发布仅绑定 MediaAsset ID 且不泄漏本地路径', () async {
    final media = RecordingContentMediaFacet();
    final publication = RecordingContentPostPublicationWriter();
    const bytes = <int>[1, 2, 3, 4];
    final uploads = <String>[];
    final state = CreateEditorState.initial(editorKind: CreateEditorKind.media)
        .copyWith(
          mediaKind: CreateMediaKind.video,
          videoPath: '/tmp/recorded.mp4',
          originalVideoPath: '/tmp/recorded.mp4',
          videoDurationMs: 1600,
          videoCoverStrategy: 'first_frame',
          videoWidth: 1080,
          videoHeight: 1920,
          body: '刚录制的视频，直接发布。',
        );

    final prepared = await buildPostPublicationPayloadWithRemoteMedia(
      media: media,
      state: state,
      mediaPreparationIdentity: 'draft-video-roundtrip',
      sourceReader: _SingleSourceReader(bytes),
      uploadStream:
          (
            uri,
            stream, {
            required contentLength,
            required mimeType,
            required expectedSha256,
            abortTrigger,
          }) async {
            final uploadedBytes = await stream
                .expand((chunk) => chunk)
                .toList();
            expect(uploadedBytes.length, contentLength);
            uploads.add(mimeType);
          },
    );
    final command = submitContentPostPublicationCommandFromPreparedPayload(
      prepared.payload,
      localDraftId: 'draft-video-roundtrip',
      mediaAssetIds: prepared.mediaAssetIds,
    );
    await publication.submitPostPublication(command);

    expect(prepared.payload['contentType'], 'video');
    expect(uploads, <String>['video/mp4']);
    expect(media.selectedAutoCoverMediaIds, <String>['video_asset_1']);
    expect(prepared.payload, isNot(contains('videoUrl')));
    expect(prepared.payload, isNot(contains('thumbnailUrl')));
    expect(prepared.payload, isNot(contains('coverUrl')));
    expect(prepared.payload['coverStrategy'], 'first_frame');
    expect(prepared.payload['durationMs'], 1600);
    expect(prepared.payload['width'], 1080);
    expect(prepared.payload['height'], 1920);
    expect(prepared.payload.values.toString(), isNot(contains('/tmp/')));
    expect(
      prepared.payload.values.toString(),
      isNot(contains('cdn.quwoquan.test')),
    );
    expect(
      publication.submitCommands.single.mediaAssetIds,
      prepared.mediaAssetIds,
    );
  });

  test('封面上传失败重启后复用已持久化的视频资产', () async {
    final media = RecordingContentMediaFacet();
    const bytes = <int>[5, 6, 7, 8];
    final checkpoints = <ContentMediaPreparationCheckpoint>[];
    var rejectCoverUpload = true;
    final state = CreateEditorState.initial(editorKind: CreateEditorKind.media)
        .copyWith(
          mediaKind: CreateMediaKind.video,
          videoPath: '/tmp/recoverable.mp4',
          originalVideoPath: '/tmp/recoverable.mp4',
          videoThumbnail: '/tmp/recoverable-cover.jpg',
          videoCoverStrategy: 'manual',
          body: '视频和封面分段上传后可恢复。',
        );

    Future<void> upload(
      Uri _,
      Stream<List<int>> stream, {
      required int contentLength,
      required String mimeType,
      required String expectedSha256,
      Future<void>? abortTrigger,
    }) async {
      await stream.drain<void>();
      if (mimeType == 'image/jpeg' && rejectCoverUpload) {
        throw StateError('simulated cover transport failure');
      }
    }

    await expectLater(
      buildPostPublicationPayloadWithRemoteMedia(
        media: media,
        state: state,
        mediaPreparationIdentity: 'draft-video-recovery',
        sourceReader: _SingleSourceReader(bytes),
        uploadStream: upload,
        onMediaPrepared: (checkpoint) async {
          checkpoints.add(checkpoint);
        },
      ),
      throwsA(isA<StateError>()),
    );
    expect(media.initCommands, hasLength(2));
    final persistedVideo = checkpoints.lastWhere(
      (checkpoint) => checkpoint.slot == 'video:0' && checkpoint.isCompleted,
    );
    expect(persistedVideo.assetId, 'video_asset_1');

    rejectCoverUpload = false;
    final recovered = await buildPostPublicationPayloadWithRemoteMedia(
      media: media,
      state: state,
      mediaPreparationIdentity: 'draft-video-recovery',
      sourceReader: _SingleSourceReader(bytes),
      uploadStream: upload,
      preparedMediaAssets: checkpoints,
      onMediaPrepared: (checkpoint) async {
        checkpoints.add(checkpoint);
      },
    );

    expect(
      media.initCommands.map((command) => command.mediaType.name),
      <String>['video', 'image', 'image'],
    );
    expect(recovered.mediaAssetIds, <String>['video_asset_1', 'image_asset_3']);
    expect(recovered.payload, isNot(contains('mediaItems')));
  });
}

class _SingleSourceReader implements ContentMediaSourceReader {
  const _SingleSourceReader(this.bytes);

  final List<int> bytes;

  @override
  Future<PreparedContentMediaSource> prepare(String localPath) async {
    return PreparedContentMediaSource(
      fileSize: bytes.length,
      sha256Digest: sha256.convert(bytes).toString(),
      openRead: () => Stream<List<int>>.value(bytes),
    );
  }
}
