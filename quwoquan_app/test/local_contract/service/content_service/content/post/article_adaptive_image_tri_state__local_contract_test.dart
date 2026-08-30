// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-016
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-016.t2
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-016.t3
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-016.t4
//
// 文章内嵌图片三态语义（REQ-017）：
// 「缺席（引用无法解析出交付 URL）」「加载中」「失败」必须渲染
// 互不混同的语义标识；缺席是工程缺陷，必须经 ExceptionTelemetryPort
// 留证据而不是塌陷成无差别灰框。
import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
// ignore: depend_on_referenced_packages
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/app_observability_ports.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/runtime/transport/media/media_load_failure_cache.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/spacing/immersive_media_wait_motion.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_content_block_renderer.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';

final MediaEndpointConfig _testMediaEndpointConfig = MediaEndpointConfig(
  avatarBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/avatar',
  imageBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/image',
  videoBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/video',
  attachmentBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/image',
);

final class _RecordingExceptionTelemetryPort implements ExceptionTelemetryPort {
  final List<String> handledSources = <String>[];
  final List<String> handledErrorTexts = <String>[];
  final List<String> handledOperationIds = <String>[];

  @override
  Future<void> recordGlobalException({
    required String source,
    required String exceptionText,
    required String stackText,
    String pageId = '',
    String pageName = '',
    String surfaceId = '',
    String routeId = '',
    String operationId = '',
    RuntimeFailureBase? runtimeFailure,
    String exceptionType = '',
  }) async {}

  @override
  Future<void> recordHandledException({
    required String source,
    required Object error,
    required StackTrace stackTrace,
    String pageId = '',
    String pageName = '',
    String surfaceId = '',
    String routeId = '',
    String operationId = '',
  }) async {
    handledSources.add(source);
    handledErrorTexts.add(error.toString());
    handledOperationIds.add(operationId);
  }

  @override
  Future<void> flushPending() async {}
}

class _PendingHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) => _PendingHttpClient();
}

class _PendingHttpClient extends Fake implements HttpClient {
  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) async =>
      _PendingHttpClientRequest();

  @override
  void close({bool force = false}) {}
}

class _PendingHttpClientRequest extends Fake implements HttpClientRequest {
  @override
  bool followRedirects = true;

  @override
  int maxRedirects = 5;

  @override
  int contentLength = -1;

  @override
  bool persistentConnection = true;

  @override
  HttpHeaders get headers => _PendingHttpHeaders();

  @override
  Future<HttpClientResponse> close() => Completer<HttpClientResponse>().future;

  @override
  void abort([Object? exception, StackTrace? stackTrace]) {}
}

class _PendingHttpHeaders extends Fake implements HttpHeaders {
  @override
  void set(String name, Object value, {bool preserveHeaderCase = false}) {}
}

class _FakePathProviderPlatform extends PathProviderPlatform {
  _FakePathProviderPlatform(this.root);

  final Directory root;

  String _path(String name) {
    final directory = Directory('${root.path}/$name')
      ..createSync(recursive: true);
    return directory.path;
  }

  @override
  Future<String?> getTemporaryPath() async => _path('tmp');

  @override
  Future<String?> getApplicationSupportPath() async => _path('support');

  @override
  Future<String?> getApplicationDocumentsPath() async => _path('documents');

  @override
  Future<String?> getApplicationCachePath() async => _path('cache');
}

Widget _wrap(
  Widget child, {
  required _RecordingExceptionTelemetryPort telemetry,
  MediaEndpointConfig? endpointConfig,
  List<Override> overrides = const <Override>[],
}) {
  return ProviderScope(
    overrides: <Override>[
      mediaEndpointConfigProvider.overrideWithValue(endpointConfig),
      exceptionTelemetryPortProvider.overrideWithValue(telemetry),
      ...overrides,
    ],
    child: CupertinoApp(
      home: CupertinoPageScaffold(
        child: Center(child: SizedBox(width: 320, height: 240, child: child)),
      ),
    ),
  );
}

const Size _articleImageFrameSize = Size(320, 240);
const String _articleImageObjectKey =
    'media/image/s/archived-image/post/p1/v1/cover.webp';

AppCachedNetworkImage _networkImage(WidgetTester tester) =>
    tester.widget<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage));

void _reportNetworkSuccess(WidgetTester tester) {
  final callback = _networkImage(tester).onLoadSucceeded;
  expect(callback, isNotNull);
  callback!();
}

void _reportNetworkFailure(WidgetTester tester) {
  final callback = _networkImage(tester).onLoadFailed;
  expect(callback, isNotNull);
  callback!(StateError('controlled article image load failure'));
}

String _articleImageIdentity([String objectKey = _articleImageObjectKey]) =>
    _testMediaEndpointConfig
        .baseFor(MediaDeliveryKind.image)
        .replace(path: '/$objectKey')
        .toString();

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory cacheTestRoot;
  late PathProviderPlatform previousPathProvider;

  setUpAll(() {
    ensureSqfliteFfiInitialized();
    previousPathProvider = PathProviderPlatform.instance;
    HttpOverrides.global = _PendingHttpOverrides();
    cacheTestRoot = Directory.systemTemp.createTempSync(
      'qwq-article-image-tri-state-test-',
    );
    PathProviderPlatform.instance = _FakePathProviderPlatform(cacheTestRoot);
  });

  tearDownAll(() {
    HttpOverrides.global = null;
    PathProviderPlatform.instance = previousPathProvider;
    try {
      if (cacheTestRoot.existsSync()) {
        cacheTestRoot.deleteSync(recursive: true);
      }
    } on FileSystemException catch (error) {
      if (error.osError?.errorCode != 2) {
        rethrow;
      }
    }
  });

  setUp(() {
    MediaLoadFailureCache.instance.clear();
  });

  group('ArticleAdaptiveImage 三态语义（GWT-016）', () {
    testWidgets('缺席：空引用渲染独立缺席标识并经异常遥测留证据', (tester) async {
      final telemetry = _RecordingExceptionTelemetryPort();
      await tester.pumpWidget(
        _wrap(
          const ArticleAdaptiveImage(imageUrl: ''),
          telemetry: telemetry,
          endpointConfig: _testMediaEndpointConfig,
        ),
      );
      await tester.pump();

      expect(find.byKey(articleImageSourceAbsentKey), findsOneWidget);
      // 用户视觉与失败一致（可见的失败文案），但语义标识独立。
      expect(find.text(ContentText.imageLoadFailed), findsOneWidget);
      expect(find.byKey(appImageLoadErrorKey), findsNothing);
      expect(find.byKey(appImageLoadPlaceholderKey), findsNothing);
      expect(telemetry.handledSources, hasLength(1));
      expect(
        telemetry.handledSources.single,
        contains('article_adaptive_image'),
      );
      expect(
        telemetry.handledOperationIds.single,
        'app.content.article_image_resolve',
      );
    });

    testWidgets('缺席：asset:// 残留引用同样归缺席态且遥测携带资产引用', (tester) async {
      final telemetry = _RecordingExceptionTelemetryPort();
      await tester.pumpWidget(
        _wrap(
          const ArticleAdaptiveImage(imageUrl: 'asset://asset-42'),
          telemetry: telemetry,
          endpointConfig: _testMediaEndpointConfig,
        ),
      );
      await tester.pump();

      expect(find.byKey(articleImageSourceAbsentKey), findsOneWidget);
      expect(find.byKey(appImageLoadErrorKey), findsNothing);
      expect(telemetry.handledSources, hasLength(1));
      expect(telemetry.handledErrorTexts.single, contains('asset-42'));
    });

    testWidgets('缺席：媒体端点未注入时 media key 引用归缺席态而非伪装本地加载', (tester) async {
      final telemetry = _RecordingExceptionTelemetryPort();
      await tester.pumpWidget(
        _wrap(
          const ArticleAdaptiveImage(
            imageUrl: 'media/image/s/archived-image/post/p1/v1/cover.webp',
          ),
          telemetry: telemetry,
          endpointConfig: null,
        ),
      );
      await tester.pump();

      expect(find.byKey(articleImageSourceAbsentKey), findsOneWidget);
      expect(find.byKey(appImageLoadErrorKey), findsNothing);
      expect(telemetry.handledSources, hasLength(1));
    });

    testWidgets('缺席态 rebuild 不重复上报遥测', (tester) async {
      final telemetry = _RecordingExceptionTelemetryPort();
      await tester.pumpWidget(
        _wrap(
          const ArticleAdaptiveImage(imageUrl: ''),
          telemetry: telemetry,
          endpointConfig: _testMediaEndpointConfig,
        ),
      );
      await tester.pump();
      await tester.pump();
      await tester.pump();

      expect(telemetry.handledSources, hasLength(1));
    });

    testWidgets('加载中：可解析引用渲染占位标识，与缺席/失败互不混同', (tester) async {
      final telemetry = _RecordingExceptionTelemetryPort();
      await tester.pumpWidget(
        _wrap(
          const ArticleAdaptiveImage(
            imageUrl: 'media/image/s/archived-image/post/p1/v1/cover.webp',
          ),
          telemetry: telemetry,
          endpointConfig: _testMediaEndpointConfig,
        ),
      );
      await tester.pump();

      expect(find.byKey(appImageLoadPlaceholderKey), findsOneWidget);
      expect(find.byKey(articleImageSourceAbsentKey), findsNothing);
      expect(find.byKey(appImageLoadErrorKey), findsNothing);
      expect(telemetry.handledSources, isEmpty);
    });

    testWidgets('失败：负缓存激活时渲染可见失败态而非无差别灰块，且不产生缺席遥测', (tester) async {
      final telemetry = _RecordingExceptionTelemetryPort();
      final identity = _articleImageIdentity();
      MediaLoadFailureCache.instance.recordFailure(
        identity,
        error: const HttpExceptionWithStatus(404, 'not found', uri: null),
        candidateUrl: identity,
      );

      await tester.pumpWidget(
        _wrap(
          const ArticleAdaptiveImage(imageUrl: _articleImageObjectKey),
          telemetry: telemetry,
          endpointConfig: _testMediaEndpointConfig,
        ),
      );
      await tester.pump();

      expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
      expect(find.text(ContentText.imageLoadFailed), findsOneWidget);
      expect(find.byKey(articleImageSourceAbsentKey), findsNothing);
      expect(telemetry.handledSources, isEmpty);
    });

    testWidgets('阈值内成功：全程零等待指示、快速淡入且图片框几何恒定', (tester) async {
      final telemetry = _RecordingExceptionTelemetryPort();
      await tester.pumpWidget(
        _wrap(
          const ArticleAdaptiveImage(imageUrl: _articleImageObjectKey),
          telemetry: telemetry,
          endpointConfig: _testMediaEndpointConfig,
        ),
      );
      await tester.pump();

      expect(find.byKey(articleImageSilentPlaceholderKey), findsOneWidget);
      expect(find.byKey(articleImageDelayedIndicatorKey), findsNothing);
      expect(
        tester.getSize(find.byKey(articleImagePresentedContentKey)),
        _articleImageFrameSize,
      );

      await tester.pump(const Duration(milliseconds: 450));
      expect(find.byKey(articleImageDelayedIndicatorKey), findsNothing);
      _reportNetworkSuccess(tester);
      await tester.pump();

      expect(find.byKey(articleImageDelayedIndicatorKey), findsNothing);
      expect(
        tester
            .widget<AnimatedOpacity>(
              find.byKey(articleImagePresentedContentKey),
            )
            .duration,
        ImmersiveMediaWaitMotion.quickReveal,
      );
      expect(
        tester.getSize(find.byKey(articleImagePresentedContentKey)),
        _articleImageFrameSize,
      );
    });

    testWidgets('运行时失败：重试加载经公开回调进入失败态且图片框几何恒定', (tester) async {
      final runtimeFailureObjectKey =
          'media/image/s/archived-image/post/p1/v1/'
          'runtime-failure-${DateTime.now().microsecondsSinceEpoch}.webp';
      final identity = _articleImageIdentity(runtimeFailureObjectKey);
      MediaLoadFailureCache.instance.recordFailure(
        identity,
        error: const HttpExceptionWithStatus(404, 'not found', uri: null),
        candidateUrl: identity,
      );
      final telemetry = _RecordingExceptionTelemetryPort();
      await tester.pumpWidget(
        _wrap(
          ArticleAdaptiveImage(imageUrl: runtimeFailureObjectKey),
          telemetry: telemetry,
          endpointConfig: _testMediaEndpointConfig,
        ),
      );
      await tester.pump();

      final frameBeforeFailure = tester.getSize(
        find.byKey(articleImagePresentedContentKey),
      );
      expect(find.byKey(articleImageFailedSurfaceKey), findsOneWidget);
      await tester.tap(find.byKey(articleImageRetryKey));
      await tester.pump();
      expect(find.byKey(articleImageDelayedIndicatorKey), findsOneWidget);
      expect(
        MediaLoadFailureCache.instance.shouldSkipNetwork(identity),
        isFalse,
      );

      _reportNetworkFailure(tester);
      await tester.pump(const Duration(milliseconds: 16));

      expect(find.byKey(articleImageDelayedIndicatorKey), findsOneWidget);
      expect(find.byKey(articleImageFailedSurfaceKey), findsNothing);
      await tester.pump(ImmersiveMediaWaitMotion.indicatorMinDisplay);
      await tester.pump(const Duration(milliseconds: 16));
      expect(find.byKey(articleImageFailedSurfaceKey), findsOneWidget);
      expect(find.byKey(articleImageRetryKey), findsOneWidget);
      expect(
        tester.getSize(find.byKey(articleImagePresentedContentKey)),
        frameBeforeFailure,
        reason: 'loading → failure 只替换框内状态，不得改变文章图片占位几何。',
      );
      expect(telemetry.handledSources, isEmpty);
    });

    testWidgets('慢成功：指示出现后保持最短窗口再交叉淡出，Reduce Motion 仅压缩转场', (tester) async {
      final telemetry = _RecordingExceptionTelemetryPort();
      await tester.pumpWidget(
        _wrap(
          const MediaQuery(
            data: MediaQueryData(disableAnimations: true),
            child: ArticleAdaptiveImage(imageUrl: _articleImageObjectKey),
          ),
          telemetry: telemetry,
          endpointConfig: _testMediaEndpointConfig,
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 510));

      expect(find.byKey(articleImageDelayedIndicatorKey), findsOneWidget);
      expect(
        tester.getSize(find.byKey(articleImageDelayedIndicatorKey)),
        _articleImageFrameSize,
      );
      _reportNetworkSuccess(tester);
      await tester.pump(const Duration(milliseconds: 16));
      expect(
        find.byKey(articleImageDelayedIndicatorKey),
        findsOneWidget,
        reason: '指示刚出现后即成功仍须保持满最短展示窗口。',
      );

      await tester.pump(ImmersiveMediaWaitMotion.indicatorMinDisplay);
      await tester.pump(const Duration(milliseconds: 16));
      expect(
        tester
            .widget<AnimatedOpacity>(
              find.byKey(articleImagePresentedContentKey),
            )
            .duration,
        ImmersiveMediaWaitMotion.reducedMotionTransition,
      );
      expect(
        tester.getSize(find.byKey(articleImagePresentedContentKey)),
        _articleImageFrameSize,
      );
    });

    testWidgets('slow failure preserves the indicator minimum display window', (
      tester,
    ) async {
      final telemetry = _RecordingExceptionTelemetryPort();
      await tester.pumpWidget(
        _wrap(
          const ArticleAdaptiveImage(imageUrl: _articleImageObjectKey),
          telemetry: telemetry,
          endpointConfig: _testMediaEndpointConfig,
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 510));

      final frameBeforeFailure = tester.getSize(
        find.byKey(articleImagePresentedContentKey),
      );
      expect(find.byKey(articleImageDelayedIndicatorKey), findsOneWidget);
      _reportNetworkFailure(tester);
      await tester.pump(const Duration(milliseconds: 16));

      expect(find.byKey(articleImageDelayedIndicatorKey), findsOneWidget);
      expect(find.byKey(articleImageFailedSurfaceKey), findsNothing);
      expect(
        tester.getSize(find.byKey(articleImagePresentedContentKey)),
        frameBeforeFailure,
      );

      await tester.pump(ImmersiveMediaWaitMotion.indicatorMinDisplay);
      await tester.pump(const Duration(milliseconds: 16));
      expect(find.byKey(articleImageFailedSurfaceKey), findsOneWidget);
      expect(
        tester.getSize(find.byKey(articleImagePresentedContentKey)),
        frameBeforeFailure,
      );
    });

    testWidgets('失败重试：同框呈现恢复入口，清负缓存并以新 generation 立即显示指示', (tester) async {
      const retryObjectKey =
          'media/image/s/archived-image/post/p1/v1/retry.webp';
      final identity = _articleImageIdentity(retryObjectKey);
      MediaLoadFailureCache.instance.recordFailure(
        identity,
        error: const HttpExceptionWithStatus(404, 'not found', uri: null),
        candidateUrl: identity,
      );
      final telemetry = _RecordingExceptionTelemetryPort();
      await tester.pumpWidget(
        _wrap(
          const ArticleAdaptiveImage(imageUrl: retryObjectKey),
          telemetry: telemetry,
          endpointConfig: _testMediaEndpointConfig,
        ),
      );
      await tester.pump();

      expect(find.byKey(articleImageFailedSurfaceKey), findsOneWidget);
      expect(find.byKey(articleImageRetryKey), findsOneWidget);
      expect(
        tester.getSize(find.byKey(articleImageFailedSurfaceKey)),
        _articleImageFrameSize,
      );
      final failedGeneration = _networkImage(tester).key;

      await tester.tap(find.byKey(articleImageRetryKey));
      await tester.pump();

      expect(
        MediaLoadFailureCache.instance.shouldSkipNetwork(identity),
        isFalse,
      );
      expect(find.byKey(articleImageDelayedIndicatorKey), findsOneWidget);
      expect(find.byKey(articleImageRetryKey), findsNothing);
      expect(_networkImage(tester).key, isNot(failedGeneration));
      expect(
        tester.getSize(find.byKey(articleImageDelayedIndicatorKey)),
        _articleImageFrameSize,
      );
    });
  });
}

/// flutter_cache_manager 的 HttpExceptionWithStatus 形状：负缓存分类只看
/// statusCode 字段，这里用本地最小实现避免依赖其内部导出路径。
class HttpExceptionWithStatus implements Exception {
  const HttpExceptionWithStatus(this.statusCode, this.message, {this.uri});

  final int statusCode;
  final String message;
  final Uri? uri;

  @override
  String toString() => 'HttpExceptionWithStatus($statusCode, $message)';
}
