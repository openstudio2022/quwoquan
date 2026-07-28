import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/picker/create_media_picker_presentation.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';

void main() {
  group('creation mixed media picker contract', () {
    test('mixed 模式使用下一步语义，不复用图片编辑完成双按钮', () {
      final actions = mediaPickerBottomActionsForEntryMode(
        mode: MediaPickerEntryMode.mixed,
        selectionCount: 1,
      );

      expect(isMixedCreationEntryMode(MediaPickerEntryMode.mixed), isTrue);
      expect(isPhotoCreationEntryMode(MediaPickerEntryMode.mixed), isFalse);
      expect(actions, hasLength(1));
      expect(actions.single.action, CreateMediaPickerBottomAction.nextStep);
      expect(actions.single.label, '下一步(1)');
      expect(actions.single.label, isNot(MediaText.mediaPickerEditImage));
    });

    test('mixed 模式第一项锁定媒体类型：图片可多选，视频单选，图片视频不可混选', () {
      final imageA = _item('image_a', CreateMediaType.image);
      final imageB = _item('image_b', CreateMediaType.image);
      final video = _item('video_a', CreateMediaType.video);

      expect(
        mediaPickerSelectionBlockReason(
          mode: MediaPickerEntryMode.mixed,
          selectedItems: const <CreateMediaItem>[],
          candidate: imageA,
          maxSelection: 9,
        ),
        MediaPickerSelectionBlockReason.none,
      );
      expect(
        mediaPickerSelectionBlockReason(
          mode: MediaPickerEntryMode.mixed,
          selectedItems: <CreateMediaItem>[imageA],
          candidate: imageB,
          maxSelection: 9,
        ),
        MediaPickerSelectionBlockReason.none,
      );
      expect(
        mediaPickerSelectionBlockReason(
          mode: MediaPickerEntryMode.mixed,
          selectedItems: <CreateMediaItem>[imageA],
          candidate: video,
          maxSelection: 9,
        ),
        MediaPickerSelectionBlockReason.imageLocked,
      );
      expect(
        mediaPickerSelectionBlockReason(
          mode: MediaPickerEntryMode.mixed,
          selectedItems: <CreateMediaItem>[video],
          candidate: imageA,
          maxSelection: 9,
        ),
        MediaPickerSelectionBlockReason.videoLocked,
      );
    });
  });
}

CreateMediaItem _item(String id, CreateMediaType type) {
  return CreateMediaItem(
    id: id,
    path: '/tmp/$id',
    type: type,
    source: CreateMediaSource.album,
  );
}
