import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/entry/services/publish_settings_services.dart';

void main() {
  group('CreateLocationService.parseIntegrationLocationItems', () {
    test('null / 非 Map 返回空', () {
      expect(
        CreateLocationService.parseIntegrationLocationItems(null),
        isEmpty,
      );
      expect(
        CreateLocationService.parseIntegrationLocationItems(''),
        isEmpty,
      );
      expect(
        CreateLocationService.parseIntegrationLocationItems(<Object?>[]),
        isEmpty,
      );
    });

    test('Map 无 items 或 items 非 List 返回空', () {
      expect(
        CreateLocationService.parseIntegrationLocationItems(<String, dynamic>{}),
        isEmpty,
      );
      expect(
        CreateLocationService.parseIntegrationLocationItems(<String, dynamic>{
          'items': 'nope',
        }),
        isEmpty,
      );
    });

    test('合法 items 解析为选项', () {
      final out = CreateLocationService.parseIntegrationLocationItems(
        <String, dynamic>{
          'items': <Map<String, Object?>>[
            {
              'id': 'p1',
              'name': '测试 POI',
              'latitude': 39.9,
              'longitude': 116.4,
            },
          ],
        },
      );
      expect(out, hasLength(1));
      expect(out.first.name, '测试 POI');
    });

    test('条目非 Map 或 name 空则跳过', () {
      final out = CreateLocationService.parseIntegrationLocationItems(
        <String, dynamic>{
          'items': <Object?>[
            1,
            <String, dynamic>{'name': '', 'latitude': 0, 'longitude': 0},
            <String, dynamic>{
              'name': '保留',
              'latitude': 1,
              'longitude': 2,
            },
          ],
        },
      );
      expect(out, hasLength(1));
      expect(out.first.name, '保留');
    });
  });
}
