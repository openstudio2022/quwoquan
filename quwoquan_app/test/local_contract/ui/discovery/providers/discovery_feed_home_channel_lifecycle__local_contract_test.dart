// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-005

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_feed_page.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CloudOperationCancellationSignal,
        ContentFeedEmptyReason,
        ContentFeedOutcome;

void main() {
  test('远端首页频道变更只回收已移除频道并取消请求，不误删 discovery tab', () async {
    final recommend = ContentUIConfig.homeChannels.firstWhere(
      (channel) => channel.id == 'recommend',
    );
    final travel = ContentUIConfig.homeChannels.firstWhere(
      (channel) => channel.id == 'travel',
    );
    final query = _PendingDiscoveryFeedQuery();
    final container = ProviderContainer(
      overrides: <Override>[
        contentDiscoveryFeedQueryProvider.overrideWithValue(query),
        homeChannelsProvider.overrideWithValue(<HomeChannelConfig>[
          recommend,
          travel,
        ]),
      ],
    );
    addTearDown(container.dispose);
    final notifier = container.read(discoveryFeedMapProvider.notifier);
    notifier.state = <String, AsyncValue<DiscoveryFeedState>>{
      'travel': const AsyncData(DiscoveryFeedState()),
      'photo': const AsyncData(DiscoveryFeedState()),
    };

    final removedLoad = notifier.load('recommend', force: true);
    await container.pump();
    expect(query.cancellation?.isCancelled, isFalse);
    expect(
      container.read(discoveryFeedMapProvider).containsKey('recommend'),
      isTrue,
    );

    container.updateOverrides(<Override>[
      contentDiscoveryFeedQueryProvider.overrideWithValue(query),
      homeChannelsProvider.overrideWithValue(<HomeChannelConfig>[travel]),
    ]);
    await container.pump();

    final afterChurn = container.read(discoveryFeedMapProvider);
    expect(query.cancellation?.isCancelled, isTrue);
    expect(afterChurn.containsKey('recommend'), isFalse);
    expect(afterChurn.containsKey('travel'), isTrue);
    expect(afterChurn.containsKey('photo'), isTrue);

    query.completeLate();
    final removedResult = await removedLoad;
    expect(removedResult.terminal, DiscoveryFeedLoadTerminal.cancelled);
    expect(
      container.read(discoveryFeedMapProvider).containsKey('recommend'),
      isFalse,
    );
  });

  test('load 返回 canonicalEmpty 而不由 Widget 二次猜测', () async {
    final recommend = ContentUIConfig.homeChannels.firstWhere(
      (channel) => channel.id == 'recommend',
    );
    final container = ProviderContainer(
      overrides: <Override>[
        contentDiscoveryFeedQueryProvider.overrideWithValue(
          _ImmediateDiscoveryFeedQuery(
            () async => const DiscoveryFeedPage(
              items: [],
              outcome: ContentFeedOutcome.empty,
              emptyReason: ContentFeedEmptyReason.noActiveRelease,
            ),
          ),
        ),
        homeChannelsProvider.overrideWithValue(<HomeChannelConfig>[recommend]),
        postInteractionStateProvider.overrideWith(
          _NoopPostInteractionStateNotifier.new,
        ),
      ],
    );
    addTearDown(container.dispose);

    final result = await container
        .read(discoveryFeedMapProvider.notifier)
        .load('recommend', force: true);

    expect(result.terminal, DiscoveryFeedLoadTerminal.canonicalEmpty);
    expect(
      container.read(discoveryFeedMapProvider)['recommend']?.value?.emptyReason,
      ContentFeedEmptyReason.noActiveRelease,
    );
  });

  test('load 失败返回 stillBlocked 并绑定本次 generation', () async {
    final recommend = ContentUIConfig.homeChannels.firstWhere(
      (channel) => channel.id == 'recommend',
    );
    final container = ProviderContainer(
      overrides: <Override>[
        contentDiscoveryFeedQueryProvider.overrideWithValue(
          _ImmediateDiscoveryFeedQuery(
            () async => throw StateError('service unavailable'),
          ),
        ),
        homeChannelsProvider.overrideWithValue(<HomeChannelConfig>[recommend]),
        postInteractionStateProvider.overrideWith(
          _NoopPostInteractionStateNotifier.new,
        ),
      ],
    );
    addTearDown(container.dispose);

    final result = await container
        .read(discoveryFeedMapProvider.notifier)
        .load('recommend', force: true);

    expect(result.terminal, DiscoveryFeedLoadTerminal.stillBlocked);
    expect(result.generation, greaterThan(0));
    expect(result.failure, isNotNull);
    expect(
      container
          .read(discoveryFeedMapProvider)['recommend']
          ?.value
          ?.blockingError,
      isNotNull,
    );
  });
}

final class _NoopPostInteractionStateNotifier
    extends PostInteractionStateNotifier {
  @override
  PostInteractionState build() => const PostInteractionState();

  @override
  void applyConfirmedPosts(Iterable<ContentPostViewData> posts) {}
}

final class _ImmediateDiscoveryFeedQuery implements ContentDiscoveryFeedQuery {
  const _ImmediateDiscoveryFeedQuery(this._load);

  final Future<DiscoveryFeedPage> Function() _load;

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
  }) => _load();
}

final class _PendingDiscoveryFeedQuery implements ContentDiscoveryFeedQuery {
  final Completer<DiscoveryFeedPage> _pending = Completer<DiscoveryFeedPage>();
  CloudOperationCancellationSignal? cancellation;

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
    this.cancellation = cancellation;
    return _pending.future;
  }

  void completeLate() {
    _pending.complete(const DiscoveryFeedPage(items: []));
  }
}
