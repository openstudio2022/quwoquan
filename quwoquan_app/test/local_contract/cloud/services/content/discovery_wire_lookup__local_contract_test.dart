import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';
import '../../../../support/cloud_services/content/mock_content_repository.dart';
import '../../../../support/cloud_services/content/content_mock_data.dart';

void main() {
  group('discovery_wire_lookup（test/support 迁移后）', () {
    test('findDiscoveryWireRowByPostId resolves postId key', () {
      final rows = aggregateDiscoveryWireSlices(
        photo: ContentMockData.discoveryPhotoData,
        video: const <FeedItemDto>[],
        article: const <FeedItemDto>[],
        moment: const <FeedItemDto>[],
      );
      final row = findDiscoveryWireRowByPostId('d1', rows);
      expect(row, isNotNull);
      expect(row!['id'], 'd1');
    });

    test('lookupCanonicalDiscoveryWireRowByPostId uses ContentMockData', () {
      final row = lookupCanonicalDiscoveryWireRowByPostId('m1');
      expect(row, isNotNull);
      expect(row!['id'], 'm1');
    });

    // 契约单轨：mockDiscoveryWireFallback / prototypeDiscoveryWireRowForMock
    // UI mock 桥已随 lib 侧 mock 本体删除（生产组合根 Remote-only），
    // 不再保留对应正向断言。
  });
}
