import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/user/pages/profile_stats_page.dart';

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
  void addCredentials(Uri url, String realm, HttpClientCredentials credentials) {}
  @override
  void addProxyCredentials(String host, int port, String realm, HttpClientCredentials credentials) {}
  @override
  set authenticate(Future<bool> Function(Uri, String, String?)? f) {}
  @override
  set authenticateProxy(Future<bool> Function(String, int, String, String?)? f) {}
  @override
  set badCertificateCallback(bool Function(X509Certificate, String, int)? callback) {}
  @override
  set connectionFactory(Future<ConnectionTask<Socket>> Function(Uri, String?, int?)? f) {}
  @override
  set findProxy(String Function(Uri)? f) {}
  @override
  set keyLog(Function(String)? callback) {}
  @override
  void close({bool force = false}) {}
  @override
  Future<HttpClientRequest> open(String method, String host, int port, String path) => _fakeRequest();
  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> get(String host, int port, String path) => _fakeRequest();
  @override
  Future<HttpClientRequest> getUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> post(String host, int port, String path) => _fakeRequest();
  @override
  Future<HttpClientRequest> postUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> put(String host, int port, String path) => _fakeRequest();
  @override
  Future<HttpClientRequest> putUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> delete(String host, int port, String path) => _fakeRequest();
  @override
  Future<HttpClientRequest> deleteUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> head(String host, int port, String path) => _fakeRequest();
  @override
  Future<HttpClientRequest> headUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> patch(String host, int port, String path) => _fakeRequest();
  @override
  Future<HttpClientRequest> patchUrl(Uri url) => _fakeRequest();
  Future<HttpClientRequest> _fakeRequest() => Future.value(_FakeHttpClientRequest());
}

class _FakeHttpClientRequest extends Fake implements HttpClientRequest {
  @override
  HttpHeaders get headers => _FakeHttpHeaders();
  @override
  Future<HttpClientResponse> close() => Future.value(_FakeHttpClientResponse());
}

class _FakeHttpHeaders extends Fake implements HttpHeaders {}

class _FakeHttpClientResponse extends Fake implements HttpClientResponse {
  static const _kTransparentPng = [
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
    0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
    0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
    0x0A, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x62, 0x00, 0x00, 0x00, 0x02,
    0x00, 0x01, 0xE5, 0x27, 0xDE, 0xFC, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,
    0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
  ];
  @override
  int get statusCode => 200;
  @override
  int get contentLength => _kTransparentPng.length;
  @override
  HttpClientResponseCompressionState get compressionState =>
      HttpClientResponseCompressionState.notCompressed;
  @override
  StreamSubscription<List<int>> listen(void Function(List<int>)? onData,
      {Function? onError, void Function()? onDone, bool? cancelOnError}) {
    return Stream<List<int>>.fromIterable([_kTransparentPng]).listen(
      onData,
      onError: onError,
      onDone: onDone,
      cancelOnError: cancelOnError,
    );
  }
}

void main() {
  setUp(() {
    HttpOverrides.global = _FakeHttpOverrides();
  });

  Widget buildTestApp({
    required String type,
    String userId = 'user_001',
  }) {
    return ProviderScope(
      child: MaterialApp.router(
        routerConfig: GoRouter(
          initialLocation: '/profile/stats?type=$type&userId=$userId',
          routes: [
            GoRoute(
              path: '/profile/stats',
              builder: (_, state) {
                final type = state.uri.queryParameters['type'] ?? 'fans';
                final userId = state.uri.queryParameters['userId'] ?? '';
                return ProfileStatsPage(type: type, userId: userId);
              },
            ),
            GoRoute(
              path: '/circle/:id',
              builder: (_, state) =>
                  Text('Circle ${state.pathParameters['id']}'),
            ),
            GoRoute(
              path: '/user/:username',
              builder: (_, state) =>
                  Text('User ${state.pathParameters['username']}'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> pumpUntilLoaded(WidgetTester tester) async {
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 50));
      if (find.byType(CircularProgressIndicator).evaluate().isEmpty &&
          find.text(UITextConstants.noData).evaluate().isEmpty) {
        if (find.text('极简摄影俱乐部').evaluate().isNotEmpty ||
            find.text('你的皮炎有点辣').evaluate().isNotEmpty) {
          break;
        }
      }
      if (find.text('极简摄影俱乐部').evaluate().isNotEmpty ||
          find.text('你的皮炎有点辣').evaluate().isNotEmpty) {
        break;
      }
    }
  }

  group('ProfileStatsPage — 统计行与列表 (A3)', () {
    testWidgets('type=circles 时渲染圈子列表', (tester) async {
      await tester.pumpWidget(buildTestApp(type: 'circles'));
      await pumpUntilLoaded(tester);

      expect(find.text(UITextConstants.contactsTabCircles), findsOneWidget);
      expect(find.text('极简摄影俱乐部'), findsOneWidget);
      expect(find.text('旅行手账'), findsOneWidget);
      expect(find.text('128 创作'), findsOneWidget);
    });

    testWidgets('type=following 时渲染关注列表', (tester) async {
      await tester.pumpWidget(buildTestApp(type: 'following'));
      await pumpUntilLoaded(tester);

      expect(find.text(UITextConstants.follow), findsAtLeastNWidgets(1));
      expect(find.text('你的皮炎有点辣'), findsOneWidget);
    });

    testWidgets('type=fans 时渲染粉丝列表', (tester) async {
      await tester.pumpWidget(buildTestApp(type: 'fans'));
      await pumpUntilLoaded(tester);

      expect(find.text(UITextConstants.circleFans), findsAtLeastNWidgets(1));
      expect(find.text('你的皮炎有点辣'), findsOneWidget);
    });

    testWidgets('圈子项点击跳转 circle_detail', (tester) async {
      await tester.pumpWidget(buildTestApp(type: 'circles'));
      await pumpUntilLoaded(tester);

      await tester.tap(find.text('极简摄影俱乐部'));
      await tester.pumpAndSettle();

      expect(find.text('Circle c1'), findsOneWidget);
    });

    testWidgets('用户项点击跳转 user_profile', (tester) async {
      await tester.pumpWidget(buildTestApp(type: 'following'));
      await pumpUntilLoaded(tester);

      await tester.tap(find.text('你的皮炎有点辣'));
      await tester.pumpAndSettle();

      expect(find.text('User u1'), findsOneWidget);
    });
  });
}
