import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/location_poi_dto.g.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';

void main() {
  group('CreateDraft', () {
    test('从 v2 存储 map 恢复文字草稿与预览文案', () {
      final draft = CreateDraft.fromStorageMap({
        'id': 'draft_1',
        'draftVersion': 'v2',
        'updatedAt': 123,
        'type': 'text',
        'editorKind': 'text',
        'mediaKind': 'images',
        'imagePaths': ['a.png'],
        'title': '东京三日清单',
        'body': '第一天先去浅草寺',
        'titlePresentation': 'expanded',
        'settings': const <String, dynamic>{},
      });

      expect(draft.identity, CreateContentIdentity.moment);
      expect(draft.previewText, '东京三日清单');
      expect(draft.toStorageMap()['type'], 'text');
      expect(draft.state.imagePaths, hasLength(1));
    });

    test('从文章块恢复正文与图片索引', () {
      final draft = CreateDraft.fromStorageMap({
        'id': 'draft_blocks',
        'draftVersion': 'v2',
        'updatedAt': 456,
        'type': 'text',
        'editorKind': 'text',
        'mediaKind': 'none',
        'title': '块编辑器',
        'body': '',
        'articleBlocks': [
          {
            'id': 'p1',
            'type': 'paragraph',
            'text': '第一段',
            'imagePath': '',
          },
          {
            'id': 'o1',
            'type': 'orderedItem',
            'text': '第二条',
            'imagePath': '',
          },
          {
            'id': 'i1',
            'type': 'image',
            'text': '',
            'imagePath': 'inline.png',
          },
        ],
        'activeArticleBlockId': 'o1',
        'settings': const <String, dynamic>{},
      });

      expect(draft.state.body, '第一段\n1. 第二条');
      expect(draft.state.imagePaths, <String>['inline.png']);
      expect(draft.state.activeArticleBlockId, 'o1');
      expect(
        (draft.toStorageMap()['articleBlocks'] as List).length,
        3,
      );
    });

    test('图片块布局样式可序列化恢复', () {
      final block = CreateTextBlock.image(
        id: 'img_1',
        imagePath: 'inline.png',
        imageLayout: CreateTextImageLayout.wrapRight,
      );

      final restored = CreateTextBlock.fromMap(block.toMap());
      expect(restored.imageLayout, CreateTextImageLayout.wrapRight);
      expect(restored.usesWrappedLayout, isTrue);
    });

    test('旧草稿缺失 identity 时按 tabKey 迁移到 v2', () {
      final draft = CreateDraft.fromStorageMap({
        'id': 'legacy_photo',
        'type': 'photo',
        'updatedAt': 456,
        'data': {'description': '旧版图片草稿'},
      });

      expect(draft.identity, CreateContentIdentity.work);
      expect(draft.previewText, '旧版图片草稿');
      expect(draft.state.editorKind, CreateEditorKind.media);
    });
  });

  group('PublishSettings', () {
    test('toPayloadFields 输出发布设置基础字段', () {
      final payload = PublishSettings(
        isPublic: false,
        locationName: '成都',
        locationPoi: const LocationPoiDto(
          id: 't_poi',
          name: '',
          latitude: 30.6,
          longitude: 104.0,
        ),
      ).toPayloadFields();

      expect(payload['visibility'], 'private');
      expect(payload['locationName'], '成都');
      expect(payload['location'], isNotEmpty);
    });

    test('fromMap 在私密态下清空圈子', () {
      final settings = PublishSettings.fromMap({
        'visibility': 'private',
        'circleIds': ['circle_1'],
        'circleNames': ['摄影圈'],
      });

      expect(settings.isPublic, isFalse);
      expect(settings.circleIds, isEmpty);
      expect(settings.locationName, isEmpty);
    });
  });
}
