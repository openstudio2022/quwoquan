import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/feed_item_discovery_wire_map.dart';
import '../../../../../support/cloud_services/repository_mock_reexports.dart';

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

List<FeedItemDto> _contractItemsOfType(String type) => _contractDiscoveryItems()
    .where((item) => item.type == type)
    .toList(growable: false);

/// L1a 契约测试：PostDto — 覆盖 mock.yaml dto_scenarios
///
/// 三维度覆盖：
///   常规契约  — 正常输入 → 正确输出（字段解析、计算属性、类型分发）
///   单轨契约 — 拒绝旧字段/alias；round-trip 只输出 canonical 字段
///   异常/边界契约 — 缺字段/null 安全、全字段缺失不崩溃
void main() {
  // ──────────────────────────────────────────────────────────────────
  // 常规契约
  // ──────────────────────────────────────────────────────────────────
  group('PostDto — 常规契约', () {
    group('PhotoPostDto', () {
      test('fromMap parses canonical photo data including width/height', () {
        const raw = <String, dynamic>{
          'id': 'p1',
          'type': 'image',
          'authorId': 'auth1',
          'displayName': '摄影师',
          'avatarUrl': 'https://example.com/avatar.jpg',
          'coverUrl': 'https://example.com/cover.jpg',
          'imageUrls': [
            'https://example.com/img1.jpg',
            'https://example.com/img2.jpg',
          ],
          'width': 1200,
          'height': 800,
          'likeCount': 100,
          'commentCount': 10,
          'shareCount': 5,
          'createdAt': '2025-12-01T10:00:00Z',
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
          'id': 'p2',
          'type': 'image',
          'authorId': 'a',
          'displayName': 'A',
          'avatarUrl': '',
          'coverUrl': '',
          'width': 1920,
          'height': 1080,
          'publishedAt': '2025-01-01T00:00:00Z',
        };
        final dto = PhotoPostDto.fromMap(raw);
        expect(dto.aspectRatio, closeTo(1920 / 1080, 0.001));
      });

      test('contract fixture: all photo entries have dimensions', () {
        for (final item in _contractItemsOfType('image')) {
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
          'id': 'video_portrait',
          'type': 'video',
          'authorId': 'auth2',
          'displayName': '视频创作者',
          'avatarUrl': 'https://example.com/avatar2.jpg',
          'videoUrl': 'https://example.com/video.mp4',
          'thumbnailUrl': 'https://example.com/thumb.jpg',
          'width': 1080,
          'height': 1920,
          'durationMs': 30000,
          'likeCount': 500,
          'commentCount': 50,
          'shareCount': 20,
          'publishedAt': '2026-01-10T00:00:00Z',
        };
        final dto = VideoPostDto.fromMap(raw);
        expect(dto.id, equals('video_portrait'));
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
          'id': 'video_aspect_portrait',
          'type': 'video',
          'authorId': 'a',
          'displayName': 'A',
          'avatarUrl': '',
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

      test('contract fixture: all video entries have dimensions', () {
        for (final item in _contractItemsOfType('video')) {
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
          'id': 'art1',
          'type': 'article',
          'authorId': 'writer',
          'displayName': 'Tech Writer',
          'avatarUrl': 'https://example.com/avatar3.jpg',
          'title': '2026年AI趋势',
          'body': '文章摘要内容',
          'coverUrl': 'https://example.com/cover3.jpg',
          'likeCount': 1000,
          'commentCount': 80,
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
          'id': 'art_doc',
          'type': 'article',
          'authorId': 'writer',
          'displayName': 'Tech Writer',
          'avatarUrl': 'https://example.com/avatar3.jpg',
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

      test('contract article fixture: body non-empty，标题可留空', () {
        for (final item in _contractItemsOfType('article')) {
          final dto = ArticlePostDto.fromMap(item.toDiscoveryWireMap());
          expect(
            dto.normalizedBody,
            isNotEmpty,
            reason: 'postId=${item.id} should have non-empty body',
          );
        }
      });

      test('contract article fixture carries render metadata', () {
        final items = _contractItemsOfType('article');
        expect(items, isNotEmpty);
        expect(
          items.every(
            (item) =>
                (item.articleMarkdownDigest ?? '').isNotEmpty &&
                (item.articleRenderProfile ?? const <String, dynamic>{})
                    .isNotEmpty,
          ),
          isTrue,
        );
      });
    });

    group('MicroPostDto', () {
      test('fromMap parses text-only moment', () {
        const raw = <String, dynamic>{
          'id': 'm1',
          'type': 'micro',
          'authorId': 'user1',
          'displayName': '用户A',
          'avatarUrl': '',
          'body': '一条微趣文字',
          'publishedAt': '2026-01-14T10:00:00Z',
        };
        final dto = MicroPostDto.fromMap(raw);
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
          'id': 'm2',
          'type': 'micro',
          'authorId': 'user2',
          'displayName': '用户B',
          'avatarUrl': '',
          'body': '图文微趣',
          'imageUrls': [
            'https://example.com/img1.jpg',
            'https://example.com/img2.jpg',
          ],
          'publishedAt': '2026-01-13T08:00:00Z',
        };
        final dto = MicroPostDto.fromMap(raw);
        expect(dto.imageUrls.length, equals(2));
        expect(dto.displayFormat, equals('image'));
        expect(dto.hasImages, isTrue);
        expect(dto.hasVideo, isFalse);
      });

      test('fromMap parses video moment', () {
        const raw = <String, dynamic>{
          'id': 'm3',
          'type': 'micro',
          'authorId': 'user3',
          'displayName': '用户C',
          'avatarUrl': '',
          'body': '视频微趣',
          'videoUrl': 'https://example.com/video.mp4',
          'durationMs': 15000,
          'publishedAt': '2026-01-12T06:00:00Z',
        };
        final dto = MicroPostDto.fromMap(raw);
        expect(dto.videoUrl, equals('https://example.com/video.mp4'));
        expect(dto.durationMs, equals(15000));
        expect(dto.displayFormat, equals('video'));
        expect(dto.hasVideo, isTrue);
      });
    });

    group('ContentPostViewData polymorphism & contentPostViewDataFromReadModelMap dispatch', () {
      test('dispatches image contentType to PhotoPostDto', () {
        final dto = contentPostViewDataFromReadModelMap({
          'id': 'x',
          'type': 'image',
          'publishedAt': '2025-01-01T00:00:00Z',
        });
        expect(dto, isA<PhotoPostDto>());
      });

      test('dispatches video contentType to VideoPostDto', () {
        final dto = contentPostViewDataFromReadModelMap({
          'id': 'x',
          'type': 'video',
          'videoUrl': '',
          'thumbnailUrl': '',
          'publishedAt': '2025-01-01T00:00:00Z',
        });
        expect(dto, isA<VideoPostDto>());
      });

      test('dispatches article contentType to ArticlePostDto', () {
        final dto = contentPostViewDataFromReadModelMap({
          'id': 'x',
          'type': 'article',
          'publishedAt': '2025-01-01T00:00:00Z',
        });
        expect(dto, isA<ArticlePostDto>());
      });

      test('dispatches micro contentType to MicroPostDto', () {
        final dto = contentPostViewDataFromReadModelMap({
          'id': 'x',
          'type': 'micro',
          'publishedAt': '2025-01-01T00:00:00Z',
        });
        expect(dto, isA<MicroPostDto>());
      });

      test('mixed list of ContentPostViewData subtypes is type-safe', () {
        final rawList = _contractDiscoveryItems();
        final dtos = rawList
            .map((e) => contentPostViewDataFromReadModelMap(e.toDiscoveryWireMap()))
            .toList(growable: false);
        expect(dtos, isA<List<ContentPostViewData>>());

        final photos = dtos.whereType<PhotoPostDto>().toList();
        final videos = dtos.whereType<VideoPostDto>().toList();
        final moments = dtos.whereType<MicroPostDto>().toList();
        final articles = dtos.whereType<ArticlePostDto>().toList();

        expect(
          photos.length,
          equals(rawList.where((item) => item.type == 'image').length),
        );
        expect(
          videos.length,
          equals(rawList.where((item) => item.type == 'video').length),
        );
        expect(
          moments.length,
          equals(rawList.where((item) => item.type == 'micro').length),
        );
        expect(
          articles.length,
          equals(rawList.where((item) => item.type == 'article').length),
        );
      });

      test('base fields accessible via ContentPostViewData interface', () {
        final dtos = _contractItemsOfType(
          'image',
        ).map((e) => contentPostViewDataFromReadModelMap(e.toDiscoveryWireMap())).toList();
        for (final dto in dtos) {
          expect(dto.id, isNotEmpty);
          expect(dto.authorId, isNotEmpty);
          expect(dto.displayName, isNotEmpty);
        }
      });
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 单轨契约：拒旧 alias 键；round-trip 只认 canonical
  // ──────────────────────────────────────────────────────────────────
  group('PostDto — 单轨契约', () {
    test('PhotoPostDto: rejects imageWidth/imageHeight alias keys', () {
      const raw = <String, dynamic>{
        'id': 'p4',
        'type': 'image',
        'authorId': 'a',
        'displayName': 'A',
        'avatarUrl': '',
        'coverUrl': '',
        'imageWidth': 800,
        'imageHeight': 600,
        'publishedAt': '2025-01-01T00:00:00Z',
      };
      final dto = PhotoPostDto.fromMap(raw);
      expect(dto.width, isNull);
      expect(dto.height, isNull);
    });

    test('PhotoPostDto: toMap round-trip preserves width/height', () {
      const raw = <String, dynamic>{
        'id': 'p5',
        'type': 'image',
        'authorId': 'a',
        'displayName': 'A',
        'avatarUrl': '',
        'coverUrl': '',
        'width': 1080,
        'height': 720,
        'publishedAt': '2025-01-01T00:00:00Z',
      };
      final dto = PhotoPostDto.fromMap(raw);
      final map = dto.toPresentationMap();
      expect(map['width'], equals(1080));
      expect(map['height'], equals(720));
    });

    test('PhotoPostDto: copyWith updates width/height while preserving id', () {
      const raw = <String, dynamic>{
        'id': 'p6',
        'type': 'image',
        'authorId': 'a',
        'displayName': 'A',
        'avatarUrl': '',
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

    test('VideoPostDto: rejects videoWidth/videoHeight alias keys', () {
      const raw = <String, dynamic>{
        'id': 'video_alias_rejection',
        'type': 'video',
        'authorId': 'a',
        'displayName': 'A',
        'avatarUrl': '',
        'videoUrl': '',
        'thumbnailUrl': '',
        'videoWidth': 1920,
        'videoHeight': 1080,
        'publishedAt': '2026-01-01T00:00:00Z',
      };
      final dto = VideoPostDto.fromMap(raw);
      expect(dto.width, isNull);
      expect(dto.height, isNull);
    });

    test(
      'ContentPostViewData: rejects photo contentType alias (canonical is image)',
      () {
        expect(
          () => contentPostViewDataFromReadModelMap({
            'id': 'x',
            'type': 'photo',
            'publishedAt': '2025-01-01T00:00:00Z',
          }),
          throwsA(isA<ArgumentError>()),
        );
      },
    );
  });

  // ──────────────────────────────────────────────────────────────────
  // 异常/边界契约：缺字段/null 安全、全字段缺失不崩溃
  // ──────────────────────────────────────────────────────────────────
  group('PostDto — 异常/边界契约', () {
    test('PhotoPostDto: aspectRatio is null when width/height missing', () {
      const raw = <String, dynamic>{
        'id': 'p3',
        'type': 'image',
        'authorId': 'a',
        'displayName': 'A',
        'avatarUrl': '',
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
      'MicroPostDto: no images or video → hasImages and hasVideo are false',
      () {
        const raw = <String, dynamic>{
          'id': 'mx',
          'type': 'micro',
          'authorId': 'u',
          'displayName': 'U',
          'avatarUrl': '',
          'body': '纯文字',
          'publishedAt': '2026-01-01T00:00:00Z',
        };
        final dto = MicroPostDto.fromMap(raw);
        expect(dto.hasImages, isFalse);
        expect(dto.hasVideo, isFalse);
        expect(dto.imageUrls, isEmpty);
        expect(dto.videoUrl, isNull);
      },
    );

    test('contentPostViewDataFromReadModelMap: unknown contentType is rejected explicitly', () {
      expect(
        () => contentPostViewDataFromReadModelMap({
          'id': 'x',
          'type': 'unknown_type',
          'publishedAt': '2025-01-01T00:00:00Z',
        }),
        throwsArgumentError,
      );
    });
  });
}
