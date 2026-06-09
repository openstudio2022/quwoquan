import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/creation_template_track.dart';

void main() {
  group('CreationTemplateTrack', () {
    test('六类模板均有标题、正文骨架、helper 与身份建议', () {
      expect(
        creationTemplateTracks.length,
        CreationTemplateTrackId.values.length,
      );
      for (final track in creationTemplateTracks) {
        expect(track.label.trim(), isNotEmpty);
        expect(track.helperText.trim(), isNotEmpty);
        expect(track.titlePlaceholder.trim(), isNotEmpty);
        expect(track.bodySkeleton.trim(), isNotEmpty);
      }
      expect(
        creationTemplateTracks.map((track) => track.id).toSet(),
        CreationTemplateTrackId.values.toSet(),
      );
    });

    test('模板可给空编辑器预填标题、正文和文章样式', () {
      final track = creationTemplateTrackById(CreationTemplateTrackId.guide);
      final next = track.applyTo(CreateEditorState.initial());

      expect(next.editorKind, CreateEditorKind.text);
      expect(next.mediaKind, CreateMediaKind.none);
      expect(next.title, track.titlePlaceholder);
      expect(next.body, track.bodySkeleton);
      expect(next.articleTemplate, track.articleTemplate);
      expect(next.articleDocument.body, contains('适合谁'));
    });

    test('模板不覆盖用户已经输入的标题和正文', () {
      final track = creationTemplateTrackById(CreationTemplateTrackId.story);
      final initial = CreateEditorState.initial().copyWith(
        title: '已有标题',
        body: '已有正文',
      );
      final next = track.applyTo(initial);

      expect(next.title, '已有标题');
      expect(next.body, '已有正文');
      expect(next.articleDocument.body, '已有正文');
    });
  });
}
