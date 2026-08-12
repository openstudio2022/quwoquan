import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/fixtures/object_contract_example_reader.dart';
import '../../../../../support/service/content_service/content/post/mock_content_repository.dart';

List<ContentPostViewData> _contractDiscoveryItems() {
  final posts = objectContractExampleReader.contentExample()?['posts'];
  if (posts is! List) {
    throw StateError('content_discovery_core.posts fixture is missing');
  }
  return posts
      .whereType<Map>()
      .map((raw) {
        final item = raw.cast<String, dynamic>();
        return ContentPostViewData.fromWire(
          ContentPostProjection(
            postId: item['postId']! as String,
            contentType: item['contentType']! as String,
            contentIdentity: item['contentIdentity'] as String?,
            authorId: item['authorId'] as String?,
            authorDisplayName: item['authorDisplayName'] as String?,
            authorAvatarUrl: item['authorAvatarUrl'] as String?,
            likeCount: item['likeCount']! as int,
            commentCount: item['commentCount']! as int,
            shareCount: item['shareCount']! as int,
          ),
        );
      })
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
        video: const <ContentPostViewData>[],
        article: const <ContentPostViewData>[],
        moment: const <ContentPostViewData>[],
      );
      final row = findDiscoveryWireRowByPostId('fixture_photo_001', rows);
      expect(row, isNotNull);
      expect(row!['postId'], 'fixture_photo_001');
    });

    test('lookupCanonicalDiscoveryWireRowByPostId resolves canonical row', () {
      final row = lookupCanonicalDiscoveryWireRowByPostId('m1');
      expect(row, isNotNull);
      expect(row!['postId'], 'm1');
    });

    // 契约单轨：mockDiscoveryWireFallback / prototypeDiscoveryWireRowForMock
    // UI mock 桥已随 lib 侧 mock 本体删除（生产组合根 Remote-only），
    // 不再保留对应正向断言。
  });
}
