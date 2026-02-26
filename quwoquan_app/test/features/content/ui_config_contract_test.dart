import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';

/// 契约测试：ContentUIConfig — 覆盖 mock.yaml ui_config_scenarios
///
/// 确保 codegen 输出与 ui_config.yaml 元数据一致。
void main() {
  group('ContentUIConfig — ui_config_scenarios contract', () {
    test('discovery_tabs_count — exactly 4 tabs defined', () {
      expect(ContentUIConfig.discoveryTabs.length, equals(4));
    });

    test('discovery tabs have correct ids: photo, video, moment, article', () {
      final ids = ContentUIConfig.discoveryTabs.map((t) => t.id).toList();
      expect(ids, containsAll(['photo', 'video', 'moment', 'article']));
    });

    test('photo tab uses waterfall_grid layout', () {
      final photoTab =
          ContentUIConfig.discoveryTabs.firstWhere((t) => t.id == 'photo');
      expect(photoTab.layout, equals('waterfall_grid'));
      expect(photoTab.contentType, equals('image'));
    });

    test('video tab uses full_width_vertical_pager layout', () {
      final videoTab =
          ContentUIConfig.discoveryTabs.firstWhere((t) => t.id == 'video');
      expect(videoTab.layout, equals('full_width_vertical_pager'));
      expect(videoTab.contentType, equals('video'));
    });

    test('moment tab uses list_with_optional_media layout', () {
      final momentTab =
          ContentUIConfig.discoveryTabs.firstWhere((t) => t.id == 'moment');
      expect(momentTab.layout, equals('list_with_optional_media'));
      expect(momentTab.contentType, equals('micro'));
    });

    test('article tab uses list_with_cover layout', () {
      final articleTab =
          ContentUIConfig.discoveryTabs.firstWhere((t) => t.id == 'article');
      expect(articleTab.layout, equals('list_with_cover'));
      expect(articleTab.contentType, equals('article'));
    });

    test('feature_flags_complete — required flags present', () {
      expect(ContentUIConfig.featureFlags.containsKey('enable_helper_read'),
          isTrue);
      expect(
          ContentUIConfig.featureFlags.containsKey('enable_behavior_tracking'),
          isTrue);
      expect(
          ContentUIConfig.featureFlags.containsKey('enable_photo_waterfall'),
          isTrue);
    });

    test('feature flags all have bool defaults', () {
      for (final entry in ContentUIConfig.featureFlags.entries) {
        expect(entry.value, isA<bool>(),
            reason: '${entry.key} must have a bool default');
      }
    });

    test('card_config_all_types — emptyStates has feed_empty key', () {
      expect(ContentUIConfig.emptyStates.containsKey('feed_empty'), isTrue);
    });

    test('each tab has a non-empty labelKey and icon', () {
      for (final tab in ContentUIConfig.discoveryTabs) {
        expect(tab.labelKey, isNotEmpty,
            reason: 'Tab ${tab.id} must have a labelKey');
        expect(tab.icon, isNotEmpty,
            reason: 'Tab ${tab.id} must have an icon');
      }
    });

    test('feature_flags no duplicates — all keys are unique', () {
      final keys = ContentUIConfig.featureFlags.keys.toList();
      final uniqueKeys = keys.toSet();
      expect(keys.length, equals(uniqueKeys.length),
          reason: 'feature_flags keys must be unique');
    });
  });
}
