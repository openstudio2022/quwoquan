// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003

import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/runtime/di/post_interaction_state_dependencies.dart';
import 'package:quwoquan_app/runtime/di/client_state_sync_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/storage/client_interaction_state_store.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync.dart';
import 'package:quwoquan_app/runtime/di/user_relationship_state_dependencies.dart';

void main() {
  late Directory tempDir;

  setUpAll(() async {
    tempDir = await Directory.systemTemp.createTemp('client_state_sync_test_');
    Hive.init(tempDir.path);
    final box = await Hive.openBox<String>('client_interaction_state');
    await box.clear();
    await box.close();
  });

  setUp(() async {
    if (Hive.isBoxOpen('client_interaction_state')) {
      await Hive.box<String>('client_interaction_state').clear();
      return;
    }
    final box = await Hive.openBox<String>('client_interaction_state');
    await box.clear();
    await box.close();
  });

  tearDownAll(() async {
    await Hive.close();
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  test('账号 closed 终态清除交互投影与 outbox 并停止旧 notifier 入队', () async {
    final executor = _RecordingClientStateSyncExecutor();
    final container = ProviderContainer(
      overrides: <Override>[
        clientStateSyncRuntimeDependenciesProvider.overrideWithValue(
          ClientStateSyncRuntimeDependencies(
            readConfig: () => _fixedConfig,
            readPersistedState: () =>
                readPersistedInteractionMap('client_state_sync_outbox'),
            writePersistedState: (value) =>
                writePersistedInteractionMap('client_state_sync_outbox', value),
            executeEntry: executor.call,
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    final outbox = container.read(clientStateSyncOutboxProvider.notifier);
    container.read(userRelationshipStateProvider.notifier).seedFollowing(
      const <String>['profile-closed'],
    );
    container
        .read(postInteractionStateProvider.notifier)
        .setLiked('post-closed', true, likeCount: 1);
    outbox.enqueuePostLike(
      postId: 'post-pending',
      currentLiked: false,
      isLiked: true,
    );
    await Future<void>.delayed(const Duration(milliseconds: 10));

    outbox.purgeForTerminalAccountClosure();
    await clearClientInteractionStateForTerminalAccountClosure();
    container.invalidate(userRelationshipStateProvider);
    container.invalidate(postInteractionStateProvider);
    container.invalidate(clientStateSyncOutboxProvider);

    final box = Hive.box<String>('client_interaction_state');
    expect(box, isEmpty);
    expect(
      container.read(userRelationshipStateProvider).followingPersonaIds,
      isEmpty,
    );
    expect(container.read(postInteractionStateProvider).likedPostIds, isEmpty);
    expect(container.read(clientStateSyncOutboxProvider).entries, isEmpty);
    outbox.enqueuePostLike(
      postId: 'post-after-closed',
      currentLiked: false,
      isLiked: true,
    );
    expect(box, isEmpty);
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

final class _RecordingClientStateSyncExecutor {
  final List<ClientStateSyncOutboxEntry> entries =
      <ClientStateSyncOutboxEntry>[];

  Future<void> call(ClientStateSyncOutboxEntry entry) async {
    entries.add(entry);
  }
}
