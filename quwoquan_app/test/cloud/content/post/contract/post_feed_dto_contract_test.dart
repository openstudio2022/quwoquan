import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/content/mock/content_mock_data.dart';

/// L1a 契约测试：FeedItemDto — 覆盖 mock.yaml dto_scenarios
///
/// 三维度覆盖：
///   常规契约  — 四类内容 canonical 字段正确解析
///   兼容性契约 — alias 字段解析；toMap round-trip；copyWith 偏更新
///   异常/边界契约 — 缺字段降级为零值；全字段缺失不崩溃
void main() {
  // ──────────────────────────────────────────────────────────────────
  // 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('PostFeedDto — 常规契约', () {
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

    test('all mock data: id/authorId/displayName non-empty for every item', () {
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
  });

  // ──────────────────────────────────────────────────────────────────
  // 兼容性契约：旧字段/alias 仍正确解析；round-trip 稳定
  // ──────────────────────────────────────────────────────────────────
  group('PostFeedDto — 兼容性契约', () {
    test('resolves server-side alias fields: postId, authorNickname, likesCount', () {
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

    test('toMap round-trips canonical fields correctly', () {
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

    test('copyWith produces correct partial update while preserving other fields', () {
      final original = FeedItemDto.fromMap(ContentMockData.discoveryPhotoData.first);
      final updated = original.copyWith(likeCount: 9999, displayName: 'Updated Name');

      expect(updated.likeCount, equals(9999));
      expect(updated.displayName, equals('Updated Name'));
      expect(updated.id, equals(original.id));
      expect(updated.type, equals(original.type));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 异常/边界契约：缺字段降级为零值；全字段缺失不崩溃
  // ──────────────────────────────────────────────────────────────────
  group('PostFeedDto — 异常/边界契约', () {
    test('missing count fields fall back to zero', () {
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

    test('all fields missing → fromMap returns object without crash', () {
      expect(() => FeedItemDto.fromMap(const {}), returnsNormally);
    });

    test('nextCursor from CursorPage is non-empty when more data exists', () {
      // CursorPage.nextCursor is managed by ContentRepository, not FeedItemDto.
      // This test validates that CursorPage correctly stores and returns the cursor.
      const cursorValue = 'post_d1';
      final page = CursorPage<FeedItemDto>(
        items: [FeedItemDto.fromMap(ContentMockData.discoveryPhotoData.first)],
        nextCursor: cursorValue,
      );
      expect(page.nextCursor, equals(cursorValue),
          reason: 'nextCursor must be preserved in CursorPage for pagination');
      expect(page.items, isNotEmpty,
          reason: 'items must be non-empty when cursor is set');
    });

    test('CursorPage with null nextCursor indicates last page', () {
      final page = CursorPage<FeedItemDto>(
        items: [FeedItemDto.fromMap(ContentMockData.discoveryPhotoData.first)],
        // no nextCursor — this is the last page
      );
      expect(page.nextCursor, isNull,
          reason: 'null nextCursor signals the last page to the consumer');
    });

    test('null imageUrls field returns empty list (not null)', () {
      const raw = <String, dynamic>{
        'postId': 'x2',
        'contentType': 'image',
        'authorId': 'u1',
        'displayName': 'Test',
        'authorAvatarUrl': '',
        'imageUrls': null,
        'publishedAt': '2025-01-01T00:00:00Z',
      };
      final dto = FeedItemDto.fromMap(raw);
      expect(dto.imageUrls, isNotNull);
      expect(dto.imageUrls, isEmpty);
    });
  });
}
