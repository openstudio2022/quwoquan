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

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_image.dart';

List<Override> _boundaryOverrides() {
  return <Override>[...sealedCloudBoundaryOverrides()];
}

void main() {
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
                thumbnailBinding: MediaDeliveryBinding(
                  assetId: '',
                  accessMode: null,
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
