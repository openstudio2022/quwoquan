import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/components/media/shared/viewer/media_caption_widgets.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/ui/content/pages/unified_media_viewer_page.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';
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
                posts: <PostSummaryView>[PostSummaryView.fromDto(post)],
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
          externalPostViews: [PostSummaryView.fromDto(post)],
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

  testWidgets('text-only moment 使用文本画布展示 title/body', (tester) async {
    final post = _textMoment();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [PostSummaryView.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
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
          externalPostViews: [PostSummaryView.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'moment',
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
          externalPostViews: [PostSummaryView.fromDto(post)],
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
              'coverUrl': post.coverUrl,
              'cards': const [
                {'title': '第二页标题', 'body': '第二页正文'},
              ],
            },
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

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();
    expect(find.text('第二页标题'), findsWidgets);

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
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
              'articleDocument': <String, dynamic>{
                'template': post.articleTemplate,
                'fontPreset': post.articleFontPreset,
                'coverImageUrl': post.coverUrl,
                'titleStyle': 'major',
                'nodes': <Map<String, dynamic>>[
                  {'id': 'title', 'type': 'documentTitle', 'text': post.title},
                  {'id': 'p0', 'type': 'paragraph', 'text': '第一页前言。'},
                  {'id': 'p1', 'type': 'paragraph', 'text': '第二段落继续展开说明。'},
                  {'id': 'p2', 'type': 'paragraph', 'text': '第三段落把正文推到下一页。'},
                ],
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
      findsWidgets,
    );
    final imageRect = tester.getRect(
      find.byKey(const ValueKey<String>('article-frontispiece-image')).first,
    );
    expect(imageRect.height, greaterThan(0));
    expect(find.text(post.title), findsWidgets);
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
          rawPostsById: _viewerRawByPostId({
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
              'cards': const [
                {'title': '第二页标题', 'body': '第二页正文'},
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

    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();

    expect(find.text('第二页标题'), findsWidgets);
  });

  testWidgets('长文阅读会自动降级为 book-style pager', (tester) async {
    final post = _articlePost();
    final cards = List<Map<String, dynamic>>.generate(
      82,
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
          rawPostsById: _viewerRawByPostId({
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
              'cards': cards,
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
          rawPostsById: _viewerRawByPostId({
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

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();

    expect(find.text('第二页标题'), findsWidgets);
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
          'articleDocument': <String, dynamic>{
            'template': post.articleTemplate,
            'fontPreset': post.articleFontPreset,
            'coverImageUrl': post.coverUrl,
            'titleStyle': 'major',
            'nodes': <Map<String, dynamic>>[
              {'id': 'title', 'type': 'documentTitle', 'text': '水合后的标题'},
              {'id': 'h2', 'type': 'headingMajor', 'text': '水合章节'},
              {'id': 'p1', 'type': 'paragraph', 'text': '水合后的正文第一段。'},
              {'id': 'p2', 'type': 'paragraph', 'text': '水合后的正文第二段。'},
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
    expect(structureFallback.properties['reason'], contains('body'));
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
          rawPostsById: _viewerRawByPostId({
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
          }),
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
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();

    final flipEvent = analytics.events.firstWhere(
      (event) => event.eventName == 'article_page_flip_commit_ms',
    );
    expect(flipEvent.properties['mechanism'], equals('page_curl'));
    expect(flipEvent.properties['direction'], equals('forward'));
  });

  testWidgets('文章回翻会记录 backward flip commit 埋点', (tester) async {
    final post = _articlePost();
    final analytics = _FakeAnalyticsService();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [PostSummaryView.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
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
          }),
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
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
      const Offset(260, -40),
    );
    await tester.pumpAndSettle();

    final flipEvents = analytics.events
        .where((event) => event.eventName == 'article_page_flip_commit_ms')
        .toList(growable: false);
    expect(flipEvents, isNotEmpty);
    expect(flipEvents.last.properties['mechanism'], equals('page_curl'));
    expect(flipEvents.last.properties['direction'], equals('backward'));
  });

  testWidgets('沉浸式阅读器中的文章回翻保持统一 book deck 宿主', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [PostSummaryView.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
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
