import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_life_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_work_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/user_setting_model.dart';

void main() {
  test('UserWorkDto 由 canonical projection 解析', () {
    final dto = UserWorkDto.fromMap(<String, dynamic>{
      'id': 'w001',
      'userId': 'u001',
      'title': '摄影作品集',
      'coverUrl': 'https://cdn.example.com/cover.jpg',
      'workType': 'photography',
      'refId': 'ref_001',
      'sortOrder': 1,
      'createdAt': '2024-01-01T00:00:00Z',
      'updatedAt': '2024-06-01T00:00:00Z',
    });

    expect(dto.id, 'w001');
    expect(dto.title, '摄影作品集');
    expect(dto.workType, 'photography');
  });

  test('UserLifeItemDto 由 canonical projection 解析', () {
    final dto = UserLifeItemDto.fromMap(<String, dynamic>{
      'id': 'li001',
      'userId': 'u001',
      'category': 'travel',
      'title': '日本之旅',
      'subtitle': '东京/京都',
      'imageUrl': 'https://cdn.example.com/japan.jpg',
      'sortOrder': 0,
      'createdAt': '2024-01-01T00:00:00Z',
      'updatedAt': '2024-06-01T00:00:00Z',
    });

    expect(dto.id, 'li001');
    expect(dto.category, 'travel');
    expect(dto.title, '日本之旅');
  });

  test('UserSettingModel 明确属于应用映射而非 generated ABI', () {
    final model = UserSettingModel.fromWire(<String, dynamic>{
      'userId': 'u001',
      'enablePush': true,
      'profileVisibility': 'private',
    });

    expect(model.userId, 'u001');
    expect(model.enablePush, isTrue);
    expect(model.profileVisibility, 'private');
  });
}
