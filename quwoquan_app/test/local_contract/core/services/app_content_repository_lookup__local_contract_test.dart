import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/app_content/app_content_repository_mock.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

void main() {
  group('discoveryPostsAsDtos', () {
    test('Mock 聚合 wire 后解析出非空 PostBaseDto 列表', () {
      final repo = MockAppContentRepository();
      final dtos = repo.discoveryPostsAsDtos;
      expect(dtos, isNotEmpty);
      final byId = {for (final p in dtos) p.id: p};
      expect(byId.containsKey('d1'), isTrue);
    });

    test('Remote 空 discovery 列表时返回空', () {
      final repo = RemoteAppContentRepository();
      expect(repo.discoveryPostsAsDtos, isEmpty);
    });
  });

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
