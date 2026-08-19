// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-001
// readiness_case: media_asset_viewer_remote_app_uat

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/patrol/patrol_core_readback_support.dart';
import '../../../../../support/runtime/patrol/patrol_environment_harness.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

const _imageWorkId = String.fromEnvironment('DATA_RELEASE_IMAGE_WORK_ID');

void main() {
  patrolTest(
    'release-bound MediaAsset is read back and decoded on the real viewer',
    tags: const <String>['user-acceptance', 'content', 'media-asset'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 15)),
    ($) async {
      expect(_imageWorkId.trim(), isNotEmpty);
      await launchEnvironmentPatrolApp($);
      final container = patrolMountedContainer();
      final detail = await container
          .read(workBrowserContentPostDetailReaderProvider)
          .getPost(postId: _imageWorkId);
      final mediaId = detail.post.mediaAssetId?.trim() ?? '';
      expect(mediaId, isNotEmpty);
      expect(detail.post.imageUrls, isNotEmpty);
      final asset = await container
          .read(workBrowserContentMediaFacetProvider)
          .getMediaAsset(GetContentMediaAssetQuery(mediaId: mediaId));
      expect(asset.assetId, mediaId);
      expect(asset.mediaType, MediaType.image);
      expect(asset.status, MediaAssetStatus.ready);
      expect(asset.cdnUrl.scheme, 'https');

      await patrolGoTo(
        $,
        AppRoutePaths.workBrowser(
          workId: _imageWorkId,
          source: 'mediaAssetViewerRemoteUat',
        ),
      );
      expect(
        await _waitFor($, find.byKey(TestKeys.worksImmersivePager)),
        isTrue,
      );
      final contentImage = find.byWidgetPredicate(
        (widget) =>
            widget is AppCachedNetworkImage &&
            detail.post.imageUrls.contains(widget.imageUrl),
        description: 'release-bound work content image',
      );
      expect(await _waitFor($, contentImage), isTrue);
      expect(
        find.descendant(
          of: contentImage,
          matching: find.byKey(appImageLoadSuccessKey),
        ),
        findsAtLeastNWidgets(1),
        reason:
            'content image itself must decode; avatar success is insufficient',
      );
      expect(
        find.descendant(
          of: contentImage,
          matching: find.byKey(appImageLoadErrorKey),
        ),
        findsNothing,
      );
    },
  );
}

Future<bool> _waitFor(PatrolIntegrationTester $, Finder finder) async {
  final deadline = DateTime.now().add(const Duration(seconds: 45));
  while (DateTime.now().isBefore(deadline)) {
    await $.pump();
    if (finder.evaluate().isNotEmpty) return true;
    await $.pump(const Duration(milliseconds: 250));
  }
  return false;
}
