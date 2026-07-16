import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/core/di/app_data_source_mode.dart';
import 'package:quwoquan_app/ui/circle/pages/circles_hub_page.dart';
import 'package:quwoquan_app/ui/circle/widgets/home_circles_category_tab.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

class _HubTestMockDataSourceModeNotifier extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.mock;
}

class _FailingHubCircleRepository extends MockCircleRepository {
  @override
  Future<List<PostBaseDto>> listHomeCircleDiscoveryFeed({
    int limit = kHomeCircleDiscoveryFeedDefaultLimit,
  }) async {
    throw StateError('hub unavailable');
  }
}

/// 契约 seed 的 groupFeedPostIds 与摄影 tab 的 category 过滤不对齐；
/// 网格导航测试需要稳定的 circle_post_image_1 / circle_post_video_1 样本。
class _PriorHubCircleFeedRepository extends MockCircleRepository {
  @override
  Future<List<PostBaseDto>> listHomeCircleDiscoveryFeed({
    int limit = kHomeCircleDiscoveryFeedDefaultLimit,
  }) async {
    return CircleMockData.catalogCircleFeedPostDtos
        .take(limit)
        .toList(growable: false);
  }
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
    ],
  );
  return ProviderScope(
    overrides: [
      appDataSourceModeProvider.overrideWith(
        _HubTestMockDataSourceModeNotifier.new,
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
  });

  test('Provider 覆盖下 Mock 圈子发现流非空', () async {
    final container = ProviderContainer(
      overrides: [
        appDataSourceModeProvider.overrideWith(
          _HubTestMockDataSourceModeNotifier.new,
        ),
      ],
    );
    addTearDown(container.dispose);
    final repo = container.read(circleRepositoryProvider);
    expect(repo, isA<MockCircleRepository>());
    final feed = await repo.listHomeCircleDiscoveryFeed(limit: 20);
    expect(feed, isNotEmpty);
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
    for (final removed in <String>['推荐', '遇见', '人文', '生活', '运动', '美食', '车友']) {
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

  testWidgets('圈子 hub bootstrap 失败时展示统一页态', (tester) async {
    await tester.pumpWidget(
      _buildTestApp(
        overrides: [
          circleRepositoryProvider.overrideWithValue(
            _FailingHubCircleRepository(),
          ),
        ],
      ),
    );
    await _hubPumpSettled(tester);

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(find.text(UITextConstants.tryAgain), findsOneWidget);
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

    final horizontalCircleRail = find
        .byWidgetPredicate(
          (widget) =>
              widget is ListView && widget.scrollDirection == Axis.horizontal,
        )
        .last;
    await tester.dragUntilVisible(
      find.text(UITextConstants.homeCirclesViewAll),
      horizontalCircleRail,
      const Offset(-240, 0),
      maxIteration: 20,
      duration: const Duration(milliseconds: 8),
    );
    await _hubPumpSettled(tester);
    await tester.tap(find.text(UITextConstants.homeCirclesViewAll));
    await _hubPumpSettled(tester);

    expect(find.text('circles-page'), findsOneWidget);
  });

  testWidgets('一级 tab 图片作品网格渲染 inline carousel（导航由视频帖覆盖）', (tester) async {
    await tester.pumpWidget(
      _buildTestApp(
        overrides: [
          circleRepositoryProvider.overrideWithValue(
            _PriorHubCircleFeedRepository(),
          ),
        ],
      ),
    );
    _consumeImageLoadExceptions(tester);

    await _pumpUntilHubCategoryTabsVisible(tester);
    await tester.tap(find.text('摄影'));
    await _hubPumpSettled(tester);
    await _pumpUntilHubGridKeysVisible(tester);
    final card = find.byKey(
      const ValueKey('home-circle-grid-post-circle_post_image_1'),
    );
    expect(card, findsOneWidget);
    await _scrollHubUntilVisible(tester, card);
    expect(find.byType(AppCachedNetworkImage), findsWidgets);
  });

  testWidgets('一级 tab 视频作品点击进入 unified work browser', (tester) async {
    await tester.pumpWidget(
      _buildTestApp(
        overrides: [
          circleRepositoryProvider.overrideWithValue(
            _PriorHubCircleFeedRepository(),
          ),
        ],
      ),
    );
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
