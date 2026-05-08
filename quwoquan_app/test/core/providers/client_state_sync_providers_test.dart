import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

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

  group('client state sync outbox', () {
    test('同一 profile follow 意图会按 latest_wins 合并', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final notifier = container.read(clientStateSyncOutboxProvider.notifier);

      notifier.enqueueFollow(subAccountId: 'profile-1', shouldFollow: true);
      notifier.enqueueFollow(
        subAccountId: 'profile-1',
        shouldFollow: false,
      );

      final state = container.read(clientStateSyncOutboxProvider);
      expect(state.entries.length, 1);
      expect(state.entries.single.desiredBoolValue, isFalse);
    });

    test('同一 post 的 like/save 意图分别独立合并', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final notifier = container.read(clientStateSyncOutboxProvider.notifier);

      notifier.enqueuePostLike(postId: 'post-1', isLiked: true);
      notifier.enqueuePostLike(postId: 'post-1', isLiked: false);
      notifier.enqueuePostSave(postId: 'post-1', isSaved: true);

      final state = container.read(clientStateSyncOutboxProvider);
      expect(state.entries.length, 2);
      expect(
        state.entries
            .where(
              (entry) =>
                  entry.objectId == 'post-1' && entry.intentType == 'like',
            )
            .single
            .desiredBoolValue,
        isFalse,
      );
      expect(
        state.entries
            .where(
              (entry) =>
                  entry.objectId == 'post-1' && entry.intentType == 'save',
            )
            .single
            .desiredBoolValue,
        isTrue,
      );
    });

    test('同一 post 的 share 意图也按 latest_wins 合并', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final notifier = container.read(clientStateSyncOutboxProvider.notifier);

      notifier.enqueuePostShare(postId: 'post-1', isShared: true);
      notifier.enqueuePostShare(postId: 'post-1', isShared: false);

      final state = container.read(clientStateSyncOutboxProvider);
      expect(state.entries.length, 1);
      expect(state.entries.single.intentType, 'share');
      expect(state.entries.single.desiredBoolValue, isFalse);
    });
  });

  group('post interaction counters', () {
    test('comment/share 使用 confirmed + pending 渲染并在权威回读后收敛', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final notifier = container.read(postInteractionStateProvider.notifier);

      notifier.stageOptimisticComment('post-1', baseCommentCount: 3, delta: 1);
      notifier.stageOptimisticShare('post-1', baseShareCount: 2);

      var state = container.read(postInteractionStateProvider);
      expect(state.commentCountFor('post-1'), 4);
      expect(state.shareCountFor('post-1'), 3);
      expect(state.isShared('post-1'), isTrue);

      notifier.applyConfirmedCounters('post-1', commentCount: 3, shareCount: 2);

      state = container.read(postInteractionStateProvider);
      expect(state.commentCountFor('post-1'), 3);
      expect(state.shareCountFor('post-1'), 2);
    });

    test('PostInteractionState round-trip 会保留 confirmed 与 pending 字段', () {
      const state = PostInteractionState(
        sharedPostIds: <String>{'post-1'},
        confirmedShareCounts: <String, int>{'post-1': 5},
        pendingShareDeltas: <String, int>{'post-1': 1},
        confirmedCommentCounts: <String, int>{'post-1': 9},
        pendingCommentDeltas: <String, int>{'post-1': -1},
      );

      final restored = PostInteractionState.fromMap(state.toMap());

      expect(restored.shareCountFor('post-1'), 6);
      expect(restored.commentCountFor('post-1'), 8);
      expect(restored.isShared('post-1'), isTrue);
    });
  });
}
