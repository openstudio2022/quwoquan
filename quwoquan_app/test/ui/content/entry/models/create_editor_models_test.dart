import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';

void main() {
  group('CreateDraft', () {
    test('从存储 map 恢复 identity 和预览文案', () {
      final draft = CreateDraft.fromStorageMap({
        'id': 'draft_1',
        'type': 'article',
        'updatedAt': 123,
        'identity': 'work',
        'data': {'title': '东京三日清单'},
      });

      expect(draft.identity, CreateContentIdentity.work);
      expect(draft.previewText, '东京三日清单');
      expect(draft.toStorageMap()['identity'], 'work');
    });

    test('旧草稿缺失 identity 时按 tabKey 回填作品身份', () {
      final draft = CreateDraft.fromStorageMap({
        'id': 'legacy_photo',
        'type': 'photo',
        'updatedAt': 456,
        'data': {'description': '旧版图片草稿'},
      });

      expect(draft.identity, CreateContentIdentity.work);
      expect(draft.previewText, '旧版图片草稿');
    });
  });

  group('PublishSettings', () {
    test('toPayloadFields 包含 assistantUsePolicy', () {
      final payload = PublishSettings(
        isPublic: false,
        allowAssistantUse: false,
        locationName: '成都',
        location: const {'latitude': 30.6, 'longitude': 104.0},
      ).toPayloadFields();

      expect(payload['visibility'], 'private');
      expect(payload['assistantUsePolicy'], 'exclude');
    });

    test('fromMap 在私密态下清空圈子', () {
      final settings = PublishSettings.fromMap({
        'visibility': 'private',
        'assistantUsePolicy': 'inherit',
        'circleIds': ['circle_1'],
        'circleNames': ['摄影圈'],
      });

      expect(settings.isPublic, isFalse);
      expect(settings.circleIds, isEmpty);
      expect(settings.allowAssistantUse, isTrue);
    });
  });
}
