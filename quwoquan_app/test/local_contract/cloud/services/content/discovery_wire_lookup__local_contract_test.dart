import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';
import '../../../../support/cloud_services/content/mock_content_repository.dart';

List<FeedItemDto> _contractDiscoveryItems() {
  final posts = objectScenarioSeedReader.contentSeedSet()?['posts'];
  if (posts is! List) {
    throw StateError('content_discovery_core.posts fixture is missing');
  }
  return posts
      .whereType<Map>()
      .map((item) => FeedItemDto.fromReadModelMap(item.cast<String, dynamic>()))
      .toList(growable: false);
}

void main() {
  group('discovery_wire_lookup（test/support 迁移后）', () {
    test('findDiscoveryWireRowByPostId resolves postId key', () {
      final rows = aggregateDiscoveryWireSlices(
        photo: _contractDiscoveryItems()
            .where((item) => item.type == 'image')
            .take(1)
            .toList(growable: false),
        video: const <FeedItemDto>[],
        article: const <FeedItemDto>[],
        moment: const <FeedItemDto>[],
      );
      final row = findDiscoveryWireRowByPostId('fixture_photo_001', rows);
      expect(row, isNotNull);
      expect(row!['id'], 'fixture_photo_001');
    });

    test('lookupCanonicalDiscoveryWireRowByPostId resolves canonical row', () {
      final row = lookupCanonicalDiscoveryWireRowByPostId('m1');
      expect(row, isNotNull);
      expect(row!['id'], 'm1');
    });

    // 契约单轨：mockDiscoveryWireFallback / prototypeDiscoveryWireRowForMock
    // UI mock 桥已随 lib 侧 mock 本体删除（生产组合根 Remote-only），
    // 不再保留对应正向断言。
  });
}
