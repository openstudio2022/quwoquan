import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_life_item_dto.g.dart';

/// T1 契约：codegen `UserLifeItemDto` wire 字段名、类型与 `LifeItemCategory` 枚举值，
/// 必须与 contracts/metadata/user/user_life_item 一致（端云同源）。
void main() {
  group('UserLifeItemDto — wire 契约', () {
    test('fromJson 按 wire 字段名解析（id/userId/category/title/subtitle/imageUrl/refId）', () {
      final dto = UserLifeItemDto.fromJson(<String, dynamic>{
        'id': 'i1',
        'userId': 'u1',
        'category': 'footprint',
        'title': '阿那亚礼堂',
        'subtitle': '海边的孤独感',
        'imageUrl': 'https://cdn.example.com/cover.png',
        'refId': 'work_42',
        'sortOrder': 3,
        'createdAt': '2026-05-31T00:00:00Z',
        'updatedAt': '2026-05-31T00:00:00Z',
      });

      expect(dto.id, 'i1');
      expect(dto.userId, 'u1');
      expect(dto.category, 'footprint');
      expect(dto.title, '阿那亚礼堂');
      expect(dto.subtitle, '海边的孤独感');
      expect(dto.imageUrl, 'https://cdn.example.com/cover.png');
      expect(dto.refId, 'work_42');
      expect(dto.sortOrder, 3);
    });

    test('可空字段缺省安全（subtitle/imageUrl/refId 允许 null，sortOrder/时间有默认）', () {
      final dto = UserLifeItemDto.fromJson(<String, dynamic>{
        'id': 'i2',
        'userId': 'u1',
        'category': 'soul',
        'title': '《摄影的哲学》',
      });

      expect(dto.subtitle, isNull);
      expect(dto.imageUrl, isNull);
      expect(dto.refId, isNull);
      expect(dto.sortOrder, 0);
      expect(dto.createdAt, '');
    });

    test('LifeItemCategory 四枚举值均可解析并 round-trip', () {
      for (final category in <String>['footprint', 'soul', 'taste', 'private']) {
        final json = <String, dynamic>{
          'id': 'i_$category',
          'userId': 'u1',
          'category': category,
          'title': 't_$category',
          'sortOrder': 0,
          'createdAt': '',
          'updatedAt': '',
        };
        final dto = UserLifeItemDto.fromJson(json);
        expect(dto.category, category);
        expect(dto.toJson()['category'], category);
      }
    });
  });
}
