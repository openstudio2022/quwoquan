import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/media/media_download_cache.dart';
import 'package:quwoquan_app/components/media/video/player/video_player_widget.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/media/media_load_failure_cache.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

import '../../../../../support/video/fake_video_player_platform.dart';

final class _NoopMediaDownloadCache extends MediaDownloadCache {
  _NoopMediaDownloadCache() : super();

  @override
  Future<String?> getCachedFilePath(String url) async => null;
}

void main() {
  final delivery =
      MediaDeliveryResolver(
        MediaEndpointConfig(
          avatarBaseUrl: 'https://alpha-avatar.quwoquan-env.test:17100',
          imageBaseUrl: 'https://alpha-image.quwoquan-env.test:17100',
          videoBaseUrl: 'https://alpha-video.quwoquan-env.test:17100',
          attachmentBaseUrl: 'https://alpha-image.quwoquan-env.test:17100',
        ),
      ).resolve(
        'media/video/s/video-primary-0001/post/video-content-0001/source.mp4',
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
    final container = ProviderContainer(
      overrides: [
        mediaDownloadCacheProvider.overrideWithValue(_NoopMediaDownloadCache()),
      ],
    );
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

  testWidgets('异步 native dispose 完成前保持控制器释放在途', (tester) async {
    VideoPlayerWidget.debugResetControllerSlots();
    final previousPlatform = VideoPlayerPlatform.instance;
    final fakePlatform = FakeVideoPlayerPlatform();
    VideoPlayerPlatform.instance = fakePlatform;
    addTearDown(() {
      VideoPlayerPlatform.instance = previousPlatform;
      VideoPlayerWidget.debugResetControllerSlots();
    });
    final container = ProviderContainer(
      overrides: [
        mediaDownloadCacheProvider.overrideWithValue(_NoopMediaDownloadCache()),
      ],
    );
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
    final container = ProviderContainer(
      overrides: [
        mediaDownloadCacheProvider.overrideWithValue(_NoopMediaDownloadCache()),
      ],
    );
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

  test('VideoPlayerWidget API 仅暴露 deliveryReference', () {
    // 编译期契约：构造函数需要 MediaDeliveryReference；运行时抽检字段。
    final widget = VideoPlayerWidget(deliveryReference: delivery);
    expect(widget.deliveryReference.kind, MediaDeliveryKind.video);
    expect(widget.deliveryReference.url, contains('video-primary-0001'));
  });

  test('外层离屏视频不抢占原生解码器槽位', () {
    final source =
        File(
          'lib/ui/discovery/widgets/works_immersive_viewer.dart',
        ).readAsStringSync() +
        File(
          'lib/ui/discovery/widgets/works_immersive_viewer_canvas.dart',
        ).readAsStringSync() +
        File(
          'lib/ui/discovery/widgets/works_immersive_viewer_build.dart',
        ).readAsStringSync() +
        File(
          'lib/ui/discovery/widgets/works_immersive_viewer_lifecycle.dart',
        ).readAsStringSync();

    expect(source, contains('isVisible: index == _currentPage'));
    expect(source, contains('initialize: widget.isVisible && isCurrent'));
    expect(source, contains('viewportEpoch != _videoViewportEpoch'));
  });
}
