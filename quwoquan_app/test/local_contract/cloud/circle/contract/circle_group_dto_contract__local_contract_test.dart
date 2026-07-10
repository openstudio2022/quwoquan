import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';

void main() {
  group('CircleGroupDto', () {
    test('fromMap 接受 id / _id / groupId 别名', () {
      final a = CircleGroupDto.fromMap({
        'id': 'g1',
        'circleId': 'c1',
        'groupType': 'public_group',
        'name': '群A',
        'visibility': 'public',
        'joinPolicy': 'open',
        'ownerUserId': 'u1',
        'status': 'active',
        'createdAt': '2024-01-01T00:00:00.000Z',
        'updatedAt': '2024-01-02T00:00:00.000Z',
      });
      expect(a.id, 'g1');

      final b = CircleGroupDto.fromMap({
        '_id': 'g2',
        'circleId': 'c1',
        'groupType': 'public_group',
        'name': '群B',
        'visibility': 'public',
        'joinPolicy': 'open',
        'ownerUserId': 'u1',
        'status': 'active',
        'createdAt': '2024-01-01T00:00:00.000Z',
        'updatedAt': '2024-01-02T00:00:00.000Z',
      });
      expect(b.id, 'g2');
    });

    test('toMap 含 groupId 与 id 对齐', () {
      final m = CircleGroupDto.fromMap({
        'id': 'g1',
        'circleId': 'c1',
        'groupType': 'public_group',
        'name': '群',
        'visibility': 'public',
        'joinPolicy': 'open',
        'ownerUserId': 'u1',
        'status': 'active',
        'createdAt': '2024-01-01T00:00:00.000Z',
        'updatedAt': '2024-01-02T00:00:00.000Z',
      }).toMap();
      expect(m['groupId'], 'g1');
      expect(m['id'], 'g1');
    });
  });

  group('CircleGroupMemberDto', () {
    test('fromMap 接受 id / _id', () {
      final m = CircleGroupMemberDto.fromMap({
        '_id': 'm1',
        'groupId': 'g1',
        'circleId': 'c1',
        'userId': 'u1',
        'role': 'owner',
        'status': 'joined',
        'createdAt': '2024-01-01T00:00:00.000Z',
        'updatedAt': '2024-01-02T00:00:00.000Z',
      });
      expect(m.id, 'm1');
    });
  });
}
