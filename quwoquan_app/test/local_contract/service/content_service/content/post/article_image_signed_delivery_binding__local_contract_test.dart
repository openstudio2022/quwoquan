import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_content_block_renderer.dart';

/// 文章图接私有交付的验收锚点（DEC-033 / GWT-016）。
///
/// 换签只解决「取到哪个地址」，不该顺带换掉消费面的加载体验：文章图有自己的
/// 静默占位阈值、延迟指示与失败重试入口，私有路必须仍走这一套，否则同一篇文章
/// 里公开图与私有图会呈现两种观感。同时短签 query 随 TTL 轮换，不得进缓存键，
/// 否则每次换签都变成一次冷加载。
void main() {
  testWidgets('私有短签地址单候选直传，不经公开候选推导', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(
          home: ArticleAdaptiveImage(
            imageUrl: 'media-object-key-not-a-url',
            signedDeliveryUrl: 'https://signed.example/asset.jpg?sig=abc',
            signedCacheIdentity: 'asset-stable-identity',
          ),
        ),
      ),
    );
    await tester.pump();

    // 媒体端点未注入时公开路会落缺席态；私有路不依赖端点推导，因此不得缺席。
    expect(find.byKey(articleImageSourceAbsentKey), findsNothing);

    final network = tester.widget<AppCachedNetworkImage>(
      find.byType(AppCachedNetworkImage),
    );
    expect(network.imageUrl, 'https://signed.example/asset.jpg?sig=abc');
    expect(network.imageUrlCandidates, <String>[
      'https://signed.example/asset.jpg?sig=abc',
    ]);
    expect(network.cacheKey, 'asset-stable-identity');
    expect(network.cdnPreset, CdnImagePreset.none);
  });

  testWidgets('私有路仍走文章自有加载体验：初始为静默占位而非通用占位', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(
          home: ArticleAdaptiveImage(
            imageUrl: 'media-object-key',
            signedDeliveryUrl: 'https://signed.example/asset.jpg?sig=abc',
            signedCacheIdentity: 'asset-stable-identity',
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.byKey(articleImageSilentPlaceholderKey), findsOneWidget);
    expect(find.byKey(articleImageDelayedIndicatorKey), findsNothing);
    expect(find.byKey(articleImageFailedSurfaceKey), findsNothing);
  });

  testWidgets('短签地址缺席时回落公开候选推导，不是把私有当成缺席', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(
          home: ArticleAdaptiveImage(imageUrl: 'media-object-key'),
        ),
      ),
    );
    await tester.pump();

    // 端点缺席 + 无短签：落工程缺陷缺席态，与「加载失败」互不混同。
    expect(find.byKey(articleImageSourceAbsentKey), findsOneWidget);
    expect(find.byType(AppCachedNetworkImage), findsNothing);
  });
}
