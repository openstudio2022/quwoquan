import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';
import 'package:quwoquan_app/cloud/services/content/discovery_wire_lookup.dart';
import 'package:quwoquan_app/cloud/services/content/mock/content_mock_data.dart';

void main() {
  group('discovery_wire_lookup', () {
    test('findDiscoveryWireRowByPostId resolves postId key', () {
      final rows = aggregateDiscoveryWireSlices(
        photo: ContentMockData.discoveryPhotoData,
        video: const <FeedItemDto>[],
        article: const <FeedItemDto>[],
        moment: const <FeedItemDto>[],
      );
      final row = findDiscoveryWireRowByPostId('d1', rows);
      expect(row, isNotNull);
      expect(row!['postId'], 'd1');
    });

    test('lookupCanonicalDiscoveryWireRowByPostId uses ContentMockData', () {
      final row = lookupCanonicalDiscoveryWireRowByPostId('m1');
      expect(row, isNotNull);
      expect(row!['postId'], 'm1');
    });

    test('mockDiscoveryWireFallback mirrors remote when not mock', () {
      final canonical = ContentMockData.discoveryPhotoData;
      expect(mockDiscoveryWireFallback(false, canonical), isEmpty);
      final mapped = mockDiscoveryWireFallback(true, canonical);
      expect(mapped, isNotEmpty);
      expect(mapped.first['postId'], canonical.first.id);
    });

    test('prototypeDiscoveryWireRowForMock only when mock and non-empty id', () {
      expect(prototypeDiscoveryWireRowForMock(false, 'd1'), isNull);
      expect(prototypeDiscoveryWireRowForMock(true, ''), isNull);
      expect(prototypeDiscoveryWireRowForMock(true, 'd1'), isNotNull);
    });
  });
}
