/// Feed 弱网/断连降级与恢复的可靠性契约（typed fault 注入 → 错误态 → 恢复重试成功）。
///
/// 故障 profile 消费测试树共享闭集（disconnect / latency），与环境边缘
/// harness 契约同源；断言遵循「无伪成功、错误映射唯一恢复组、恢复后
/// 同装配重试成功」。
///
/// spec_ref: specs/feature-tree/runtime/runtime-testinfra/fault-injection-harness/spec.md#gwt-001
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart'
    show kFeedSortRecommend;
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;

import '../../../../../support/runtime/fault/typed_fault_injection.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_test_builder.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

/// 组合共享 TypedFaultInjector 的 feed query double：故障态由测试切换。
class _FaultInjectingFeedQuery extends InMemoryContentDiscoveryFeedQuery {
  _FaultInjectingFeedQuery(this.injector)
    : super(
        InMemoryContentPostStore(
          posts: <ContentPostViewData>[
            contentPostViewDataBuilder(
              postId: 'fault-recovery-photo',
              contentType: 'image',
              mediaUrls: const <String>[testContentImageUrl],
            ),
          ],
        ),
      );

  final TypedFaultInjector injector;

  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    return injector.guard(
      () => super.listDiscoveryFeedPage(
        category: category,
        channelId: channelId,
        identity: identity,
        type: type,
        subCategory: subCategory,
        limit: limit,
        cursor: cursor,
        sort: sort,
        sessionId: sessionId,
        feedRequestId: feedRequestId,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      ),
    );
  }
}

Widget _scopedApp(_FaultInjectingFeedQuery feedQuery) {
  return ProviderScope(
    overrides: [
      ...mockContentFacetOverrides(
        store: InMemoryContentPostStore(),
        feedQuery: feedQuery,
      ),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => const MaterialApp(home: SizedBox.shrink()),
    ),
  );
}

void main() {
  testWidgets('断连故障下 feed 进入唯一恢复组错误态且无伪成功', (tester) async {
    final injector = TypedFaultInjector();
    final query = _FaultInjectingFeedQuery(injector);
    await tester.pumpWidget(_scopedApp(query));
    final container = ProviderScope.containerOf(
      tester.element(find.byType(MaterialApp)),
    );

    injector.activate(TypedFaultProfile.disconnect);
    await container.read(discoveryFeedMapProvider.notifier).load('photo');
    await tester.pump();

    final faultedFeed = container.read(discoveryFeedMapProvider)['photo']?.value;
    expect(faultedFeed, isNotNull);
    expect(
      faultedFeed!.error,
      SearchText.recoveryConnectionUnavailableMessage,
      reason: '断连故障必须映射到网络到达性恢复组，而不是裸异常或静默空态',
    );
    expect(faultedFeed.items, isEmpty, reason: '故障期间不得出现伪成功数据');
  });

  testWidgets('故障恢复后同装配重试成功且数据完整', (tester) async {
    final injector = TypedFaultInjector();
    final query = _FaultInjectingFeedQuery(injector);
    await tester.pumpWidget(_scopedApp(query));
    final container = ProviderScope.containerOf(
      tester.element(find.byType(MaterialApp)),
    );

    injector.activate(TypedFaultProfile.disconnect);
    await container.read(discoveryFeedMapProvider.notifier).load('photo');
    await tester.pump();
    expect(
      container.read(discoveryFeedMapProvider)['photo']?.value?.items,
      isEmpty,
    );

    injector.deactivate();
    await container.read(discoveryFeedMapProvider.notifier).load('photo');
    await tester.pump();

    final recoveredFeed = container
        .read(discoveryFeedMapProvider)['photo']
        ?.value;
    expect(recoveredFeed, isNotNull);
    expect(recoveredFeed!.error, isNull, reason: '恢复后错误态必须清除');
    expect(
      recoveredFeed.items,
      isNotEmpty,
      reason: '同一装配在故障恢复后重试必须取回真实数据',
    );
    expect(recoveredFeed.items.first.type, 'image');
  });

  testWidgets('弱网延迟 profile 下加载变慢但最终成功且无重复副作用', (tester) async {
    final injector = TypedFaultInjector();
    final query = _FaultInjectingFeedQuery(injector);
    await tester.pumpWidget(_scopedApp(query));
    final container = ProviderScope.containerOf(
      tester.element(find.byType(MaterialApp)),
    );

    injector.activate(
      TypedFaultProfile.latency,
      latency: const Duration(milliseconds: 200),
    );
    final pending = container.read(discoveryFeedMapProvider.notifier).load('photo');
    await tester.pump(const Duration(milliseconds: 400));
    await pending;
    await tester.pump();

    final slowFeed = container.read(discoveryFeedMapProvider)['photo']?.value;
    expect(slowFeed, isNotNull);
    expect(slowFeed!.error, isNull, reason: '弱网变慢不是失败，必须最终成功');
    expect(slowFeed.items, isNotEmpty);
    expect(
      slowFeed.items.map((item) => item.id).toSet().length,
      slowFeed.items.length,
      reason: '弱网重放不得引入重复条目',
    );
  });
}
