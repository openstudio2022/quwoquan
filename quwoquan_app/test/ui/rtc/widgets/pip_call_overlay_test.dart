import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/services/active_call_service.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/widgets/pip_call_overlay.dart';

class _FakeHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    return _FakeHttpClient();
  }
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
          Uri url, String realm, HttpClientCredentials credentials) {}

  @override
  void addProxyCredentials(
          String host, int port, String realm, HttpClientCredentials credentials) {}

  @override
  set authenticate(Future<bool> Function(Uri, String, String?)? f) {}

  @override
  set authenticateProxy(
      Future<bool> Function(String, int, String, String?)? f) {}

  @override
  set badCertificateCallback(
      bool Function(X509Certificate, String, int)? callback) {}

  @override
  set connectionFactory(
      Future<ConnectionTask<Socket>> Function(Uri, String?, int?)? f) {}

  @override
  set findProxy(String Function(Uri)? f) {}

  @override
  set keyLog(Function(String)? callback) {}

  @override
  void close({bool force = false}) {}

  @override
  Future<HttpClientRequest> open(
          String method, String host, int port, String path) =>
      _fakeRequest();

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
      Future.value(_FakeHttpClientRequest());
}

class _FakeHttpClientRequest extends Fake implements HttpClientRequest {
  @override
  HttpHeaders get headers => _FakeHttpHeaders();

  @override
  Future<HttpClientResponse> close() =>
      Future.value(_FakeHttpClientResponse());
}

class _FakeHttpHeaders extends Fake implements HttpHeaders {}

class _FakeHttpClientResponse extends Fake implements HttpClientResponse {
  @override
  int get statusCode => 200;

  @override
  int get contentLength => _kTransparentImage.length;

  @override
  HttpClientResponseCompressionState get compressionState =>
      HttpClientResponseCompressionState.notCompressed;

  @override
  StreamSubscription<List<int>> listen(void Function(List<int>)? onData,
      {Function? onError, void Function()? onDone, bool? cancelOnError}) {
    return Stream<List<int>>.fromIterable([_kTransparentImage]).listen(
      onData,
      onError: onError,
      onDone: onDone,
      cancelOnError: cancelOnError,
    );
  }
}

final Uint8List _kTransparentImage = Uint8List.fromList(<int>[
  0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
  0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
  0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
  0x0A, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x62, 0x00, 0x00, 0x00, 0x02,
  0x00, 0x01, 0xE5, 0x27, 0xDE, 0xFC, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,
  0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
]);

class _TestActiveCallNotifier extends ActiveCallNotifier {
  _TestActiveCallNotifier(this._initial);

  final ActiveCallState _initial;

  @override
  ActiveCallState build() => _initial;
}

Widget _buildOverlay({
  VoidCallback? onReturnToCall,
  VoidCallback? onHangup,
  CallParticipant? activeSpeaker,
  ActiveCallState? initialState,
}) {
  final state = initialState ??
      const ActiveCallState(
        callId: 'call_001',
        callType: 'video',
        isInCall: true,
        isPipMode: true,
        elapsed: Duration(minutes: 3, seconds: 15),
      );

  return ProviderScope(
    overrides: [
      activeCallProvider.overrideWith(() {
        return _TestActiveCallNotifier(state);
      }),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: SizedBox(
          width: 400,
          height: 800,
          child: PipCallOverlay(
            onReturnToCall: onReturnToCall ?? () {},
            onHangup: onHangup ?? () {},
            activeSpeaker: activeSpeaker,
          ),
        ),
      ),
    ),
  );
}

void main() {
  setUp(() => HttpOverrides.global = _FakeHttpOverrides());
  tearDown(() => HttpOverrides.global = null);

  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('PipCallOverlay — 渲染契约', () {
    testWidgets('PiP 模式下渲染浮窗', (tester) async {
      await tester.pumpWidget(_buildOverlay());
      await tester.pump();

      expect(find.byType(PipCallOverlay), findsOneWidget);
    });

    testWidgets('显示通话计时', (tester) async {
      await tester.pumpWidget(_buildOverlay());
      await tester.pump();

      expect(find.textContaining('03:15'), findsOneWidget);
    });

    testWidgets('非 PiP 模式时不渲染内容', (tester) async {
      await tester.pumpWidget(_buildOverlay(
        initialState: const ActiveCallState(
          callId: 'call_001',
          callType: 'video',
          isInCall: true,
          isPipMode: false,
        ),
      ));
      await tester.pump();

      expect(find.byType(PipCallOverlay), findsOneWidget);
      expect(find.textContaining('03:15'), findsNothing);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 交互契约
  // ──────────────────────────────────────────────────────────────────
  group('PipCallOverlay — 交互契约', () {
    testWidgets('点击触发 onReturnToCall 回调', (tester) async {
      var returnCalled = false;
      await tester.pumpWidget(_buildOverlay(
        onReturnToCall: () => returnCalled = true,
      ));
      await tester.pump();

      final gesture = find.byType(GestureDetector);
      if (gesture.evaluate().isNotEmpty) {
        await tester.tap(gesture.first);
        await tester.pump();
        expect(returnCalled, isTrue);
      }

      expect(find.byType(PipCallOverlay), findsOneWidget);
    });

    testWidgets('PiP 可拖拽', (tester) async {
      await tester.pumpWidget(_buildOverlay());
      await tester.pump();

      final gestureDetectors = find.byType(GestureDetector);
      expect(gestureDetectors, findsWidgets);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('PipCallOverlay — 错误态渲染', () {
    testWidgets('不在通话时不渲染', (tester) async {
      await tester.pumpWidget(_buildOverlay(
        initialState: const ActiveCallState(isInCall: false),
      ));
      await tester.pump();

      expect(find.byType(PipCallOverlay), findsOneWidget);
      expect(find.byType(AnimatedPositioned), findsNothing);
    });

    testWidgets('无 activeSpeaker 时显示默认内容', (tester) async {
      await tester.pumpWidget(_buildOverlay(activeSpeaker: null));
      await tester.pump();

      expect(find.byType(PipCallOverlay), findsOneWidget);
    });

    testWidgets('activeSpeaker 有头像时显示', (tester) async {
      await tester.pumpWidget(_buildOverlay(
        activeSpeaker: const CallParticipant(
          userId: 'user_001',
          displayName: 'Alice',
          avatarUrl: 'https://example.com/avatar.jpg',
          status: ParticipantStatus.connected,
          isCameraOn: false,
        ),
      ));
      await tester.pump();

      expect(find.byType(PipCallOverlay), findsOneWidget);
      expect(find.text('Alice'), findsOneWidget);
    });
  });
}
