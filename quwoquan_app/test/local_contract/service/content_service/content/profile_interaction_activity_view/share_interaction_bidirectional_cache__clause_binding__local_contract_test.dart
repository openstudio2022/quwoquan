// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-005
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-005.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-005.t2
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-005.t3
import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/profile_interaction_activity_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/share_interaction_provider.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_capabilities.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const _received = ShareInteractionBucketKey(
  personaId: 'persona-a',
  direction: ShareInteractionDirection.received,
);
const _initiated = ShareInteractionBucketKey(
  personaId: 'persona-a',
  direction: ShareInteractionDirection.initiated,
);

void main() {
  // GWT-005.t1：两个方向各自保存 items/cursor/scrollOffset/loading/lastFetchedAt/error。
  // 逐字段改一个方向再读另一个方向：任何一个字段被提升成共享状态，另一个方向都会
  // 被污染，这里就会失败。
  test('两个方向的六类状态字段互不串桶', () async {
    final repository = _ShareRepository();
    final container = _container(repository);
    addTearDown(container.dispose);

    container.read(shareInteractionStateProvider(_received));
    container.read(shareInteractionStateProvider(_initiated));
    await pumpEventQueue();

    final receivedState = container.read(shareInteractionStateProvider(_received));
    final initiatedState = container.read(
      shareInteractionStateProvider(_initiated),
    );
    expect(receivedState.items.single.direction, ShareInteractionDirection.received);
    expect(initiatedState.items.single.direction, ShareInteractionDirection.initiated);
    expect(receivedState.nextCursor, 'cursor-received');
    expect(initiatedState.nextCursor, 'cursor-sent');
    expect(receivedState.lastFetchedAt, isNotNull);
    expect(initiatedState.lastFetchedAt, isNotNull);

    container
        .read(shareInteractionControllerProvider(_received))
        .saveScrollOffset(280);
    expect(container.read(shareInteractionStateProvider(_received)).scrollOffset, 280);
    expect(container.read(shareInteractionStateProvider(_initiated)).scrollOffset, 0);

    repository.failNextListFor = ShareInteractionDirection.received;
    await container.read(shareInteractionControllerProvider(_received)).refresh();
    expect(
      container.read(shareInteractionStateProvider(_received)).error,
      isA<StateError>(),
    );
    expect(container.read(shareInteractionStateProvider(_initiated)).error, isNull);

    final loading = container.read(shareInteractionControllerProvider(_received));
    repository.deferNextListFor = ShareInteractionDirection.received;
    final inflight = loading.refresh();
    expect(
      container.read(shareInteractionStateProvider(_received)).isRefreshing,
      isTrue,
    );
    expect(
      container.read(shareInteractionStateProvider(_initiated)).isRefreshing,
      isFalse,
    );
    repository.releaseDeferred(ShareInteractionDirection.received);
    await inflight;
  });

  // GWT-005.t2：缓存 5 分钟内直接命中，过期后转成后台刷新而不是清空重来。
  test('缓存 5 分钟内命中，过期后后台刷新且不清空已有列表', () async {
    expect(ShareInteractionNotifier.cacheTtl, const Duration(minutes: 5));

    final repository = _ShareRepository();
    final container = _container(repository);
    addTearDown(container.dispose);

    container.read(shareInteractionStateProvider(_received));
    await pumpEventQueue();
    expect(repository.listCalls, 1);

    await container.read(shareInteractionControllerProvider(_received)).ensureLoaded();
    await pumpEventQueue();
    expect(repository.listCalls, 1, reason: '新鲜缓存不得再打一次请求');

    container.read(shareInteractionControllerProvider(_received)).saveScrollOffset(120);
    _expireCache(container, _received);

    await container.read(shareInteractionControllerProvider(_received)).ensureLoaded();
    expect(
      container.read(shareInteractionStateProvider(_received)).items,
      isNotEmpty,
      reason: '过期刷新是后台刷新，不得先清空再拉',
    );
    await pumpEventQueue();
    expect(repository.listCalls, 2);
  });

  // GWT-005.t3：距尾 5 条触发预加载；刷新只作用当前方向。
  test('距尾 5 条预加载，刷新不波及另一个方向', () async {
    final repository = _ShareRepository(pageItemCount: 20);
    final container = _container(repository);
    addTearDown(container.dispose);

    container.read(shareInteractionStateProvider(_received));
    container.read(shareInteractionStateProvider(_initiated));
    await pumpEventQueue();
    final baseline = repository.listCalls;

    final state = container.read(shareInteractionStateProvider(_received));
    expect(state.items, hasLength(20));
    expect(state.hasMore, isTrue);
    expect(
      _prefetchTriggerIndex(state.items.length),
      15,
      reason: '列表在 sourceIndex >= items.length - 5 时预加载',
    );

    await container.read(shareInteractionControllerProvider(_received)).loadMore();
    expect(
      container.read(shareInteractionStateProvider(_received)).items,
      hasLength(40),
    );
    expect(
      container.read(shareInteractionStateProvider(_initiated)).items,
      hasLength(20),
      reason: '预加载只作用当前方向',
    );

    repository.listCalls = baseline;
    await container.read(shareInteractionControllerProvider(_received)).refresh();
    await pumpEventQueue();
    expect(repository.callsFor(ShareInteractionDirection.initiated), 1);
  });
}

/// 与 [share_interaction_list.dart] 的 `sourceIndex >= state.items.length - 5`
/// 同一算式；列表把阈值改掉时这条断言先失败，而不是等真机滚不动才发现。
int _prefetchTriggerIndex(int loadedCount) => loadedCount - 5;

void _expireCache(ProviderContainer container, ShareInteractionBucketKey key) {
  final notifier = container.read(shareInteractionControllerProvider(key));
  (notifier as ShareInteractionNotifier).state = notifier.state.copyWith(
    lastFetchedAt: DateTime.now().subtract(const Duration(minutes: 6)),
  );
}

ProviderContainer _container(_ShareRepository repository) {
  return ProviderContainer(
    overrides: [
      profileInteractionQueryFacetProvider.overrideWithValue(repository),
      profileInteractionReadFactAppendFacetProvider.overrideWithValue(repository),
      authSessionControllerProvider.overrideWith(_TestAuthController.new),
    ],
  );
}

class _TestAuthController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'test-token',
    ownerId: 'owner-a',
    activePersonaId: 'persona-a',
  );
}

class _ShareRepository
    implements
        ContentProfileInteractionQueryFacet,
        ContentProfileInteractionReadFactAppendFacet {
  _ShareRepository({this.pageItemCount = 1});

  final int pageItemCount;
  int listCalls = 0;
  ShareInteractionDirection? failNextListFor;
  ShareInteractionDirection? deferNextListFor;
  final Map<ShareInteractionDirection, int> _callsByDirection =
      <ShareInteractionDirection, int>{};
  final Map<ShareInteractionDirection,
      Completer<ProfileInteractionActivityPageSlice>> _deferred =
      <ShareInteractionDirection,
          Completer<ProfileInteractionActivityPageSlice>>{};

  int callsFor(ShareInteractionDirection direction) =>
      _callsByDirection[direction] ?? 0;

  void releaseDeferred(ShareInteractionDirection direction) {
    _deferred.remove(direction)?.complete(
      _page(direction, pageItemCount, listCalls),
    );
  }

  @override
  Future<ProfileInteractionActivityPageSlice> listActivities(
    ContentProfileInteractionPageQuery query, {
    required InteractionDirection direction,
  }) {
    final bucket = direction == InteractionDirection.received
        ? ShareInteractionDirection.received
        : ShareInteractionDirection.initiated;
    listCalls += 1;
    _callsByDirection[bucket] = callsFor(bucket) + 1;
    if (failNextListFor == bucket) {
      failNextListFor = null;
      return Future<ProfileInteractionActivityPageSlice>.error(
        StateError('share list unavailable'),
      );
    }
    if (deferNextListFor == bucket) {
      deferNextListFor = null;
      final completer = Completer<ProfileInteractionActivityPageSlice>();
      _deferred[bucket] = completer;
      return completer.future;
    }
    return Future.value(_page(bucket, pageItemCount, listCalls));
  }

  @override
  Future<ProfileInteractionReadFactAck> appendReadFact(
    AppendContentProfileInteractionReadFactCommand command,
  ) async {
    return ProfileInteractionReadFactAck(
      factId: 'fact-${command.activityId}',
      activityId: command.activityId,
      state: command.state,
      occurredAt: DateTime.utc(2026, 7, 12),
      replayed: false,
    );
  }
}

ProfileInteractionActivityPageSlice _page(
  ShareInteractionDirection direction,
  int itemCount,
  int callSequence,
) {
  final wireDirection = direction == ShareInteractionDirection.received
      ? 'received'
      : 'sent';
  return ProfileInteractionActivityPageSlice(
    items: List<ProfileInteractionActivityView>.generate(
      itemCount,
      (index) => ProfileInteractionActivityView(
        ownerPersonaId: 'persona-a',
        activityId: '$wireDirection-$callSequence-$index',
        activityType: InteractionActivityType.share,
        direction: InteractionDirection.fromWire(
          wireDirection,
          'ProfileInteractionActivityView.direction',
        ),
        sourceType: 'local_contract',
        sourceEventId: 'event-$wireDirection-$callSequence-$index',
        sourceVersion: 1,
        viewerReactionVersion: 1,
        targetVersion: 1,
        active: true,
        commentKind: 'none',
        viewerReaction: CommentReactionType.none,
        actorPersonaId: 'actor',
        actorDisplayName: '山海来信',
        actorAvatarVersion: 1,
        targetPersonaId: 'persona-a',
        targetContentId: 'target',
        targetContentType: ContentType.image,
        targetContentSummary: '川西晨光',
        targetKind: 'post',
        targetAvailability: 'active',
        targetReplyCount: 0,
        displayPersonaId: 'actor',
        displayName: '山海来信',
        displayAvatarVersion: 1,
        primaryText: '转发互动',
        previewMediaKind: 'text',
        previewText: '川西晨光',
        previewUnavailable: false,
        filterKeys: const <String>['shares'],
        createdAt: DateTime.utc(2026, 7, 12),
        occurredAt: DateTime.utc(2026, 7, 12),
      ),
    ),
    nextCursor: 'cursor-$wireDirection',
    hasMore: true,
  );
}
