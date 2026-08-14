// 推荐频道主链路（channelId=recommend, sort=recommend）的端云 roundtrip：
// 排序窗口驱动的首刷 envelope、稳定续页与 feed→behavior 归因闭环。
// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md#sit-001
// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md#req-002
// readiness_case: post_get_feed_recommend_channel_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';

void main() {
  late ContentApiContractHarness harness;
  var harnessCreated = false;

  setUpAll(() async {
    harness = await ContentApiContractHarness.create();
    harnessCreated = true;
  });
  tearDownAll(() async {
    if (harnessCreated) {
      await harness.close();
    }
  });

  final sessionId =
      'recommend-roundtrip-${DateTime.now().microsecondsSinceEpoch}';

  test('推荐频道首刷返回排序窗口 envelope 与 typed objectCards', () async {
    final page = await harness.feed.listDiscoveryFeedPage(
      category: 'recommended',
      channelId: 'recommend',
      sessionId: sessionId,
      limit: 20,
    );

    expect(page.items, isNotEmpty);
    expect(page.feedRequestId, allOf(isNotNull, isNotEmpty));
    expect(page.policyDigest, matches(RegExp(r'^sha256:[0-9a-f]{64}$')));
    expect(page.outcome, ContentFeedOutcome.content);
    expect(page.emptyReason, isNull);
    // objectCards 是 typed 列表（可为空）；出现时必须可路由。
    for (final card in page.objectCards) {
      expect(card.objectKind, isNotEmpty);
      expect(card.objectId, isNotEmpty);
    }
  });

  test('推荐频道续页保持 feedRequestId 归因且跨页无重复 postId', () async {
    final first = await harness.feed.listDiscoveryFeedPage(
      category: 'recommended',
      channelId: 'recommend',
      sessionId: sessionId,
      limit: 20,
    );
    expect(first.nextCursor, allOf(isNotNull, isNotEmpty));

    final second = await harness.feed.listDiscoveryFeedPage(
      category: 'recommended',
      channelId: 'recommend',
      sessionId: sessionId,
      cursor: first.nextCursor,
      feedRequestId: first.feedRequestId,
      limit: 20,
    );

    expect(second.feedRequestId, first.feedRequestId);
    expect(
      first.items
          .map((item) => item.id)
          .toSet()
          .intersection(second.items.map((item) => item.id).toSet()),
      isEmpty,
    );
    // 已交付页回翻锚点必须随续页下发（FeedDeliveryPage 语义）。
    expect(second.previousCursor, allOf(isNotNull, isNotEmpty));
  });

  test('feed 下发归因经 behavior 上报闭环（feedRequestId/channelId/policyDigest）',
      () async {
    final page = await harness.feed.listDiscoveryFeedPage(
      category: 'recommended',
      channelId: 'recommend',
      sessionId: sessionId,
      limit: 20,
    );
    expect(page.items, isNotEmpty);
    final target = page.items.first;

    await harness.behaviors.reportBehaviors(
      ReportContentBehaviorsCommand(
        events: <ContentBehaviorEventWire>[
          ContentBehaviorEventWire(
            clientEventId:
                'recommend-roundtrip-impression-${DateTime.now().microsecondsSinceEpoch}',
            occurredAt: DateTime.now().toUtc(),
            contentId: target.id,
            action: BehaviorEventType.impression,
            state: 'impressed',
            feedRequestId: page.feedRequestId,
            channelId: 'recommend',
            policyDigest: page.policyDigest,
            position: 0,
          ),
        ],
      ),
    );
  });
}
