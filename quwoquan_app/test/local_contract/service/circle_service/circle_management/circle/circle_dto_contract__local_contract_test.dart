import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/domain/circle_edit_submit_payload.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/domain/circle_stats_view_data.dart';
import 'package:quwoquan_cloud_contracts/generated/circle_contracts.dart';

// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-001

void main() {
  group('Circle canonical wire owner', () {
    test('generated Circle is the only Circle wire decoder', () {
      final wire = Circle.fromWire(<String, Object?>{
        'id': 'circle-1',
        'name': '旅行摄影',
        'description': '同行创作群组',
        'ownerId': 'persona-owner',
        'category': 'travel',
        'tags': <String>['travel', 'photography'],
        'memberCount': 42,
        'postCount': 100,
        'weeklyActiveCount': 15,
        'version': 3,
        'status': 'active',
        'visibility': 'public',
        'joinPolicy': 'open',
        'kind': 'interest',
        'displaySubjectType': 'circle',
        'followEnabled': true,
        'autoSyncChat': true,
        'sectionConfig': <Object?>[
          <String, Object?>{
            'sectionType': 'works',
            'visible': true,
            'order': 0,
          },
        ],
        'storageUsedBytes': 1024,
        'storageQuotaBytes': 1073741824,
        'domainId': 'travel',
        'createdAt': '2025-01-01T00:00:00.000Z',
        'updatedAt': '2025-06-01T00:00:00.000Z',
      });

      expect(wire.id, 'circle-1');
      expect(wire.name, '旅行摄影');
      expect(wire.tags, <String>['travel', 'photography']);
      expect(wire.memberCount, 42);
      expect(wire.sectionConfig, hasLength(1));
      expect(wire.sectionConfig!.single.sectionType, CircleSectionType.works);
      expect(wire.createdAt, DateTime.utc(2025));
    });

    test(
      'generated Circle rejects storage aliases and missing canonical id',
      () {
        expect(
          () => Circle.fromWire(<String, Object?>{
            '_id': 'mongo-id',
            'name': 'invalid',
          }),
          throwsFormatException,
        );
      },
    );

    test(
      'generated Circle rejects unknown fields instead of ignoring them',
      () {
        final canonical = _minimalCircleWire()..['cover'] = 'retired-cover';
        expect(() => Circle.fromWire(canonical), throwsFormatException);
      },
    );
  });

  group('Circle embedded value mapping', () {
    test('generated CircleSectionConfig is the only wire decoder', () {
      final wire = CircleSectionConfig.fromWire(<String, Object?>{
        'sectionType': 'members',
        'visible': false,
        'order': 2,
        'customTitle': '同行者',
      });

      final view = CircleSectionEditValue.fromWire(wire);
      expect(view.sectionType, CircleSectionType.members);
      expect(view.visible, isFalse);
      expect(view.order, 2);
      expect(view.customTitle, '同行者');
    });

    test('generated embedded value rejects missing fields', () {
      expect(
        () => CircleSectionConfig.fromWire(const <String, Object?>{}),
        throwsFormatException,
      );
    });
  });

  group('Circle stats generated projection', () {
    test('generated CircleStatsWire maps to page ViewData', () {
      final wire = CircleStatsWire.fromWire(<String, Object?>{
        'circleId': 'circle-1',
        'memberCount': 10,
        'postCount': 20,
        'discussionCount': 4,
        'weeklyActiveCount': 3,
        'likeCount': 99,
        'storageUsedBytes': 100,
        'storageQuotaBytes': 1000,
      });

      final view = CircleStatsViewData.fromWire(wire);
      expect(view.members, 10);
      expect(view.posts, 20);
      expect(view.discussions, 4);
      expect(view.weeklyActive, 3);
      expect(view.likes, 99);
    });

    test('generated stats rejects retired aliases', () {
      expect(
        () => CircleStatsWire.fromWire(<String, Object?>{
          'circleId': 'circle-1',
          'totalMembers': 10,
          'totalPosts': 20,
          'totalLikes': 99,
        }),
        throwsFormatException,
      );
    });
  });
}

Map<String, Object?> _minimalCircleWire() => <String, Object?>{
  'id': 'circle-1',
  'name': '旅行摄影',
  'ownerId': 'persona-owner',
  'memberCount': 0,
  'postCount': 0,
  'weeklyActiveCount': 0,
  'version': 1,
  'status': 'active',
  'visibility': 'public',
  'joinPolicy': 'open',
  'kind': 'interest',
  'displaySubjectType': 'circle',
  'followEnabled': true,
  'autoSyncChat': true,
  'storageUsedBytes': 0,
  'storageQuotaBytes': 1073741824,
  'createdAt': '2025-01-01T00:00:00.000Z',
  'updatedAt': '2025-01-01T00:00:00.000Z',
};
