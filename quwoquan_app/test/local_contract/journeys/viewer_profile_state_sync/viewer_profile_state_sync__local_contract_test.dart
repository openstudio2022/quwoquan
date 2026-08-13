// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-001

import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/client_state_sync_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_relationship_state_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync.dart';

void main() {
  // spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-001.t1
  group('viewer、profile、feed 消费同一 canonical 关系矩阵', () {
    String sourceOf(String path) => File(path).readAsStringSync();

    test('三个页面域源码消费同一 userRelationshipStateProvider 真相源', () {
      const relationProvider = 'userRelationshipStateProvider';
      final viewerSource = sourceOf(
        'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_build.dart',
      );
      final feedSource = sourceOf(
        'lib/service/content_service/content/post/presentation/home_multi_form_feed_post_cards.dart',
      );
      final profileSource = sourceOf(
        'lib/service/user_service/persona_management/persona/presentation/profile_state_provider.dart',
      );
      expect(viewerSource, contains(relationProvider));
      expect(feedSource, contains(relationProvider));
      expect(profileSource, contains(relationProvider));
      // profile 的关系能力矩阵消费 canonical RelationshipCapabilityViewData，
      // 其唯一定义位于 relationship_capability_repository.dart。
      expect(profileSource, contains('RelationshipCapabilityViewData'));
      final canonicalDefinition = sourceOf(
        'lib/service/user_service/relationship/persona_relationship/'
        'application/public/relationship_capability_repository.dart',
      );
      expect(
        canonicalDefinition,
        contains('class RelationshipCapabilityViewData'),
      );
    });

    test('关注态变更经统一 provider 传播到全部读取视角', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      container
          .read(userRelationshipStateProvider.notifier)
          .setFollowing('profile-t1', true);

      expect(
        container.read(userRelationshipStateProvider).followingPersonaIds,
        contains('profile-t1'),
      );
      // feed 卡片同款 select 视角看到同一事实，不存在页面局部状态拼装。
      final isFollowing = container.read(
        userRelationshipStateProvider.select(
          (state) => state.followingPersonaIds.contains('profile-t1'),
        ),
      );
      expect(isFollowing, isTrue);
    });
  });

  test('confirmed 态会在 follow / like 的多次点击之间保留', () {
    final harness = _ClientStateSyncHarness();
    addTearDown(harness.dispose);
    final notifier = harness.container.read(
      clientStateSyncOutboxProvider.notifier,
    );

    notifier.enqueueFollow(
      personaId: 'profile-1',
      currentFollowing: true,
      shouldFollow: false,
      sourceSurfaceId: 'userProfile',
    );
    notifier.enqueuePostLike(
      postId: 'post-1',
      currentLiked: true,
      isLiked: false,
    );

    var state = harness.container.read(clientStateSyncOutboxProvider);
    expect(
      state
          .entryFor(
            objectType: 'profile',
            objectId: 'profile-1',
            intentType: 'follow',
          )
          ?.confirmedBoolValue,
      isTrue,
    );
    expect(
      state
          .entryFor(objectType: 'post', objectId: 'post-1', intentType: 'like')
          ?.confirmedBoolValue,
      isTrue,
    );

    notifier.enqueueFollow(
      personaId: 'profile-1',
      currentFollowing: false,
      shouldFollow: true,
      sourceSurfaceId: 'userProfile',
    );
    notifier.enqueuePostLike(
      postId: 'post-1',
      currentLiked: false,
      isLiked: true,
    );

    state = harness.container.read(clientStateSyncOutboxProvider);
    expect(state.entries, isEmpty);
  });
}

const _fixedConfig = ClientStateSyncConfig(
  flushDelay: Duration(hours: 1),
  retryDelay: Duration(minutes: 5),
  maxBatchSize: 20,
  maxPendingAge: Duration(hours: 72),
  flushOnForegroundResume: true,
  flushOnNetworkRecovered: true,
);

final class _ClientStateSyncHarness {
  _ClientStateSyncHarness() {
    container = ProviderContainer(
      overrides: <Override>[
        clientStateSyncRuntimeDependenciesProvider.overrideWithValue(
          ClientStateSyncRuntimeDependencies(
            readConfig: () => _fixedConfig,
            readPersistedState: store.read,
            writePersistedState: store.write,
            executeEntry: executor.call,
          ),
        ),
      ],
    );
  }

  final _InMemoryClientStateSyncStore store = _InMemoryClientStateSyncStore();
  final _RecordingClientStateSyncExecutor executor =
      _RecordingClientStateSyncExecutor();
  late final ProviderContainer container;

  void dispose() => container.dispose();
}

final class _InMemoryClientStateSyncStore {
  Map<String, dynamic>? value;

  Future<Map<String, dynamic>?> read() async => value;

  Future<void> write(Map<String, dynamic> next) async {
    value = next;
  }
}

final class _RecordingClientStateSyncExecutor {
  final List<ClientStateSyncOutboxEntry> entries =
      <ClientStateSyncOutboxEntry>[];

  Future<void> call(ClientStateSyncOutboxEntry entry) async {
    entries.add(entry);
  }
}
