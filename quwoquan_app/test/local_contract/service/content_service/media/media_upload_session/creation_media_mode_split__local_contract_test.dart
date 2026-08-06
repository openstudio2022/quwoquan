// spec_ref: specs/feature-tree/discovery-content/content-type-framework/creation-mode-and-surface-ia-unification/spec.md#gwt-001
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/create_media_picker_presentation.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/create_media_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/create_page_remote_helpers.dart';

void main() {
  group('creation media mode split', () {
    test('图片模式隐藏视频动作且 payload contentType 为 image', () {
      final categories = mediaPickerCategoriesForEntryMode(
        MediaPickerEntryMode.image,
      );
      final actions = mediaPickerBottomActionsForEntryMode(
        mode: MediaPickerEntryMode.image,
        selectionCount: 2,
      );
      final state =
          CreateEditorState.initial(
            editorKind: CreateEditorKind.media,
          ).copyWith(
            mediaKind: CreateMediaKind.images,
            imagePaths: <String>['/tmp/a.jpg', '/tmp/b.jpg'],
          );
      final payload = buildPostPublicationPayloadMap(state);

      expect(categories, isEmpty);
      expect(
        actions.map((action) => action.label),
        contains(MediaText.mediaPickerOneTapMovie),
      );
      expect(actions.map((action) => action.label), contains('下一步(2)'));
      expect(payload['contentType'], 'image');
      expect(payload['mediaUrls'], <String>['/tmp/a.jpg', '/tmp/b.jpg']);
    });

    test('视频模式只暴露视频下一步语义且 payload contentType 为 video', () {
      final categories = mediaPickerCategoriesForEntryMode(
        MediaPickerEntryMode.video,
      );
      final actions = mediaPickerBottomActionsForEntryMode(
        mode: MediaPickerEntryMode.video,
        selectionCount: 1,
      );
      final state =
          CreateEditorState.initial(
            editorKind: CreateEditorKind.media,
          ).copyWith(
            mediaKind: CreateMediaKind.video,
            videoPath: '/tmp/video.mp4',
            videoThumbnail: '/tmp/cover.jpg',
          );
      final payload = buildPostPublicationPayloadMap(state);

      expect(categories, isEmpty);
      expect(actions, hasLength(1));
      expect(actions.single.action, CreateMediaPickerBottomAction.nextStep);
      expect(actions.single.label, isNot(MediaText.mediaPickerEditImage));
      expect(payload['contentType'], 'video');
      expect(payload['videoUrl'], '/tmp/video.mp4');
    });
  });
}
