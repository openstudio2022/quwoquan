import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/micro_post_dto.g.dart';
import 'package:quwoquan_app/cloud/services/content/feed_item_discovery_wire_map.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';

/// V1-A/V1-E/V1-H T1：交集理由强类型贯通 FeedItemDto → wire → MicroPostDto。
///
/// 特性树：content-intersection-reason
void main() {
  group('MicroPostDto.intersectionReasons', () {
    test('从 wire map 解析为强类型 List<IntersectionReason>', () {
      final dto = MicroPostDto.fromMap(<String, dynamic>{
        'postId': 'm-test',
        'contentType': 'micro',
        'authorId': 'u1',
        'body': 'hello',
        'intersectionReasons': [
          {
            'dimension': 'identity',
            'tagRefs': ['identity/campus/xdf'],
            'displayText': '你和 TA 都来自新东方校友圈',
            'sharedCount': 3,
            'source': 'identity',
          },
        ],
      });

      expect(dto.intersectionReasons, isNotNull);
      expect(dto.intersectionReasons!.length, 1);
      final reason = dto.intersectionReasons!.first;
      expect(reason.dimension, 'identity');
      expect(reason.displayText, '你和 TA 都来自新东方校友圈');
      expect(reason.tagRefs, contains('identity/campus/xdf'));
    });

    test('无交集来源时为 null（内容卡无来源不展示）', () {
      final dto = MicroPostDto.fromMap(<String, dynamic>{
        'postId': 'm-empty',
        'contentType': 'micro',
        'authorId': 'u1',
        'body': 'hello',
      });

      expect(dto.intersectionReasons, isNull);
    });

    test('content 维度（Topic/旅行）解析为强类型（T4 旅行内容命中）', () {
      final dto = MicroPostDto.fromMap(<String, dynamic>{
        'postId': 'm-travel-content',
        'contentType': 'micro',
        'authorId': 'u1',
        'body': '去了趟洱海',
        'intersectionReasons': [
          {
            'dimension': 'content',
            'tagRefs': ['Topic/旅行'],
            'displayText': '你和 TA 都在聊 旅行',
            'sharedCount': 12,
            'source': 'tagRef',
          },
        ],
      });

      final reason = dto.intersectionReasons!.single;
      expect(reason.dimension, 'content');
      expect(reason.tagRefs, contains('Topic/旅行'));
      expect(reason.displayText, '你和 TA 都在聊 旅行');
    });

    test('FeedItemDto → 发现 wire → MicroPostDto 往返保留交集理由', () {
      final feedItem = FeedItemDto.fromMap(<String, dynamic>{
        'postId': 'm-roundtrip',
        'contentType': 'micro',
        'authorId': 'u1',
        'body': '左边董宇辉右边俞敏洪',
        'intersectionReasons': [
          {
            'dimension': 'location',
            'tagRefs': ['location/geo/west-lake'],
            'displayText': '你和 TA 都去过 西湖',
            'sharedCount': 5,
            'source': 'location',
          },
        ],
      });

      final wire = feedItem.toDiscoveryWireMap();
      final dto = MicroPostDto.fromMap(wire);

      expect(dto.intersectionReasons, isNotNull);
      expect(dto.intersectionReasons!.single.displayText, '你和 TA 都去过 西湖');
      expect(dto.intersectionReasons!.single.dimension, 'location');
    });
  });
}
