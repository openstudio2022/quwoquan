// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-014
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-012
// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-003
import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/media_download_cache.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/event_record/adapters/event_record_batch_writer.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_playback_session.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_player_widget.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/ops_event_record_dependencies.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/adaptive_video_delivery.dart';
import 'package:quwoquan_app/runtime/transport/media/media_candidate_failure.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/runtime/transport/media/media_load_failure_cache.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/media_playback_failure.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart' as ops;
import 'package:video_player/video_player.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/platform/media/fake_video_player_platform.dart';
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';

/// 该 double 覆写了全部网络入口，因此数据面 client 永不应被触达；
/// 内层传输故意直接抛错，把「意外发起真实下载」变成显式测试失败。
CloudHttpClient _unreachableDataPlaneClient() => CloudHttpClient(
  client: MockClient(
    (request) async => throw StateError(
      'MediaDownloadCache double must not perform network IO',
    ),
  ),
);

final class _NoopMediaDownloadCache extends MediaDownloadCache {
  _NoopMediaDownloadCache() : super(client: _unreachableDataPlaneClient());

  final List<String> lookedUpUrls = <String>[];

  @override
  Future<String?> getCachedFilePath(String url) async {
    lookedUpUrls.add(url);
    return null;
  }
}

/// 对象级 typed in-memory double：吃下 runtime 日志/事件出站批次。
///
/// 播放器 Widget 本身不发业务请求，但它经 `runtimeDiagnosticsProvider` ->
/// `runtimeLoggerProvider` -> `opsEventRecordBatchWriterProvider` 依赖这条横切
/// 观测出站面。这是绝大多数 Widget 测试撞上 generated client 的真实路径。
final class _InMemoryOpsEventRecordBatchWriter
    implements OpsEventRecordBatchWriter {
  final List<String> idempotencyKeys = <String>[];

  @override
  Future<ops.EventRecordBatchReceipt> reportEventBatch(
    ops.EventRecordBatchRequest request, {
    required String idempotencyKey,
  }) async {
    idempotencyKeys.add(idempotencyKey);
    return const ops.EventRecordBatchReceipt(
      acceptedCount: 0,
      duplicateBatch: false,
    );
  }

  @override
  Future<ops.EventRecordBatchReceipt> reportRuntimeLogBatch(
    ops.RuntimeLogBatchRequest request, {
    required String idempotencyKey,
  }) async {
    idempotencyKeys.add(idempotencyKey);
    return const ops.EventRecordBatchReceipt(
      acceptedCount: 0,
      duplicateBatch: false,
    );
  }
}

/// 本套件的 App↔Cloud 边界装配：先封边界，再声明真正依赖的对象级 typed port。
List<Override> _boundaryOverrides({
  MediaDownloadCache? mediaDownloadCache,
  List<Override> extra = const <Override>[],
}) {
  return <Override>[
    ...sealedCloudBoundaryOverrides(),
    opsEventRecordBatchWriterProvider.overrideWithValue(
      _InMemoryOpsEventRecordBatchWriter(),
    ),
    mediaDownloadCacheProvider.overrideWithValue(
      mediaDownloadCache ?? _NoopMediaDownloadCache(),
    ),
    ...extra,
  ];
}

final _runtimeAdaptiveFlagProvider =
    NotifierProvider<_RuntimeAdaptiveFlagNotifier, bool>(
      _RuntimeAdaptiveFlagNotifier.new,
    );

final class _RuntimeAdaptiveFlagNotifier extends Notifier<bool> {
  @override
  bool build() => true;

  void setEnabled(bool value) {
    state = value;
  }
}

void main() {
  final delivery =
      MediaDeliveryResolver(
        MediaEndpointConfig(
          avatarBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
          imageBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
          videoBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
          attachmentBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
        ),
      ).resolve(
        'media/video/s/video-primary-0001/post/video-content-0001/v1/source.mp4',
        kind: MediaDeliveryKind.video,
        assetId: 'video-primary-0001',
        version: 1,
      );
  final adaptiveDelivery =
      MediaDeliveryResolver(
        MediaEndpointConfig(
          avatarBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
          imageBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
          videoBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
          attachmentBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
        ),
      ).resolve(
        'media/video/s/asset/video-primary-0001/v1/hls/master.m3u8',
        kind: MediaDeliveryKind.video,
        assetId: 'video-primary-0001',
        version: 1,
      );

  tearDown(VideoPlayerWidget.debugResetControllerSlots);

  setUp(() {
    MediaLoadFailureCache.instance.clearIdentity(delivery.cacheIdentity);
  });

  test('debug 槽位钩子可重置', () {
    VideoPlayerWidget.debugResetControllerSlots();
    expect(VideoPlayerWidget.debugActiveControllerCount, 0);
  });

  testWidgets('dispose 后并发槽位归零', (tester) async {
    VideoPlayerWidget.debugResetControllerSlots();
    final previousPlatform = VideoPlayerPlatform.instance;
    final fakePlatform = FakeVideoPlayerPlatform();
    VideoPlayerPlatform.instance = fakePlatform;
    addTearDown(() {
      VideoPlayerPlatform.instance = previousPlatform;
    });
    final container = ProviderContainer(overrides: _boundaryOverrides());
    addTearDown(() {
      container.dispose();
      VideoPlayerWidget.debugResetControllerSlots();
    });

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, _) => CupertinoApp(
            home: SizedBox(
              width: 390,
              height: 220,
              child: VideoPlayerWidget(
                deliveryReference: delivery,
                initialize: true,
                autoPlay: false,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(VideoPlayerWidget.debugActiveControllerCount, 1);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    await tester.runAsync(() async {
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pump();
    container.dispose();

    expect(
      VideoPlayerWidget.debugActiveControllerCount,
      0,
      reason: 'dispose 后不得泄漏控制器槽',
    );
  });

  testWidgets('有效播放业务回调抛错也必须完成 native dispose 并归还槽位', (tester) async {
    VideoPlayerWidget.debugResetControllerSlots();
    final previousPlatform = VideoPlayerPlatform.instance;
    final fakePlatform = FakeVideoPlayerPlatform();
    VideoPlayerPlatform.instance = fakePlatform;
    addTearDown(() {
      VideoPlayerPlatform.instance = previousPlatform;
      VideoPlayerWidget.debugResetControllerSlots();
    });
    final container = ProviderContainer(overrides: _boundaryOverrides());
    addTearDown(container.dispose);
    var now = DateTime.utc(2026, 8, 10, 2);
    final playbackSession = VideoPlaybackSession(now: () => now);
    var effectivePlaybackCallbacks = 0;

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, _) => CupertinoApp(
            home: SizedBox(
              width: 390,
              height: 220,
              child: VideoPlayerWidget(
                deliveryReference: delivery,
                playbackSession: playbackSession,
                initialize: true,
                autoPlay: true,
                onEffectivePlayback: (_) {
                  effectivePlaybackCallbacks += 1;
                  throw StateError('injected disposed consumer callback');
                },
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(playbackSession.snapshot.isPlaying, isTrue);
    now = now.add(const Duration(seconds: 6));

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    await tester.runAsync(() async {
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pump();

    expect(effectivePlaybackCallbacks, 1);
    expect(fakePlatform.disposeCount, 1);
    expect(VideoPlayerWidget.debugActiveControllerCount, 0);
    playbackSession.dispose();
    expect(tester.takeException(), isNull);
  });

  testWidgets('异步 native dispose 完成前保持控制器释放在途', (tester) async {
    VideoPlayerWidget.debugResetControllerSlots();
    final previousPlatform = VideoPlayerPlatform.instance;
    final fakePlatform = FakeVideoPlayerPlatform();
    VideoPlayerPlatform.instance = fakePlatform;
    addTearDown(() {
      VideoPlayerPlatform.instance = previousPlatform;
      VideoPlayerWidget.debugResetControllerSlots();
    });
    final container = ProviderContainer(overrides: _boundaryOverrides());
    addTearDown(container.dispose);
    var controllerCreated = false;
    var playbackFailed = false;
    final initialize = ValueNotifier<bool>(true);
    addTearDown(initialize.dispose);

    Widget buildPlayer() {
      return UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, _) => ValueListenableBuilder<bool>(
            valueListenable: initialize,
            builder: (_, shouldInitialize, _) => Directionality(
              textDirection: TextDirection.ltr,
              child: SizedBox(
                width: 390,
                height: 220,
                child: VideoPlayerWidget(
                  key: ValueKey<String>('release-$shouldInitialize'),
                  deliveryReference: delivery,
                  initialize: shouldInitialize,
                  autoPlay: false,
                  onControllerCreated: (_) {
                    controllerCreated = true;
                  },
                  onPlaybackFailed: (_) {
                    playbackFailed = true;
                  },
                ),
              ),
            ),
          ),
        ),
      );
    }

    await tester.pumpWidget(buildPlayer());
    await tester.pumpAndSettle();
    expect(
      controllerCreated,
      isTrue,
      reason: '受控 platform 应完成 controller 初始化；failed=$playbackFailed',
    );
    expect(VideoPlayerWidget.debugActiveControllerCount, 1);
    expect(VideoPlayerPlatform.instance, same(fakePlatform));

    final nativeDispose = Completer<void>();
    fakePlatform.disposeCompleter = nativeDispose;
    initialize.value = false;
    await tester.pump();
    await tester.pump();
    await tester.runAsync(() async {
      await Future<void>.delayed(Duration.zero);
    });

    expect(find.byKey(const ValueKey<String>('release-false')), findsOneWidget);
    expect(fakePlatform.disposeCount, 1);
    expect(nativeDispose.isCompleted, isFalse);

    nativeDispose.complete();
    await tester.runAsync(() async {
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pumpAndSettle();
    expect(VideoPlayerWidget.debugActiveControllerCount, 0);
  });

  testWidgets('取消在途初始化不会让旧控制器复活', (tester) async {
    VideoPlayerWidget.debugResetControllerSlots();
    final previousPlatform = VideoPlayerPlatform.instance;
    final fakePlatform = FakeVideoPlayerPlatform()
      ..initializeCompleter = Completer<void>();
    VideoPlayerPlatform.instance = fakePlatform;
    addTearDown(() {
      VideoPlayerPlatform.instance = previousPlatform;
      VideoPlayerWidget.debugResetControllerSlots();
    });
    final container = ProviderContainer(overrides: _boundaryOverrides());
    addTearDown(container.dispose);
    final initialize = ValueNotifier<bool>(true);
    addTearDown(initialize.dispose);
    var controllerCreated = false;

    Widget buildPlayer() {
      return UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, _) => ValueListenableBuilder<bool>(
            valueListenable: initialize,
            builder: (_, shouldInitialize, _) => Directionality(
              textDirection: TextDirection.ltr,
              child: SizedBox(
                width: 390,
                height: 220,
                child: VideoPlayerWidget(
                  key: ValueKey<String>('cancel-$shouldInitialize'),
                  deliveryReference: delivery,
                  initialize: shouldInitialize,
                  autoPlay: false,
                  onControllerCreated: (_) {
                    controllerCreated = true;
                  },
                ),
              ),
            ),
          ),
        ),
      );
    }

    await tester.pumpWidget(buildPlayer());
    await tester.pump();
    await tester.runAsync(() async {
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pump();
    expect(VideoPlayerWidget.debugActiveControllerCount, 1);

    initialize.value = false;
    await tester.pump();
    await tester.pump();
    await tester.runAsync(() async {
      await Future<void>.delayed(Duration.zero);
    });

    fakePlatform.initializeCompleter!.complete();
    await tester.runAsync(() async {
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pumpAndSettle();

    expect(fakePlatform.disposeCount, 1);
    expect(controllerCreated, isFalse);
    expect(
      find.byKey(const ValueKey<String>('video-player-ready')),
      findsNothing,
    );
  });

  testWidgets('视频初始化共用 6 秒预算并按 300ms/3s/6s 进入唯一终态', (tester) async {
    VideoPlayerWidget.debugResetControllerSlots();
    final previousPlatform = VideoPlayerPlatform.instance;
    final fakePlatform = FakeVideoPlayerPlatform()
      ..initializeCompleter = Completer<void>();
    VideoPlayerPlatform.instance = fakePlatform;
    addTearDown(() {
      VideoPlayerPlatform.instance = previousPlatform;
      VideoPlayerWidget.debugResetControllerSlots();
    });
    final container = ProviderContainer(overrides: _boundaryOverrides());
    addTearDown(container.dispose);
    MediaCandidateFailureKind? reportedFailure;

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, _) => CupertinoApp(
            home: SizedBox(
              width: 390,
              height: 220,
              child: VideoPlayerWidget(
                deliveryReference: delivery,
                initialize: true,
                autoPlay: true,
                onPlaybackFailed: (failure) {
                  reportedFailure = failure.kind;
                },
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.runAsync(() async {
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pump();

    expect(find.byType(CupertinoActivityIndicator), findsNothing);
    expect(VideoPlayerWidget.debugActiveControllerCount, 1);

    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byType(CupertinoActivityIndicator), findsOneWidget);
    expect(find.text(FoundationText.requestWaitSlow), findsNothing);

    await tester.pump(const Duration(milliseconds: 2700));
    expect(find.text(FoundationText.requestWaitSlow), findsOneWidget);

    await tester.pump(const Duration(seconds: 3));
    expect(reportedFailure, MediaCandidateFailureKind.initializationTimeout);
    expect(find.text(SearchText.recoveryRequestTimedOutTitle), findsOneWidget);
    expect(
      find.text(SearchText.recoveryRequestTimedOutMessage),
      findsOneWidget,
    );
    expect(find.text(FoundationText.requestWaitSlow), findsNothing);
    expect(find.byType(CupertinoActivityIndicator), findsNothing);
    expect(VideoPlayerWidget.debugActiveControllerCount, 0);

    fakePlatform.initializeCompleter!.complete();
    await tester.runAsync(() async {
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pump();
    expect(find.text(SearchText.recoveryRequestTimedOutTitle), findsOneWidget);
  });

  test('VideoPlayerWidget API 只接收已验证的 typed delivery reference', () {
    // 编译期契约：P0/P1 都必须是 MediaDeliveryReference，不能传裸业务 object key。
    final widget = VideoPlayerWidget(deliveryReference: delivery);
    expect(widget.deliveryReference.kind, MediaDeliveryKind.video);
    expect(widget.deliveryReference.url, contains('video-primary-0001'));
    expect(widget.adaptiveDeliveryReference, isNull);
  });

  testWidgets('渲染器变更会原子替换控制器而不双占槽位', (tester) async {
    VideoPlayerWidget.debugResetControllerSlots();
    final previousPlatform = VideoPlayerPlatform.instance;
    final fakePlatform = FakeVideoPlayerPlatform();
    VideoPlayerPlatform.instance = fakePlatform;
    addTearDown(() {
      VideoPlayerPlatform.instance = previousPlatform;
      VideoPlayerWidget.debugResetControllerSlots();
    });
    final container = ProviderContainer(
      overrides: _boundaryOverrides(
        extra: <Override>[
          platformCapabilitiesProvider.overrideWithValue(
            CapabilityProfile.mobile,
          ),
          contentFeatureFlagProvider(
            hlsCmafAdaptivePlaybackFeatureFlag,
          ).overrideWithValue(false),
        ],
      ),
    );
    addTearDown(container.dispose);
    final controllers = <VideoPlayerController>[];

    Widget player(VideoViewType viewType) => UncontrolledProviderScope(
      container: container,
      child: ScreenUtilInit(
        designSize: const Size(390, 844),
        builder: (_, _) => CupertinoApp(
          home: SizedBox(
            width: 390,
            height: 220,
            child: VideoPlayerWidget(
              deliveryReference: delivery,
              viewType: viewType,
              onControllerCreated: controllers.add,
            ),
          ),
        ),
      ),
    );

    await tester.pumpWidget(player(VideoViewType.platformView));
    await tester.pumpAndSettle();
    expect(controllers, hasLength(1));
    expect(controllers.single.viewType, VideoViewType.platformView);
    expect(VideoPlayerWidget.debugActiveControllerCount, 1);

    await tester.pumpWidget(player(VideoViewType.textureView));
    await tester.pump();
    await tester.runAsync(() async {
      for (var attempt = 0; attempt < 20 && controllers.length < 2; attempt++) {
        await Future<void>.delayed(const Duration(milliseconds: 10));
      }
    });
    await tester.pumpAndSettle();
    expect(controllers, hasLength(2));
    expect(controllers.last.viewType, VideoViewType.textureView);
    expect(fakePlatform.disposeCount, 1);
    expect(VideoPlayerWidget.debugActiveControllerCount, 1);
  });

  testWidgets('feature flag 变化不重建没有 adaptive descriptor 的 MP4', (tester) async {
    VideoPlayerWidget.debugResetControllerSlots();
    final previousPlatform = VideoPlayerPlatform.instance;
    final fakePlatform = FakeVideoPlayerPlatform();
    VideoPlayerPlatform.instance = fakePlatform;
    addTearDown(() {
      VideoPlayerPlatform.instance = previousPlatform;
      VideoPlayerWidget.debugResetControllerSlots();
    });
    final container = ProviderContainer(
      overrides: _boundaryOverrides(
        extra: <Override>[
          platformCapabilitiesProvider.overrideWithValue(
            CapabilityProfile.mobile,
          ),
          contentFeatureFlagProvider(
            hlsCmafAdaptivePlaybackFeatureFlag,
          ).overrideWith((ref) => ref.watch(_runtimeAdaptiveFlagProvider)),
        ],
      ),
    );
    addTearDown(container.dispose);
    final controllers = <VideoPlayerController>[];

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, _) => CupertinoApp(
            home: SizedBox(
              width: 390,
              height: 220,
              child: VideoPlayerWidget(
                deliveryReference: delivery,
                onControllerCreated: controllers.add,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(controllers, hasLength(1));

    container.read(_runtimeAdaptiveFlagProvider.notifier).setEnabled(false);
    await tester.pumpAndSettle();

    expect(fakePlatform.createdDataSources, hasLength(1));
    expect(fakePlatform.disposeCount, 0);
    expect(controllers, hasLength(1));
  });

  testWidgets('HLS 初始化失败按候选序回退同 asset/version MP4', (tester) async {
    VideoPlayerWidget.debugResetControllerSlots();
    final previousPlatform = VideoPlayerPlatform.instance;
    final fakePlatform = FakeVideoPlayerPlatform()
      ..failCreateForUris.add(adaptiveDelivery.url);
    VideoPlayerPlatform.instance = fakePlatform;
    addTearDown(() {
      VideoPlayerPlatform.instance = previousPlatform;
      VideoPlayerWidget.debugResetControllerSlots();
    });
    final cache = _NoopMediaDownloadCache();
    final container = ProviderContainer(
      overrides: _boundaryOverrides(
        mediaDownloadCache: cache,
        extra: <Override>[
          platformCapabilitiesProvider.overrideWithValue(
            CapabilityProfile.mobile,
          ),
          contentFeatureFlagProvider(
            hlsCmafAdaptivePlaybackFeatureFlag,
          ).overrideWithValue(true),
        ],
      ),
    );
    addTearDown(container.dispose);
    int? startedCandidateIndex;

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, _) => CupertinoApp(
            home: SizedBox(
              width: 390,
              height: 220,
              child: VideoPlayerWidget(
                deliveryReference: delivery,
                adaptiveDeliveryReference: adaptiveDelivery,
                adaptiveDescriptorVersion: 1,
                onPlaybackStarted: (_, candidateIndex) {
                  startedCandidateIndex = candidateIndex;
                },
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      fakePlatform.createdDataSources.map((source) => source.uri),
      <String>[adaptiveDelivery.url, delivery.url],
    );
    expect(fakePlatform.createdDataSources.first.formatHint, VideoFormat.hls);
    expect(startedCandidateIndex, 1);
    expect(cache.lookedUpUrls, <String>[
      delivery.url,
    ], reason: 'HLS master 不能进入脱离相对 segment 上下文的单文件缓存');
  });

  testWidgets('HLS 运行时失败只在当前 delivery 内降级 MP4', (tester) async {
    VideoPlayerWidget.debugResetControllerSlots();
    final previousPlatform = VideoPlayerPlatform.instance;
    final fakePlatform = FakeVideoPlayerPlatform();
    VideoPlayerPlatform.instance = fakePlatform;
    addTearDown(() {
      VideoPlayerPlatform.instance = previousPlatform;
      VideoPlayerWidget.debugResetControllerSlots();
    });
    final container = ProviderContainer(
      overrides: _boundaryOverrides(
        extra: <Override>[
          platformCapabilitiesProvider.overrideWithValue(
            CapabilityProfile.mobile,
          ),
          contentFeatureFlagProvider(
            hlsCmafAdaptivePlaybackFeatureFlag,
          ).overrideWithValue(true),
        ],
      ),
    );
    addTearDown(container.dispose);
    final controllers = <VideoPlayerController>[];
    final startedCandidateIndexes = <int>[];
    final playbackSession = VideoPlaybackSession();
    addTearDown(playbackSession.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, _) => CupertinoApp(
            home: SizedBox(
              width: 390,
              height: 220,
              child: VideoPlayerWidget(
                deliveryReference: delivery,
                adaptiveDeliveryReference: adaptiveDelivery,
                adaptiveDescriptorVersion: 1,
                playbackSession: playbackSession,
                onControllerCreated: controllers.add,
                onPlaybackStarted: (_, candidateIndex) {
                  startedCandidateIndexes.add(candidateIndex);
                },
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(controllers, hasLength(1));
    expect(
      fakePlatform.createdDataSources.map((source) => source.uri),
      <String>[adaptiveDelivery.url],
    );

    controllers.single.value = controllers.single.value.copyWith(
      position: const Duration(seconds: 37),
    );
    controllers.single.value = controllers.single.value.copyWith(
      errorDescription: 'injected HLS runtime failure',
    );
    await tester.pump();
    await tester.runAsync(() async {
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pumpAndSettle();

    expect(
      fakePlatform.createdDataSources.map((source) => source.uri),
      <String>[adaptiveDelivery.url, delivery.url],
    );
    expect(startedCandidateIndexes, <int>[0, 1]);
    expect(controllers, hasLength(2));
    expect(fakePlatform.seekTargets, <Duration>[
      const Duration(seconds: 37),
    ], reason: '同资产 HLS → MP4 降级必须从原播放位置续接，不能从 0 秒重播');
    expect(
      playbackSession.snapshot.lastSourceSwitchSeekResult?.outcome,
      VideoSourceSwitchSeekOutcome.positionReadbackSettled,
      reason: '切源 seek 必须在新 controller attach 后进入 typed session 结果',
    );
    expect(
      find.byKey(const ValueKey<String>('video-player-ready')),
      findsOneWidget,
    );
  });

  testWidgets('HLS 降级后的 source-switch seek 永不返回也会退出初始化链', (tester) async {
    VideoPlayerWidget.debugResetControllerSlots();
    final previousPlatform = VideoPlayerPlatform.instance;
    final fakePlatform = FakeVideoPlayerPlatform();
    VideoPlayerPlatform.instance = fakePlatform;
    addTearDown(() {
      VideoPlayerPlatform.instance = previousPlatform;
      VideoPlayerWidget.debugResetControllerSlots();
    });
    final container = ProviderContainer(
      overrides: _boundaryOverrides(
        extra: <Override>[
          platformCapabilitiesProvider.overrideWithValue(
            CapabilityProfile.mobile,
          ),
          contentFeatureFlagProvider(
            hlsCmafAdaptivePlaybackFeatureFlag,
          ).overrideWithValue(true),
        ],
      ),
    );
    addTearDown(container.dispose);
    final controllers = <VideoPlayerController>[];
    final startedCandidateIndexes = <int>[];
    final playbackSession = VideoPlaybackSession();
    addTearDown(playbackSession.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, _) => CupertinoApp(
            home: SizedBox(
              width: 390,
              height: 220,
              child: VideoPlayerWidget(
                deliveryReference: delivery,
                adaptiveDeliveryReference: adaptiveDelivery,
                adaptiveDescriptorVersion: 1,
                playbackSession: playbackSession,
                onControllerCreated: controllers.add,
                onPlaybackStarted: (_, candidateIndex) {
                  startedCandidateIndexes.add(candidateIndex);
                },
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(controllers, hasLength(1));

    controllers.single.value = controllers.single.value.copyWith(
      position: const Duration(seconds: 37),
    );
    fakePlatform.seekCompleter = Completer<void>();
    controllers.single.value = controllers.single.value.copyWith(
      errorDescription: 'injected HLS runtime failure with stalled seek',
    );
    await tester.pump();
    await tester.runAsync(() async {
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();

    expect(controllers, hasLength(2));
    expect(startedCandidateIndexes, <int>[0, 1]);
    expect(
      playbackSession.snapshot.lastSourceSwitchSeekResult?.outcome,
      VideoSourceSwitchSeekOutcome.commandTimedOut,
    );
    expect(
      playbackSession.takeQoeSummary().seekEvidenceSource,
      'source_switch_command_failed',
    );
    expect(
      find.byKey(const ValueKey<String>('video-player-ready')),
      findsOneWidget,
      reason: '初始化等待虽已结束，source-switch 自身 deadline 仍必须让链路退出',
    );
  });

  testWidgets('flag 切换与 HLS error 并发时按 controller 冻结快照降级', (tester) async {
    VideoPlayerWidget.debugResetControllerSlots();
    final previousPlatform = VideoPlayerPlatform.instance;
    final fakePlatform = FakeVideoPlayerPlatform();
    VideoPlayerPlatform.instance = fakePlatform;
    addTearDown(() {
      VideoPlayerPlatform.instance = previousPlatform;
      VideoPlayerWidget.debugResetControllerSlots();
    });
    final container = ProviderContainer(
      overrides: _boundaryOverrides(
        extra: <Override>[
          platformCapabilitiesProvider.overrideWithValue(
            CapabilityProfile.mobile,
          ),
          contentFeatureFlagProvider(
            hlsCmafAdaptivePlaybackFeatureFlag,
          ).overrideWith((ref) => ref.watch(_runtimeAdaptiveFlagProvider)),
        ],
      ),
    );
    addTearDown(container.dispose);
    final controllers = <VideoPlayerController>[];
    final failures = <MediaPlaybackFailure>[];

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, _) => CupertinoApp(
            home: SizedBox(
              width: 390,
              height: 220,
              child: VideoPlayerWidget(
                deliveryReference: delivery,
                adaptiveDeliveryReference: adaptiveDelivery,
                adaptiveDescriptorVersion: 1,
                onControllerCreated: controllers.add,
                onPlaybackFailed: failures.add,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(controllers, hasLength(1));

    container.read(_runtimeAdaptiveFlagProvider.notifier).setEnabled(false);
    controllers.single.value = controllers.single.value.copyWith(
      errorDescription: 'injected HLS runtime failure during flag switch',
    );
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 20));
    });

    expect(failures, isEmpty, reason: '旧 HLS controller 不得用已变更的 flag 重算候选数');
    await tester.pumpAndSettle();
    expect(
      fakePlatform.createdDataSources.map((source) => source.uri),
      <String>[adaptiveDelivery.url, delivery.url],
      reason: '并发降级完成后，已是目标 MP4 的 controller 不应再被重建',
    );
    expect(controllers, hasLength(2));
    expect(failures, isEmpty);
  });

  testWidgets('HLS 位置超过较短 MP4 时降级到可播放尾部而非 0 秒', (tester) async {
    VideoPlayerWidget.debugResetControllerSlots();
    final previousPlatform = VideoPlayerPlatform.instance;
    final fakePlatform = FakeVideoPlayerPlatform(
      duration: const Duration(seconds: 20),
    );
    VideoPlayerPlatform.instance = fakePlatform;
    addTearDown(() {
      VideoPlayerPlatform.instance = previousPlatform;
      VideoPlayerWidget.debugResetControllerSlots();
    });
    final container = ProviderContainer(
      overrides: _boundaryOverrides(
        extra: <Override>[
          platformCapabilitiesProvider.overrideWithValue(
            CapabilityProfile.mobile,
          ),
          contentFeatureFlagProvider(
            hlsCmafAdaptivePlaybackFeatureFlag,
          ).overrideWithValue(true),
        ],
      ),
    );
    addTearDown(container.dispose);
    final controllers = <VideoPlayerController>[];
    final playbackSession = VideoPlaybackSession();
    addTearDown(playbackSession.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, _) => CupertinoApp(
            home: SizedBox(
              width: 390,
              height: 220,
              child: VideoPlayerWidget(
                deliveryReference: delivery,
                adaptiveDeliveryReference: adaptiveDelivery,
                adaptiveDescriptorVersion: 1,
                playbackSession: playbackSession,
                onControllerCreated: controllers.add,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(controllers, hasLength(1));

    controllers.single.value = controllers.single.value.copyWith(
      duration: const Duration(seconds: 60),
      position: const Duration(seconds: 37),
    );
    controllers.single.value = controllers.single.value.copyWith(
      errorDescription: 'injected HLS runtime failure',
    );
    await tester.pump();
    await tester.runAsync(() async {
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pumpAndSettle();

    expect(
      fakePlatform.createdDataSources.map((source) => source.uri),
      <String>[adaptiveDelivery.url, delivery.url],
    );
    expect(controllers, hasLength(2));
    expect(
      fakePlatform.seekTargets,
      <Duration>[const Duration(milliseconds: 19500)],
      reason: '超出 fallback 时长时应留出尾部安全量，不得 seek 到 duration 或从 0 秒重播',
    );
    expect(
      playbackSession.snapshot.lastSourceSwitchSeekResult?.target,
      const Duration(milliseconds: 19500),
    );
  });

  test('外层离屏视频不抢占槽位且视频书只预热唯一 N+1', () {
    final source =
        File(
          'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer.dart',
        ).readAsStringSync() +
        File(
          'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_canvas.dart',
        ).readAsStringSync() +
        File(
          'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_build.dart',
        ).readAsStringSync() +
        File(
          'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_lifecycle.dart',
        ).readAsStringSync();

    expect(source, contains('isVisible: index == _currentPage'));
    expect(source, contains('final shouldPreheat ='));
    expect(source, contains('index == _currentEpisodeIndex + 1'));
    expect(source, contains('initialize: shouldInitialize'));
    expect(source, contains('didHaveMemoryPressure()'));
    expect(source, contains('viewportEpoch != _videoViewportEpoch'));
  });
}
