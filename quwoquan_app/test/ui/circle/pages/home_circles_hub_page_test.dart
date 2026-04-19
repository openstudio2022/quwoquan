import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/ui/circle/constants/circle_channel_manage_layout.dart';
import 'package:quwoquan_app/ui/circle/pages/circles_hub_page.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 单用例原则：settle 上界 1s，避免默认 10 分钟超时拖死整批测试。
const Duration _kHubPumpSettleTimeout = Duration(seconds: 1);

Future<void> _hubPumpSettled(WidgetTester tester) async {
  await tester.pumpAndSettle(
    const Duration(milliseconds: 100),
    EnginePhase.sendSemanticsUpdate,
    _kHubPumpSettleTimeout,
  );
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

Widget _buildTestApp({double textScaleFactor = 1.0}) {
  final router = GoRouter(
    routes: [
      GoRoute(
        path: '/',
        builder: (context, state) => const Scaffold(body: CirclesHubPage()),
      ),
      GoRoute(
        path: '/media-viewer/:category/:index',
        builder: (context, state) =>
            const Scaffold(body: Center(child: Text('media-viewer'))),
      ),
      GoRoute(
        path: '/video-viewer/:index',
        builder: (context, state) =>
            const Scaffold(body: Center(child: Text('video-viewer'))),
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
  while (tester.takeException() != null) {
    // swallow network image loading errors in widget tests
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
  for (var i = 0; i < 12 && probe.evaluate().isEmpty; i++) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  await _hubPumpSettled(tester);
}

Future<void> _pumpUntilHubCategoryTabsVisible(WidgetTester tester) async {
  final probe = find.text('生活');
  await _hubPumpSettled(tester);
  for (var i = 0; i < 12 && probe.evaluate().isEmpty; i++) {
    await tester.pump(const Duration(milliseconds: 16));
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

  testWidgets('频道管理按钮右缘保持统一安全边距', (tester) async {
    await tester.pumpWidget(_buildTestApp());
    await _hubPumpSettled(tester);
    _consumeImageLoadExceptions(tester);

    final page = find.byType(CirclesHubPage);
    final channelIcon = find.byIcon(CupertinoIcons.line_horizontal_3_decrease);
    final screenWidth = tester.getSize(page).width;
    final iconRightInset = screenWidth - tester.getTopRight(channelIcon).dx;
    final expectedInset = AppSpacing.topBarTrailingVisualInset(
      tester.element(page),
    );

    expect(channelIcon, findsOneWidget);
    expect(iconRightInset, closeTo(expectedInset, 2.0));
  });

  testWidgets('频道管理面板在窄屏下仅占上半屏且空白处可关闭', (tester) async {
    tester.view.physicalSize = const Size(320, 690);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    SharedPreferences.setMockInitialValues(const <String, Object>{
      'home_circles.selected_channels.v1': <String>['life'],
    });

    await tester.pumpWidget(_buildTestApp());
    await _hubPumpSettled(tester);
    _consumeImageLoadExceptions(tester);
    await _pumpUntilHubCategoryTabsVisible(tester);

    await tester.tap(find.byIcon(CupertinoIcons.line_horizontal_3_decrease));
    await _hubPumpSettled(tester);

    final panel = find.byKey(const ValueKey('home-circles-channel-panel'));
    expect(panel, findsOneWidget);

    final panelRect = tester.getRect(panel);
    final pageSize = tester.getSize(find.byType(CirclesHubPage));
    expect(panelRect.top, closeTo(0.0, 1.0));
    expect(
      panelRect.height,
      lessThanOrEqualTo(
        pageSize.height *
                CircleChannelManageLayout.panelMaxHeightRatio(
                  tester.element(panel),
                ) +
            1.0,
      ),
    );

    expect(
      find.descendant(
        of: panel,
        matching: find.text(UITextConstants.circleTapToAdd),
      ),
      findsOneWidget,
    );

    await tester.tapAt(Offset(pageSize.width * 0.5, pageSize.height * 0.82));
    await _hubPumpSettled(tester);

    expect(
      find.byKey(const ValueKey('home-circles-channel-panel')),
      findsNothing,
    );
  });

  testWidgets('iPad 频道管理面板全宽展开且完成按钮右对齐', (tester) async {
    tester.view.physicalSize = const Size(1024, 768);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    SharedPreferences.setMockInitialValues(const <String, Object>{
      'home_circles.selected_channels.v1': <String>['life'],
    });

    await tester.pumpWidget(_buildTestApp());
    await _hubPumpSettled(tester);
    _consumeImageLoadExceptions(tester);
    await _pumpUntilHubCategoryTabsVisible(tester);

    await tester.tap(find.byIcon(CupertinoIcons.line_horizontal_3_decrease));
    await _hubPumpSettled(tester);

    final panel = find.byKey(const ValueKey('home-circles-channel-panel'));
    expect(panel, findsOneWidget);

    final panelRect = tester.getRect(panel);
    final pageSize = tester.getSize(find.byType(CirclesHubPage));
    expect(panelRect.left, closeTo(0.0, 1.0));
    expect(panelRect.width, closeTo(pageSize.width, 1.0));

    final doneButton = find.byKey(const ValueKey('home-circles-channel-done'));
    final horizontalPadding = AppSpacing.feedContentHorizontal(
      tester.element(panel),
    );
    final doneRightInset = pageSize.width - tester.getTopRight(doneButton).dx;
    expect(doneRightInset, closeTo(horizontalPadding, 4.0));
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

  testWidgets('一级 tab 图片作品点击进入 unified media viewer', (tester) async {
    await tester.pumpWidget(_buildTestApp());
    _consumeImageLoadExceptions(tester);

    await _pumpUntilHubGridKeysVisible(tester);
    final card = find.byKey(
      const ValueKey('home-circle-grid-post-circle_post_image_1'),
    );
    expect(card, findsOneWidget);
    await _scrollHubUntilVisible(tester, card);
    await tester.tap(card);
    await _hubPumpSettled(tester);

    expect(find.text('media-viewer'), findsOneWidget);
  });

  testWidgets('一级 tab 视频作品点击进入 unified video viewer', (tester) async {
    await tester.pumpWidget(_buildTestApp());
    _consumeImageLoadExceptions(tester);

    await _pumpUntilHubGridKeysVisible(tester);
    final card = find.byKey(
      const ValueKey('home-circle-grid-post-circle_post_video_1'),
    );
    expect(card, findsOneWidget);
    await _scrollHubUntilVisible(tester, card);
    await tester.tap(card);
    await _hubPumpSettled(tester);

    expect(find.text('video-viewer'), findsOneWidget);
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
