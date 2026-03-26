import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/mock/content_mock_data.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/post_view_projection.dart';

/// 投射契约测试：projectPostMap（→ PostSummaryView）/ projectArticleDetailView（→ ArticleDetailView）
///
/// 守护目标：
/// - DTO 字段变更后，投射输出的强类型字段必须第一时间失败，不悄悄回归。
/// - 覆盖"0→1 bug"：真实计数必须被忠实投射，不被归零后再 +1。
/// - 覆盖别名兼容：旧字段名（likesCount/commentsCount/savesCount）须被正确归一。
/// - 覆盖 mock 数据全量：每条 mock 数据均可无异常投射。
void main() {
  // ─────────────────────────────────────────────────────────────────────────
  // 辅助：构造最小合法 Photo/Video/Article raw map
  // ─────────────────────────────────────────────────────────────────────────
  const Map<String, dynamic> minPhoto = {
    'postId': 'ph1',
    'contentType': 'image',
    'authorId': 'auth1',
    'displayName': '摄影师',
    'authorAvatarUrl': 'https://example.com/avatar.jpg',
    'coverUrl': 'https://example.com/cover.jpg',
    'mediaUrls': [
      'https://example.com/img1.jpg',
      'https://example.com/img2.jpg',
    ],
    'width': 1200,
    'height': 900,
    'likeCount': 100,
    'commentCount': 20,
    'favoriteCount': 30,
    'shareCount': 5,
    'publishedAt': '2025-12-01T10:00:00Z',
  };

  const Map<String, dynamic> minVideo = {
    'postId': 'vd1',
    'contentType': 'video',
    'authorId': 'vauth1',
    'displayName': '视频创作者',
    'authorAvatarUrl': 'https://example.com/vavatar.jpg',
    'videoUrl': 'https://example.com/video.mp4',
    'thumbnailUrl': 'https://example.com/thumb.jpg',
    'width': 1080,
    'height': 1920,
    'durationMs': 45000,
    'likeCount': 500,
    'commentCount': 80,
    'favoriteCount': 120,
    'shareCount': 25,
    'publishedAt': '2026-01-10T00:00:00Z',
  };

  const Map<String, dynamic> minArticle = {
    'postId': 'art1',
    'contentType': 'article',
    'authorId': 'writer1',
    'displayName': '技术作者',
    'authorAvatarUrl': 'https://example.com/wavatar.jpg',
    'title': '2026年技术趋势',
    'body': '这是文章内容，包含多段落...',
    'coverUrl': 'https://example.com/cover3.jpg',
    'likeCount': 1000,
    'commentCount': 90,
    'favoriteCount': 200,
    'shareCount': 150,
    'publishedAt': '2026-01-15T08:00:00Z',
  };

  // ─────────────────────────────────────────────────────────────────────────
  // projectPostMap → PostSummaryView 公共字段
  // ─────────────────────────────────────────────────────────────────────────
  group('projectPostMap → PostSummaryView 公共字段投射', () {
    test('id 来自 DTO.id（postId 字段）', () {
      final r = projectPostMap(minPhoto);
      expect(r, isA<PostSummaryView>());
      expect(r.id, equals('ph1'));
    });

    test('type 来自 DTO.type', () {
      final r = projectPostMap(minPhoto);
      expect(r.type, isNotEmpty);
    });

    test('authorId 来自 DTO.authorId', () {
      final r = projectPostMap(minPhoto);
      expect(r.authorId, equals('auth1'));
    });

    test('displayName 来自 DTO.displayName', () {
      final r = projectPostMap(minPhoto);
      expect(r.displayName, equals('摄影师'));
    });

    test('avatarUrl 来自 DTO.avatarUrl', () {
      final r = projectPostMap(minPhoto);
      expect(r.avatarUrl, equals('https://example.com/avatar.jpg'));
    });

    test('author 子对象包含 id/username/name/avatar', () {
      final r = projectPostMap(minPhoto);
      expect(r.author, isA<PostAuthorSummary>());
      expect(r.author.id, equals('auth1'));
      expect(r.author.username, equals('auth1'));
      expect(r.author.name, equals('摄影师'));
      expect(r.author.avatar, equals('https://example.com/avatar.jpg'));
    });

    test('authorBackgroundUrl 投射到 backgroundImage', () {
      final raw = Map<String, dynamic>.from(minPhoto)
        ..['authorBackgroundUrl'] = 'https://example.com/bg.jpg';
      final r = projectPostMap(raw);
      expect(r.backgroundImage, equals('https://example.com/bg.jpg'));
    });

    test('createdAt 是 ISO8601 字符串', () {
      final r = projectPostMap(minPhoto);
      expect(r.createdAt, isA<String>());
      expect(() => DateTime.parse(r.createdAt), returnsNormally);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // projectPostMap — 计数字段（0→1 回归守护核心）
  // ─────────────────────────────────────────────────────────────────────────
  group('projectPostMap → PostSummaryView 计数字段 & 0→1 回归', () {
    test('likeCount → likesCount 忠实保留原始计数', () {
      final r = projectPostMap(minPhoto);
      expect(r.likesCount, equals(100), reason: '投射不得把 100 归零：0→1 bug');
    });

    test('commentCount → commentsCount 忠实保留原始计数', () {
      final r = projectPostMap(minPhoto);
      expect(r.commentsCount, equals(20));
    });

    test('favoriteCount → savesCount 忠实保留原始计数', () {
      final r = projectPostMap(minPhoto);
      expect(r.savesCount, equals(30));
    });

    test('shareCount → sharesCount 忠实保留原始计数', () {
      final r = projectPostMap(minPhoto);
      expect(r.sharesCount, equals(5));
    });

    test('大数值计数也能忠实保留（不截断）', () {
      final raw = Map<String, dynamic>.from(minPhoto)..['likeCount'] = 999999;
      final r = projectPostMap(raw);
      expect(r.likesCount, equals(999999));
    });

    test('别名输入 likesCount 也能正确投射', () {
      final raw = <String, dynamic>{
        'postId': 'alias1',
        'contentType': 'image',
        'authorId': 'a',
        'displayName': 'A',
        'authorAvatarUrl': '',
        'coverUrl': '',
        'likesCount': 200,
        'commentsCount': 10,
        'savesCount': 40,
        'publishedAt': '2025-01-01T00:00:00Z',
      };
      final r = projectPostMap(raw);
      expect(
        r.likesCount,
        equals(200),
        reason: 'likesCount alias 必须被 DTO 正确归一',
      );
      expect(r.commentsCount, equals(10));
      expect(r.savesCount, equals(40));
    });

    test('计数字段缺失时默认为 0，不抛异常', () {
      final raw = <String, dynamic>{
        'postId': 'no_counts',
        'contentType': 'image',
        'authorId': 'a',
        'displayName': 'A',
        'authorAvatarUrl': '',
        'coverUrl': '',
        'publishedAt': '2025-01-01T00:00:00Z',
      };
      final r = projectPostMap(raw);
      expect(r.likesCount, equals(0));
      expect(r.commentsCount, equals(0));
      expect(r.savesCount, equals(0));
      expect(r.sharesCount, equals(0));
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // projectPostMap — Photo 专属字段
  // ─────────────────────────────────────────────────────────────────────────
  group('projectPostMap → PostSummaryView Photo 专属字段', () {
    test('images 来自 DTO.imageUrls（mediaUrls）', () {
      final r = projectPostMap(minPhoto);
      expect(r.images, isNotNull);
      expect(r.images!.length, equals(2));
      expect(r.images!.first, contains('img1.jpg'));
    });

    test('thumbnail / thumbnailUrl / coverUrl 均来自 DTO.coverUrl', () {
      final r = projectPostMap(minPhoto);
      expect(r.thumbnail, equals('https://example.com/cover.jpg'));
      expect(r.thumbnailUrl, equals('https://example.com/cover.jpg'));
      expect(r.coverUrl, equals('https://example.com/cover.jpg'));
    });

    test('aspectRatio 来自 DTO 计算（width/height）', () {
      final r = projectPostMap(minPhoto);
      expect(r.aspectRatio, isNotNull);
      expect(r.aspectRatio!, closeTo(1200 / 900, 0.001));
    });

    test('无宽高时 aspectRatio 为 null', () {
      final raw = <String, dynamic>{
        'postId': 'no_dim',
        'contentType': 'image',
        'authorId': 'a',
        'displayName': 'A',
        'authorAvatarUrl': '',
        'coverUrl': 'https://example.com/c.jpg',
        'publishedAt': '2025-01-01T00:00:00Z',
      };
      final r = projectPostMap(raw);
      expect(r.aspectRatio, isNull);
    });

    test('imageWidth/imageHeight 别名也能计算 aspectRatio', () {
      final raw = <String, dynamic>{
        'postId': 'alias_dim',
        'contentType': 'image',
        'authorId': 'a',
        'displayName': 'A',
        'authorAvatarUrl': '',
        'coverUrl': '',
        'imageWidth': 800,
        'imageHeight': 600,
        'publishedAt': '2025-01-01T00:00:00Z',
      };
      final r = projectPostMap(raw);
      expect(r.aspectRatio!, closeTo(800 / 600, 0.001));
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // projectPostMap — Video 专属字段
  // ─────────────────────────────────────────────────────────────────────────
  group('projectPostMap → PostSummaryView Video 专属字段', () {
    test('videoUrl 来自 DTO.videoUrl', () {
      final r = projectPostMap(minVideo);
      expect(r.videoUrl, equals('https://example.com/video.mp4'));
    });

    test('thumbnail / thumbnailUrl / coverUrl 均来自 DTO.thumbnailUrl', () {
      final r = projectPostMap(minVideo);
      expect(r.thumbnail, equals('https://example.com/thumb.jpg'));
      expect(r.thumbnailUrl, equals('https://example.com/thumb.jpg'));
      expect(r.coverUrl, equals('https://example.com/thumb.jpg'));
    });

    test('duration 来自 DTO.durationMs', () {
      final r = projectPostMap(minVideo);
      expect(r.duration, equals(45000));
    });

    test('视频计数字段正确投射', () {
      final r = projectPostMap(minVideo);
      expect(r.likesCount, equals(500));
      expect(r.commentsCount, equals(80));
      expect(r.savesCount, equals(120));
      expect(r.sharesCount, equals(25));
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // projectPostMap — Article 专属字段
  // ─────────────────────────────────────────────────────────────────────────
  group('projectPostMap → PostSummaryView Article 专属字段', () {
    test('title 来自 DTO.title', () {
      final r = projectPostMap(minArticle);
      expect(r.title, equals('2026年技术趋势'));
    });

    test('body 来自 DTO.body', () {
      final r = projectPostMap(minArticle);
      expect(r.body, equals('这是文章内容，包含多段落...'));
    });

    test('coverUrl/thumbnailUrl 来自 DTO.coverUrl', () {
      final r = projectPostMap(minArticle);
      expect(r.coverUrl, equals('https://example.com/cover3.jpg'));
      expect(r.thumbnailUrl, equals('https://example.com/cover3.jpg'));
    });

    test('images 为 [coverUrl]（单图列表）', () {
      final r = projectPostMap(minArticle);
      expect(r.images, isNotNull);
      expect(r.images!.length, equals(1));
      expect(r.images!.first, equals('https://example.com/cover3.jpg'));
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // projectPostMap — 异常兜底
  // ─────────────────────────────────────────────────────────────────────────
  group('projectPostMap → PostSummaryView 异常兜底', () {
    test('空 map 不抛异常，返回 PostSummaryView', () {
      final result = projectPostMap({});
      expect(result, isA<PostSummaryView>());
    });

    test('仅含无效字段也不抛异常', () {
      final raw = <String, dynamic>{'unknown': 'value'};
      expect(() => projectPostMap(raw), returnsNormally);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // projectPostMap — mock 数据全量覆盖
  // ─────────────────────────────────────────────────────────────────────────
  group('projectPostMap → PostSummaryView mock 数据全量投射', () {
    test('所有 Photo mock 投射后均有非空 id / authorId / images / likesCount', () {
      for (final raw in ContentMockData.discoveryPhotoData) {
        final r = projectPostMap(raw);
        expect(
          r.id,
          isNotEmpty,
          reason: 'photo postId=${raw['postId']} 的 id 不得为空',
        );
        expect(
          r.authorId,
          isNotEmpty,
          reason: 'photo postId=${raw['postId']} 的 authorId 不得为空',
        );
        expect(
          r.images,
          isNotNull,
          reason: 'photo postId=${raw['postId']} 应有 images 字段',
        );
        final rawLikes = (raw['likeCount'] as num?)?.toInt() ?? 0;
        expect(
          r.likesCount,
          equals(rawLikes),
          reason:
              'photo postId=${raw['postId']} 的 likesCount 与原始数据不一致（0→1 bug）',
        );
      }
    });

    test('所有 Video mock 投射后均有 videoUrl / thumbnailUrl', () {
      for (final raw in ContentMockData.discoveryVideoData) {
        final r = projectPostMap(raw);
        expect(
          r.videoUrl,
          isNotNull,
          reason: 'video postId=${raw['postId']} 应有 videoUrl',
        );
        expect(
          r.thumbnailUrl,
          isNotNull,
          reason: 'video postId=${raw['postId']} 应有 thumbnailUrl',
        );
        final rawLikes = (raw['likeCount'] as num?)?.toInt() ?? 0;
        expect(
          r.likesCount,
          equals(rawLikes),
          reason:
              'video postId=${raw['postId']} 的 likesCount 与原始数据不一致（0→1 bug）',
        );
      }
    });

    test('所有 Article mock 投射后均有 body，title 保持 mock 语义', () {
      for (final raw in ContentMockData.discoveryArticleData) {
        final r = projectPostMap(raw);
        expect(
          r.body,
          isNotEmpty,
          reason: 'article postId=${raw['postId']} 应有非空 body',
        );
        final rawTitle = (raw['title'] ?? '').toString().trim();
        if (rawTitle.isNotEmpty) {
          expect(
            r.title,
            isNotEmpty,
            reason: 'article postId=${raw['postId']} 应保留显式标题',
          );
        } else {
          expect(
            (r.title ?? '').trim(),
            isEmpty,
            reason: 'article postId=${raw['postId']} 的无标题语义不应被强行补标题',
          );
        }
      }
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // projectArticleDetailView → ArticleDetailView
  // ─────────────────────────────────────────────────────────────────────────
  group('projectArticleDetailView → ArticleDetailView 输出结构契约', () {
    test('返回 ArticleDetailView 强类型实例', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r, isA<ArticleDetailView>());
    });

    test('id 从 raw.postId 解析', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r.id, equals('art1'));
    });

    test('fallbackArticleId 在无 id 时生效', () {
      final raw = <String, dynamic>{
        'contentType': 'article',
        'authorId': 'a',
        'displayName': 'A',
        'authorAvatarUrl': '',
        'title': 'T',
        'body': 'B',
        'coverUrl': '',
        'publishedAt': '2025-01-01T00:00:00Z',
      };
      final r = projectArticleDetailView(raw, fallbackArticleId: 'fallback_id');
      expect(r.id, equals('fallback_id'));
    });

    test('title 正确传递', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r.title, equals('2026年技术趋势'));
    });

    test('description 和 contentHtml 均来自 body', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r.description, equals('这是文章内容，包含多段落...'));
      expect(r.contentHtml, equals('这是文章内容，包含多段落...'));
    });

    test('author 强类型：包含 name / avatar / isOfficial / badge', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r.author, isA<ArticleAuthorView>());
      expect(r.author.name, equals('技术作者'));
      expect(r.author.avatar, equals('https://example.com/wavatar.jpg'));
      expect(r.author.isOfficial, isFalse);
      expect(r.author.badge, isNull);
    });

    test('author.isOfficial 来自 raw.isOfficial', () {
      final raw = Map<String, dynamic>.from(minArticle)
        ..['isOfficial'] = true
        ..['badge'] = 'VIP';
      final r = projectArticleDetailView(raw, fallbackArticleId: 'fb1');
      expect(r.author.isOfficial, isTrue);
      expect(r.author.badge, equals('VIP'));
    });

    test('stats 强类型：包含 likes / comments / bookmarks', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r.stats, isA<ArticleStatsView>());
      expect(r.stats.likes, equals(1000));
      expect(r.stats.comments, equals(90));
      expect(r.stats.bookmarks, equals(200));
    });

    test('stats 计数与 DTO 一致（0→1 回归守护）', () {
      final raw = Map<String, dynamic>.from(minArticle)..['likeCount'] = 8888;
      final r = projectArticleDetailView(raw, fallbackArticleId: 'fb4');
      expect(r.stats.likes, equals(8888));
    });

    test('单图时 layoutMode 为 hero', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r.layoutMode, equals('hero'));
    });

    test('coverImage 来自 coverUrl', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r.coverImage, equals('https://example.com/cover3.jpg'));
    });

    test('coverImage 回退链：无 coverUrl 时取 thumbnailUrl', () {
      final raw = <String, dynamic>{
        'postId': 'art_fallback',
        'contentType': 'article',
        'authorId': 'a',
        'displayName': 'A',
        'authorAvatarUrl': '',
        'title': 'T',
        'body': 'B',
        'thumbnailUrl': 'https://example.com/thumb.jpg',
        'publishedAt': '2025-01-01T00:00:00Z',
      };
      final r = projectArticleDetailView(raw, fallbackArticleId: 'fb3');
      // ArticlePostDto 会将 thumbnailUrl alias 读入 coverUrl，因此 coverImage 仍为 thumbnailUrl 值
      expect(r.coverImage, isNotEmpty);
    });

    test('images 非空（article 至少 [coverUrl]）', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r.images, isNotEmpty);
      expect(r.images.first, equals('https://example.com/cover3.jpg'));
    });

    test('无 articleBlocks/calls 时 contentBlocks 回退为 body 段落', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r.contentBlocks, hasLength(1));
      expect(r.contentBlocks.first.type, equals('paragraph'));
      expect(r.contentBlocks.first.body, contains('这是文章内容'));
    });

    test('articleBlocks 优先投射为连续内容块', () {
      final raw = Map<String, dynamic>.from(minArticle)
        ..['articleBlocks'] = <Map<String, dynamic>>[
          {'id': 'p1', 'type': 'paragraph', 'text': '第一段', 'imagePath': ''},
          {'id': 'o1', 'type': 'orderedItem', 'text': '第二条', 'imagePath': ''},
          {
            'id': 'i1',
            'type': 'image',
            'text': '',
            'imagePath': 'https://example.com/block.jpg',
          },
        ];
      final r = projectArticleDetailView(raw, fallbackArticleId: 'fb_blocks');
      expect(r.contentBlocks, hasLength(3));
      expect(r.contentBlocks[0].type, equals('paragraph'));
      expect(r.contentBlocks[1].type, equals('ordered_item'));
      expect(r.contentBlocks[1].orderedIndex, equals(1));
      expect(r.contentBlocks[2].type, equals('image'));
      expect(
        r.contentBlocks[2].imageUrl,
        equals('https://example.com/block.jpg'),
      );
    });

    test('wrap image + paragraph 会投射为 wrapped_paragraph', () {
      final raw = Map<String, dynamic>.from(minArticle)
        ..['articleBlocks'] = <Map<String, dynamic>>[
          {
            'id': 'i1',
            'type': 'image',
            'text': '',
            'imagePath': 'https://example.com/wrap.jpg',
            'imageLayout': 'wrapLeft',
          },
          {'id': 'p1', 'type': 'paragraph', 'text': '图片旁边的正文', 'imagePath': ''},
        ];
      final r = projectArticleDetailView(raw, fallbackArticleId: 'fb_wrap');
      expect(r.contentBlocks, hasLength(1));
      expect(r.contentBlocks.first.type, equals('wrapped_paragraph'));
      expect(r.contentBlocks.first.imageLayout, equals('wrapLeft'));
      expect(
        r.contentBlocks.first.imageUrl,
        equals('https://example.com/wrap.jpg'),
      );
    });

    test('正文标题块会投射到连续文档与阅读块语义', () {
      final raw = Map<String, dynamic>.from(minArticle)
        ..['articleBlocks'] = <Map<String, dynamic>>[
          {'id': 'p1', 'type': 'paragraph', 'text': '第一段'},
          {'id': 'h2_1', 'type': 'heading2', 'text': '章节一'},
          {'id': 'p2', 'type': 'paragraph', 'text': '第二段'},
          {'id': 's1', 'type': 'sectionTitle', 'text': '尾声'},
        ];
      final r = projectArticleDetailView(raw, fallbackArticleId: 'fb_headings');
      expect(r.document.blocks, hasLength(2));
      expect(r.document.blocks.first.text, equals('章节一'));
      expect(r.document.blocks.last.text, equals('尾声'));
      expect(r.contentBlocks[1].type, equals('heading_2'));
      expect(r.contentBlocks.last.type, equals('section_heading'));
    });

    test('旧 cards 可回退为连续阅读 section 块', () {
      final raw = Map<String, dynamic>.from(minArticle)
        ..['cards'] = <Map<String, dynamic>>[
          {
            'title': '小节一',
            'body': '这是第一节',
            'imageUrl': 'https://example.com/card.jpg',
          },
        ];
      final r = projectArticleDetailView(raw, fallbackArticleId: 'fb_cards');
      expect(r.contentBlocks, hasLength(1));
      expect(r.contentBlocks.first.type, equals('section'));
      expect(r.contentBlocks.first.title, equals('小节一'));
      expect(
        r.contentBlocks.first.imageUrl,
        equals('https://example.com/card.jpg'),
      );
    });

    test('articleDocument canonical 优先投射为连续内容块与分页首页', () {
      final raw = Map<String, dynamic>.from(minArticle)
        ..['title'] = '旧标题'
        ..['body'] = '分发摘要正文'
        ..['cards'] = <Map<String, dynamic>>[]
        ..['articleBlocks'] = <Map<String, dynamic>>[]
        ..['articleDocument'] = <String, dynamic>{
          'title': '连续文档标题',
          'body': '前言段落\n结尾段落',
          'assets': <Map<String, dynamic>>[
            {
              'id': 'asset_1',
              'offset': 4,
              'imageUrl': 'https://example.com/doc.jpg',
              'imageLayout': 'wrapRight',
              'caption': '文档配图',
            },
          ],
          'blocks': <Map<String, dynamic>>[
            {'id': 'h2_1', 'type': 'heading2', 'offset': 0, 'text': '章节一'},
            {
              'id': 'img_1',
              'type': 'image',
              'offset': 5,
              'imageUrl': 'https://example.com/doc.jpg',
              'imageLayout': 'wrapRight',
            },
            {'id': 'p_1', 'type': 'paragraph', 'offset': 6, 'text': '图旁正文'},
          ],
        };
      final r = projectArticleDetailView(raw, fallbackArticleId: 'fb_document');
      expect(r.document.title, equals('连续文档标题'));
      expect(r.documentSource, ArticleDetailDocumentSource.articleDocument);
      expect(r.contentBlocks, isNotEmpty);
      expect(r.contentBlocks.first.type, equals('heading_2'));
      expect(r.title, equals('连续文档标题'));
      expect(r.description, contains('前言段落'));
      expect(
        r.contentBlocks.any(
          (block) =>
              block.type == 'wrapped_paragraph' &&
              block.imageUrl == 'https://example.com/doc.jpg',
        ),
        isTrue,
      );
      expect(r.pages, isNotEmpty);
      expect(r.pages.first.title, equals('连续文档标题'));
    });

    test(
      'legacy fallback fixtures 覆盖 articleDocument/articleBlocks/cards/body 四条链路',
      () {
        final fixtures = ContentMockData.legacyArticleFallbackData;
        expect(fixtures, hasLength(4));
        final expectedSources = <String, ArticleDetailDocumentSource>{
          'legacy_document_only': ArticleDetailDocumentSource.articleDocument,
          'legacy_blocks_only': ArticleDetailDocumentSource.articleBlocks,
          'legacy_cards_only': ArticleDetailDocumentSource.cards,
          'legacy_body_only': ArticleDetailDocumentSource.body,
        };
        for (final raw in fixtures) {
          final postId = raw['postId']?.toString() ?? 'legacy_fallback';
          final r = projectArticleDetailView(raw, fallbackArticleId: postId);
          expect(
            r.document.isEmpty,
            isFalse,
            reason: 'postId=$postId 应能产出 document',
          );
          expect(
            r.documentSource,
            expectedSources[postId],
            reason: 'postId=$postId 应命中正确的 fallback 来源',
          );
          expect(
            r.contentBlocks,
            isNotEmpty,
            reason: 'postId=$postId 应能回退出连续阅读内容块',
          );
          expect(r.pages, isNotEmpty, reason: 'postId=$postId 应能回退出阅读页');
        }
      },
    );
  });

  // ──────────────────────────────────────────────────────────────────
  // MomentPostDto 投影契约
  // ──────────────────────────────────────────────────────────────────
  group('MomentPostDto 投影契约', () {
    final momentWithImages = <String, dynamic>{
      'postId': 'moment_01',
      'contentType': 'moment',
      'authorId': 'u99',
      'authorNickname': '小趣',
      'authorAvatarUrl': 'https://example.com/avatar.jpg',
      'body': '今天天气真好 ☀️',
      'mediaUrls': [
        'https://example.com/img1.jpg',
        'https://example.com/img2.jpg',
      ],
      'likeCount': 5,
      'commentCount': 2,
      'favoriteCount': 1,
      'shareCount': 0,
      'publishedAt': '2025-06-01T10:00:00Z',
    };

    final momentWithVideo = <String, dynamic>{
      'postId': 'moment_02',
      'contentType': 'micro',
      'authorId': 'u88',
      'authorNickname': '视频君',
      'authorAvatarUrl': 'https://example.com/avatar2.jpg',
      'body': '短视频时刻',
      'mediaUrls': <String>[],
      'videoUrl': 'https://example.com/moment_video.mp4',
      'durationMs': 8000,
      'likeCount': 12,
      'commentCount': 3,
      'favoriteCount': 0,
      'shareCount': 1,
      'publishedAt': '2025-06-01T11:00:00Z',
    };

    test('moment type dispatches to MomentPostDto', () {
      final dto = postBaseDtoFromMap(momentWithImages);
      expect(
        dto,
        isA<MomentPostDto>(),
        reason: 'contentType=moment must dispatch to MomentPostDto',
      );
    });

    test('micro type also dispatches to MomentPostDto', () {
      final dto = postBaseDtoFromMap(momentWithVideo);
      expect(
        dto,
        isA<MomentPostDto>(),
        reason: 'contentType=micro must dispatch to MomentPostDto',
      );
    });

    test('moment body is projected to PostSummaryView', () {
      final view = projectPostMap(momentWithImages);
      expect(
        view.body,
        equals('今天天气真好 ☀️'),
        reason: 'moment body must be projected to PostSummaryView.body',
      );
    });

    test('moment imageUrls projected correctly', () {
      final dto = postBaseDtoFromMap(momentWithImages) as MomentPostDto;
      expect(dto.imageUrls, hasLength(2));
      expect(dto.imageUrls.first, contains('img1.jpg'));
    });

    test('moment videoUrl projected correctly', () {
      final dto = postBaseDtoFromMap(momentWithVideo) as MomentPostDto;
      expect(dto.videoUrl, equals('https://example.com/moment_video.mp4'));
      expect(dto.durationMs, equals(8000));
    });

    test('moment stats projected to PostSummaryView', () {
      final view = projectPostMap(momentWithImages);
      expect(view.likesCount, equals(5));
      expect(view.commentsCount, equals(2));
    });

    test('moment with no images has empty imageUrls list (not null)', () {
      final dto = postBaseDtoFromMap(momentWithVideo) as MomentPostDto;
      expect(
        dto.imageUrls,
        isEmpty,
        reason: 'imageUrls must be an empty list when no images provided',
      );
    });

    test('mock moment data dispatches to MomentPostDto', () {
      final mockMoments = ContentMockData.discoveryMomentData;
      expect(
        mockMoments,
        isNotEmpty,
        reason: 'mock discovery moment data must not be empty',
      );
      for (final raw in mockMoments) {
        final dto = postBaseDtoFromMap(raw);
        expect(
          dto,
          isA<MomentPostDto>(),
          reason: 'All mock micro data must dispatch to MomentPostDto',
        );
      }
    });
  });
}
