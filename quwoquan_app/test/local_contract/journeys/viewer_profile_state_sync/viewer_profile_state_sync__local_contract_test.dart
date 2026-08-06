// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-001

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/client_state_sync_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync.dart';

void main() {
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
