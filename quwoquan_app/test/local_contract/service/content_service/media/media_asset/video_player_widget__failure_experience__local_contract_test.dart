// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-042
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-012
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-012.t1
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Icons;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_media_failure_content.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_playback_failure_overlay.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/runtime/transport/media/media_candidate_failure.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/media_playback_failure.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_record.dart';
import 'package:quwoquan_app/runtime/observability/runtime_logger.dart';
import 'package:quwoquan_app/runtime/transport/media/media_load_failure_cache.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_player_widget.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';
import '../../../../../support/runtime/platform/media/fake_video_player_platform.dart';

import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_image.dart';

List<Override> _boundaryOverrides() {
  return <Override>[...sealedCloudBoundaryOverrides()];
}

void main() {
  setUp(MediaLoadFailureCache.instance.clear);
  tearDown(MediaLoadFailureCache.instance.clear);
  tearDown(VideoPlayerWidget.debugResetControllerSlots);

  for (final signed in <bool>[false, true]) {
    testWidgets('视频负缓存命中不刷新 TTL、不换签或重复 QoE（signed=$signed）', (tester) async {
      final cache = MediaLoadFailureCache.instance;
      final delivery = MediaDeliveryResolver(
        MediaEndpointConfig(
          avatarBaseUrl: 'https://media.example.test',
          imageBaseUrl: 'https://media.example.test',
          videoBaseUrl: 'https://media.example.test',
          attachmentBaseUrl: 'https://media.example.test',
        ),
      ).resolve(
        'media/video/s/fixture/v1/missing.mp4',
        kind: MediaDeliveryKind.video,
      );
      final identity = delivery.cacheIdentity;
      cache.recordTerminalFailure(
        identity,
        kind: MediaCandidateFailureKind.http404,
        statusCode: 404,
        cooldown: const Duration(seconds: 7),
      );
      final original = cache.activeFailure(identity)!;
      final telemetry = RecordingAppTelemetryRecorder();
      final logger = RuntimeLogger(
        resource: const RuntimeLogResource(
          sourceType: 'app',
          environment: 'alpha',
          service: 'quwoquan_app',
          appVersion: 'test',
        ),
        buffer: InMemoryRuntimeLogBuffer(),
      );
      addTearDown(logger.dispose);
      final fakePlatform = FakeVideoPlayerPlatform();
      final previousPlatform = VideoPlayerPlatform.instance;
      VideoPlayerPlatform.instance = fakePlatform;
      addTearDown(() => VideoPlayerPlatform.instance = previousPlatform);
      var reSignCount = 0;
      final failures = <MediaPlaybackFailure>[];
      Widget player(int instance) => ProviderScope(
        overrides: <Override>[
          ..._boundaryOverrides(),
          appTelemetryReporterProvider.overrideWithValue(telemetry),
          runtimeLoggerProvider.overrideWithValue(logger),
        ],
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, _) => CupertinoApp(
            home: SizedBox(
              width: 390,
              height: 220,
              child: VideoPlayerWidget(
                key: ValueKey<int>(instance),
                deliveryReference: signed ? null : delivery,
                signedDelivery: signed
                    ? SignedVideoDelivery(
                        deliveryUri: Uri.parse(
                          '${delivery.url}?sign=fixture&t=1893456300',
                        ),
                        cacheIdentity: identity,
                        assetId: 'fixture-video',
                        onReSignRequested: () => reSignCount += 1,
                      )
                    : null,
                onPlaybackFailed: failures.add,
              ),
            ),
          ),
        ),
      );
      for (var instance = 0; instance < 3; instance += 1) {
        await tester.pumpWidget(player(instance));
        await tester.pump();
        expect(
          find.byKey(const ValueKey<String>('video-player-error')),
          findsOneWidget,
        );
        expect(cache.activeFailure(identity), same(original));
        expect(
          cache.activeFailure(identity)!.cooldown,
          const Duration(seconds: 7),
        );
      }
      expect(fakePlatform.createdDataSources, isEmpty);
      expect(VideoPlayerWidget.debugActiveControllerCount, 0);
      expect(reSignCount, 0);
      expect(failures, isEmpty);
      expect(
        telemetry.recorded.where(
          (event) => event.eventType == 'video_playback_qoe',
        ),
        isEmpty,
      );
      await tester.pumpWidget(const SizedBox.shrink());
      expect(tester.takeException(), isNull);
    });
  }

  final thumbnail =
      MediaDeliveryResolver(
        MediaEndpointConfig(
          avatarBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
          imageBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
          videoBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
          attachmentBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
        ),
      ).resolve(
        'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
        kind: MediaDeliveryKind.image,
      );

  Future<void> pumpOverlay(
    WidgetTester tester, {
    required MediaPlaybackFailure failure,
    VoidCallback? onRetry,
    bool retrying = false,
  }) {
    final container = ProviderContainer(overrides: _boundaryOverrides());
    addTearDown(container.dispose);
    return tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, _) => CupertinoApp(
            home: SizedBox(
              width: 390,
              height: 220,
              child: VideoPlaybackFailureOverlay(
                failure: failure,
                thumbnailBinding: MediaDeliveryBinding.public(
                  publicUrl: thumbnail.url,
                ),
                onRetry: onRetry,
                retrying: retrying,
              ),
            ),
          ),
        ),
      ),
    );
  }

  testWidgets('短暂失败保留同源封面并提供唯一可访问的重试', (tester) async {
    var retryCount = 0;
    final failure = MediaPlaybackFailure.fromKind(
      MediaCandidateFailureKind.certificateVerifyFailed,
    );

    await pumpOverlay(
      tester,
      failure: failure,
      onRetry: () {
        retryCount += 1;
      },
    );

    expect(
      find.byKey(const ValueKey<String>('video-player-error')),
      findsOneWidget,
    );
    expect(
      find.text(SearchText.recoveryConnectionUnavailableTitle),
      findsOneWidget,
    );
    expect(
      find.text(SearchText.recoveryConnectionUnavailableMessage),
      findsOneWidget,
    );
    expect(find.text('请稍后重试'), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('video-player-retry')),
      findsOneWidget,
    );
    expect(find.text(SearchText.reload), findsOneWidget);
    expect(find.byType(ImmersiveMediaFailureContent), findsOneWidget);
    expect(find.byIcon(Icons.image_not_supported_outlined), findsNothing);
    expect(find.byIcon(CupertinoIcons.refresh), findsNothing);
    expect(find.byType(AppCachedNetworkImage), findsOneWidget);
    expect(
      tester
          .widget<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
          .imageUrl,
      thumbnail.url,
    );

    await tester.tap(find.byKey(const ValueKey<String>('video-player-retry')));
    expect(retryCount, 1);
  });

  testWidgets('404/4xx 不提供无效重试', (tester) async {
    final failure = MediaPlaybackFailure.fromKind(
      MediaCandidateFailureKind.http404,
    );

    await pumpOverlay(tester, failure: failure);

    expect(
      find.text(SearchText.recoveryContentUnavailableTitle),
      findsOneWidget,
    );
    expect(
      find.text(SearchText.recoveryContentUnavailableMessage),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('video-player-retry')),
      findsNothing,
    );
  });

  testWidgets('不支持播放给出替代路径而不展示无效重试', (tester) async {
    final failure = MediaPlaybackFailure.fromKind(
      MediaCandidateFailureKind.decoderInitialization,
    );

    await pumpOverlay(tester, failure: failure);

    expect(
      find.text(SearchText.recoveryContentUnavailableTitle),
      findsOneWidget,
    );
    expect(
      find.text(SearchText.recoveryContentUnavailableMessage),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('video-player-retry')),
      findsNothing,
    );
    expect(find.text(SearchText.reload), findsNothing);
  });

  testWidgets('重试中按钮禁用并只显示按钮内进度', (tester) async {
    final failure = MediaPlaybackFailure.fromKind(
      MediaCandidateFailureKind.certificateVerifyFailed,
    );

    await pumpOverlay(tester, failure: failure, retrying: true, onRetry: () {});

    expect(find.text(SearchText.reload), findsNothing);
    expect(find.byType(CupertinoActivityIndicator), findsOneWidget);
    expect(
      tester
          .widget<CupertinoButton>(
            find.byKey(const ValueKey<String>('video-player-retry')),
          )
          .minimumSize,
      const Size(AppSpacing.minInteractiveSize, AppSpacing.minInteractiveSize),
    );
  });
}
