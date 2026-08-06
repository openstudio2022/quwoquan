// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-005

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_video_episode_identity.dart';

void main() {
  test('同一公开交付引用的重复分集不会覆盖 session registry', () {
    final allocator = WorksVideoEpisodeIdentityAllocator('post-1');

    final first = allocator.allocate(
      deliveryCacheIdentity: 'video|https://cdn.example/a.mp4||0',
    );
    final second = allocator.allocate(
      deliveryCacheIdentity: 'video|https://cdn.example/a.mp4||0',
    );

    expect(first, isNot(second));
  });

  test('canonical asset identity 跨重排稳定且不同 Post 隔离', () {
    final original = WorksVideoEpisodeIdentityAllocator('post-1');
    final assetA = original.allocate(
      deliveryCacheIdentity: 'delivery-a',
      mediaAssetId: 'asset-a',
      mediaAssetVersion: 3,
    );
    final assetB = original.allocate(
      deliveryCacheIdentity: 'delivery-b',
      mediaAssetId: 'asset-b',
      mediaAssetVersion: 8,
    );

    final reordered = WorksVideoEpisodeIdentityAllocator('post-1');
    final reorderedB = reordered.allocate(
      deliveryCacheIdentity: 'changed-delivery-b',
      mediaAssetId: 'asset-b',
      mediaAssetVersion: 8,
    );
    final reorderedA = reordered.allocate(
      deliveryCacheIdentity: 'changed-delivery-a',
      mediaAssetId: 'asset-a',
      mediaAssetVersion: 3,
    );
    final otherPost = WorksVideoEpisodeIdentityAllocator('post-2').allocate(
      deliveryCacheIdentity: 'delivery-a',
      mediaAssetId: 'asset-a',
      mediaAssetVersion: 3,
    );

    expect(reorderedA, assetA);
    expect(reorderedB, assetB);
    expect(otherPost, isNot(assetA));
  });

  test('重复 canonical asset 行以 occurrence 唯一化且可重放', () {
    List<String> allocateSeries() {
      final allocator = WorksVideoEpisodeIdentityAllocator('post-1');
      return List<String>.generate(
        3,
        (_) => allocator.allocate(
          deliveryCacheIdentity: 'delivery-a',
          mediaAssetId: 'asset-a',
          mediaAssetVersion: 3,
        ),
      );
    }

    final firstRun = allocateSeries();
    final secondRun = allocateSeries();
    expect(firstRun.toSet(), hasLength(3));
    expect(secondRun, firstRun);
  });

  test('拒绝空 Post 与空 delivery identity', () {
    expect(() => WorksVideoEpisodeIdentityAllocator(' '), throwsArgumentError);
    expect(
      () => WorksVideoEpisodeIdentityAllocator(
        'post-1',
      ).allocate(deliveryCacheIdentity: ' '),
      throwsArgumentError,
    );
  });
}
