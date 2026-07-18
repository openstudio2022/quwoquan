import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Icons;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/shared/viewer/immersive_media_failure_content.dart';
import 'package:quwoquan_app/components/media/video/player/video_playback_failure_overlay.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/media/media_candidate_failure.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/media/media_playback_failure.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

void main() {
  final thumbnail =
      MediaDeliveryResolver(
        MediaEndpointConfig(
          avatarBaseUrl: 'https://alpha-avatar.quwoquan-env.test:17100',
          imageBaseUrl: 'https://alpha-image.quwoquan-env.test:17100',
          videoBaseUrl: 'https://alpha-video.quwoquan-env.test:17100',
          attachmentBaseUrl: 'https://alpha-image.quwoquan-env.test:17100',
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
    final container = ProviderContainer();
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
                thumbnailReference: thumbnail,
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
      find.text(UITextConstants.videoPlaybackTemporaryTitle),
      findsOneWidget,
    );
    expect(find.text('请稍后重试'), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('video-player-retry')),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.retry), findsOneWidget);
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
      find.text(UITextConstants.videoPlaybackUnavailableTitle),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.videoPlaybackUnavailableMessage),
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
      find.text(UITextConstants.videoPlaybackUnsupportedTitle),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.videoPlaybackUnsupportedMessage),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('video-player-retry')),
      findsNothing,
    );
    expect(find.text(UITextConstants.retry), findsNothing);
  });

  testWidgets('重试中以禁用文字状态替代加载图标', (tester) async {
    final failure = MediaPlaybackFailure.fromKind(
      MediaCandidateFailureKind.certificateVerifyFailed,
    );

    await pumpOverlay(tester, failure: failure, retrying: true, onRetry: () {});

    expect(find.text(UITextConstants.mediaRetrying), findsOneWidget);
    expect(find.byType(CupertinoActivityIndicator), findsNothing);
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
