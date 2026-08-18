// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-005

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_interaction_state.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AssistantUsePolicy,
        CloudOperationCancellationSignal,
        ContentFeedEmptyReason,
        ContentFeedOutcome;

void main() {
  setUp(CloudRuntimeConfig.clearNativeRuntimePackageForTest);
  tearDown(CloudRuntimeConfig.clearNativeRuntimePackageForTest);

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

  test('noActiveRelease 始终是服务确认的 canonicalEmpty', () async {
    final recommend = ContentUIConfig.homeChannels.firstWhere(
      (channel) => channel.id == 'recommend',
    );
    final container = ProviderContainer(
      overrides: <Override>[
        contentDiscoveryFeedQueryProvider.overrideWithValue(
          _ImmediateDiscoveryFeedQuery(
            () async => DiscoveryFeedPage(
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

  test('runtime provider 不可用时快速收敛 typed unavailable 且绑定 generation', () async {
    final recommend = ContentUIConfig.homeChannels.firstWhere(
      (channel) => channel.id == 'recommend',
    );
    final container = ProviderContainer(
      overrides: <Override>[
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
    final state = container
        .read(discoveryFeedMapProvider)['recommend']
        ?.requireValue;

    expect(result.terminal, DiscoveryFeedLoadTerminal.stillBlocked);
    expect(result.generation, greaterThan(0));
    expect(
      (result.failure! as CloudException).runtimeFailure.kind,
      RuntimeFailureKind.unavailable,
    );
    expect(state?.blockingError, isA<CloudException>());
    expect(state?.items, isEmpty);
    expect(state?.emptyReason, isNull);
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

  test('同一 Provider 实例重试后清除阻断并恢复 canonical 内容', () async {
    final recommend = ContentUIConfig.homeChannels.firstWhere(
      (channel) => channel.id == 'recommend',
    );
    final query = _SequencedDiscoveryFeedQuery(
      <Future<DiscoveryFeedPage> Function()>[
        () async => throw StateError('service unavailable'),
        () async => DiscoveryFeedPage(
          items: <ContentPostViewData>[_recoveredCanonicalPost()],
          outcome: ContentFeedOutcome.content,
          feedRequestId: 'feed-request-recovered',
          policyDigest: 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        ),
      ],
    );
    final container = ProviderContainer(
      overrides: <Override>[
        contentDiscoveryFeedQueryProvider.overrideWithValue(query),
        homeChannelsProvider.overrideWithValue(<HomeChannelConfig>[recommend]),
        postInteractionStateProvider.overrideWith(
          _NoopPostInteractionStateNotifier.new,
        ),
      ],
    );
    addTearDown(container.dispose);
    final notifier = container.read(discoveryFeedMapProvider.notifier);

    final blocked = await notifier.load('recommend', force: true);
    expect(blocked.terminal, DiscoveryFeedLoadTerminal.stillBlocked);
    expect(
      container
          .read(discoveryFeedMapProvider)['recommend']
          ?.value
          ?.blockingError,
      isNotNull,
    );

    final recovered = await notifier.load('recommend', force: true);
    final state = container
        .read(discoveryFeedMapProvider)['recommend']
        ?.requireValue;
    expect(recovered.terminal, DiscoveryFeedLoadTerminal.content);
    expect(query.callCount, 2);
    expect(state?.blockingError, isNull);
    expect(state?.items.single.id, 'post-recovered');
    expect(state?.feedRequestId, 'feed-request-recovered');
  });
}

final class _NoopPostInteractionStateNotifier
    extends PostInteractionStateNotifier {
  @override
  PostInteractionState build() => const PostInteractionState();

  @override
  void applyConfirmedPosts(
    Iterable<ContentPostViewData> posts, {
    Set<String> pendingLikePostIds = const <String>{},
  }) {}
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

final class _SequencedDiscoveryFeedQuery implements ContentDiscoveryFeedQuery {
  _SequencedDiscoveryFeedQuery(this._loads);

  final List<Future<DiscoveryFeedPage> Function()> _loads;
  int callCount = 0;

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
    final index = callCount;
    callCount += 1;
    return _loads[index]();
  }
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
    _pending.complete(DiscoveryFeedPage(items: []));
  }
}

ContentPostViewData _recoveredCanonicalPost() => ContentPostViewData(
  id: 'post-recovered',
  type: 'micro',
  identity: 'moment',
  displayFormat: 'note',
  assistantUsePolicy: AssistantUsePolicy.inherit,
  authorId: 'author-recovered',
  displayName: '恢复内容作者',
  avatarUrl: '',
  authorRoleLabel: '旅行创作者',
  authorIdentityTags: const <String>[],
  authorVerified: false,
  body: '服务恢复后返回的 canonical 首页内容',
  likeCount: 0,
  commentCount: 0,
  shareCount: 0,
  createdAt: DateTime.utc(2026, 8, 4),
);
