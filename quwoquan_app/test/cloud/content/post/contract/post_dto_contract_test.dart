import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/feed_item_discovery_wire_map.dart';
import 'package:quwoquan_app/cloud/services/content/mock/content_mock_data.dart';

/// L1a 契约测试：PostDto — 覆盖 mock.yaml dto_scenarios
///
/// 三维度覆盖：
///   常规契约  — 正常输入 → 正确输出（字段解析、计算属性、类型分发）
///   兼容性契约 — alias 字段/旧字段名仍正确解析；round-trip 稳定
///   异常/边界契约 — 缺字段/null 安全、全字段缺失不崩溃
void main() {
  // ──────────────────────────────────────────────────────────────────
  // 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('PostDto — 常规契约', () {
    group('PhotoPostDto', () {
      test('fromMap parses canonical photo data including width/height', () {
        const raw = <String, dynamic>{
          'postId': 'p1',
          'contentType': 'image',
          'authorId': 'auth1',
          'authorNickname': '摄影师',
          'authorAvatarUrl': 'https://example.com/avatar.jpg',
          'coverUrl': 'https://example.com/cover.jpg',
          'mediaUrls': [
            'https://example.com/img1.jpg',
            'https://example.com/img2.jpg',
          ],
          'width': 1200,
          'height': 800,
          'likeCount': 100,
          'commentCount': 10,
          'favoriteCount': 20,
          'shareCount': 5,
          'publishedAt': '2025-12-01T10:00:00Z',
        };
        final dto = PhotoPostDto.fromMap(raw);
        expect(dto.id, equals('p1'));
        expect(dto.type, equals('image'));
        expect(dto.authorId, equals('auth1'));
        expect(dto.displayName, equals('摄影师'));
        expect(dto.imageUrls.length, equals(2));
        expect(dto.identity, equals('work'));
        expect(dto.displayFormat, equals('image'));
        expect(dto.width, equals(1200));
        expect(dto.height, equals(800));
        expect(dto.likeCount, equals(100));
        expect(dto.createdAt.year, equals(2025));
      });

      test('aspectRatio computed from width/height', () {
        const raw = <String, dynamic>{
          'postId': 'p2',
          'contentType': 'image',
          'authorId': 'a',
          'displayName': 'A',
          'authorAvatarUrl': '',
          'coverUrl': '',
          'width': 1920,
          'height': 1080,
          'publishedAt': '2025-01-01T00:00:00Z',
        };
        final dto = PhotoPostDto.fromMap(raw);
        expect(dto.aspectRatio, closeTo(1920 / 1080, 0.001));
      });

      test('mock data: all photo entries have width > 0 and height > 0', () {
        for (final item in ContentMockData.discoveryPhotoData) {
          final dto = PhotoPostDto.fromMap(item.toDiscoveryWireMap());
          expect(
            dto.width,
            isNotNull,
            reason: 'postId=${item.id} should have width',
          );
          expect(
            dto.height,
            isNotNull,
            reason: 'postId=${item.id} should have height',
          );
          expect(
            dto.width!,
            greaterThan(0),
            reason: 'postId=${item.id} width should be > 0',
          );
          expect(
            dto.height!,
            greaterThan(0),
            reason: 'postId=${item.id} height should be > 0',
          );
        }
      });
    });

    group('VideoPostDto', () {
      test('fromMap parses canonical video data including width/height', () {
        const raw = <String, dynamic>{
          'postId': 'v1',
          'contentType': 'video',
          'authorId': 'auth2',
          'authorNickname': '视频创作者',
          'authorAvatarUrl': 'https://example.com/avatar2.jpg',
          'videoUrl': 'https://example.com/video.mp4',
          'thumbnailUrl': 'https://example.com/thumb.jpg',
          'width': 1080,
          'height': 1920,
          'durationMs': 30000,
          'likeCount': 500,
          'commentCount': 50,
          'favoriteCount': 80,
          'shareCount': 20,
          'publishedAt': '2026-01-10T00:00:00Z',
        };
        final dto = VideoPostDto.fromMap(raw);
        expect(dto.id, equals('v1'));
        expect(dto.type, equals('video'));
        expect(dto.videoUrl, equals('https://example.com/video.mp4'));
        expect(dto.thumbnailUrl, equals('https://example.com/thumb.jpg'));
        expect(dto.identity, equals('work'));
        expect(dto.displayFormat, equals('video'));
        expect(dto.width, equals(1080));
        expect(dto.height, equals(1920));
        expect(dto.durationMs, equals(30000));
        expect(dto.likeCount, equals(500));
      });

      test('aspectRatio for portrait video is less than 1', () {
        const raw = <String, dynamic>{
          'postId': 'v2',
          'contentType': 'video',
          'authorId': 'a',
          'displayName': 'A',
          'authorAvatarUrl': '',
          'videoUrl': '',
          'thumbnailUrl': '',
          'width': 1080,
          'height': 1920,
          'publishedAt': '2026-01-01T00:00:00Z',
        };
        final dto = VideoPostDto.fromMap(raw);
        expect(dto.aspectRatio, isNotNull);
        expect(dto.aspectRatio!, lessThan(1.0));
      });

      test('mock data: all video entries have width > 0 and height > 0', () {
        for (final item in ContentMockData.discoveryVideoData) {
          final dto = VideoPostDto.fromMap(item.toDiscoveryWireMap());
          expect(
            dto.width,
            isNotNull,
            reason: 'postId=${item.id} should have width',
          );
          expect(
            dto.height,
            isNotNull,
            reason: 'postId=${item.id} should have height',
          );
          expect(dto.width!, greaterThan(0));
          expect(dto.height!, greaterThan(0));
        }
      });
    });

    group('ArticlePostDto', () {
      test('fromMap parses canonical article data', () {
        const raw = <String, dynamic>{
          'postId': 'art1',
          'contentType': 'article',
          'authorId': 'writer',
          'displayName': 'Tech Writer',
          'authorAvatarUrl': 'https://example.com/avatar3.jpg',
          'title': '2026年AI趋势',
          'body': '文章摘要内容',
          'coverUrl': 'https://example.com/cover3.jpg',
          'likeCount': 1000,
          'commentCount': 80,
          'favoriteCount': 200,
          'shareCount': 150,
          'publishedAt': '2026-01-15T08:00:00Z',
        };
        final dto = ArticlePostDto.fromMap(raw);
        expect(dto.id, equals('art1'));
        expect(dto.type, equals('article'));
        expect(dto.identity, equals('work'));
        expect(dto.displayFormat, equals('note'));
        expect(dto.title, equals('2026年AI趋势'));
        expect(dto.body, equals('文章摘要内容'));
        expect(dto.coverUrl, equals('https://example.com/cover3.jpg'));
      });

      test('fromMap parses article presentation fields', () {
        const raw = <String, dynamic>{
          'postId': 'art_doc',
          'contentType': 'article',
          'authorId': 'writer',
          'displayName': 'Tech Writer',
          'authorAvatarUrl': 'https://example.com/avatar3.jpg',
          'title': '连续文档标题',
          'body': '文章摘要内容',
          'articleTemplate': 'journal',
          'articleFontPreset': 'handwritten',
          'publishedAt': '2026-01-15T08:00:00Z',
        };
        final dto = ArticlePostDto.fromMap(raw);
        expect(dto.articleTemplate, equals('journal'));
        expect(dto.articleFontPreset, equals('handwritten'));
      });

      test('mock article data: body non-empty，标题可留空', () {
        for (final item in ContentMockData.discoveryArticleData) {
          final dto = ArticlePostDto.fromMap(item.toDiscoveryWireMap());
          expect(
            dto.normalizedBody,
            isNotEmpty,
            reason: 'postId=${item.id} should have non-empty body',
          );
        }
      });

      test('canonical article mock 覆盖 5 模板 x 2 封面形态', () {
        expect(
          ContentMockData.discoveryArticleData.length,
          greaterThanOrEqualTo(10),
        );
        const templates = <String>[
          'gentle',
          'ritual',
          'diffuse',
          'journal',
          'tech',
        ];
        for (final template in templates) {
          final items = ContentMockData.discoveryArticleData
              .where((it) => it.articleTemplate == template)
              .toList(growable: false);
          expect(
            items.length,
            greaterThanOrEqualTo(2),
            reason: 'template=$template 至少要有有封面/无封面两种存在形态',
          );
          expect(
            items.any((it) => it.coverUrl.trim().isNotEmpty),
            isTrue,
            reason: 'template=$template 必须至少有 1 条有封面样本',
          );
          expect(
            items.any((it) => it.coverUrl.trim().isEmpty),
            isTrue,
            reason: 'template=$template 必须至少有 1 条无封面样本',
          );
          expect(
            items.every(
              (it) =>
                  it.articleDocument != null && it.articleDocument!.isNotEmpty,
            ),
            isTrue,
            reason: 'template=$template 的 canonical 样本必须带 articleDocument',
          );
        }
      });

      test('canonical article mock 覆盖封面/标题四种组合', () {
        final items = ContentMockData.discoveryArticleData;
        bool hasCase({required bool expectCover, required bool expectTitle}) {
          return items.any((it) {
            final hasCover = it.coverUrl.trim().isNotEmpty;
            final hasTitle = (it.title ?? '').trim().isNotEmpty;
            final hasBody = (it.body ?? '').trim().isNotEmpty;
            return hasBody &&
                hasCover == expectCover &&
                hasTitle == expectTitle;
          });
        }

        expect(hasCase(expectCover: true, expectTitle: true), isTrue);
        expect(hasCase(expectCover: false, expectTitle: true), isTrue);
        expect(hasCase(expectCover: true, expectTitle: false), isTrue);
        expect(hasCase(expectCover: false, expectTitle: false), isTrue);
      });
    });

    group('MomentPostDto', () {
      test('fromMap parses text-only moment', () {
        const raw = <String, dynamic>{
          'postId': 'm1',
          'contentType': 'micro',
          'authorId': 'user1',
          'displayName': '用户A',
          'authorAvatarUrl': '',
          'body': '一条微趣文字',
          'publishedAt': '2026-01-14T10:00:00Z',
        };
        final dto = MomentPostDto.fromMap(raw);
        expect(dto.id, equals('m1'));
        expect(dto.type, equals('micro'));
        expect(dto.identity, equals('moment'));
        expect(dto.displayFormat, equals('note'));
        expect(dto.body, equals('一条微趣文字'));
        expect(dto.imageUrls, isEmpty);
        expect(dto.videoUrl, isNull);
        expect(dto.hasImages, isFalse);
        expect(dto.hasVideo, isFalse);
      });

      test('fromMap parses image moment', () {
        const raw = <String, dynamic>{
          'postId': 'm2',
          'contentType': 'micro',
          'authorId': 'user2',
          'displayName': '用户B',
          'authorAvatarUrl': '',
          'body': '图文微趣',
          'mediaUrls': [
            'https://example.com/img1.jpg',
            'https://example.com/img2.jpg',
          ],
          'publishedAt': '2026-01-13T08:00:00Z',
        };
        final dto = MomentPostDto.fromMap(raw);
        expect(dto.imageUrls.length, equals(2));
        expect(dto.displayFormat, equals('image'));
        expect(dto.hasImages, isTrue);
        expect(dto.hasVideo, isFalse);
      });

      test('fromMap parses video moment', () {
        const raw = <String, dynamic>{
          'postId': 'm3',
          'contentType': 'micro',
          'authorId': 'user3',
          'displayName': '用户C',
          'authorAvatarUrl': '',
          'body': '视频微趣',
          'videoUrl': 'https://example.com/video.mp4',
          'durationMs': 15000,
          'publishedAt': '2026-01-12T06:00:00Z',
        };
        final dto = MomentPostDto.fromMap(raw);
        expect(dto.videoUrl, equals('https://example.com/video.mp4'));
        expect(dto.durationMs, equals(15000));
        expect(dto.displayFormat, equals('video'));
        expect(dto.hasVideo, isTrue);
      });
    });

    group('PostBaseDto polymorphism & postBaseDtoFromMap dispatch', () {
      test('dispatches image contentType to PhotoPostDto', () {
        final dto = postBaseDtoFromMap({
          'postId': 'x',
          'contentType': 'image',
          'publishedAt': '2025-01-01T00:00:00Z',
        });
        expect(dto, isA<PhotoPostDto>());
      });

      test('dispatches video contentType to VideoPostDto', () {
        final dto = postBaseDtoFromMap({
          'postId': 'x',
          'contentType': 'video',
          'videoUrl': '',
          'thumbnailUrl': '',
          'publishedAt': '2025-01-01T00:00:00Z',
        });
        expect(dto, isA<VideoPostDto>());
      });

      test('dispatches article contentType to ArticlePostDto', () {
        final dto = postBaseDtoFromMap({
          'postId': 'x',
          'contentType': 'article',
          'publishedAt': '2025-01-01T00:00:00Z',
        });
        expect(dto, isA<ArticlePostDto>());
      });

      test('dispatches micro contentType to MomentPostDto', () {
        final dto = postBaseDtoFromMap({
          'postId': 'x',
          'contentType': 'micro',
          'publishedAt': '2025-01-01T00:00:00Z',
        });
        expect(dto, isA<MomentPostDto>());
      });

      test('mixed list of PostBaseDto subtypes is type-safe', () {
        final rawList = [
          ...ContentMockData.discoveryPhotoData,
          ...ContentMockData.discoveryVideoData,
          ...ContentMockData.discoveryMomentData,
          ...ContentMockData.discoveryArticleData,
        ];
        final dtos = rawList
            .map((e) => postBaseDtoFromMap(e.toDiscoveryWireMap()))
            .toList(growable: false);
        expect(dtos, isA<List<PostBaseDto>>());

        final photos = dtos.whereType<PhotoPostDto>().toList();
        final videos = dtos.whereType<VideoPostDto>().toList();
        final moments = dtos.whereType<MomentPostDto>().toList();
        final articles = dtos.whereType<ArticlePostDto>().toList();

        expect(
          photos.length,
          equals(ContentMockData.discoveryPhotoData.length),
        );
        expect(
          videos.length,
          equals(ContentMockData.discoveryVideoData.length),
        );
        expect(
          moments.length,
          equals(ContentMockData.discoveryMomentData.length),
        );
        expect(
          articles.length,
          equals(ContentMockData.discoveryArticleData.length),
        );
      });

      test('base fields accessible via PostBaseDto interface', () {
        final dtos = ContentMockData.discoveryPhotoData
            .map((e) => postBaseDtoFromMap(e.toDiscoveryWireMap()))
            .toList();
        for (final dto in dtos) {
          expect(dto.id, isNotEmpty);
          expect(dto.authorId, isNotEmpty);
          expect(dto.displayName, isNotEmpty);
        }
      });
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 兼容性契约：旧字段名/alias 仍正确解析；round-trip 稳定
  // ──────────────────────────────────────────────────────────────────
  group('PostDto — 兼容性契约', () {
    test(
      'PhotoPostDto: alias imageWidth/imageHeight alternate field names',
      () {
        const raw = <String, dynamic>{
          'postId': 'p4',
          'contentType': 'image',
          'authorId': 'a',
          'displayName': 'A',
          'authorAvatarUrl': '',
          'coverUrl': '',
          'imageWidth': 800,
          'imageHeight': 600,
          'publishedAt': '2025-01-01T00:00:00Z',
        };
        final dto = PhotoPostDto.fromMap(raw);
        expect(dto.width, equals(800));
        expect(dto.height, equals(600));
      },
    );

    test('PhotoPostDto: toMap round-trip preserves width/height', () {
      const raw = <String, dynamic>{
        'postId': 'p5',
        'contentType': 'image',
        'authorId': 'a',
        'displayName': 'A',
        'authorAvatarUrl': '',
        'coverUrl': '',
        'width': 1080,
        'height': 720,
        'publishedAt': '2025-01-01T00:00:00Z',
      };
      final dto = PhotoPostDto.fromMap(raw);
      final map = dto.toMap();
      expect(map['width'], equals(1080));
      expect(map['height'], equals(720));
    });

    test('PhotoPostDto: copyWith updates width/height while preserving id', () {
      const raw = <String, dynamic>{
        'postId': 'p6',
        'contentType': 'image',
        'authorId': 'a',
        'displayName': 'A',
        'authorAvatarUrl': '',
        'coverUrl': '',
        'width': 800,
        'height': 600,
        'publishedAt': '2025-01-01T00:00:00Z',
      };
      final original = PhotoPostDto.fromMap(raw);
      final updated = original.copyWith(width: 1920, height: 1080);
      expect(updated.width, equals(1920));
      expect(updated.height, equals(1080));
      expect(updated.id, equals(original.id));
    });

    test(
      'VideoPostDto: alias videoWidth/videoHeight alternate field names',
      () {
        const raw = <String, dynamic>{
          'postId': 'v3',
          'contentType': 'video',
          'authorId': 'a',
          'displayName': 'A',
          'authorAvatarUrl': '',
          'videoUrl': '',
          'thumbnailUrl': '',
          'videoWidth': 1920,
          'videoHeight': 1080,
          'publishedAt': '2026-01-01T00:00:00Z',
        };
        final dto = VideoPostDto.fromMap(raw);
        expect(dto.width, equals(1920));
        expect(dto.height, equals(1080));
      },
    );

    test('PostBaseDto: dispatches photo contentType alias to PhotoPostDto', () {
      final dto = postBaseDtoFromMap({
        'postId': 'x',
        'contentType': 'photo',
        'publishedAt': '2025-01-01T00:00:00Z',
      });
      expect(dto, isA<PhotoPostDto>());
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 异常/边界契约：缺字段/null 安全、全字段缺失不崩溃
  // ──────────────────────────────────────────────────────────────────
  group('PostDto — 异常/边界契约', () {
    test('PhotoPostDto: aspectRatio is null when width/height missing', () {
      const raw = <String, dynamic>{
        'postId': 'p3',
        'contentType': 'image',
        'authorId': 'a',
        'displayName': 'A',
        'authorAvatarUrl': '',
        'coverUrl': '',
        'publishedAt': '2025-01-01T00:00:00Z',
      };
      final dto = PhotoPostDto.fromMap(raw);
      expect(dto.width, isNull);
      expect(dto.height, isNull);
      expect(dto.aspectRatio, isNull);
    });

    test(
      'PhotoPostDto: all fields missing → fromMap returns object without crash',
      () {
        expect(() => PhotoPostDto.fromMap(const {}), returnsNormally);
        final dto = PhotoPostDto.fromMap(const {});
        expect(dto.id, isEmpty);
        expect(dto.width, isNull);
        expect(dto.aspectRatio, isNull);
      },
    );

    test(
      'VideoPostDto: all fields missing → fromMap returns object without crash',
      () {
        expect(() => VideoPostDto.fromMap(const {}), returnsNormally);
        final dto = VideoPostDto.fromMap(const {});
        expect(dto.durationMs, isNull);
        expect(dto.aspectRatio, isNull);
      },
    );

    test(
      'MomentPostDto: no images or video → hasImages and hasVideo are false',
      () {
        const raw = <String, dynamic>{
          'postId': 'mx',
          'contentType': 'micro',
          'authorId': 'u',
          'displayName': 'U',
          'authorAvatarUrl': '',
          'body': '纯文字',
          'publishedAt': '2026-01-01T00:00:00Z',
        };
        final dto = MomentPostDto.fromMap(raw);
        expect(dto.hasImages, isFalse);
        expect(dto.hasVideo, isFalse);
        expect(dto.imageUrls, isEmpty);
        expect(dto.videoUrl, isNull);
      },
    );

    test('postBaseDtoFromMap: unknown contentType falls back gracefully', () {
      expect(
        () => postBaseDtoFromMap({
          'postId': 'x',
          'contentType': 'unknown_type',
          'publishedAt': '2025-01-01T00:00:00Z',
        }),
        returnsNormally,
      );
    });
  });
}
