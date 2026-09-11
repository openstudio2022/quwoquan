// spec_ref: specs/feature-tree/runtime/runtime-media/spec.md#sit-003
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_content_block_renderer.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/media/signed_media_lease_test_support.dart';

void main() {
  testWidgets('文章私有图只凭校验 lease 交付且保留静默占位', (tester) async {
    final lease = testSignedMediaLease(
      deliveryUri: Uri.parse('https://signed.example/asset.jpg?sign=abc&t=1'),
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: sealedCloudBoundaryOverrides(),
        child: MaterialApp(
          home: ArticleAdaptiveImage(
            imageUrl: 'private-original-reference',
            lease: lease,
          ),
        ),
      ),
    );
    await tester.pump();
    final image = tester.widget<AppCachedNetworkImage>(
      find.byType(AppCachedNetworkImage),
    );
    expect(image.lease, same(lease));
    expect(image.imageUrl, lease.deliveryUri.toString());
    expect(image.cacheKey, lease.cacheIdentity);
    expect(find.byKey(articleImageSilentPlaceholderKey), findsOneWidget);
    expect(find.byKey(articleImageDelayedIndicatorKey), findsNothing);
  });
  testWidgets('引用在场但无有效交付不能伪装内容缺席', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: sealedCloudBoundaryOverrides(),
        child: const MaterialApp(
          home: ArticleAdaptiveImage(imageUrl: 'invalid-reference'),
        ),
      ),
    );
    await tester.pump();
    expect(find.byKey(articleImageSourceAbsentKey), findsNothing);
    expect(find.byType(AppCachedNetworkImage), findsOneWidget);
  });
}
