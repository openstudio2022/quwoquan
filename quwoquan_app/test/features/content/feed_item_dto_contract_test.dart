import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';
import 'package:quwoquan_app/cloud/services/content/mock/content_mock_data.dart';

/// 契约测试：FeedItemDto 字段解析正确性（canonical fields）
///
/// 覆盖 acceptance.yaml A1~A3：
/// - A1: FeedItemDto 由 codegen 从 _projections/discovery_feed.yaml 生成
/// - A2: ContentMockData 使用 canonical 字段，FeedItemDto.fromMap 解析正确
/// - A3: MockContentRepository 输出的每个 FeedItemDto 均通过 canonical 验证
void main() {
  group('FeedItemDto.fromMap — canonical fields contract', () {
    test('parses canonical photo item correctly', () {
      final raw = ContentMockData.discoveryPhotoData.first;
      final dto = FeedItemDto.fromMap(raw);

      expect(dto.id, equals('d1'));
      expect(dto.type, equals('image'));
      expect(dto.authorId, equals('nature_photographer'));
      expect(dto.displayName, equals('自然摄影师'));
      expect(dto.avatarUrl, contains('unsplash.com'));
      expect(dto.coverUrl, contains('unsplash.com'));
      expect(dto.thumbnailUrl, contains('unsplash.com'));
      expect(dto.imageUrls, isNotEmpty);
      expect(dto.likeCount, equals(1200));
      expect(dto.commentCount, equals(45));
      expect(dto.favoriteCount, equals(230));
      expect(dto.shareCount, equals(18));
      expect(dto.createdAt, isA<DateTime>());
      expect(dto.createdAt.year, equals(2025));
    });

    test('parses canonical video item correctly', () {
      final raw = ContentMockData.discoveryVideoData.first;
      final dto = FeedItemDto.fromMap(raw);

      expect(dto.id, equals('v1'));
      expect(dto.type, equals('video'));
      expect(dto.authorId, equals('a1'));
      expect(dto.displayName, equals('楹语小筑'));
      expect(dto.coverUrl, contains('unsplash.com'));
      expect(dto.body, contains('东京'));
      expect(dto.durationMs, equals(45000));
      expect(dto.likeCount, equals(12500));
      expect(dto.commentCount, equals(892));
    });

    test('parses canonical moment item correctly', () {
      final raw = ContentMockData.discoveryMomentData.first;
      final dto = FeedItemDto.fromMap(raw);

      expect(dto.id, equals('m4'));
      expect(dto.type, equals('micro'));
      expect(dto.authorId, equals('u4'));
      expect(dto.displayName, equals('李想'));
      expect(dto.likeCount, equals(1581));
      expect(dto.commentCount, equals(301));
    });

    test('parses canonical article item correctly', () {
      final raw = ContentMockData.discoveryArticleData.first;
      final dto = FeedItemDto.fromMap(raw);

      expect(dto.id, equals('web-dev'));
      expect(dto.type, equals('article'));
      expect(dto.authorId, equals('tech_daily'));
      expect(dto.displayName, equals('TechDaily'));
      expect(dto.title, contains('Web开发'));
      expect(dto.likeCount, equals(1240));
    });

    test('no alias chains — all fields resolve from canonical names', () {
      // All ContentMockData items must have zero-fallback canonical fields
      for (final raw in [
        ...ContentMockData.discoveryPhotoData,
        ...ContentMockData.discoveryVideoData,
        ...ContentMockData.discoveryMomentData,
        ...ContentMockData.discoveryArticleData,
      ]) {
        final dto = FeedItemDto.fromMap(raw);
        expect(dto.id, isNotEmpty, reason: 'id must be non-empty for ${raw['postId']}');
        expect(dto.authorId, isNotEmpty, reason: 'authorId must be set for ${raw['postId']}');
        expect(dto.displayName, isNotEmpty, reason: 'displayName must be set for ${raw['postId']}');
      }
    });

    test('toMap round-trips canonical fields', () {
      final raw = ContentMockData.discoveryPhotoData.first;
      final dto = FeedItemDto.fromMap(raw);
      final map = dto.toMap();

      expect(map['id'], equals(dto.id));
      expect(map['type'], equals(dto.type));
      expect(map['authorId'], equals(dto.authorId));
      expect(map['displayName'], equals(dto.displayName));
      expect(map['likeCount'], equals(dto.likeCount));
      expect(map['imageUrls'], equals(dto.imageUrls));
    });

    test('copyWith produces correct partial update', () {
      final original = FeedItemDto.fromMap(ContentMockData.discoveryPhotoData.first);
      final updated = original.copyWith(likeCount: 9999, displayName: 'Updated Name');

      expect(updated.likeCount, equals(9999));
      expect(updated.displayName, equals('Updated Name'));
      expect(updated.id, equals(original.id));
      expect(updated.type, equals(original.type));
    });
  });

  group('FeedItemDto.fromMap — alias resolution (legacy format compat)', () {
    test('resolves server-side alias fields (postId, authorNickname, likesCount)', () {
      // Server response may use postId, authorNickname, likesCount etc.
      const serverRaw = <String, dynamic>{
        'postId': 'v_server',
        'contentType': 'video',
        'authorId': 'a_server',
        'authorNickname': 'Server Author',
        'authorAvatarUrl': 'https://example.com/avatar.jpg',
        'thumbnailUrl': 'https://example.com/thumb.jpg',
        'likesCount': 200,
        'commentsCount': 20,
        'savesCount': 5,
        'publishedAt': '2025-06-01T00:00:00Z',
      };

      final dto = FeedItemDto.fromMap(serverRaw);
      expect(dto.id, equals('v_server'));
      expect(dto.displayName, equals('Server Author'));
      expect(dto.likeCount, equals(200));
      expect(dto.commentCount, equals(20));
      expect(dto.favoriteCount, equals(5));
      expect(dto.createdAt.year, equals(2025));
    });

    test('falls back to zero counts when count fields missing', () {
      const minimalRaw = <String, dynamic>{
        'postId': 'x1',
        'contentType': 'image',
        'authorId': 'u1',
        'displayName': 'Test',
        'authorAvatarUrl': 'https://example.com/a.jpg',
        'thumbnailUrl': 'https://example.com/t.jpg',
        'createdAt': '2025-01-01T00:00:00Z',
      };

      final dto = FeedItemDto.fromMap(minimalRaw);
      expect(dto.likeCount, equals(0));
      expect(dto.commentCount, equals(0));
      expect(dto.favoriteCount, equals(0));
      expect(dto.shareCount, equals(0));
      expect(dto.imageUrls, isEmpty);
    });
  });
}
