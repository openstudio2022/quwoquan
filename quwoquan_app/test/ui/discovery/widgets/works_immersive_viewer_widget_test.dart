import 'dart:async';
import 'dart:io';
import 'dart:ui' show TextBox;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show RenderParagraph;
import 'package:flutter/services.dart' show TextSelection;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/content/feed_item_discovery_wire_map.dart';
import 'package:quwoquan_app/cloud/services/content/mock/content_mock_data.dart';
import 'package:quwoquan_app/components/media/shared/viewer/media_caption_widgets.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/immersive_engagement_bar.dart';
import 'package:quwoquan_app/components/media/video/player/video_player_widget.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_reader_flip_host.dart';
import 'package:quwoquan_app/ui/content/pages/unified_media_viewer_page.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';

Map<String, MediaViewerPostWireRow> _viewerRawByPostId(
  Map<String, Map<String, dynamic>> raw,
) => raw.map(
  (id, row) => MapEntry(id, MediaViewerPostWireRow.fromDynamicMap(row)),
);

class _FakeHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) => _FakeHttpClient();
}

class _FakeHttpClient implements HttpClient {
  @override
  bool autoUncompress = true;
  @override
  Duration? connectionTimeout;
  @override
  Duration idleTimeout = const Duration(seconds: 15);
  @override
  int? maxConnectionsPerHost;
  @override
  String? userAgent;
  @override
  void addCredentials(
    Uri url,
    String realm,
    HttpClientCredentials credentials,
  ) {}
  @override
  void addProxyCredentials(
    String host,
    int port,
    String realm,
    HttpClientCredentials credentials,
  ) {}
  @override
  set authenticate(Future<bool> Function(Uri, String, String?)? f) {}
  @override
  set authenticateProxy(
    Future<bool> Function(String, int, String, String?)? f,
  ) {}
  @override
  set badCertificateCallback(
    bool Function(X509Certificate, String, int)? callback,
  ) {}
  @override
  set connectionFactory(
    Future<ConnectionTask<Socket>> Function(Uri, String?, int?)? f,
  ) {}
  @override
  set findProxy(String Function(Uri)? f) {}
  @override
  set keyLog(Function(String)? callback) {}
  @override
  void close({bool force = false}) {}
  @override
  Future<HttpClientRequest> open(
    String method,
    String host,
    int port,
    String path,
  ) => _fakeRequest();
  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> get(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> getUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> post(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> postUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> put(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> putUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> delete(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> deleteUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> head(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> headUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> patch(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> patchUrl(Uri url) => _fakeRequest();

  Future<HttpClientRequest> _fakeRequest() =>
      Future<HttpClientRequest>.value(_FakeHttpClientRequest());
}

class _FakeHttpClientRequest extends Fake implements HttpClientRequest {
  @override
  HttpHeaders get headers => _FakeHttpHeaders();

  @override
  Future<HttpClientResponse> close() =>
      Future<HttpClientResponse>.value(_FakeHttpClientResponse());
}

class _FakeHttpHeaders extends Fake implements HttpHeaders {}

class _FakeHttpClientResponse extends Fake implements HttpClientResponse {
  static const _kTransparentPng = [
    0x89,
    0x50,
    0x4E,
    0x47,
    0x0D,
    0x0A,
    0x1A,
    0x0A,
    0x00,
    0x00,
    0x00,
    0x0D,
    0x49,
    0x48,
    0x44,
    0x52,
    0x00,
    0x00,
    0x00,
    0x01,
    0x00,
    0x00,
    0x00,
    0x01,
    0x08,
    0x06,
    0x00,
    0x00,
    0x00,
    0x1F,
    0x15,
    0xC4,
    0x89,
    0x00,
    0x00,
    0x00,
    0x0A,
    0x49,
    0x44,
    0x41,
    0x54,
    0x78,
    0x9C,
    0x62,
    0x00,
    0x00,
    0x00,
    0x02,
    0x00,
    0x01,
    0xE5,
    0x27,
    0xDE,
    0xFC,
    0x00,
    0x00,
    0x00,
    0x00,
    0x49,
    0x45,
    0x4E,
    0x44,
    0xAE,
    0x42,
    0x60,
    0x82,
  ];

  @override
  int get statusCode => 200;

  @override
  int get contentLength => _kTransparentPng.length;

  @override
  HttpClientResponseCompressionState get compressionState =>
      HttpClientResponseCompressionState.notCompressed;

  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int>)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return Stream<List<int>>.fromIterable([_kTransparentPng]).listen(
      onData,
      onError: onError,
      onDone: onDone,
      cancelOnError: cancelOnError,
    );
  }
}

class _FakeAnalyticsService extends AnalyticsService {
  _FakeAnalyticsService() : super.forTesting();

  final List<AnalyticsEvent> events = <AnalyticsEvent>[];

  @override
  Future<void> trackEvent(AnalyticsEvent event) async {
    events.add(event);
  }
}

class _ConfigurableContentRepository extends MockContentRepository {
  _ConfigurableContentRepository({
    this.appConfig,
    this.detailById = const <String, Map<String, dynamic>>{},
  });

  final Map<String, dynamic>? appConfig;
  final Map<String, Map<String, dynamic>> detailById;
  int getPostCallCount = 0;

  @override
  Future<ContentAppConfigWire> getAppConfig() async {
    if (appConfig != null) {
      return ContentAppConfigWire.fromResponseObject(
        Map<String, dynamic>.from(appConfig!),
      );
    }
    return super.getAppConfig();
  }

  @override
  Future<ContentPostDetailPayload> getPost({required String postId}) async {
    getPostCallCount += 1;
    final detail = detailById[postId];
    if (detail != null) {
      return ContentPostDetailPayload.fromWire(
        Map<String, dynamic>.from(detail),
      );
    }
    return super.getPost(postId: postId);
  }
}

class _PagedFeaturedContentRepository extends MockContentRepository {
  _PagedFeaturedContentRepository();

  final int pageSize = 2;
  final Duration appendDelay = const Duration(seconds: 4);
  int appendCallCount = 0;

  List<PostBaseDto> _postsForCategory(String category) {
    List<FeedItemDto> source;
    switch (category) {
      case 'photo':
        source = ContentMockData.discoveryPhotoData
            .take(4)
            .toList(growable: false);
        break;
      case 'video':
        source = ContentMockData.discoveryVideoData
            .take(4)
            .toList(growable: false);
        break;
      case 'article':
        source = ContentMockData.discoveryArticleData
            .take(4)
            .toList(growable: false);
        break;
      default:
        return const <PostBaseDto>[];
    }
    return source
        .map((item) => postBaseDtoFromMap(item.toDiscoveryWireMap()))
        .toList(growable: false);
  }

  @override
  Future<CursorPage<PostBaseDto>> listDiscoveryFeedPage({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
  }) async {
    final posts = _postsForCategory(category);
    if (posts.isEmpty) {
      return super.listDiscoveryFeedPage(
        category: category,
        identity: identity,
        type: type,
        subCategory: subCategory,
        limit: limit,
        cursor: cursor,
        sort: sort,
        sessionId: sessionId,
        feedRequestId: feedRequestId,
      );
    }
    final offset = int.tryParse((cursor ?? '').trim()) ?? 0;
    if (offset > 0 && appendDelay > Duration.zero) {
      appendCallCount += 1;
      await Future<void>.delayed(appendDelay);
    }
    final end = (offset + pageSize).clamp(0, posts.length);
    return CursorPage<PostBaseDto>(
      items: posts.sublist(offset, end),
      nextCursor: end < posts.length ? '$end' : null,
    );
  }

  @override
  DiscoveryPresentationWire? discoveryPresentationWireForPost(String postId) {
    final isArticle = ContentMockData.discoveryArticleData.any(
      (item) => item.id == postId,
    );
    if (isArticle) {
      final row = ContentMockData.discoveryArticleData.firstWhere(
        (item) => item.id == postId,
      );
      return DiscoveryPresentationWire.fromRow(<String, dynamic>{
        ...row.toDiscoveryWireMap(),
        'id': row.id,
        'type': 'article',
        'contentType': 'article',
        'title': row.title,
        'body': row.summary ?? row.body,
        'cards': const <Map<String, dynamic>>[
          {'title': '第二页标题', 'body': '第二页正文'},
        ],
      });
    }
    return super.discoveryPresentationWireForPost(postId);
  }
}

class _RemoteModeNotifier extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.remote;
}

PhotoPostDto _photoPost({
  List<String> imageUrls = const ['https://example.com/photo.jpg'],
  int? width,
  int? height,
}) {
  return PhotoPostDto(
    id: 'photo-1',
    type: 'image',
    identity: 'work',
    assistantUsePolicy: 'inherit',
    authorId: 'author-1',
    displayName: '摄影师',
    avatarUrl: 'https://example.com/avatar.jpg',
    body: 'dto body',
    coverUrl: 'https://example.com/photo.jpg',
    imageUrls: imageUrls,
    width: width,
    height: height,
    likeCount: 0,
    commentCount: 0,
    shareCount: 0,
    createdAt: DateTime.now(),
  );
}

VideoPostDto _videoPost({int? width, int? height}) {
  return VideoPostDto(
    id: 'video-1',
    type: 'video',
    identity: 'work',
    assistantUsePolicy: 'inherit',
    authorId: 'author-video',
    displayName: '视频作者',
    avatarUrl: 'https://example.com/avatar-video.jpg',
    body: 'video body',
    videoUrl: 'https://example.com/video.mp4',
    thumbnailUrl: 'https://example.com/video.jpg',
    width: width,
    height: height,
    likeCount: 0,
    commentCount: 0,
    shareCount: 0,
    createdAt: DateTime.now(),
  );
}

ArticlePostDto _articlePost() {
  return ArticlePostDto(
    id: 'article-1',
    type: 'article',
    identity: 'work',
    assistantUsePolicy: 'inherit',
    authorId: 'author-3',
    displayName: '写作者',
    avatarUrl: 'https://example.com/avatar-3.jpg',
    title: '图文翻页',
    body: '文章摘要',
    summary: '文章摘要',
    coverUrl: 'https://example.com/article-cover.jpg',
    articleTemplate: 'gentle',
    articleFontPreset: 'clean',
    likeCount: 0,
    commentCount: 0,
    shareCount: 0,
    createdAt: DateTime.now(),
  );
}

/// 生成确定性多页文章 markdown（唯一内容真相源）。
/// 替代旧 `cards` 借壳分页：markdown-only 契约下，多页由排版流引擎按视口高度切分。
String _multiPageArticleMarkdown(
  ArticlePostDto post, {
  int sections = 14,
  int paragraphsPerSection = 1,
}) {
  final blocks = List<String>.generate(sections, (index) {
    final paragraphs = List<String>.generate(
      paragraphsPerSection,
      (p) =>
          '这是第 ${index + 1} 小节第 ${p + 1} 段用于沉浸式文章自动分页的长正文，'
          '需要被继续拆到后续页面中，不能仍然停留在 1/1。',
    ).join('\n\n');
    return '## 小节${index + 1}\n\n$paragraphs';
  }).join('\n\n');
  return '---\n'
      'title: ${post.title}\n'
      'template: ${post.articleTemplate}\n'
      'fontPreset: ${post.articleFontPreset}\n'
      '---\n\n'
      '$blocks\n';
}

/// 以 markdown 为唯一内容源构造沉浸 viewer 的文章原始行。
Map<String, dynamic> _articleMarkdownRaw(
  ArticlePostDto post,
  String markdown, {
  Map<String, dynamic> extra = const <String, dynamic>{},
}) {
  return <String, dynamic>{
    'postId': post.id,
    'type': 'article',
    'contentType': 'article',
    'authorId': post.authorId,
    'authorNickname': post.displayName,
    'authorAvatarUrl': post.avatarUrl,
    'title': post.title,
    'body': post.body,
    'summary': post.summary,
    'coverUrl': post.coverUrl,
    'articleTemplate': post.articleTemplate,
    'articleFontPreset': post.articleFontPreset,
    'articleMarkdown': markdown,
    'articleMarkdownVersion': 'qwq-rich-md/1',
    'articleAssetManifest': const <String, dynamic>{
      'schemaVersion': 1,
      'articleMarkdownVersion': 'qwq-rich-md/1',
      'articleMarkdownDigest': 'fixture:multipage',
      'assets': <Map<String, dynamic>>[],
    },
    'articleRenderProfile': <String, dynamic>{
      'template': post.articleTemplate,
      'fontPreset': post.articleFontPreset,
    },
    ...extra,
  };
}

String _articleProgressLabel(WidgetTester tester) {
  final label = tester.widget<Text>(
    find.byKey(const ValueKey<String>('works-article-page-progress')),
  );
  return label.data ?? '';
}

/// 断言已离开第 1 页（翻页生效）。markdown-only 后不再断言具体卡片文案。
void _expectArticleAdvancedPastFirstPage(WidgetTester tester) {
  expect(_articleProgressLabel(tester), isNot(startsWith('1 / ')));
}

/// 用页码 chevron 把文章翻到末页（确定性导航，替代旧 2 页 fixture 的单次拖拽到末页）。
Future<void> _flipArticleToLastPage(WidgetTester tester) async {
  final next = find.byKey(const ValueKey<String>('works-article-page-next'));
  for (var guard = 0; guard < 200; guard += 1) {
    final parts = _articleProgressLabel(tester).split(' / ');
    if (parts.length == 2 && parts[0].trim() == parts[1].trim()) {
      return;
    }
    if (next.evaluate().isEmpty) {
      return;
    }
    await tester.tap(next);
    await tester.pumpAndSettle();
  }
}

MicroPostDto _textMoment({List<IntersectionReason>? intersectionReasons}) {
  return MicroPostDto(
    id: 'moment-1',
    type: 'micro',
    identity: 'moment',
    assistantUsePolicy: 'inherit',
    authorId: 'author-2',
    displayName: '圈友',
    avatarUrl: 'https://example.com/avatar-2.jpg',
    body: '今天风有点大，大家从南门集合。',
    imageUrls: const <String>[],
    likeCount: 0,
    commentCount: 0,
    shareCount: 0,
    createdAt: DateTime.now(),
    intersectionReasons: intersectionReasons,
  );
}

Widget _wrap(
  Widget child, {
  List overrides = const [],
  bool useRemoteMode = false,
}) {
  final allOverrides = [
    ...overrides,
    if (useRemoteMode)
      appDataSourceModeProvider.overrideWith(_RemoteModeNotifier.new),
  ];
  return ProviderScope(
    overrides: allOverrides.cast(),
    child: ScreenUtilInit(
      designSize: const Size(375, 812),
      builder: (context, _) => MaterialApp(
        theme: ThemeData.dark(),
        home: Scaffold(body: child),
      ),
    ),
  );
}

Widget _wrapWithRouter(Widget child, {List overrides = const []}) {
  final router = GoRouter(
    routes: [
      GoRoute(
        path: '/',
        builder: (context, state) => Scaffold(body: child),
      ),
      GoRoute(
        path: '/homepages/:id',
        builder: (context, state) => Text(
          'homepage:${state.pathParameters['id']}',
          key: const ValueKey<String>('homepage-detail-probe'),
        ),
      ),
    ],
  );
  return ProviderScope(
    overrides: overrides.cast(),
    child: ScreenUtilInit(
      designSize: const Size(375, 812),
      builder: (context, _) =>
          MaterialApp.router(theme: ThemeData.dark(), routerConfig: router),
    ),
  );
}

void _consumeImageLoadExceptions(WidgetTester tester) {
  while (tester.takeException() != null) {
    // swallow network image loading errors in widget tests
  }
}

Future<void> _tapRichTextSubstring(
  WidgetTester tester,
  Finder finder,
  String substring,
) async {
  final render = tester.renderObject<RenderParagraph>(finder);
  final plainText = render.text.toPlainText();
  final start = plainText.indexOf(substring);
  expect(start, greaterThanOrEqualTo(0), reason: '未找到文本片段: $substring');
  final end = start + substring.length;
  final boxes = render.getBoxesForSelection(
    TextSelection(baseOffset: start, extentOffset: end),
  );
  expect(boxes, isNotEmpty, reason: '文本片段未生成可点击字形框: $substring');
  final TextBox box = boxes.first;
  await tester.tapAt(render.localToGlobal(box.toRect().center));
}

class _DeferredPostWorksViewer extends StatefulWidget {
  const _DeferredPostWorksViewer({
    required this.post,
    required this.rawRow,
    required this.revealDelay,
  });

  final PostBaseDto post;
  final Map<String, dynamic> rawRow;
  final Duration revealDelay;

  @override
  State<_DeferredPostWorksViewer> createState() =>
      _DeferredPostWorksViewerState();
}

class _DeferredPostWorksViewerState extends State<_DeferredPostWorksViewer> {
  List<PostBaseDto> _posts = const <PostBaseDto>[];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await Future<void>.delayed(widget.revealDelay);
      if (!mounted) {
        return;
      }
      setState(() {
        _posts = <PostBaseDto>[widget.post];
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return WorksImmersiveViewer(
      showWorksToolbar: true,
      showTopNavigation: false,
      externalPosts: _posts,
      externalPostViews: _posts
          .map(ContentSurfaceViewMapper.fromDto)
          .toList(growable: false),
      rawPostsById: _posts.isEmpty
          ? const <String, MediaViewerPostWireRow>{}
          : _viewerRawByPostId({widget.post.id: widget.rawRow}),
      onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
      onAssistantTap: () {},
    );
  }
}

void main() {
  setUp(() {
    HttpOverrides.global = _FakeHttpOverrides();
  });

  test('沉浸媒体滑动顺滑性静态契约', () {
    final viewerSource = File(
      'lib/ui/discovery/widgets/works_immersive_viewer.dart',
    ).readAsStringSync();
    final videoPlayerSource = File(
      'lib/components/media/video/player/video_player_widget.dart',
    ).readAsStringSync();

    expect(
      viewerSource,
      contains('double _pageWidthForConstraints(BoxConstraints constraints)'),
      reason: '图片横滑分页距离必须来自实际 stage 宽度，而不是全屏宽度。',
    );
    expect(
      viewerSource,
      contains('Duration _settleDuration({'),
      reason: '图片释放吸附应根据距离/速度动态收敛，避免固定时长拖沓。',
    );
    expect(
      viewerSource,
      contains('precacheImage(CachedNetworkImageProvider(url), context)'),
      reason: '图片横滑应预热相邻图，降低快速滑动时 placeholder 闪动。',
    );
    expect(
      viewerSource,
      contains('allowImplicitScrolling: true'),
      reason: '视频横滑应允许 PageView 提前构建相邻页以降低黑屏概率。',
    );
    expect(
      viewerSource,
      contains('class _KeepAliveStage'),
      reason: '视频相邻页构建后应保活，避免来回滑动反复初始化。',
    );
    expect(
      videoPlayerSource,
      contains('void didUpdateWidget(covariant VideoPlayerWidget oldWidget)'),
      reason: '视频播放器必须响应 autoPlay 变化，同步切页后的播放/暂停状态。',
    );
    expect(videoPlayerSource, contains('_syncPlaybackWithAutoPlay();'));
  });

  testWidgets('精品沉浸流尾部显示加载哨兵并预取下一批内容', (tester) async {
    final repo = _PagedFeaturedContentRepository();
    final analytics = _FakeAnalyticsService();
    final container = ProviderContainer(
      overrides: [
        contentRepositoryProvider.overrideWithValue(repo),
        analyticsProvider.overrideWithValue(analytics),
      ],
    );
    addTearDown(container.dispose);

    var switchedToHome = false;

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            theme: ThemeData.dark(),
            home: Scaffold(
              body: WorksImmersiveViewer(
                showWorksToolbar: true,
                showTopNavigation: true,
                onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
                onAssistantTap: () {},
                onSwitchToCircles: () => switchedToHome = true,
                onSwitchToFollowing: () => switchedToHome = true,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(
      container.read(discoveryFeedProvider('photo')).value?.items.length,
      equals(2),
    );
    expect(
      container.read(discoveryFeedProvider('video')).value?.items.length,
      equals(2),
    );
    expect(
      container.read(discoveryFeedProvider('article')).value?.items.length,
      equals(2),
    );

    final verticalPager = find.byWidgetPredicate(
      (widget) => widget is PageView && widget.scrollDirection == Axis.vertical,
    );
    var reachedSentinel = false;
    for (var i = 0; i < 8; i += 1) {
      await tester.fling(verticalPager, const Offset(0, -700), 1200);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 450));
      reachedSentinel = find
          .byKey(const ValueKey<String>('works-load-more-sentinel'))
          .evaluate()
          .isNotEmpty;
      if (reachedSentinel) {
        break;
      }
    }

    expect(reachedSentinel, isTrue);
    expect(repo.appendCallCount, greaterThan(0));
    expect(switchedToHome, isFalse);

    await tester.pump(const Duration(seconds: 5));
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(
      container.read(discoveryFeedProvider('photo')).value?.items.length,
      equals(4),
    );
    expect(
      container.read(discoveryFeedProvider('video')).value?.items.length,
      equals(4),
    );
    expect(
      container.read(discoveryFeedProvider('article')).value?.items.length,
      equals(4),
    );
    expect(
      find.byKey(const ValueKey<String>('works-load-more-sentinel')),
      findsNothing,
    );
    expect(switchedToHome, isFalse);

    // 滚动翻页会经 trackSkip 懒创建 ContentBehaviorTracker（周期性 flush 定时器，
    // 生命周期绑定 container.onDispose）。在测试体结束前显式 dispose container，
    // 使定时器在 pending-timer 不变量校验前被取消，避免 "Timer still pending"。
    container.dispose();
  });

  testWidgets('精品顶部仅保留返回与更多入口（V1.0 取消形态分段与一级 tab）', (tester) async {
    final repo = _PagedFeaturedContentRepository();
    final container = ProviderContainer(
      overrides: [contentRepositoryProvider.overrideWithValue(repo)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            theme: ThemeData.dark(),
            home: Scaffold(
              body: WorksImmersiveViewer(
                showWorksToolbar: true,
                showTopNavigation: true,
                onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
                onAssistantTap: () {},
                onSwitchToFollowing: () {},
                onSwitchToCircles: () {},
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    // V1.0：顶部仅保留「返回 + 更多」，禁止形态分段 / 一级 tab。
    expect(
      find.byKey(const ValueKey<String>('works-top-back')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('works-top-more')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('works-format-tab-strip')),
      findsNothing,
    );

    // 不再出现「关注 / 精品」一级 tab。
    expect(find.text('关注'), findsNothing);
    expect(find.text('精品'), findsNothing);

    container.dispose();
  });

  testWidgets('UnifiedMediaViewerPage 首帧后灌入互动快照且不抛 provider 生命周期异常', (
    tester,
  ) async {
    final post = _photoPost(
      imageUrls: const ['https://example.com/photo-regression.jpg'],
    );
    final container = ProviderContainer();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            theme: ThemeData.dark(),
            home: UnifiedMediaViewerPage(
              extra: MediaViewerExtra(
                posts: <ContentSurfaceView>[
                  ContentSurfaceViewMapper.fromDto(post),
                ],
                dtoPosts: <PostBaseDto>[post],
                initialIndex: 0,
                category: 'photo',
                rawPostsById: _viewerRawByPostId({
                  post.id: <String, dynamic>{
                    'postId': post.id,
                    'type': 'photo',
                    'contentType': 'image',
                    'authorId': post.authorId,
                    'authorNickname': post.displayName,
                    'authorAvatarUrl': post.avatarUrl,
                    'title': '回归标题',
                    'body': '回归正文',
                    'coverUrl': post.coverUrl,
                    'imageUrls': post.imageUrls,
                  },
                }),
                interactionSnapshot: MediaViewerInteractionSnapshot(
                  scopePostIds: <String>{post.id},
                  scopeProfileIds: <String>{post.subAccountId},
                  followingUsers: <String>{post.subAccountId},
                  likedPosts: <String>{post.id},
                  postLikesCount: <String, int>{post.id: 7},
                  postCommentCount: <String, int>{post.id: 4},
                  postSharesCount: <String, int>{post.id: 3},
                ),
              ),
            ),
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);
    await tester.pump();
    expect(tester.takeException(), isNull);
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    expect(find.byType(WorksImmersiveViewer), findsOneWidget);
    final relationshipState = container.read(userRelationshipStateProvider);
    final postInteractionState = container.read(postInteractionStateProvider);
    expect(relationshipState.isFollowing(post.subAccountId), isTrue);
    expect(postInteractionState.isLiked(post.id), isTrue);
    expect(postInteractionState.commentCountFor(post.id), 4);
    expect(postInteractionState.shareCountFor(post.id), 3);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    container.dispose();
  });

  testWidgets('UnifiedMediaViewerPage 文章底部工具栏沿统一安全轨道收口', (tester) async {
    final post = _articlePost();
    final container = ProviderContainer();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MediaQuery(
          data: const MediaQueryData(
            size: Size(390, 844),
            padding: EdgeInsets.only(top: 47, bottom: 34),
            viewPadding: EdgeInsets.only(top: 47, bottom: 34),
          ),
          child: MaterialApp(
            theme: ThemeData.dark(),
            home: UnifiedMediaViewerPage(
              extra: MediaViewerExtra(
                posts: <ContentSurfaceView>[
                  ContentSurfaceViewMapper.fromDto(post),
                ],
                dtoPosts: <PostBaseDto>[post],
                initialIndex: 0,
                category: 'article',
                rawPostsById: _viewerRawByPostId({
                  post.id: <String, dynamic>{
                    'postId': post.id,
                    'type': 'article',
                    'contentType': 'article',
                    'authorId': post.authorId,
                    'authorNickname': post.displayName,
                    'authorAvatarUrl': post.avatarUrl,
                    'title': post.title,
                    'body': post.body,
                    'summary': post.summary,
                    'coverUrl': post.coverUrl,
                    'articleTemplate': post.articleTemplate,
                    'articleFontPreset': post.articleFontPreset,
                    'cards': const [
                      {'title': '第二页标题', 'body': '第二页正文'},
                    ],
                  },
                }),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    final barFinder = find.byType(ImmersiveEngagementBar);
    final railFinder = find.byKey(const ValueKey('immersive-engagement-rail'));
    final barRect = tester.getRect(barFinder);
    final railRect = tester.getRect(railFinder);
    final barContext = tester.element(barFinder);
    final expectedSideInset =
        AppSpacing.containerMd +
        AppSpacing.appChromeBottomSafeSideInset(barContext, 34);

    expect(
      (railRect.left - barRect.left - expectedSideInset).abs(),
      lessThan(1),
    );
    expect(
      (barRect.right - railRect.right - expectedSideInset).abs(),
      lessThan(1),
    );

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    container.dispose();
  });

  testWidgets('photo post 在 unified viewer 中展示 raw title/body', (tester) async {
    final post = _photoPost(
      imageUrls: const [
        'https://example.com/photo.jpg',
        'https://example.com/photo-2.jpg',
        'https://example.com/photo-3.jpg',
        'https://example.com/photo-4.jpg',
        'https://example.com/photo-5.jpg',
        'https://example.com/photo-6.jpg',
        'https://example.com/photo-7.jpg',
        'https://example.com/photo-8.jpg',
      ],
    );
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'photo',
              'contentType': 'image',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '封面标题',
              'body': '封面正文，需要在浏览器底部展示出来。',
              'coverUrl': post.coverUrl,
              'imageUrls': post.imageUrls,
              'circleSummaries': const [
                {'id': 'circle-1', 'name': '测试圈子A'},
                {'id': 'circle-2', 'name': '测试圈子B'},
              ],
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(find.text('封面标题'), findsOneWidget);
    expect(find.textContaining('封面正文'), findsOneWidget);
    // V1.0：禁止顶部页码；多图导航使用点指示器（内容下方、标题上方）。
    expect(
      find.byKey(const ValueKey<String>('works-top-progress-label')),
      findsNothing,
    );
    expect(find.text('1/8'), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('works-page-indicator')),
      findsOneWidget,
    );
    final indicatorRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-page-indicator')),
    );
    final backRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-top-back')),
    );
    final titleRect = tester.getRect(find.text('封面标题'));
    expect(indicatorRect.top, greaterThan(backRect.bottom));
    expect(indicatorRect.bottom, lessThanOrEqualTo(titleRect.top));
    // 圈子信息不再出现在工具栏（被交集理由位替代）。
    expect(find.text('测试圈子A'), findsNothing);
    expect(find.text('测试圈子B'), findsNothing);
    expect(find.byType(MediaBlurCaptionOverlay), findsNothing);
  });

  testWidgets('精品页竖向图片按宽高比铺入状态栏', (tester) async {
    final post = _photoPost(width: 900, height: 1200);
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          topChromeSafeInset: AppSpacing.twenty,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    final canvasRect = tester.getRect(
      find.byKey(ValueKey<String>('works-status-content-canvas-${post.id}')),
    );
    expect((canvasRect.top - viewerRect.top).abs(), lessThan(1));
  });

  testWidgets('精品页宽横图保留状态栏安全区', (tester) async {
    final post = _photoPost(width: 1600, height: 900);
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          topChromeSafeInset: AppSpacing.twenty,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    final canvasRect = tester.getRect(
      find.byKey(ValueKey<String>('works-status-content-canvas-${post.id}')),
    );
    expect(
      canvasRect.top - viewerRect.top,
      moreOrLessEquals(AppSpacing.twenty),
    );
  });

  testWidgets('精品页视频可铺入状态栏', (tester) async {
    final post = _videoPost(width: 1920, height: 1080);
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          topChromeSafeInset: AppSpacing.twenty,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    final canvasRect = tester.getRect(
      find.byKey(ValueKey<String>('works-status-content-canvas-${post.id}')),
    );
    expect((canvasRect.top - viewerRect.top).abs(), lessThan(1));
  });

  testWidgets('photo post 在 iPad 宽屏下顶部说明底部对齐到同一 media rail', (tester) async {
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = const Size(1024, 1366);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final post = _photoPost(
      imageUrls: const ['https://example.com/photo-wide.jpg'],
    );
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'photo',
              'contentType': 'image',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '宽屏标题',
              'body': '宽屏说明正文',
              'coverUrl': post.coverUrl,
              'imageUrls': post.imageUrls,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    final topRailRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-top-rail')),
    );
    final captionRailRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-caption-rail')),
    );
    final bottomRailRect = tester.getRect(
      find.byKey(const ValueKey('immersive-engagement-rail')),
    );

    // photo 使用 mediaStage：全宽 rail，与图片/视频左右对齐。
    expect((topRailRect.left - AppSpacing.containerMd).abs(), lessThan(1));
    expect(
      (viewerRect.right - topRailRect.right - AppSpacing.containerMd).abs(),
      lessThan(1),
    );
    expect((captionRailRect.left - topRailRect.left).abs(), lessThan(1));
    expect((captionRailRect.right - topRailRect.right).abs(), lessThan(1));
    expect((bottomRailRect.left - topRailRect.left).abs(), lessThan(1));
    expect((bottomRailRect.right - topRailRect.right).abs(), lessThan(1));
  });

  testWidgets('首帧帖子延后就绪时 follow 按钮随工具栏常驻可见（V1.0 无定时）', (tester) async {
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final post = _photoPost();
    await tester.pumpWidget(
      _wrap(
        _DeferredPostWorksViewer(
          post: post,
          revealDelay: const Duration(milliseconds: 50),
          rawRow: <String, dynamic>{
            'postId': post.id,
            'type': 'photo',
            'contentType': 'image',
            'authorId': post.authorId,
            'authorNickname': post.displayName,
            'authorAvatarUrl': post.avatarUrl,
            'title': '延后加载标题',
            'body': '延后加载正文',
            'coverUrl': post.coverUrl,
            'imageUrls': post.imageUrls,
          },
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 60));
    _consumeImageLoadExceptions(tester);
    await tester.pump();

    final followLane = find.byKey(const ValueKey('immersive-follow-lane'));
    expect(find.byType(ImmersiveEngagementBar), findsOneWidget);
    // V1.0：关注按钮随工具栏常驻，不再有出现定时。
    expect(tester.getSize(followLane).width, greaterThan(0));
    expect(
      find.byKey(const ValueKey('immersive-follow-button')),
      findsOneWidget,
    );
  });

  testWidgets('photo caption 与底部工具栏顶部保持固定间距', (tester) async {
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final post = _photoPost(
      imageUrls: const ['https://example.com/photo-gap.jpg'],
    );
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'photo',
              'contentType': 'image',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '贴底标题',
              'body': '贴底说明正文',
              'coverUrl': post.coverUrl,
              'imageUrls': post.imageUrls,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    final captionRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-caption-rail')),
    );
    final toolbarRect = tester.getRect(find.byType(ImmersiveEngagementBar));

    expect(
      toolbarRect.top - captionRect.bottom,
      moreOrLessEquals(AppSpacing.containerSm, epsilon: 1),
    );
  });

  testWidgets('分页书内容区与底部工具栏保持统一净空', (tester) async {
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final post = _articlePost();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    final bookRect = tester.getRect(find.byType(ArticleReadOnlyBookDeck));
    final toolbarRect = tester.getRect(find.byType(ImmersiveEngagementBar));
    final screenWidth =
        tester.view.physicalSize.width / tester.view.devicePixelRatio;

    expect(
      toolbarRect.top - bookRect.bottom,
      moreOrLessEquals(AppSpacing.containerMd, epsilon: 1),
    );
    expect(bookRect.left, closeTo(0, 1));
    expect(bookRect.top, closeTo(0, 1));
    expect(bookRect.right, closeTo(screenWidth, 1));
  });

  testWidgets('text-only moment 使用文本画布展示 title/body', (tester) async {
    final post = _textMoment();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'micro',
              'contentType': 'micro',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '临时改地点提醒',
              'body': post.body,
              'circleName': '测试圈子',
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('临时改地点提醒'), findsOneWidget);
    expect(find.textContaining('今天风有点大'), findsOneWidget);
  });

  testWidgets('交集以「N 个交集」入口呈现并点击弹出推荐解释详情', (tester) async {
    final post = _textMoment(
      intersectionReasons: <IntersectionReason>[
        IntersectionReason(
          dimension: 'identity',
          primaryText: '你和 TA 都来自同一校园',
          totalPointCount: 2,
          source: 'identity',
        ),
      ],
    );
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'micro',
              'contentType': 'micro',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '临时改地点提醒',
              'body': post.body,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    // V1.0：交集作为推荐解释层入口（作者区「N 个交集 >」），不在 caption 内平铺。
    expect(
      find.byKey(const ValueKey<String>('works-caption-intersection-reason')),
      findsNothing,
    );
    final entry = find.byKey(const ValueKey('immersive-intersection-entry'));
    expect(entry, findsOneWidget);
    expect(
      find.text(UITextConstants.intersectionEntrySummary(1)),
      findsOneWidget,
    );
    expect(find.text('你和 TA 都来自同一校园'), findsNothing);

    // 点击入口弹出交集详情面板，展示完整 displayText。
    await tester.tap(entry);
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey<String>('works-intersection-detail-sheet')),
      findsOneWidget,
    );
    expect(find.text('你和 TA 都来自同一校园'), findsOneWidget);
    // V1.0：详情 sheet 为「为什么推荐给你」+ ✓ 证据列表。
    expect(find.text(UITextConstants.intersectionDetailTitle), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('works-intersection-check')),
      findsOneWidget,
    );
  });

  testWidgets('text-only moment 在 iPad 宽屏下顶部内容底部共享 text rail', (tester) async {
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = const Size(1024, 1366);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final post = _textMoment();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'micro',
              'contentType': 'micro',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '临时改地点提醒',
              'body': post.body,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    await tester.pumpAndSettle();

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    final topRailRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-top-rail')),
    );
    final textRailRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-text-stage-rail')),
    );
    final bottomRailRect = tester.getRect(
      find.byKey(const ValueKey('immersive-engagement-rail')),
    );
    final expectedRailWidth = (viewerRect.width - AppSpacing.containerMd * 2)
        .clamp(0.0, AppSpacing.feedMaxContentWidth);
    final expectedSideMargin = (viewerRect.width - expectedRailWidth) / 2;

    expect((topRailRect.left - expectedSideMargin).abs(), lessThan(1));
    expect((textRailRect.left - expectedSideMargin).abs(), lessThan(1));
    expect((bottomRailRect.left - expectedSideMargin).abs(), lessThan(1));
    expect(
      (viewerRect.right - topRailRect.right - expectedSideMargin).abs(),
      lessThan(1),
    );
    expect(
      (viewerRect.right - textRailRect.right - expectedSideMargin).abs(),
      lessThan(1),
    );
    expect(
      (viewerRect.right - bottomRailRect.right - expectedSideMargin).abs(),
      lessThan(1),
    );
  });

  testWidgets('沉浸式浏览器更多功能使用贴底非全屏面板', (tester) async {
    final post = _photoPost();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(CupertinoIcons.ellipsis));
    await tester.pumpAndSettle();

    final panel = find.byKey(TestKeys.modalBottomSheetPanel);
    final screenHeight =
        tester.view.physicalSize.height / tester.view.devicePixelRatio;

    expect(panel, findsOneWidget);
    expect(find.text('取消'), findsOneWidget);
    expect(tester.getTopLeft(panel).dy, greaterThan(0));
    expect(tester.getBottomRight(panel).dy, closeTo(screenHeight, 2.0));
  });

  testWidgets('沉浸式浏览器更多功能在不感兴趣上方提供深色「内容过滤」入口并支持多选', (tester) async {
    final post = _photoPost();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(CupertinoIcons.ellipsis));
    await tester.pumpAndSettle();

    final contentFilter = find.text('内容过滤');
    final notInterested = find.text('不感兴趣');
    expect(contentFilter, findsOneWidget);
    expect(notInterested, findsOneWidget);
    expect(
      tester.getTopLeft(contentFilter).dy,
      lessThan(tester.getTopLeft(notInterested).dy),
    );

    final panelContainer = tester.widget<Container>(
      find.byKey(TestKeys.modalBottomSheetPanel),
    );
    final panelDecoration = panelContainer.decoration! as BoxDecoration;
    expect(
      panelDecoration.color,
      equals(SettingsSemanticConstants.conversationSheetPanelBackground(true)),
    );

    await tester.tap(contentFilter);
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('more-action-content-filter-panel')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('more-action-content-filter-image')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('more-action-content-filter-video')),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('more-action-content-filter-image')),
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey<String>('more-action-content-filter-video')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('完成'));
    await tester.pumpAndSettle();

    expect(find.text('图片 / 视频'), findsOneWidget);
  });

  testWidgets('内容过滤多选后作品流按组合筛选，不再显示未选中的文章', (tester) async {
    final photo = _photoPost();
    final video = _videoPost(width: 1920, height: 1080);
    final article = _articlePost();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [photo, video, article],
          externalPostViews: [
            ContentSurfaceViewMapper.fromDto(photo),
            ContentSurfaceViewMapper.fromDto(video),
            ContentSurfaceViewMapper.fromDto(article),
          ],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(CupertinoIcons.ellipsis));
    await tester.pumpAndSettle();
    await tester.tap(find.text('内容过滤'));
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey<String>('more-action-content-filter-image')),
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey<String>('more-action-content-filter-video')),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('完成'));
    await tester.pumpAndSettle();
    expect(find.text(article.title), findsNothing);
    expect(find.byType(VideoPlayerWidget), findsNothing);
    expect(find.text('图片 / 视频'), findsOneWidget);
  });

  testWidgets('图片滑到边界后从内容区继续横滑不会切换主 tab', (tester) async {
    final post = _photoPost(
      imageUrls: const [
        'https://example.com/photo.jpg',
        'https://example.com/photo-2.jpg',
      ],
    );
    var switchedToCircles = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          initialImageIndex: 1,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onSwitchToCircles: () {
            switchedToCircles = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    await tester.dragFrom(
      tester.getCenter(find.byType(WorksImmersiveViewer)),
      const Offset(-220, 0),
    );
    await tester.pumpAndSettle();

    expect(switchedToCircles, isFalse);
  });

  testWidgets('图片首图从内容区继续横滑时会出现回弹并恢复原位', (tester) async {
    final post = _photoPost(
      imageUrls: const [
        'https://example.com/photo.jpg',
        'https://example.com/photo-2.jpg',
      ],
    );
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: false,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          initialImageIndex: 0,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    final photoStage = find.byKey(const ValueKey<String>('works-photo-stage'));
    final initialRect = tester.getRect(photoStage);
    final gesture = await tester.startGesture(initialRect.center);
    await gesture.moveBy(const Offset(24, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(48, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(48, 0));
    await tester.pump();

    final draggedTransform = tester
        .widget<AnimatedContainer>(photoStage)
        .transform;
    expect(draggedTransform, isNotNull);
    expect(draggedTransform!.storage[12], greaterThan(8));
    expect(dismissed, isFalse);

    await gesture.up();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 260));
    await tester.pumpAndSettle();

    final settledTransform = tester
        .widget<AnimatedContainer>(photoStage)
        .transform;
    expect(settledTransform, isNotNull);
    expect(settledTransform!.storage[12], closeTo(0, 0.5));
    expect(dismissed, isFalse);
  });

  testWidgets('图片末图从内容区继续横滑时会出现回弹并恢复原位', (tester) async {
    final post = _photoPost(
      imageUrls: const [
        'https://example.com/photo.jpg',
        'https://example.com/photo-2.jpg',
      ],
    );
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: false,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          initialImageIndex: 1,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    final photoStage = find.byKey(const ValueKey<String>('works-photo-stage'));
    final initialRect = tester.getRect(photoStage);
    final gesture = await tester.startGesture(initialRect.center);
    await gesture.moveBy(const Offset(-24, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(-48, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(-48, 0));
    await tester.pump();

    final draggedTransform = tester
        .widget<AnimatedContainer>(photoStage)
        .transform;
    expect(draggedTransform, isNotNull);
    expect(draggedTransform!.storage[12], lessThan(-8));
    expect(dismissed, isFalse);

    await gesture.up();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 260));
    await tester.pumpAndSettle();

    final settledTransform = tester
        .widget<AnimatedContainer>(photoStage)
        .transform;
    expect(settledTransform, isNotNull);
    expect(settledTransform!.storage[12], closeTo(0, 0.5));
    expect(dismissed, isFalse);
  });

  testWidgets('文章翻页到边界后从内容区继续横滑不会切换主 tab', (tester) async {
    final post = _articlePost();
    var switchedToCircles = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onSwitchToCircles: () {
            switchedToCircles = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    await _flipArticleToLastPage(tester);
    _expectArticleAdvancedPastFirstPage(tester);

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();

    expect(switchedToCircles, isFalse);
  });

  testWidgets('多页文章在首页从内容区继续横滑时会出现回弹并恢复原位', (tester) async {
    final post = _articlePost();
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    final stage = find.byKey(const ValueKey<String>('article-boundary-stage'));
    final stageRect = tester.getRect(stage);
    final gesture = await tester.startGesture(
      Offset(stageRect.left + 120, stageRect.center.dy),
    );
    await gesture.moveBy(const Offset(24, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(48, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(48, 0));
    await tester.pump();

    final draggedTransform = tester.widget<AnimatedContainer>(stage).transform;
    expect(draggedTransform, isNotNull);
    expect(draggedTransform!.storage[12], greaterThan(8));
    expect(dismissed, isFalse);

    await gesture.up();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 260));
    await tester.pumpAndSettle();

    final settledTransform = tester.widget<AnimatedContainer>(stage).transform;
    expect(settledTransform, isNotNull);
    expect(settledTransform!.storage[12], closeTo(0, 0.5));
    expect(dismissed, isFalse);
  });

  testWidgets('多页文章在末页从内容区继续横滑时会出现回弹并恢复原位', (tester) async {
    final post = _articlePost();
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    await _flipArticleToLastPage(tester);

    final stage = find.byKey(const ValueKey<String>('article-boundary-stage'));
    final stageRect = tester.getRect(stage);
    final gesture = await tester.startGesture(
      Offset(stageRect.right - 120, stageRect.center.dy),
    );
    await gesture.moveBy(const Offset(-24, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(-48, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(-48, 0));
    await tester.pump();

    final draggedTransform = tester.widget<AnimatedContainer>(stage).transform;
    expect(draggedTransform, isNotNull);
    expect(draggedTransform!.storage[12], lessThan(-8));
    expect(dismissed, isFalse);

    await gesture.up();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 260));
    await tester.pumpAndSettle();

    final settledTransform = tester.widget<AnimatedContainer>(stage).transform;
    expect(settledTransform, isNotNull);
    expect(settledTransform!.storage[12], closeTo(0, 0.5));
    expect(dismissed, isFalse);
  });

  testWidgets('长正文文章底部页码跟随真实排版页数而不是 fallback 单页', (tester) async {
    final post = _articlePost();
    final markdownSections = List<String>.generate(
      14,
      (index) =>
          '## 小节${index + 1}\n\n这是一段用于沉浸式文章自动分页的长正文，需要被继续拆到后续页面中，不能仍然停留在 1/1。',
    ).join('\n\n');
    final articleMarkdown =
        '---\n'
        'title: ${post.title}\n'
        'template: ${post.articleTemplate}\n'
        'fontPreset: ${post.articleFontPreset}\n'
        '---\n\n'
        '$markdownSections\n';

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'article',
              'contentType': 'article',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': post.title,
              'body': post.body,
              'summary': post.summary,
              'coverUrl': post.coverUrl,
              'articleTemplate': post.articleTemplate,
              'articleFontPreset': post.articleFontPreset,
              'articleMarkdown': articleMarkdown,
              'articleMarkdownVersion': 'qwq-rich-md/1',
              'articleAssetManifest': const <String, dynamic>{
                'schemaVersion': 1,
                'articleMarkdownVersion': 'qwq-rich-md/1',
                'articleMarkdownDigest': 'fixture:test-long',
                'assets': <Map<String, dynamic>>[],
              },
              'articleRenderProfile': <String, dynamic>{
                'template': post.articleTemplate,
                'fontPreset': post.articleFontPreset,
              },
              'cards': const <Map<String, dynamic>>[],
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('works-article-page-progress')),
      findsOneWidget,
    );
    final progressLabel = tester.widget<Text>(
      find.byKey(const ValueKey<String>('works-article-page-progress')),
    );
    expect(
      progressLabel.data,
      isNot(UITextConstants.workArticlePageProgress(1, 1)),
    );

    // V1.0：页码两侧 chevron `‹ ›` 可点切页（正文后、作者工具栏前）。
    final prevChevron = find.byKey(
      const ValueKey<String>('works-article-page-prev'),
    );
    final nextChevron = find.byKey(
      const ValueKey<String>('works-article-page-next'),
    );
    expect(prevChevron, findsOneWidget);
    expect(nextChevron, findsOneWidget);

    await tester.tap(nextChevron);
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();
    final advancedLabel = tester.widget<Text>(
      find.byKey(const ValueKey<String>('works-article-page-progress')),
    );
    expect(advancedLabel.data, startsWith('2 / '));

    await tester.tap(prevChevron);
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();
    final restoredLabel = tester.widget<Text>(
      find.byKey(const ValueKey<String>('works-article-page-progress')),
    );
    expect(restoredLabel.data, startsWith('1 / '));
  });

  testWidgets('单页文章从内容区横滑时只回弹不进入翻页宿主', (tester) async {
    final post = _articlePost();
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(
              post,
              '---\n'
              'title: 单页文章\n'
              'template: ${post.articleTemplate}\n'
              'fontPreset: ${post.articleFontPreset}\n'
              '---\n\n'
              '这是一页内就能装下的短正文。\n',
            ),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.workArticlePageProgress(1, 1)),
      findsOneWidget,
    );
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsNothing);

    final stage = find.byKey(const ValueKey<String>('article-boundary-stage'));
    final stageRect = tester.getRect(stage);
    final gesture = await tester.startGesture(stageRect.center);
    await gesture.moveBy(const Offset(24, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(48, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(48, 0));
    await tester.pump();

    final draggedTransform = tester.widget<AnimatedContainer>(stage).transform;
    expect(draggedTransform, isNotNull);
    expect(draggedTransform!.storage[12], greaterThan(8));
    expect(dismissed, isFalse);

    await gesture.up();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 260));
    await tester.pumpAndSettle();

    final settledTransform = tester.widget<AnimatedContainer>(stage).transform;
    expect(settledTransform, isNotNull);
    expect(settledTransform!.storage[12], closeTo(0, 0.5));
    expect(dismissed, isFalse);
  });

  testWidgets('Android 下图片左边缘横滑会退出当前沉浸页', (tester) async {
    final post = _photoPost(
      imageUrls: const [
        'https://example.com/photo.jpg',
        'https://example.com/photo-2.jpg',
      ],
    );
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: false,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          initialImageIndex: 0,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    final imageRect = tester.getRect(find.byType(CachedNetworkImage).first);
    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    await tester.dragFrom(
      Offset(imageRect.left + 6, viewerRect.center.dy),
      const Offset(220, 0),
    );
    await tester.pumpAndSettle();

    expect(dismissed, isTrue);
  });

  testWidgets('视频从内容区横滑到首末边界时不会退出，仍由屏幕边缘手势返回', (tester) async {
    final post = _videoPost(width: 1920, height: 1080);
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: false,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));

    await tester.dragFrom(
      Offset(viewerRect.center.dx, viewerRect.center.dy),
      const Offset(220, 0),
    );
    await tester.pumpAndSettle();
    expect(dismissed, isFalse);

    await tester.dragFrom(
      Offset(viewerRect.left + 6, viewerRect.center.dy),
      const Offset(220, 0),
    );
    await tester.pumpAndSettle();
    expect(dismissed, isTrue);
  });

  testWidgets('iOS 下右边缘横滑不会触发沉浸式返回', (tester) async {
    final post = _photoPost(
      imageUrls: const ['https://example.com/photo-only.jpg'],
    );
    var dismissed = false;
    final container = ProviderContainer();

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          theme: ThemeData(platform: TargetPlatform.iOS),
          home: Scaffold(
            body: MediaQuery(
              data: const MediaQueryData(size: Size(390, 844)),
              child: WorksImmersiveViewer(
                showWorksToolbar: false,
                showTopNavigation: false,
                externalPosts: [post],
                externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
                onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
                onAssistantTap: () {},
                onTapBack: () {
                  dismissed = true;
                },
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    await tester.dragFrom(
      Offset(viewerRect.right - 6, viewerRect.center.dy),
      const Offset(-220, 0),
    );
    await tester.pumpAndSettle();

    expect(dismissed, isFalse);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    container.dispose();
  });

  testWidgets('Android 下文章右边缘横滑会退出当前沉浸页', (tester) async {
    final post = _articlePost();
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    await _flipArticleToLastPage(tester);
    _expectArticleAdvancedPastFirstPage(tester);

    final deckRect = tester.getRect(find.byType(ArticleReadOnlyBookDeck));
    final rightHotzoneRect = tester.getRect(
      find.byKey(TestKeys.articlePageCurlHotzoneBottomRight),
    );
    expect(rightHotzoneRect.right, lessThan(deckRect.right));

    await tester.dragFrom(
      Offset(deckRect.right - 6, deckRect.bottom - 80),
      const Offset(-220, -20),
    );
    await tester.pumpAndSettle();

    expect(dismissed, isTrue);
  });

  testWidgets('文章阅读使用底部页码且封面与标题正文共用第一页', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'article',
              'contentType': 'article',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': post.title,
              'body': post.body,
              'summary': post.summary,
              'coverUrl': post.coverUrl,
              'articleTemplate': post.articleTemplate,
              'articleFontPreset': post.articleFontPreset,
              'articleMarkdown':
                  '---\n'
                  'title: ${post.title}\n'
                  'template: ${post.articleTemplate}\n'
                  'fontPreset: ${post.articleFontPreset}\n'
                  'cover_asset_id: cover\n'
                  '---\n\n'
                  '# ${post.title}\n\n'
                  ':::figure id="cover" layout="fullWidth" caption=""\n'
                  'asset://cover\n'
                  ':::\n\n'
                  '第一页前言。\n\n'
                  '第二段落继续展开说明。\n\n'
                  '第三段落把正文推到下一页。\n',
              'articleMarkdownVersion': 'qwq-rich-md/1',
              'articleAssetManifest': <String, dynamic>{
                'schemaVersion': 1,
                'articleMarkdownVersion': 'qwq-rich-md/1',
                'articleMarkdownDigest': 'fixture:test',
                'assets': <Map<String, dynamic>>[
                  {
                    'assetId': 'cover',
                    'cdnUrl': post.coverUrl,
                    'role': 'cover',
                  },
                ],
              },
              'articleRenderProfile': <String, dynamic>{
                'template': post.articleTemplate,
                'fontPreset': post.articleFontPreset,
              },
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('works-top-back')),
      findsOneWidget,
    );
    // V1.0：文章页码在正文下方、作者工具栏上方，禁止顶部页码与点指示器。
    expect(
      find.byKey(const ValueKey<String>('works-top-progress-label')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('works-article-page-progress')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('works-page-indicator')),
      findsNothing,
    );
    expect(find.textContaining('/'), findsWidgets);
    expect(find.byType(MediaBlurCaptionOverlay), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('article-frontispiece-image')),
      findsNothing,
    );
    expect(find.text(post.title), findsWidgets);
    expect(find.textContaining('第一页前言'), findsWidgets);

    // Dark Paper：文章作品默认深色纸张舞台，页码两侧带可点 chevron。
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is ColoredBox &&
            widget.color == ArticlePaperPaletteColors.darkPaperStage,
      ),
      findsWidgets,
    );
    expect(
      find.byKey(const ValueKey<String>('works-article-page-prev')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('works-article-page-next')),
      findsOneWidget,
    );
  });

  testWidgets('文章按垂类默认使用深色纸张且阅读设置可实时切换', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(
              post,
              _multiPageArticleMarkdown(post),
              extra: const <String, dynamic>{
                'contentVertical': 'travel',
                'articleRenderProfile': <String, dynamic>{
                  'template': 'journal',
                  'fontPreset': 'clean',
                  'contentVertical': 'travel',
                  'paperThemeMode': 'system',
                },
              },
            ),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is ColoredBox &&
            widget.color == ArticlePaperPaletteColors.warmBlackStage,
      ),
      findsWidgets,
    );
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is ColoredBox &&
            widget.color == ArticlePaperPaletteColors.darkPaperStage,
      ),
      findsNothing,
    );

    await tester.tap(find.byKey(const ValueKey<String>('works-top-more')));
    await tester.pumpAndSettle();
    expect(find.text('阅读设置'), findsOneWidget);
    await tester.tap(find.text('阅读设置'));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey<String>('more-action-reading-settings-panel')),
      findsOneWidget,
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('more-action-reading-theme-coolGray')),
    );
    await tester.pumpAndSettle();

    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is ColoredBox &&
            widget.color == ArticlePaperPaletteColors.coolGrayStage,
      ),
      findsWidgets,
    );
  });

  testWidgets('文章实体标签点击进入 homepageDetail metadata 路由', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrapWithRouter(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(
              post,
              '---\n'
              'title: 杭州一日游\n'
              'template: journal\n'
              'fontPreset: clean\n'
              '---\n\n'
              '# 杭州一日游\n\n'
              '@[灵隐寺](entity:sight:west_lake)\n',
              extra: const <String, dynamic>{
                'contentVertical': 'travel',
                'entityMentions': <Map<String, dynamic>>[
                  {
                    'subjectType': 'entity',
                    'subjectId': 'entity:sight:west_lake',
                    'displayName': '灵隐寺',
                    'rangeStart': 3,
                    'rangeEnd': 6,
                  },
                ],
              },
            ),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    final entityText = find.byKey(
      const ValueKey<String>('article-entity-rich-text'),
    );
    expect(entityText, findsWidgets);
    await _tapRichTextSubstring(tester, entityText.hitTestable().first, '灵隐寺');
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('homepage-detail-probe')),
      findsOneWidget,
    );
    expect(find.text('homepage:homepage_sight_west_lake'), findsOneWidget);
  });

  testWidgets('文章阅读不显示底部 caption rail 且页码只保留正文下方一处', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(
              post,
              _multiPageArticleMarkdown(post),
              extra: const <String, dynamic>{
                'circleId': 'circle-design',
                'circleName': '设计圈',
              },
            ),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('works-top-progress-label')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('works-article-page-progress')),
      findsOneWidget,
    );
    final progressLabel = _articleProgressLabel(tester);
    expect(progressLabel, startsWith('1 / '));
    expect(progressLabel, isNot(UITextConstants.workArticlePageProgress(1, 1)));
    expect(
      find.byKey(const ValueKey<String>('works-caption-rail')),
      findsNothing,
    );
  });

  testWidgets('文章阅读纸面页头展示创作与更新时间语义', (tester) async {
    final post = _articlePost().copyWith(
      createdAt: DateTime(2025, 5, 15),
      updatedAt: DateTime(2025, 6, 20),
    );

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(find.textContaining('创作于'), findsWidgets);
    expect(find.textContaining('更新于'), findsWidgets);
  });

  testWidgets('文章阅读支持页角热区翻页', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(find.byType(ArticleReaderFlipHost), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);

    // 页角热区向内拖拽会揭开相邻页：断言末节内容（位于第 2 页）被翻出到组件树。
    final deckRect = tester.getRect(find.byType(ArticleReadOnlyBookDeck));
    await tester.dragFrom(
      Offset(deckRect.right - 2, deckRect.bottom - 80),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('小节14'), findsWidgets);
  });

  testWidgets('长文阅读会自动降级为 book-style pager', (tester) async {
    final post = _articlePost();
    // 触发页数 > maxPageCurlPages(80) 的长文：以足量长正文小节驱动排版流分页，
    // markdown-only 后不再用 cards 借壳页数。
    final longMarkdown = _multiPageArticleMarkdown(
      post,
      sections: 420,
      paragraphsPerSection: 6,
    );

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, longMarkdown),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.articleBookStylePager), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsNothing);
  });

  testWidgets('文章 book reader 总开关关闭时仍使用统一阅读器并上报 feature 关闭 fallback', (
    tester,
  ) async {
    final post = _articlePost();
    final analytics = _FakeAnalyticsService();
    final repo = _ConfigurableContentRepository(
      appConfig: <String, dynamic>{
        'app_bootstrap': <String, dynamic>{
          'activationPolicy': <String, dynamic>{'default': 'immediate'},
        },
        'content': <String, dynamic>{
          'feature_flags': <String, dynamic>{
            'enable_article_book_reader': false,
            'enable_article_page_curl': true,
          },
        },
      },
    );

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [
          contentRepositoryProvider.overrideWithValue(repo),
          analyticsProvider.overrideWithValue(analytics),
        ],
        useRemoteMode: true,
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(find.byType(ArticleReadOnlyBookDeck), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);

    await _flipArticleToLastPage(tester);
    _expectArticleAdvancedPastFirstPage(tester);
    final fallbackEvent = analytics.events.firstWhere(
      (event) => event.eventName == 'article_reader_fallback_rate',
    );
    expect(fallbackEvent.properties['reason'], equals('feature_flag_disabled'));
  });

  testWidgets('文章摘要快照会异步水合详情并上报 hydration 埋点', (tester) async {
    final post = _articlePost();
    final analytics = _FakeAnalyticsService();
    final repo = _ConfigurableContentRepository(
      detailById: <String, Map<String, dynamic>>{
        post.id: <String, dynamic>{
          'postId': post.id,
          'type': 'article',
          'contentType': 'article',
          'authorId': post.authorId,
          'authorNickname': post.displayName,
          'authorAvatarUrl': post.avatarUrl,
          'coverUrl': post.coverUrl,
          'articleTemplate': post.articleTemplate,
          'articleFontPreset': post.articleFontPreset,
          'articleMarkdown':
              '---\n'
              'title: 水合后的标题\n'
              'template: ${post.articleTemplate}\n'
              'fontPreset: ${post.articleFontPreset}\n'
              '---\n\n'
              '## 水合章节\n\n'
              '水合后的正文第一段。\n\n'
              '水合后的正文第二段。\n',
          'articleMarkdownVersion': 'qwq-rich-md/1',
          'articleAssetManifest': const <String, dynamic>{
            'schemaVersion': 1,
            'articleMarkdownVersion': 'qwq-rich-md/1',
            'articleMarkdownDigest': 'fixture:hydrated',
            'assets': <Map<String, dynamic>>[],
          },
          'articleRenderProfile': <String, dynamic>{
            'template': post.articleTemplate,
            'fontPreset': post.articleFontPreset,
          },
        },
      },
    );

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'article',
              'contentType': 'article',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '分发标题',
              'body': '分发摘要正文',
              'coverUrl': post.coverUrl,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [
          contentRepositoryProvider.overrideWithValue(repo),
          analyticsProvider.overrideWithValue(analytics),
        ],
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(repo.getPostCallCount, equals(1));
    expect(find.text('水合后的标题'), findsWidgets);
    expect(find.textContaining('水合后的正文第一段'), findsWidgets);

    final hydrationEvent = analytics.events.firstWhere(
      (event) => event.eventName == 'article_reader_hydration_ms',
    );
    expect(hydrationEvent.properties['result'], equals('success'));
    final structureFallback = analytics.events.firstWhere(
      (event) =>
          event.eventName == 'article_reader_fallback_rate' &&
          (event.properties['reason'] as String).startsWith(
            'document_structure:',
          ),
    );
    expect(structureFallback.properties['reason'], contains('empty'));
  });

  testWidgets('文章详情水合失败后进入显式错误态且不在当前会话内重复拉取', (tester) async {
    final post = _articlePost();
    final analytics = _FakeAnalyticsService();
    final repo = _ConfigurableContentRepository();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'article',
              'contentType': 'article',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '分发标题',
              'body': '分发摘要正文',
              'coverUrl': post.coverUrl,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [
          contentRepositoryProvider.overrideWithValue(repo),
          analyticsProvider.overrideWithValue(analytics),
        ],
      ),
    );

    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(repo.getPostCallCount, equals(1));
    expect(
      find.byKey(ValueKey<String>('article-hydration-error-${post.id}')),
      findsOneWidget,
    );

    await tester.pump();
    await tester.pumpAndSettle();
    expect(repo.getPostCallCount, equals(1));

    final hydrationEvent = analytics.events.firstWhere(
      (event) => event.eventName == 'article_reader_hydration_ms',
    );
    expect(hydrationEvent.properties['result'], equals('error'));
  });

  testWidgets('沉浸式阅读器中的文章回翻保持统一 book deck 宿主', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(find.byType(ArticleReadOnlyBookDeck), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();
    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
      const Offset(260, -40),
    );
    await tester.pumpAndSettle();

    expect(find.byType(ArticleReadOnlyBookDeck), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);
  });
}
