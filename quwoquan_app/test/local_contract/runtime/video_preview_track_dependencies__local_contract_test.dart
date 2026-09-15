import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show ProviderException;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/di/video_preview_track_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/video_preview_track_query.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_timeline_preview.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../support/runtime/cloud_boundary_test_scope.dart';
import '../../support/runtime/config/runtime_package_test_hydration.dart';

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007.t1
// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/video-display-journey/spec.md#gwt-004
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  tearDown(() => hydrateRuntimePackageForTests(environment: 'beta'));

  test('Alpha 真实 Provider 不要求端点，预览请求返回 typed unavailable', () async {
    await hydrateRuntimePackageForTests(environment: 'alpha');
    final container = ProviderContainer(
      overrides: sealedCloudBoundaryOverrides(),
    );
    addTearDown(container.dispose);
    expect(container.read(mediaEndpointConfigProvider), isNull);
    final query = container.read(videoPreviewTrackQueryProvider);
    await expectLater(
      query.loadManifest(await _bundledDescriptor()),
      throwsA(
        isA<CloudException>()
            .having(
              (error) => error.code,
              'code',
              RuntimeFailureCodes.clientPlatformCapabilityUnavailable,
            )
            .having(
              (error) => error.runtimeFailure.kind,
              'kind',
              RuntimeFailureKind.unsupported,
            )
            .having((error) => error.statusCode, 'statusCode', isNull),
      ),
    );
  });

  testWidgets('离线真实预览查询只隐藏增强层，不抛出 Widget 异常', (tester) async {
    await hydrateRuntimePackageForTests(environment: 'alpha');
    final descriptor = await tester.runAsync(_bundledDescriptor);
    await tester.pumpWidget(
      ProviderScope(
        overrides: sealedCloudBoundaryOverrides(),
        child: MaterialApp(
          home: Consumer(
            builder: (context, ref, _) => VideoTimelinePreview(
              descriptor: descriptor!,
              query: ref.watch(videoPreviewTrackQueryProvider),
              target: const Duration(seconds: 5),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.byType(Image), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  test('Remote 缺少 package-bound 端点仍严格拒绝，不选择离线 adapter', () async {
    await hydrateRuntimePackageForTests(environment: 'beta');
    final container = ProviderContainer(
      overrides: [
        ...sealedCloudBoundaryOverrides(),
        mediaEndpointConfigProvider.overrideWithValue(null),
      ],
    );
    addTearDown(container.dispose);
    expect(
      () => container.read(videoPreviewTrackQueryProvider),
      throwsA(
        isA<ProviderException>().having(
          (error) => error.exception,
          'exception',
          isA<StateError>().having(
            (error) => error.message,
            'message',
            '视频预览轨缺少 package-bound media endpoint config',
          ),
        ),
      ),
    );
  });

  test('Remote 有配置时仍选择网络依赖，不能回退离线', () async {
    await hydrateRuntimePackageForTests(environment: 'beta');
    final container = ProviderContainer(
      overrides: sealedCloudBoundaryOverrides(),
    );
    addTearDown(container.dispose);
    expect(container.read(mediaEndpointConfigProvider), isNotNull);
    expect(
      () => container.read(videoPreviewTrackQueryProvider),
      throwsA(
        isSealedCloudBoundaryFailure(
          providerLabel: 'unauthenticatedCloudHttpClientProvider',
        ),
      ),
    );
  });
}

Future<VideoPreviewTrackDescriptor> _bundledDescriptor() async {
  final bundle = await OfflineContentBundle.load();
  final video = bundle
      .rows('media')
      .firstWhere((row) => row['kind'] == 'video');
  // 当前快照没有预览轨：用真实视频身份请求该能力，不制造远端 manifest URL。
  return VideoPreviewTrackDescriptor(
    assetId: video['assetId']! as String,
    assetVersion: video['version']! as int,
    trackVersion: 1,
    manifestReference: MediaDeliveryReference.bundled(
      video['canonicalReference']! as String,
      kind: MediaDeliveryKind.video,
      bundleDigest: bundle.digest,
    ),
  );
}
