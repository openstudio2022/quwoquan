import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/components/media/shared/viewer/media_caption_widgets.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';

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
  Future<Map<String, dynamic>> getAppConfig() async {
    return appConfig ?? super.getAppConfig();
  }

  @override
  Future<Map<String, dynamic>> getPost({required String postId}) async {
    getPostCallCount += 1;
    final detail = detailById[postId];
    if (detail != null) {
      return Map<String, dynamic>.from(detail);
    }
    return super.getPost(postId: postId);
  }
}

class _RemoteModeNotifier extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.remote;
}

PhotoPostDto _photoPost({
  List<String> imageUrls = const ['https://example.com/photo.jpg'],
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
    likeCount: 0,
    commentCount: 0,
    favoriteCount: 0,
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
    articlePresentationVersion: 1,
    likeCount: 0,
    commentCount: 0,
    favoriteCount: 0,
    shareCount: 0,
    createdAt: DateTime.now(),
  );
}

MomentPostDto _textMoment() {
  return MomentPostDto(
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
    favoriteCount: 0,
    shareCount: 0,
    createdAt: DateTime.now(),
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

void _consumeImageLoadExceptions(WidgetTester tester) {
  while (tester.takeException() != null) {
    // swallow network image loading errors in widget tests
  }
}

void main() {
  setUp(() {
    HttpOverrides.global = _FakeHttpOverrides();
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
          externalPostViews: [PostSummaryView.fromDto(post)],
          rawPostsById: <String, Map<String, dynamic>>{
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
          },
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
    expect(
      find.byKey(const ValueKey<String>('works-top-progress-label')),
      findsOneWidget,
    );
    expect(find.text('1/8'), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('works-page-indicator')),
      findsNothing,
    );
    final indicatorRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-top-progress-label')),
    );
    final backRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-top-back')),
    );
    final titleRect = tester.getRect(find.text('封面标题'));
    expect(indicatorRect.left, greaterThan(backRect.right));
    expect(indicatorRect.bottom, lessThan(titleRect.top));
    expect(find.text('测试圈子A'), findsOneWidget);
    expect(find.text('测试圈子B'), findsOneWidget);
    expect(find.byType(MediaBlurCaptionOverlay), findsNothing);
  });

  testWidgets('text-only moment 使用文本画布展示 title/body', (tester) async {
    final post = _textMoment();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [PostSummaryView.fromDto(post)],
          rawPostsById: <String, Map<String, dynamic>>{
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'moment',
              'contentType': 'micro',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '临时改地点提醒',
              'body': post.body,
              'circleName': '测试圈子',
            },
          },
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('临时改地点提醒'), findsOneWidget);
    expect(find.textContaining('今天风有点大'), findsOneWidget);
  });

  testWidgets('沉浸式浏览器更多功能使用贴底非全屏面板', (tester) async {
    final post = _photoPost();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [PostSummaryView.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.more_horiz_rounded));
    await tester.pumpAndSettle();

    final panel = find.byKey(TestKeys.modalBottomSheetPanel);
    final screenHeight =
        tester.view.physicalSize.height / tester.view.devicePixelRatio;

    expect(panel, findsOneWidget);
    expect(find.text('取消'), findsOneWidget);
    expect(tester.getTopLeft(panel).dy, greaterThan(0));
    expect(tester.getBottomRight(panel).dy, closeTo(screenHeight, 2.0));
  });

  testWidgets('图片滑到边界后继续横滑会切换主 tab', (tester) async {
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
          externalPostViews: [PostSummaryView.fromDto(post)],
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

    expect(switchedToCircles, isTrue);
  });

  testWidgets('文章翻页到边界后继续横滑会切换主 tab', (tester) async {
    final post = _articlePost();
    var switchedToCircles = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          externalPosts: [post],
          externalPostViews: [PostSummaryView.fromDto(post)],
          rawPostsById: <String, Map<String, dynamic>>{
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'article',
              'contentType': 'article',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': post.title,
              'body': post.body,
              'coverUrl': post.coverUrl,
              'cards': const [
                {'title': '第二页标题', 'body': '第二页正文'},
              ],
            },
          },
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

    final articlePager = find.byType(PageView).last;

    await tester.flingFrom(
      tester.getCenter(articlePager),
      const Offset(-320, 0),
      1400,
    );
    await tester.pumpAndSettle();
    expect(find.text('第二页标题'), findsOneWidget);

    await tester.flingFrom(
      tester.getCenter(articlePager),
      const Offset(-320, 0),
      1400,
    );
    await tester.pumpAndSettle();

    expect(switchedToCircles, isTrue);
  });

  testWidgets('文章阅读使用顶部页码且封面进入扉页式第一页', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [PostSummaryView.fromDto(post)],
          rawPostsById: <String, Map<String, dynamic>>{
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
              'articlePresentationVersion': post.articlePresentationVersion,
              'articleDocument': <String, dynamic>{
                'title': post.title,
                'body': '第一页前言。\n第二段落继续展开说明。\n第三段落把正文推到下一页。',
                'blocks': <Map<String, dynamic>>[
                  {'id': 'p0', 'type': 'paragraph', 'text': '第一页前言。'},
                  {'id': 'p1', 'type': 'paragraph', 'text': '第二段落继续展开说明。'},
                  {'id': 'p2', 'type': 'paragraph', 'text': '第三段落把正文推到下一页。'},
                ],
              },
            },
          },
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
    expect(
      find.byKey(const ValueKey<String>('works-top-progress-label')),
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
      findsOneWidget,
    );
    final imageRect = tester.getRect(
      find.byKey(const ValueKey<String>('article-frontispiece-image')),
    );
    final titleRect = tester.getRect(find.text(post.title));
    expect(titleRect.top, lessThan(imageRect.bottom));
  });

  testWidgets('文章阅读支持页角热区翻页', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [PostSummaryView.fromDto(post)],
          rawPostsById: <String, Map<String, dynamic>>{
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'article',
              'contentType': 'article',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': post.title,
              'body': '第一页正文',
              'summary': post.summary,
              'coverUrl': post.coverUrl,
              'articleTemplate': post.articleTemplate,
              'articleFontPreset': post.articleFontPreset,
              'articlePresentationVersion': post.articlePresentationVersion,
              'cards': const [
                {'title': '第二页标题', 'body': '第二页正文'},
              ],
            },
          },
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneTopRight)),
      const Offset(-260, 60),
    );
    await tester.pumpAndSettle();

    expect(find.text('第二页标题'), findsOneWidget);
  });

  testWidgets('长文阅读会自动降级为 book-style pager', (tester) async {
    final post = _articlePost();
    final cards = List<Map<String, dynamic>>.generate(
      22,
      (index) => <String, dynamic>{
        'title': '第${index + 2}页',
        'body': '这是第 ${index + 2} 页正文。',
      },
    );

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [PostSummaryView.fromDto(post)],
          rawPostsById: <String, Map<String, dynamic>>{
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'article',
              'contentType': 'article',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': post.title,
              'body': '第一页正文',
              'summary': post.summary,
              'coverUrl': post.coverUrl,
              'articleTemplate': post.articleTemplate,
              'articleFontPreset': post.articleFontPreset,
              'articlePresentationVersion': post.articlePresentationVersion,
              'cards': cards,
            },
          },
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

  testWidgets('文章 book reader 总开关关闭时回退 legacy pager 并上报 fallback 埋点', (
    tester,
  ) async {
    final post = _articlePost();
    final analytics = _FakeAnalyticsService();
    final repo = _ConfigurableContentRepository(
      appConfig: <String, dynamic>{
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
          externalPostViews: [PostSummaryView.fromDto(post)],
          rawPostsById: <String, Map<String, dynamic>>{
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'article',
              'contentType': 'article',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': post.title,
              'body': '第一页正文',
              'coverUrl': post.coverUrl,
              'cards': const [
                {'title': '第二页标题', 'body': '第二页正文'},
              ],
            },
          },
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

    expect(find.byType(ArticleReadOnlyBookDeck), findsNothing);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsNothing);

    final articlePager = find.byType(PageView).last;
    await tester.flingFrom(
      tester.getCenter(articlePager),
      const Offset(-320, 0),
      1400,
    );
    await tester.pumpAndSettle();

    expect(find.text('第二页标题'), findsOneWidget);
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
          'articlePresentationVersion': post.articlePresentationVersion,
          'articleDocument': <String, dynamic>{
            'title': '水合后的标题',
            'body': '水合后的正文第一段。\n水合后的正文第二段。',
            'blocks': <Map<String, dynamic>>[
              {'id': 'h2', 'type': 'heading2', 'offset': 0, 'text': '水合章节'},
              {
                'id': 'p1',
                'type': 'paragraph',
                'offset': 4,
                'text': '水合后的正文第一段。',
              },
            ],
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
          externalPostViews: [PostSummaryView.fromDto(post)],
          rawPostsById: <String, Map<String, dynamic>>{
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
          },
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
    expect(find.textContaining('水合后的正文第一段'), findsOneWidget);

    final hydrationEvent = analytics.events.firstWhere(
      (event) => event.eventName == 'article_reader_hydration_ms',
    );
    expect(hydrationEvent.properties['result'], equals('success'));
    final legacyEvent = analytics.events.firstWhere(
      (event) => event.eventName == 'article_legacy_document_fallback_rate',
    );
    expect(legacyEvent.properties['source'], equals('body'));
  });

  testWidgets('文章翻页会记录 flip commit 埋点', (tester) async {
    final post = _articlePost();
    final analytics = _FakeAnalyticsService();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [PostSummaryView.fromDto(post)],
          rawPostsById: <String, Map<String, dynamic>>{
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'article',
              'contentType': 'article',
              'authorId': post.authorId,
              'authorNickname': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': post.title,
              'body': '第一页正文',
              'coverUrl': post.coverUrl,
              'cards': const [
                {'title': '第二页标题', 'body': '第二页正文'},
              ],
            },
          },
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [analyticsProvider.overrideWithValue(analytics)],
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await tester.pumpAndSettle();

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneTopRight)),
      const Offset(-260, 60),
    );
    await tester.pumpAndSettle();

    final flipEvent = analytics.events.firstWhere(
      (event) => event.eventName == 'article_page_flip_commit_ms',
    );
    expect(flipEvent.properties['mechanism'], equals('page_curl'));
    expect(flipEvent.properties['direction'], equals('forward'));
  });
}
