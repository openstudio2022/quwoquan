import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/adapters/circle_query_remote.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/home_circles_hub_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/home_circles_category_tab.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../../../support/service/circle_service/circle_management/circle/typed_circle_query_test_double.dart';
import '../../../../../support/service/circle_service/circle_management/circle/circle_contract_test_builders.dart';

Future<void> _hubPumpSettled(WidgetTester tester) async {
  for (var i = 0; i < 24; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    _consumeImageLoadExceptions(tester);
  }
}

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

class _AuthenticatedHubSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'circle-hub-test-token',
    refreshToken: 'circle-hub-test-refresh-token',
    ownerId: 'fixture-user',
    activePersonaId: 'fixture-persona',
  );
}

CircleDiscoveryFeedPageSlice _hubDiscoveryFeedFixture() {
  final circles = <Circle>[
    buildCircleContract(
      circleId: 'fixture_circle_campus',
      name: '校园同行',
      ownerId: 'owner-campus',
      category: 'campus',
      subCategory: '母校',
      memberCount: 120,
    ),
    buildCircleContract(
      circleId: 'fixture_circle_travel',
      name: '一起旅行',
      ownerId: 'owner-travel',
      category: 'travel',
      subCategory: '城市',
      memberCount: 110,
    ),
    buildCircleContract(
      circleId: 'fixture_circle_photo',
      name: '契约摄影社',
      ownerId: 'owner-photo',
      category: 'photography',
      subCategory: '风光',
      memberCount: 100,
    ),
    buildCircleContract(
      circleId: 'fixture_circle_tech',
      name: '科技前沿',
      ownerId: 'owner-tech',
      category: 'tech',
      subCategory: '数码',
      memberCount: 90,
    ),
    buildCircleContract(
      circleId: 'fixture_circle_car',
      name: '自驾同好',
      ownerId: 'owner-car',
      category: 'car',
      subCategory: '自驾',
      memberCount: 80,
    ),
  ];
  return CircleDiscoveryFeedPageSlice(
    circles: circles,
    items: <CircleFeedItemView>[
      buildCircleFeedItemContract(
        circleId: 'fixture_circle_campus',
        placementId: 'fixture-placement-campus-1',
        postId: 'circle_post_campus_1',
        contentType: 'image',
        contentIdentity: 'work',
        authorId: 'author-campus',
        authorDisplayName: '校园作者',
        body: '校园记录',
        coverUrl: 'media/image/circle_post_campus_1.jpg',
        imageUrls: const <String>['media/image/circle_post_campus_1.jpg'],
      ),
      buildCircleFeedItemContract(
        circleId: 'fixture_circle_photo',
        placementId: 'fixture-placement-photo-image-1',
        postId: 'circle_post_image_1',
        contentType: 'image',
        contentIdentity: 'work',
        authorId: 'author-photo',
        authorDisplayName: '摄影作者',
        body: '山谷晨光',
        coverUrl: 'media/image/circle_post_image_1.jpg',
        imageUrls: const <String>['media/image/circle_post_image_1.jpg'],
      ),
      buildCircleFeedItemContract(
        circleId: 'fixture_circle_photo',
        placementId: 'fixture-placement-photo-video-1',
        postId: 'circle_post_video_1',
        contentType: 'video',
        contentIdentity: 'work',
        authorId: 'author-video',
        authorDisplayName: '视频作者',
        body: '城市延时',
        videoUrl: 'media/video/circle_post_video_1.mp4',
        thumbnailUrl: 'media/image/circle_post_video_1.jpg',
      ),
    ],
  );
}

CircleDiscoveryFeedPageSlice _pagedHubDiscoveryFeedFixture({
  required int start,
  required int count,
  String? nextCursor,
  bool includeFirstPlacement = false,
}) {
  final firstCircle = _hubDiscoveryFeedFixture().circles.first;
  final items = <CircleFeedItemView>[
    if (includeFirstPlacement)
      buildCircleFeedItemContract(
        circleId: firstCircle.id,
        placementId: 'page-placement-0',
        postId: 'page-post-0',
        contentType: 'image',
        contentIdentity: 'work',
      ),
    ...List<CircleFeedItemView>.generate(count, (index) {
      final id = start + index;
      return buildCircleFeedItemContract(
        circleId: firstCircle.id,
        placementId: 'page-placement-$id',
        postId: 'page-post-$id',
        contentType: 'image',
        contentIdentity: 'work',
        body: '第 $id 个游标帖子',
      );
    }),
  ];
  return CircleDiscoveryFeedPageSlice(
    circles: <Circle>[firstCircle],
    items: items,
    cursor: nextCursor,
  );
}

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

Widget _buildTestApp({
  double textScaleFactor = 1.0,
  CircleDiscoveryFeedQueryReader? discoveryFeedQuery,
  List overrides = const [],
}) {
  final router = GoRouter(
    routes: [
      GoRoute(
        path: '/',
        builder: (context, state) => const Scaffold(body: CirclesHubPage()),
      ),
      GoRoute(
        path: '/works/browser/:workId',
        builder: (context, state) =>
            const Scaffold(body: Center(child: Text('work-browser'))),
      ),
      GoRoute(
        path: '/circles',
        builder: (context, state) =>
            const Scaffold(body: Center(child: Text('circles-page'))),
      ),
      GoRoute(
        path: '/login',
        builder: (context, state) =>
            const Scaffold(body: Center(child: Text('login-page'))),
      ),
    ],
  );
  return ProviderScope(
    overrides: [
      resolvedOwnerUserIdProvider.overrideWithValue(''),
      // 生产装配 Remote-only：local_contract 显式注入强类型 query port。
      circlesListDiscoveryFeedQueryProvider.overrideWithValue(
        discoveryFeedQuery ??
            CircleDiscoveryFeedQueryTestDouble(
              (_) => _hubDiscoveryFeedFixture(),
            ),
      ),
      ...overrides,
    ],
    child: MaterialApp.router(
      routerConfig: router,
      builder: (context, child) {
        final mediaQuery = MediaQuery.of(context);
        return MediaQuery(
          data: mediaQuery.copyWith(
            textScaler: TextScaler.linear(textScaleFactor),
          ),
          child: child ?? const SizedBox.shrink(),
        );
      },
    ),
  );
}

void _consumeImageLoadExceptions(WidgetTester tester) {
  Object? exception;
  while ((exception = tester.takeException()) != null) {
    final message = exception.toString();
    if (message.contains('HTTP request failed') ||
        message.contains('NetworkImageLoadException')) {
      continue;
    }
    fail('Unexpected test exception: $message');
  }
}

/// 主垂滑在 [CirclesHubPage] 子树内解析，避免误命中 [MaterialApp] 其它垂直 [Scrollable]。
Finder _hubVerticalScrollable() {
  return find
      .descendant(
        of: find.byType(CirclesHubPage),
        matching: find.byWidgetPredicate(
          (widget) =>
              widget is Scrollable &&
              widget.axisDirection == AxisDirection.down,
        ),
      )
      .at(0);
}

Future<void> _pumpUntilHubGridKeysVisible(WidgetTester tester) async {
  final probe = find.byKey(
    const ValueKey('home-circle-grid-post-circle_post_image_1'),
  );
  await _hubPumpSettled(tester);
  // 渐进式 bootstrap 后 feed 先 setState；短帧轮询有上界（≤~192ms 虚拟时间）
  for (var i = 0; i < 40 && probe.evaluate().isEmpty; i++) {
    await tester.pump(const Duration(milliseconds: 50));
    _consumeImageLoadExceptions(tester);
  }
  await _hubPumpSettled(tester);
}

Future<void> _pumpUntilHubCategoryTabsVisible(WidgetTester tester) async {
  final probe = find.text('车之家');
  await _hubPumpSettled(tester);
  for (var i = 0; i < 40 && probe.evaluate().isEmpty; i++) {
    await tester.pump(const Duration(milliseconds: 50));
    _consumeImageLoadExceptions(tester);
  }
  await _hubPumpSettled(tester);
}

Future<void> _scrollHubUntilVisible(WidgetTester tester, Finder target) async {
  await tester.scrollUntilVisible(
    target,
    200,
    scrollable: _hubVerticalScrollable(),
    maxScrolls: 24,
    duration: const Duration(milliseconds: 8),
  );
  await tester.ensureVisible(target);
  await _hubPumpSettled(tester);
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
    HttpOverrides.global = _FakeHttpOverrides();
    AuthGate.resetDebounce();
  });

  test('生产装配只接受 package runtime；显式注入的 typed double 非空', () async {
    final productionContainer = ProviderContainer();
    addTearDown(productionContainer.dispose);
    if (CloudRuntimeConfig.appRuntimeEnv.trim().isEmpty) {
      expect(
        () => productionContainer.read(circlesListDiscoveryFeedQueryProvider),
        throwsA(
          predicate<Object>(
            (error) => error.toString().contains('Unsupported APP_RUNTIME_ENV'),
          ),
        ),
      );
    } else {
      expect(
        productionContainer.read(circlesListDiscoveryFeedQueryProvider),
        isA<RemoteCircleQueryReader>(),
      );
    }

    final queryReader = CircleDiscoveryFeedQueryTestDouble(
      (_) => _hubDiscoveryFeedFixture(),
    );
    final container = ProviderContainer(
      overrides: [
        circlesListDiscoveryFeedQueryProvider.overrideWithValue(queryReader),
      ],
    );
    addTearDown(container.dispose);
    final page = await container
        .read(circlesListDiscoveryFeedQueryProvider)
        .listDiscoveryFeed(CircleDiscoveryFeedQuery(limit: 20));
    expect(page.items, isNotEmpty);
    expect(queryReader.receivedQueries, hasLength(1));
  });

  testWidgets('首页只展示五个固定业务垂类并隐藏频道管理入口', (tester) async {
    await tester.pumpWidget(_buildTestApp());
    await _hubPumpSettled(tester);
    _consumeImageLoadExceptions(tester);
    await _pumpUntilHubCategoryTabsVisible(tester);

    const labels = <String>['校园', '旅行', '摄影', '科技', '车之家'];
    for (final label in labels) {
      expect(find.text(label), findsOneWidget);
    }
    for (final removed in <String>['遇见', '人文', '生活', '运动', '美食', '车友']) {
      expect(find.text(removed), findsNothing);
    }
    expect(
      find.byIcon(CupertinoIcons.line_horizontal_3_decrease),
      findsNothing,
    );
    for (var i = 0; i < labels.length - 1; i++) {
      expect(
        tester.getTopLeft(find.text(labels[i])).dx,
        lessThan(tester.getTopLeft(find.text(labels[i + 1])).dx),
      );
    }
  });

  testWidgets('默认首屏只读 recommended，认证用户切换我的后才读 mine', (tester) async {
    final queryReader = CircleDiscoveryFeedQueryTestDouble(
      (_) => _hubDiscoveryFeedFixture(),
    );
    await tester.pumpWidget(
      _buildTestApp(
        discoveryFeedQuery: queryReader,
        overrides: [
          authSessionControllerProvider.overrideWith(
            _AuthenticatedHubSession.new,
          ),
          activePersonaContextProvider.overrideWith(
            (_) async => ActivePersonaContextViewData.fallback(
              personaId: 'fixture-persona',
              ownerUserId: 'fixture-user',
              displayName: '圈子测试用户',
              avatarUrl: '',
              contextVersion: 1,
            ),
          ),
        ],
      ),
    );
    await _hubPumpSettled(tester);

    expect(queryReader.receivedQueries, hasLength(1));
    expect(
      queryReader.receivedQueries.single.scope,
      CircleDiscoveryFeedScope.recommended,
    );
    expect(queryReader.receivedQueries.single.limit, 20);

    await tester.tap(find.text(DiscoveryText.circleScenarioMine));
    await _hubPumpSettled(tester);

    expect(queryReader.receivedQueries, hasLength(2));
    expect(
      queryReader.receivedQueries.last.scope,
      CircleDiscoveryFeedScope.mine,
    );

    await tester.tap(find.text(DiscoveryText.circleScenarioRecommended));
    await _hubPumpSettled(tester);
    expect(
      queryReader.receivedQueries,
      hasLength(2),
      reason: '60 秒本地已加载切片保留 cursor，切回推荐不重复请求',
    );
  });

  testWidgets('匿名切换我的不请求 mine，并进入登录续接', (tester) async {
    final queryReader = CircleDiscoveryFeedQueryTestDouble(
      (_) => _hubDiscoveryFeedFixture(),
    );
    await tester.pumpWidget(_buildTestApp(discoveryFeedQuery: queryReader));
    await _hubPumpSettled(tester);

    await tester.tap(find.text(DiscoveryText.circleScenarioMine));
    await _hubPumpSettled(tester);

    expect(queryReader.receivedQueries, hasLength(1));
    expect(find.text('login-page'), findsOneWidget);
  });

  testWidgets('游标分页只用 nextCursor 追加，重复 placement 不重复渲染', (tester) async {
    final queryReader = CircleDiscoveryFeedQueryTestDouble((query) {
      if (query.cursor == 'page-2') {
        return _pagedHubDiscoveryFeedFixture(
          start: 30,
          count: 1,
          includeFirstPlacement: true,
        );
      }
      return _pagedHubDiscoveryFeedFixture(
        start: 0,
        count: 30,
        nextCursor: 'page-2',
      );
    });
    await tester.pumpWidget(_buildTestApp(discoveryFeedQuery: queryReader));
    await _hubPumpSettled(tester);
    await _scrollHubUntilVisible(
      tester,
      find.byKey(const ValueKey('home-circle-grid-post-page-post-29')),
    );

    await tester.drag(_hubVerticalScrollable(), const Offset(0, -600));
    await _hubPumpSettled(tester);
    expect(
      queryReader.receivedQueries.map((query) => query.cursor),
      contains('page-2'),
    );

    await _scrollHubUntilVisible(
      tester,
      find.byKey(const ValueKey('home-circle-grid-post-page-post-30')),
    );
    expect(
      find
          .byKey(const ValueKey('home-circle-grid-post-page-post-0'))
          .evaluate()
          .length,
      lessThanOrEqualTo(1),
    );
  });

  testWidgets('圈子 hub bootstrap 失败时展示统一页态', (tester) async {
    await tester.pumpWidget(
      _buildTestApp(
        discoveryFeedQuery: CircleDiscoveryFeedQueryTestDouble(
          (_) => throw StateError('hub unavailable'),
        ),
      ),
    );
    await _hubPumpSettled(tester);

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(find.text(SearchText.reload), findsOneWidget);
  });

  testWidgets('旧频道偏好不会恢复已下线垂类', (tester) async {
    tester.view.physicalSize = const Size(320, 690);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    SharedPreferences.setMockInitialValues(const <String, Object>{
      'home_circles.selected_channels.v1': <String>['life'],
      'home_circles.selected_channels.v2': <String>['humanity', 'food'],
    });

    await tester.pumpWidget(_buildTestApp());
    await _hubPumpSettled(tester);
    _consumeImageLoadExceptions(tester);
    await _pumpUntilHubCategoryTabsVisible(tester);

    expect(find.text('校园'), findsOneWidget);
    expect(find.text('旅行'), findsOneWidget);
    expect(find.text('摄影'), findsOneWidget);
    expect(find.text('人文'), findsNothing);
    expect(find.text('生活'), findsNothing);
    expect(find.text('美食'), findsNothing);
    expect(
      find.byKey(const ValueKey('home-circles-channel-panel')),
      findsNothing,
    );
  });

  testWidgets('圈子主页区块表面使用更多功能同源语义 token', (tester) async {
    await tester.pumpWidget(_buildTestApp());
    await _hubPumpSettled(tester);
    _consumeImageLoadExceptions(tester);

    final isDark =
        CupertinoTheme.of(
          tester.element(find.byType(CirclesHubPage)),
        ).brightness ==
        Brightness.dark;
    final expectedPageBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.pageBackground,
    );
    final expectedCardSurface =
        SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final cardSurfaceBlocks = find.byWidgetPredicate(
      (widget) => widget is Container && widget.color == expectedCardSurface,
    );

    expect(cardSurfaceBlocks, findsWidgets);
    expect(expectedCardSurface, isNot(expectedPageBackground));
  });

  testWidgets('五个垂类窄屏均保持群组双列自适应', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    late int campusColumns;
    late int travelColumns;
    late int photographyColumns;
    late int techColumns;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) {
            campusColumns = resolveHomeCircleCategoryGridColumns(
              context,
              'campus',
            );
            travelColumns = resolveHomeCircleCategoryGridColumns(
              context,
              'travel',
            );
            photographyColumns = resolveHomeCircleCategoryGridColumns(
              context,
              'photography',
            );
            techColumns = resolveHomeCircleCategoryGridColumns(context, 'tech');
            return const SizedBox.shrink();
          },
        ),
      ),
    );

    expect(travelColumns, greaterThanOrEqualTo(AppSpacing.gridMinColumns));
    expect(photographyColumns, greaterThanOrEqualTo(AppSpacing.gridMinColumns));
    expect(campusColumns, greaterThanOrEqualTo(AppSpacing.gridMinColumns));
    expect(techColumns, greaterThanOrEqualTo(AppSpacing.gridMinColumns));
  });

  testWidgets('查看更多跳转到圈子展开页', (tester) async {
    await tester.pumpWidget(_buildTestApp());
    await _hubPumpSettled(tester);
    _consumeImageLoadExceptions(tester);

    await tester.tap(find.text('查看更多'));
    await _hubPumpSettled(tester);

    expect(find.text('circles-page'), findsOneWidget);
  });

  testWidgets('推荐圈子列表的查看全部卡片可跳转到圈子展开页', (tester) async {
    await tester.pumpWidget(_buildTestApp());
    await _hubPumpSettled(tester);
    _consumeImageLoadExceptions(tester);

    final pageScrollView = find
        .descendant(
          of: find.byKey(TestKeys.homeCirclesScrollView),
          matching: find.byType(Scrollable),
        )
        .first;
    await tester.scrollUntilVisible(
      find.byKey(TestKeys.homeCirclesRecommendationRail),
      AppSpacing.bottomNavHeight,
      scrollable: pageScrollView,
    );
    final horizontalCircleRail = find.byKey(
      TestKeys.homeCirclesRecommendationRail,
    );
    await tester.dragUntilVisible(
      find.text(DiscoveryText.homeCirclesViewAll),
      horizontalCircleRail,
      const Offset(-240, 0),
      maxIteration: 20,
      duration: const Duration(milliseconds: 8),
    );
    await _hubPumpSettled(tester);
    await tester.tap(find.text(DiscoveryText.homeCirclesViewAll));
    await _hubPumpSettled(tester);

    expect(find.text('circles-page'), findsOneWidget);
  });

  testWidgets('一级 tab 图片作品网格渲染 inline carousel（导航由视频帖覆盖）', (tester) async {
    final queryReader = CircleDiscoveryFeedQueryTestDouble(
      (_) => _hubDiscoveryFeedFixture(),
    );
    await tester.pumpWidget(_buildTestApp(discoveryFeedQuery: queryReader));
    _consumeImageLoadExceptions(tester);

    await _pumpUntilHubCategoryTabsVisible(tester);
    expect(queryReader.receivedQueries, isNotEmpty);
    expect(queryReader.receivedQueries.first.category, 'campus');
    expect(queryReader.receivedQueries.first.subCategory, '母校');
    await tester.tap(find.text('摄影'));
    await _hubPumpSettled(tester);
    await _pumpUntilHubGridKeysVisible(tester);
    expect(queryReader.receivedQueries.last.category, 'photography');
    expect(queryReader.receivedQueries.last.subCategory, '风光');
    final card = find.byKey(
      const ValueKey('home-circle-grid-post-circle_post_image_1'),
    );
    expect(card, findsOneWidget);
    await _scrollHubUntilVisible(tester, card);
    expect(find.byType(AppCachedNetworkImage), findsWidgets);
  });

  testWidgets('一级 tab 视频作品点击进入 unified work browser', (tester) async {
    await tester.pumpWidget(_buildTestApp());
    _consumeImageLoadExceptions(tester);

    await _pumpUntilHubCategoryTabsVisible(tester);
    await tester.tap(find.text('摄影'));
    await _hubPumpSettled(tester);
    final card = find.byKey(
      const ValueKey('home-circle-grid-post-circle_post_video_1'),
    );
    for (var i = 0; i < 40 && card.evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 50));
      _consumeImageLoadExceptions(tester);
    }
    await _hubPumpSettled(tester);
    expect(card, findsOneWidget);
    await _scrollHubUntilVisible(tester, card);
    await tester.tap(card);
    await _hubPumpSettled(tester);

    expect(find.text('work-browser'), findsOneWidget);
  });

  testWidgets('圈子横向卡片在窄屏大字号下保持自适应不溢出', (tester) async {
    tester.view.physicalSize = const Size(320, 690);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final capturedErrors = <FlutterErrorDetails>[];
    final originalOnError = FlutterError.onError;
    FlutterError.onError = (details) {
      capturedErrors.add(details);
    };
    addTearDown(() {
      FlutterError.onError = originalOnError;
    });

    await tester.pumpWidget(_buildTestApp(textScaleFactor: 1.4));
    await _hubPumpSettled(tester);

    final overflowErrors = capturedErrors
        .map((details) => details.exceptionAsString())
        .where((message) => message.contains('A RenderFlex overflowed'))
        .toList(growable: false);

    expect(overflowErrors, isEmpty);
  });
}
