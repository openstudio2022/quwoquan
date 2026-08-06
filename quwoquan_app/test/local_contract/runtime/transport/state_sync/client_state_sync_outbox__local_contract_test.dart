// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync_outbox_engine.dart';

void main() {
  group('client state sync outbox', () {
    test('远程同步配置拒绝字符串化数值与布尔值', () {
      expect(
        () => ClientStateSyncConfig.fromMap(<String, dynamic>{
          'max_batch_size': '20',
          'flush_on_network_recovered': 'true',
        }, fallback: ClientStateSyncConfig.defaults()),
        throwsFormatException,
      );
    });

    test('follow 在 flush 窗口内回到已确认状态时会移除 pending entry', () {
      final harness = _ClientStateSyncHarness();
      addTearDown(harness.dispose);
      final notifier = harness.engine;

      notifier.enqueueFollow(
        personaId: 'profile-1',
        currentFollowing: false,
        shouldFollow: true,
        sourceSurfaceId: 'userProfile',
      );

      var state = notifier.state;
      expect(state.entries.length, 1);
      expect(state.entries.single.confirmedBoolValue, isFalse);
      expect(state.entries.single.desiredBoolValue, isTrue);
      expect(state.entries.single.sourceSurfaceId, 'userProfile');

      notifier.enqueueFollow(
        personaId: 'profile-1',
        currentFollowing: true,
        shouldFollow: false,
        sourceSurfaceId: 'userProfile',
      );

      state = notifier.state;
      expect(state.entries, isEmpty);
    });

    test('like 在 flush 窗口内回到已确认状态时会移除 pending entry', () {
      final harness = _ClientStateSyncHarness();
      addTearDown(harness.dispose);
      final notifier = harness.engine;

      notifier.enqueuePostLike(
        postId: 'post-1',
        currentLiked: false,
        isLiked: true,
      );

      var state = notifier.state;
      expect(state.entries.length, 1);
      expect(state.entries.single.confirmedBoolValue, isFalse);
      expect(state.entries.single.desiredBoolValue, isTrue);

      notifier.enqueuePostLike(
        postId: 'post-1',
        currentLiked: true,
        isLiked: false,
      );

      state = notifier.state;
      expect(state.entries, isEmpty);
    });

    test('旧 needsRemoteSync 持久化形态失效清除且不迁移', () async {
      final store = _InMemoryClientStateSyncStore()
        ..value = <String, dynamic>{
          'entries': <Object?>[
            <String, Object?>{
              'coalesceKey': 'profile:follow:profile-1',
              'objectType': 'profile',
              'objectId': 'profile-1',
              'intentType': 'follow',
              'desiredBoolValue': true,
              'nextFlushAt': DateTime.now().toUtc().toIso8601String(),
              'guardUntil': DateTime.now()
                  .toUtc()
                  .add(const Duration(seconds: 8))
                  .toIso8601String(),
              'needsRemoteSync': false,
              'retryCount': 0,
            },
          ],
        };
      final harness = _ClientStateSyncHarness(store: store);
      addTearDown(harness.dispose);

      await harness.engine.hydrate();

      final state = harness.engine.state;
      expect(state.entries, isEmpty);
      expect(store.value, <String, Object?>{'entries': <Object?>[]});
    });
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
  _ClientStateSyncHarness({_InMemoryClientStateSyncStore? store})
    : store = store ?? _InMemoryClientStateSyncStore() {
    engine = ClientStateSyncOutboxEngine(
      readConfig: () => _fixedConfig,
      readPersistedState: this.store.read,
      writePersistedState: this.store.write,
      executeEntry: executor.call,
      onStateChanged: (_) {},
    );
  }

  final _InMemoryClientStateSyncStore store;
  final _RecordingClientStateSyncExecutor executor =
      _RecordingClientStateSyncExecutor();
  late final ClientStateSyncOutboxEngine engine;

  void dispose() => engine.dispose();
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
