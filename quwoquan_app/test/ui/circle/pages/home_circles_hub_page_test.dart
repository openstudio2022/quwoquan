import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/ui/circle/pages/circles_hub_page.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
    HttpOverrides.global = _FakeHttpOverrides();
  });

  testWidgets('频道管理按钮右缘保持统一安全边距', (tester) async {
    await tester.pumpWidget(_buildTestApp());
    await tester.pumpAndSettle();
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

  testWidgets('查看更多跳转到圈子展开页', (tester) async {
    await tester.pumpWidget(_buildTestApp());
    await tester.pumpAndSettle();
    _consumeImageLoadExceptions(tester);

    await tester.tap(find.text('查看更多'));
    await tester.pumpAndSettle();

    expect(find.text('circles-page'), findsOneWidget);
  });

  testWidgets('推荐圈子列表的查看全部卡片可跳转到圈子展开页', (tester) async {
    await tester.pumpWidget(_buildTestApp());
    await tester.pumpAndSettle();
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
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text(UITextConstants.homeCirclesViewAll));
    await tester.pumpAndSettle();

    expect(find.text('circles-page'), findsOneWidget);
  });

  testWidgets('一级 tab 图片作品点击进入 unified media viewer', (tester) async {
    await tester.pumpWidget(_buildTestApp());
    await tester.pumpAndSettle();
    _consumeImageLoadExceptions(tester);

    final gridPost = find.byKey(
      const ValueKey('home-circle-grid-post-circle_post_image_1'),
    );
    await tester.dragUntilVisible(
      gridPost,
      find.byType(Scrollable).last,
      const Offset(0, -300),
    );
    await tester.ensureVisible(gridPost);
    await tester.pumpAndSettle();
    await tester.tap(gridPost);
    await tester.pumpAndSettle();

    expect(find.text('media-viewer'), findsOneWidget);
  });

  testWidgets('一级 tab 视频作品点击进入 unified video viewer', (tester) async {
    await tester.pumpWidget(_buildTestApp());
    await tester.pumpAndSettle();
    _consumeImageLoadExceptions(tester);

    final gridPost = find.byKey(
      const ValueKey('home-circle-grid-post-circle_post_video_1'),
    );
    await tester.dragUntilVisible(
      gridPost,
      find.byType(Scrollable).last,
      const Offset(0, -300),
    );
    await tester.ensureVisible(gridPost);
    await tester.pumpAndSettle();
    await tester.tap(gridPost);
    await tester.pumpAndSettle();

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
    await tester.pumpAndSettle();

    final overflowErrors = capturedErrors
        .map((details) => details.exceptionAsString())
        .where((message) => message.contains('A RenderFlex overflowed'))
        .toList(growable: false);

    expect(overflowErrors, isEmpty);
  });
}
