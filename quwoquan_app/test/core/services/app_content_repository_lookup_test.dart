import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/app_content/app_content_repository_mock.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

void main() {
  group('lookupDiscoveryPostBaseDto', () {
    test('与 lookupDiscoveryFeedWireRow 同一 postId 可解析为 DTO', () {
      final repo = MockAppContentRepository();
      const postId = 'd1';
      final row = lookupDiscoveryFeedWireRow(repo, postId);
      final dto = lookupDiscoveryPostBaseDto(repo, postId);
      expect(row, isNotNull);
      expect(dto, isNotNull);
      expect(dto!.id, postId);
    });

    test('不存在 id 时返回 null', () {
      final repo = MockAppContentRepository();
      expect(lookupDiscoveryPostBaseDto(repo, '__no_such_post__'), isNull);
    });
  });
}
