import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/post_view_projection.dart';

/// 投射契约测试：
/// - [ContentSurfaceViewMapper.fromDto]（统一展示模型，feed/detail/immersive/share 同源）
/// - [projectArticleDetailView]（→ [ContentArticleRender] 文章富渲染载荷）
///
/// 守护目标：
/// - DTO 字段变更后，统一模型输出的强类型字段必须第一时间失败，不悄悄回归。
/// - 覆盖"0→1 bug"：真实计数必须被忠实投射，不被归零后再 +1。
/// - 覆盖别名兼容：旧字段名（likesCount/commentsCount/savesCount）须被正确归一。
/// - 自包含 inline fixtures（不依赖 lib 端 mock data 类），契约数据由本文件就地构造。
void main() {
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

  ContentSurfaceView surfaceOf(Map<String, dynamic> raw) {
    return ContentSurfaceViewMapper.fromDto(postBaseDtoFromMap(raw), wire: raw);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ContentSurfaceViewMapper.fromDto — 公共字段
  // ─────────────────────────────────────────────────────────────────────────
  group('ContentSurfaceViewMapper.fromDto 公共字段投射', () {
    test('postId 来自 DTO.id（postId 字段）', () {
      final r = surfaceOf(minPhoto);
      expect(r.postId, equals('ph1'));
    });

    test('contentType 来自 DTO.type', () {
      expect(surfaceOf(minPhoto).contentType, isNotEmpty);
    });

    test('author.id 来自 DTO.authorId', () {
      expect(surfaceOf(minPhoto).author.id, equals('auth1'));
    });

    test('author.displayName / avatarUrl 来自 DTO', () {
      final r = surfaceOf(minPhoto);
      expect(r.author.displayName, equals('摄影师'));
      expect(r.author.avatarUrl, equals('https://example.com/avatar.jpg'));
    });

    test('authorBackgroundUrl 投射到 author.backgroundUrl', () {
      final raw = Map<String, dynamic>.from(minPhoto)
        ..['authorBackgroundUrl'] = 'https://example.com/bg.jpg';
      expect(
        surfaceOf(raw).author.backgroundUrl,
        equals('https://example.com/bg.jpg'),
      );
    });

    test('createdAt 是有效 DateTime', () {
      expect(surfaceOf(minPhoto).createdAt, isA<DateTime>());
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // 计数字段（0→1 回归守护核心）
  // ─────────────────────────────────────────────────────────────────────────
  group('ContentStats 计数字段 & 0→1 回归', () {
    test('likeCount 忠实保留原始计数', () {
      expect(
        surfaceOf(minPhoto).stats.like,
        equals(100),
        reason: '投射不得把 100 归零：0→1 bug',
      );
    });

    test('commentCount / favoriteCount / shareCount 忠实保留', () {
      final r = surfaceOf(minPhoto);
      expect(r.stats.comment, equals(20));
      expect(r.stats.favorite, equals(30));
      expect(r.stats.share, equals(5));
    });

    test('大数值计数也能忠实保留（不截断）', () {
      final raw = Map<String, dynamic>.from(minPhoto)..['likeCount'] = 999999;
      expect(surfaceOf(raw).stats.like, equals(999999));
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
      final r = surfaceOf(raw);
      expect(
        r.stats.like,
        equals(200),
        reason: 'likesCount alias 必须被 DTO 正确归一',
      );
      expect(r.stats.comment, equals(10));
      expect(r.stats.favorite, equals(40));
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
      final r = surfaceOf(raw);
      expect(r.stats.like, equals(0));
      expect(r.stats.comment, equals(0));
      expect(r.stats.favorite, equals(0));
      expect(r.stats.share, equals(0));
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // 媒体形态字段
  // ─────────────────────────────────────────────────────────────────────────
  group('ContentSurfaceViewMapper.fromDto 媒体字段', () {
    test('photo images 来自 DTO.imageUrls（mediaUrls）', () {
      final r = surfaceOf(minPhoto);
      expect(r.images, hasLength(2));
      expect(r.images.first.url, contains('img1.jpg'));
    });

    test('photo cover / aspectRatio 来自 DTO', () {
      final r = surfaceOf(minPhoto);
      expect(r.cover?.url, equals('https://example.com/cover.jpg'));
      expect(r.cover?.aspectRatio, closeTo(1200 / 900, 0.001));
    });

    test('video.url / thumbnailUrl / durationMs 来自 DTO', () {
      final r = surfaceOf(minVideo);
      expect(r.video?.url, equals('https://example.com/video.mp4'));
      expect(r.video?.thumbnailUrl, equals('https://example.com/thumb.jpg'));
      expect(r.video?.durationMs, equals(45000));
    });

    test('video 计数字段正确投射', () {
      final r = surfaceOf(minVideo);
      expect(r.stats.like, equals(500));
      expect(r.stats.comment, equals(80));
      expect(r.stats.favorite, equals(120));
      expect(r.stats.share, equals(25));
    });

    test('article title / body 来自 read presentation', () {
      final r = surfaceOf(minArticle);
      expect(r.title, equals('2026年技术趋势'));
      expect(r.body, equals('这是文章内容，包含多段落...'));
    });

    test('kind 依据契约派生 getter 判别', () {
      expect(surfaceOf(minPhoto).kind, ContentSurfaceKind.image);
      expect(surfaceOf(minVideo).kind, ContentSurfaceKind.video);
      expect(surfaceOf(minArticle).kind, ContentSurfaceKind.article);
    });

    test('tagRefs 从 wire 透传（已去空）', () {
      final raw = Map<String, dynamic>.from(minPhoto)
        ..['tagRefs'] = <String>['city-walk', 'film'];
      expect(surfaceOf(raw).tags, equals(<String>['city-walk', 'film']));
    });
  });

  group('ContentSurfaceViewMapper.fromDto 异常兜底', () {
    test('空 map 不抛异常，返回 ContentSurfaceView', () {
      expect(surfaceOf(const {}), isA<ContentSurfaceView>());
    });

    test('仅含无效字段也不抛异常', () {
      expect(
        () => surfaceOf(<String, dynamic>{'unknown': 'value'}),
        returnsNormally,
      );
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // projectArticleDetailView → ContentArticleRender（文章富渲染载荷）
  // ─────────────────────────────────────────────────────────────────────────
  group('projectArticleDetailView → ContentArticleRender 输出结构契约', () {
    test('返回 ContentArticleRender 强类型实例', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r, isA<ContentArticleRender>());
    });

    test('contentHtml 来自 body', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r.contentHtml, equals('这是文章内容，包含多段落...'));
    });

    test('isOfficial / badge 来自 raw', () {
      final raw = Map<String, dynamic>.from(minArticle)
        ..['isOfficial'] = true
        ..['badge'] = 'VIP';
      final r = projectArticleDetailView(raw, fallbackArticleId: 'fb1');
      expect(r.isOfficial, isTrue);
      expect(r.badge, equals('VIP'));
    });

    test('单图时 layoutMode 为 hero', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r.layoutMode, equals('hero'));
    });

    test('images 非空（article 至少回退 [coverUrl]）', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r.images, isNotEmpty);
      expect(r.images.first, equals('https://example.com/cover3.jpg'));
    });

    test('无 articleBlocks/cards 时 contentBlocks 回退为 body 段落', () {
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

    test(
      'Markdown asset:// refs are resolved through articleAssetManifest',
      () {
        final raw = Map<String, dynamic>.from(minArticle)
          ..['articleMarkdown'] =
              '---\n'
              'title: Manifest 标题\n'
              'cover_asset_id: cover\n'
              '---\n\n'
              '# Manifest 标题\n\n'
              ':::figure id="cover" layout="fullWidth" caption="封面"\n'
              'asset://cover\n'
              ':::\n\n'
              '首段正文。\n\n'
              ':::figure id="fig1" layout="wrapLeft" caption="配图"\n'
              'asset://fig1\n'
              ':::\n';
        raw['articleAssetManifest'] = <String, dynamic>{
          'schemaVersion': 1,
          'assets': <Map<String, dynamic>>[
            {
              'assetId': 'cover',
              'cdnUrl': 'https://cdn.example.com/cover.jpg',
              'role': 'cover',
            },
            {
              'assetId': 'fig1',
              'cdnUrl': 'https://cdn.example.com/fig1.jpg',
              'role': 'figure',
            },
          ],
        };

        final r = projectArticleDetailView(
          raw,
          fallbackArticleId: 'fb_manifest',
        );
        final imageNodes = r.document.nodes
            .where((node) => node.isFigure)
            .toList();
        expect(
          imageNodes.map((node) => node.imageUrl),
          contains('https://cdn.example.com/cover.jpg'),
        );
        expect(
          imageNodes.map((node) => node.imageUrl),
          contains('https://cdn.example.com/fig1.jpg'),
        );
        expect(
          r.pages.first.fragments
              .where((fragment) => fragment.asset != null)
              .map((fragment) => fragment.asset!.imageUrl),
          contains('https://cdn.example.com/cover.jpg'),
        );
      },
    );

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

    test('cards 使用 ArticleDetailWireKeys + ArticleCardWireKeys 构造仍可投射', () {
      final raw = Map<String, dynamic>.from(minArticle)
        ..[ArticleDetailWireKeys.cards] = <Map<String, dynamic>>[
          {
            ArticleCardWireKeys.title: 'SSOT 小节',
            ArticleCardWireKeys.body: 'SSOT 正文',
            ArticleCardWireKeys.imageUrl: 'https://example.com/ssot-card.jpg',
          },
        ];
      final r = projectArticleDetailView(
        raw,
        fallbackArticleId: 'fb_cards_keys',
      );
      expect(r.contentBlocks, hasLength(1));
      expect(r.contentBlocks.first.type, equals('section'));
      expect(r.contentBlocks.first.title, equals('SSOT 小节'));
      expect(
        r.contentBlocks.first.imageUrl,
        equals('https://example.com/ssot-card.jpg'),
      );
    });

    test('articleMarkdown canonical 优先投射为连续内容块与分页首页', () {
      final raw = Map<String, dynamic>.from(minArticle)
        ..['title'] = '旧标题'
        ..['body'] = '分发摘要正文'
        ..['cards'] = <Map<String, dynamic>>[]
        ..['articleBlocks'] = <Map<String, dynamic>>[]
        ..['articleMarkdown'] =
            '---\ntitle: 连续文档标题\ntemplate: journal\nfontPreset: clean\n---\n\n# 连续文档标题\n\n## 章节一\n\n图旁正文\n\n:::figure id="hero" layout="wrapRight" caption="文档配图"\nasset://hero\n:::\n'
        ..['articleAssetManifest'] = <String, dynamic>{
          'assets': <Map<String, dynamic>>[
            {'assetId': 'hero', 'objectKey': 'https://example.com/doc.jpg'},
          ],
        }
        ..['articleRenderProfile'] = <String, dynamic>{
          'template': 'journal',
          'fontPreset': 'clean',
        };
      final r = projectArticleDetailView(raw, fallbackArticleId: 'fb_document');
      expect(r.document.title, equals('连续文档标题'));
      expect(r.documentSource, ArticleDetailDocumentSource.markdown);
      expect(r.contentBlocks, isNotEmpty);
      expect(r.contentBlocks.first.type, equals('heading_2'));
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

    test('quwoquan_data article.md + manifest 进入 App 后保持 Markdown 三件套主链', () {
      const dataArticleMarkdown =
          '---\n'
          'title: 成都出发峨眉山周末自驾周末短途（夏季）\n'
          'template: journal\n'
          'articleMarkdownVersion: qwq-rich-md/1\n'
          'coverImage: asset://data_asset_media_image_post_chuanxi_v2__________v1_cover_jpg\n'
          '---\n\n'
          '# 成都出发峨眉山周末自驾周末短途（夏季）\n\n'
          '## 周末动线\n\n'
          '出发地成都，这个周末我去 峨眉山：Day1 走核心，Day2 上午补点后返程。\n\n'
          ':::figure id="fig1" layout="fullWidth" caption="周末动线"\n'
          'asset://data_asset_media_image_post_chuanxi_v2__________v1_cover_jpg\n'
          ':::\n\n'
          '## 交通方式\n\n'
          '交通方式选 自驾；单程耗时 1 小时。\n\n'
          ':::figure id="fig2" layout="wrapRight" caption="交通方式"\n'
          'asset://data_asset_media_image_post_chuanxi_v2__________v1_cover_jpg_2\n'
          ':::\n';
      final raw = Map<String, dynamic>.from(minArticle)
        ..['articleMarkdown'] = dataArticleMarkdown
        ..['articleMarkdownVersion'] = 'qwq-rich-md/1'
        ..['articleTemplate'] = 'journal'
        ..['articleFontPreset'] = 'clean'
        ..['articleAssetManifest'] = <String, dynamic>{
          'schemaVersion': 1,
          'articleMarkdownVersion': 'qwq-rich-md/1',
          'articleMarkdownDigest': 'sha256:test',
          'assets': <Map<String, dynamic>>[
            {
              'assetId':
                  'data_asset_media_image_post_chuanxi_v2__________v1_cover_jpg',
              'kind': 'image',
              'scope': 'cold_start',
              'objectKey': 'media/image/post/chuanxi_v2_峨眉山周末_自驾/v1/cover.jpg',
              'caption': '封面',
            },
            {
              'assetId':
                  'data_asset_media_image_post_chuanxi_v2__________v1_cover_jpg_2',
              'kind': 'image',
              'scope': 'cold_start',
              'objectKey':
                  'media/image/post/chuanxi_v2_峨眉山周末_自驾/v1/detail_2.jpg',
              'caption': '配图2',
            },
          ],
        }
        ..['articleRenderProfile'] = <String, dynamic>{
          'template': 'journal',
          'fontPreset': 'clean',
        };

      final r = projectArticleDetailView(
        raw,
        fallbackArticleId: 'data_article',
      );

      expect(r.documentSource, ArticleDetailDocumentSource.markdown);
      expect(r.document.title, equals('成都出发峨眉山周末自驾周末短途（夏季）'));
      expect(r.template, ArticleTemplatePreset.journal);
      expect(r.fontPreset, ArticleFontPreset.clean);
      expect(r.document.nodes.where((node) => node.isFigure), hasLength(2));
      expect(
        r.document.nodes
            .where((node) => node.isFigure)
            .map((node) => node.imageUrl),
        contains(
          'https://127.0.0.1:17100/media/image/post/chuanxi_v2_峨眉山周末_自驾/v1/cover.jpg',
        ),
      );
      expect(r.pages, isNotEmpty);
      expect(r.pages.first.title, equals(r.document.title));
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // MicroPostDto 投影契约
  // ──────────────────────────────────────────────────────────────────
  group('MicroPostDto 投影契约', () {
    final momentWithImages = <String, dynamic>{
      'postId': 'moment_01',
      'contentType': 'micro',
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

    test('micro type dispatches to MicroPostDto', () {
      expect(
        postBaseDtoFromMap(momentWithImages),
        isA<MicroPostDto>(),
        reason: 'contentType=micro must dispatch to MicroPostDto',
      );
      expect(
        postBaseDtoFromMap(momentWithVideo),
        isA<MicroPostDto>(),
        reason: 'contentType=micro must dispatch to MicroPostDto',
      );
    });

    test('moment body is projected to ContentSurfaceView', () {
      expect(
        surfaceOf(momentWithImages).body,
        equals('今天天气真好 ☀️'),
        reason: 'moment body must be projected to ContentSurfaceView.body',
      );
    });

    test('moment imageUrls projected correctly', () {
      final dto = postBaseDtoFromMap(momentWithImages) as MicroPostDto;
      expect(dto.imageUrls, hasLength(2));
      expect(dto.imageUrls.first, contains('img1.jpg'));
    });

    test('moment videoUrl projected correctly', () {
      final dto = postBaseDtoFromMap(momentWithVideo) as MicroPostDto;
      expect(dto.videoUrl, equals('https://example.com/moment_video.mp4'));
      expect(dto.durationMs, equals(8000));
    });

    test('moment stats projected to ContentSurfaceView', () {
      final r = surfaceOf(momentWithImages);
      expect(r.stats.like, equals(5));
      expect(r.stats.comment, equals(2));
    });

    test('moment with no images has empty imageUrls list (not null)', () {
      final dto = postBaseDtoFromMap(momentWithVideo) as MicroPostDto;
      expect(
        dto.imageUrls,
        isEmpty,
        reason: 'imageUrls must be an empty list when no images provided',
      );
    });
  });

  group('ContentSurfaceView article 模板字段（wire 透传）', () {
    test('articleTemplate 经 wire 透出到 ContentSurfaceView', () {
      final raw = Map<String, dynamic>.from(minArticle)
        ..[ArticleDetailWireKeys.articleTemplate] = 'customTpl';
      expect(surfaceOf(raw).articleTemplate, 'customTpl');
    });
  });
}
