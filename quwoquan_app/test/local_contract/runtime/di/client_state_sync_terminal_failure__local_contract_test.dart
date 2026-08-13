// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-001.t6

import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/runtime/di/client_state_sync_dependencies.dart';
import 'package:quwoquan_app/runtime/di/post_interaction_state_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_relationship_state_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/storage/client_interaction_state_store.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync.dart';

void main() {
  late Directory tempDir;

  setUpAll(() async {
    tempDir = await Directory.systemTemp.createTemp(
      'client_state_sync_terminal_test_',
    );
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

  ProviderContainer buildContainer({required ClientStateSyncConfig config}) {
    return ProviderContainer(
      overrides: <Override>[
        clientStateSyncRuntimeDependenciesProvider.overrideWithValue(
          ClientStateSyncRuntimeDependencies(
            readConfig: () => config,
            readPersistedState: () =>
                readPersistedInteractionMap('client_state_sync_outbox'),
            writePersistedState: (value) =>
                writePersistedInteractionMap('client_state_sync_outbox', value),
            executeEntry: (_) async =>
                throw StateError('remote unavailable'),
          ),
        ),
      ],
    );
  }

  test('like 超期终态：乐观点赞态回滚到已确认值并发布可订阅失败信号', () async {
    final container = buildContainer(config: _expiringConfig);
    addTearDown(container.dispose);
    final outbox = container.read(clientStateSyncOutboxProvider.notifier);

    // 乐观 UI：本地立即置为已点赞，同步交给 outbox。
    container
        .read(postInteractionStateProvider.notifier)
        .setLiked('post-terminal', true);
    outbox.enqueuePostLike(
      postId: 'post-terminal',
      currentLiked: false,
      isLiked: true,
    );
    await Future<void>.delayed(const Duration(milliseconds: 10));

    await outbox.flushNow();

    expect(
      container.read(postInteractionStateProvider).likedPostIds,
      isNot(contains('post-terminal')),
    );
    expect(container.read(clientStateSyncOutboxProvider).entries, isEmpty);
    final failure = container.read(clientStateSyncTerminalFailureProvider);
    expect(failure, isNotNull);
    expect(failure!.objectId, 'post-terminal');
    // 一次性消费语义：UI 读取后清空，不重复提示。
    container.read(clientStateSyncTerminalFailureProvider.notifier).consume();
    expect(container.read(clientStateSyncTerminalFailureProvider), isNull);
  });

  test('follow 超期终态：乐观关注态回滚到已确认值', () async {
    final container = buildContainer(config: _expiringConfig);
    addTearDown(container.dispose);
    final outbox = container.read(clientStateSyncOutboxProvider.notifier);

    container
        .read(userRelationshipStateProvider.notifier)
        .setFollowing('profile-terminal', true);
    outbox.enqueueFollow(
      personaId: 'profile-terminal',
      currentFollowing: false,
      shouldFollow: true,
      sourceSurfaceId: 'userProfile',
    );
    await Future<void>.delayed(const Duration(milliseconds: 10));

    await outbox.flushNow();

    expect(
      container.read(userRelationshipStateProvider).followingPersonaIds,
      isNot(contains('profile-terminal')),
    );
    final failure = container.read(clientStateSyncTerminalFailureProvider);
    expect(failure, isNotNull);
    expect(failure!.objectId, 'profile-terminal');
  });

  test('重试期内失败保持静默：乐观态不回滚、无终态失败信号', () async {
    final container = buildContainer(config: _retryingConfig);
    addTearDown(container.dispose);
    final outbox = container.read(clientStateSyncOutboxProvider.notifier);

    container
        .read(postInteractionStateProvider.notifier)
        .setLiked('post-retrying', true);
    outbox.enqueuePostLike(
      postId: 'post-retrying',
      currentLiked: false,
      isLiked: true,
    );
    await Future<void>.delayed(const Duration(milliseconds: 10));

    await outbox.flushNow();

    expect(
      container.read(postInteractionStateProvider).likedPostIds,
      contains('post-retrying'),
    );
    expect(
      container.read(clientStateSyncOutboxProvider).entries.length,
      1,
    );
    expect(container.read(clientStateSyncTerminalFailureProvider), isNull);
  });
}

/// entry 立即到期：flushDelay 与 maxPendingAge 均为零，首次 flush 即终态。
const _expiringConfig = ClientStateSyncConfig(
  flushDelay: Duration.zero,
  retryDelay: Duration(minutes: 5),
  maxBatchSize: 20,
  maxPendingAge: Duration.zero,
  flushOnForegroundResume: true,
  flushOnNetworkRecovered: true,
);

/// 常规配置：72 小时窗口内保持静默重试。
const _retryingConfig = ClientStateSyncConfig(
  flushDelay: Duration.zero,
  retryDelay: Duration(minutes: 5),
  maxBatchSize: 20,
  maxPendingAge: Duration(hours: 72),
  flushOnForegroundResume: true,
  flushOnNetworkRecovered: true,
);
