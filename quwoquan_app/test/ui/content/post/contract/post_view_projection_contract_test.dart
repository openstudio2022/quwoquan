import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
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
    'authorAvatarUrl': 'media/avatar/s/test/content/ph1/v1/avatar.jpg',
    'coverUrl': 'media/image/s/test/content/ph1/v1/cover.jpg',
    'mediaUrls': [
      'media/image/s/test/content/ph1/v1/img1.jpg',
      'media/image/s/test/content/ph1/v1/img2.jpg',
    ],
    'width': 1200,
    'height': 900,
    'likeCount': 100,
    'commentCount': 20,
    'shareCount': 5,
    'publishedAt': '2025-12-01T10:00:00Z',
  };

  const Map<String, dynamic> minVideo = {
    'postId': 'vd1',
    'contentType': 'video',
    'authorId': 'vauth1',
    'displayName': '视频创作者',
    'authorAvatarUrl': 'media/avatar/s/test/content/vd1/v1/avatar.jpg',
    'videoUrl': 'media/video/s/test/content/vd1/v1/video.mp4',
    'thumbnailUrl': 'media/image/s/test/content/vd1/v1/thumb.jpg',
    'width': 1080,
    'height': 1920,
    'durationMs': 45000,
    'likeCount': 500,
    'commentCount': 80,
    'shareCount': 25,
    'publishedAt': '2026-01-10T00:00:00Z',
  };

  const Map<String, dynamic> minArticle = {
    'postId': 'art1',
    'contentType': 'article',
    'authorId': 'writer1',
    'displayName': '技术作者',
    'authorAvatarUrl': 'media/avatar/s/test/content/art1/v1/avatar.jpg',
    'title': '2026年技术趋势',
    'body': '这是文章内容，包含多段落...',
    'coverUrl': 'media/image/s/test/content/art1/v1/cover.jpg',
    'likeCount': 1000,
    'commentCount': 90,
    'shareCount': 150,
    'publishedAt': '2026-01-15T08:00:00Z',
  };

  ContentSurfaceView surfaceOf(Map<String, dynamic> raw) {
    return ContentSurfaceViewMapper.fromDto(postBaseDtoFromMap(raw), wire: raw);
  }

  String resolvedAvatar(String raw) => resolveAvatarImageUrl(raw);

  String resolvedMedia(String raw) => resolveContentMediaUrl(raw);

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
      expect(
        r.author.avatarUrl,
        equals(resolvedAvatar('media/avatar/s/test/content/ph1/v1/avatar.jpg')),
      );
    });

    test('authorBackgroundUrl 投射到 author.backgroundUrl', () {
      final raw = Map<String, dynamic>.from(minPhoto)
        ..['authorBackgroundUrl'] = 'media/image/s/test/content/ph1/v1/bg.jpg';
      expect(
        surfaceOf(raw).author.backgroundUrl,
        equals(resolvedMedia('media/image/s/test/content/ph1/v1/bg.jpg')),
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

    test('commentCount / shareCount 忠实保留', () {
      final r = surfaceOf(minPhoto);
      expect(r.stats.comment, equals(20));
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
      expect(
        r.cover?.url,
        equals(resolvedMedia('media/image/s/test/content/ph1/v1/cover.jpg')),
      );
      expect(r.cover?.aspectRatio, closeTo(1200 / 900, 0.001));
    });

    test('video.url / thumbnailUrl / durationMs 来自 DTO', () {
      final r = surfaceOf(minVideo);
      expect(
        r.video?.url,
        equals(resolvedMedia('media/video/s/test/content/vd1/v1/video.mp4')),
      );
      expect(
        r.video?.thumbnailUrl,
        equals(resolvedMedia('media/image/s/test/content/vd1/v1/thumb.jpg')),
      );
      expect(r.video?.durationMs, equals(45000));
    });

    test('video 计数字段正确投射', () {
      final r = surfaceOf(minVideo);
      expect(r.stats.like, equals(500));
      expect(r.stats.comment, equals(80));
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

    test('有 markdown 时 contentHtml 才承载正文 HTML 回退', () {
      final raw = Map<String, dynamic>.from(minArticle)
        ..['articleMarkdown'] =
            '---\ntitle: Markdown 标题\n---\n\n# Markdown 标题\n\n正文第一段。\n';
      final r = projectArticleDetailView(raw, fallbackArticleId: 'fb1');
      expect(r.contentHtml, equals('这是文章内容，包含多段落...'));
    });

    test('无 markdown 时 contentHtml 为空，不再借壳 body', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r.contentHtml, isEmpty);
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
      expect(
        r.images.first,
        equals(resolvedMedia('media/image/s/test/content/art1/v1/cover.jpg')),
      );
    });

    test('无 markdown 时文章视为空文档（不再有 body/blocks/cards 竞争源）', () {
      final r = projectArticleDetailView(minArticle, fallbackArticleId: 'fb1');
      expect(r.documentSource, ArticleDetailDocumentSource.empty);
      expect(r.contentBlocks, isEmpty);
      expect(r.pages.single.body, isEmpty);
    });

    test('Markdown asset:// refs are resolved through articleAssetManifest', () {
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
            'objectKey': 'media/image/s/test/article/manifest/v1/cover.jpg',
            'role': 'cover',
          },
          {
            'assetId': 'fig1',
            'objectKey': 'media/image/s/test/article/manifest/v1/fig1.jpg',
            'role': 'figure',
          },
        ],
      };

      final r = projectArticleDetailView(raw, fallbackArticleId: 'fb_manifest');
      final imageNodes = r.document.nodes
          .where((node) => node.isFigure)
          .toList();
      expect(
        imageNodes.map((node) => node.imageUrl),
        contains(resolvedMedia('media/image/s/test/article/manifest/v1/cover.jpg')),
      );
      expect(
        imageNodes.map((node) => node.imageUrl),
        contains(resolvedMedia('media/image/s/test/article/manifest/v1/fig1.jpg')),
      );
      expect(
        r.pages.first.fragments
            .where((fragment) => fragment.asset != null)
            .map((fragment) => fragment.asset!.imageUrl),
        contains(resolvedMedia('media/image/s/test/article/manifest/v1/cover.jpg')),
      );
    });

    test('Markdown figure 直接媒体 key 可投射为可加载图片 URL', () {
      final raw = Map<String, dynamic>.from(minArticle)
        ..['articleMarkdown'] =
            '---\n'
            'title: 直接媒体图\n'
            '---\n\n'
            '# 直接媒体图\n\n'
            '正文先读。\n\n'
            ':::figure id="inline1" layout="fullWidth" caption="配图"\n'
            'media/image/s/test/article/direct/v1/fig1.jpg\n'
            ':::\n';

      final r = projectArticleDetailView(raw, fallbackArticleId: 'fb_direct');
      final figures = r.document.nodes
          .where((node) => node.isFigure)
          .toList(growable: false);

      expect(figures, hasLength(1));
      expect(
        figures.single.imageUrl,
        resolvedMedia('media/image/s/test/article/direct/v1/fig1.jpg'),
      );
    });

    test('articleMarkdown canonical 优先投射为连续内容块与分页首页', () {
      final raw = Map<String, dynamic>.from(minArticle)
        ..['title'] = '旧标题'
        ..['body'] = '分发摘要正文'
        ..['articleMarkdown'] =
            '---\ntitle: 连续文档标题\ntemplate: journal\nfontPreset: clean\n---\n\n# 连续文档标题\n\n## 章节一\n\n图旁正文\n\n:::figure id="hero" layout="wrapRight" caption="文档配图"\nasset://hero\n:::\n'
        ..['articleAssetManifest'] = <String, dynamic>{
          'assets': <Map<String, dynamic>>[
            {
              'assetId': 'hero',
              'objectKey': 'media/image/s/test/article/document/v1/doc.jpg',
            },
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
              block.imageUrl ==
                  resolvedMedia('media/image/s/test/article/document/v1/doc.jpg'),
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
              'objectKey':
                  'media/image/s/archived-image/post/chuanxi_v2_峨眉山周末_自驾/v1/cover.jpg',
              'caption': '封面',
            },
            {
              'assetId':
                  'data_asset_media_image_post_chuanxi_v2__________v1_cover_jpg_2',
              'kind': 'image',
              'scope': 'cold_start',
              'objectKey':
                  'media/image/s/archived-image/post/chuanxi_v2_峨眉山周末_自驾/v1/detail_2.jpg',
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
          resolvedMedia(
            'media/image/s/archived-image/post/chuanxi_v2_峨眉山周末_自驾/v1/cover.jpg',
          ),
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
      'authorAvatarUrl': 'media/avatar/s/test/content/moment_01/v1/avatar.jpg',
      'body': '今天天气真好 ☀️',
      'mediaUrls': [
        'media/image/s/test/content/moment_01/v1/img1.jpg',
        'media/image/s/test/content/moment_01/v1/img2.jpg',
      ],
      'likeCount': 5,
      'commentCount': 2,
      'shareCount': 0,
      'publishedAt': '2025-06-01T10:00:00Z',
    };

    final momentWithVideo = <String, dynamic>{
      'postId': 'moment_02',
      'contentType': 'micro',
      'authorId': 'u88',
      'authorNickname': '视频君',
      'authorAvatarUrl': 'media/avatar/s/test/content/moment_02/v1/avatar.jpg',
      'body': '短视频时刻',
      'mediaUrls': <String>[],
      'videoUrl': 'media/video/s/test/content/moment_02/v1/moment_video.mp4',
      'durationMs': 8000,
      'likeCount': 12,
      'commentCount': 3,
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
      expect(
        dto.videoUrl,
        equals('media/video/s/test/content/moment_02/v1/moment_video.mp4'),
      );
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
