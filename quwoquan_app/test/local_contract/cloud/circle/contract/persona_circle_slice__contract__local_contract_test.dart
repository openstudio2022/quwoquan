// spec_ref: specs/feature-tree/circle-community/circle-management-and-stats/spec.md#sit-002

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('PersonaCircleSlice decodes canonical fields into generated enums', () {
    final page = decodePersonaCirclePageSlice(<String, Object?>{
      'items': <Object?>[_personaCircle()],
      'cursor': null,
    });

    final circle = page.items.single;
    expect(circle.status, CircleStatus.active);
    expect(circle.visibility, CircleVisibility.inviteOnly);
    expect(circle.joinPolicy, CircleJoinPolicy.approval);
    expect(circle.kind, CircleKind.organization);
    expect(circle.displaySubjectType, CircleDisplaySubjectType.school);
    expect(circle.linkedHomepageType, HomepageType.university);
  });

  test('PersonaCircleSlice rejects the retired state wire alias', () {
    final circle = _personaCircle()
      ..['state'] = 'active'
      ..remove('status');

    expect(
      () => decodePersonaCirclePageSlice(<String, Object?>{
        'items': <Object?>[circle],
        'cursor': null,
      }),
      throwsFormatException,
    );
  });

  test(
    'PersonaCircleSlice fails closed for an unknown canonical enum value',
    () {
      final circle = _personaCircle()..['visibility'] = 'followers_only';

      expect(
        () => decodePersonaCirclePageSlice(<String, Object?>{
          'items': <Object?>[circle],
          'cursor': null,
        }),
        throwsFormatException,
      );
    },
  );
}

Map<String, Object?> _personaCircle() => <String, Object?>{
  'circleId': 'circle-1',
  'name': '旅行社群',
  'description': '一起看世界',
  'coverUrl': 'https://example.com/cover.jpg',
  'iconUrl': 'https://example.com/icon.jpg',
  'ownerPersonaId': 'persona-owner',
  'ownerDisplayNameSnapshot': '圈主',
  'category': 'travel',
  'subCategory': 'campus',
  'tags': <Object?>['旅行', '校园'],
  'memberCount': 12,
  'postCount': 7,
  'weeklyActiveCount': 5,
  'status': 'active',
  'visibility': 'invite_only',
  'joinPolicy': 'approval',
  'kind': 'organization',
  'displaySubjectType': 'school',
  'followEnabled': true,
  'defaultPublicGroupId': 'group-public',
  'linkedHomepageId': 'homepage-1',
  'linkedHomepageType': 'university',
  'linkedHomepageTitle': '示例大学',
  'createdAt': '2026-07-28T00:00:00Z',
  'updatedAt': '2026-07-28T00:01:00Z',
};
