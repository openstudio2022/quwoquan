import 'dart:io';
import 'dart:convert';

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
    test('follow 在 flush 窗口内回到已确认状态时会移除 pending entry', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final notifier = container.read(clientStateSyncOutboxProvider.notifier);

      notifier.enqueueFollow(
        subAccountId: 'profile-1',
        currentFollowing: false,
        shouldFollow: true,
      );

      var state = container.read(clientStateSyncOutboxProvider);
      expect(state.entries.length, 1);
      expect(state.entries.single.confirmedBoolValue, isFalse);
      expect(state.entries.single.desiredBoolValue, isTrue);

      notifier.enqueueFollow(
        subAccountId: 'profile-1',
        currentFollowing: true,
        shouldFollow: false,
      );

      state = container.read(clientStateSyncOutboxProvider);
      expect(state.entries, isEmpty);
    });

    test('like 在 flush 窗口内回到已确认状态时会移除 pending entry', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final notifier = container.read(clientStateSyncOutboxProvider.notifier);

      notifier.enqueuePostLike(
        postId: 'post-1',
        currentLiked: false,
        isLiked: true,
      );

      var state = container.read(clientStateSyncOutboxProvider);
      expect(state.entries.length, 1);
      expect(state.entries.single.confirmedBoolValue, isFalse);
      expect(state.entries.single.desiredBoolValue, isTrue);

      notifier.enqueuePostLike(
        postId: 'post-1',
        currentLiked: true,
        isLiked: false,
      );

      state = container.read(clientStateSyncOutboxProvider);
      expect(state.entries, isEmpty);
    });

    test('confirmed 态会在 follow / like 的多次点击之间保留', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final notifier = container.read(clientStateSyncOutboxProvider.notifier);

      notifier.enqueueFollow(
        subAccountId: 'profile-1',
        currentFollowing: true,
        shouldFollow: false,
      );
      notifier.enqueuePostLike(
        postId: 'post-1',
        currentLiked: true,
        isLiked: false,
      );

      var state = container.read(clientStateSyncOutboxProvider);
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
            .entryFor(
              objectType: 'post',
              objectId: 'post-1',
              intentType: 'like',
            )
            ?.confirmedBoolValue,
        isTrue,
      );

      notifier.enqueueFollow(
        subAccountId: 'profile-1',
        currentFollowing: false,
        shouldFollow: true,
      );
      notifier.enqueuePostLike(
        postId: 'post-1',
        currentLiked: false,
        isLiked: true,
      );

      state = container.read(clientStateSyncOutboxProvider);
      expect(state.entries, isEmpty);
    });

    test('hydrate 旧 guard-only 持久化条目时不会误恢复为待同步请求', () async {
      final box = await Hive.openBox<String>('client_interaction_state');
      await box.put(
        'client_state_sync_outbox_v1',
        jsonEncode({
          'entries': [
            {
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
        }),
      );
      await box.close();

      final container = ProviderContainer();
      addTearDown(container.dispose);

      await Future<void>.delayed(const Duration(milliseconds: 10));

      final state = container.read(clientStateSyncOutboxProvider);
      expect(state.entries, isEmpty);
    });
  });

  group('post interaction counters', () {
    test('comment 仅使用 pending 渲染，分享只消费服务端权威计数', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final notifier = container.read(postInteractionStateProvider.notifier);

      notifier.stageOptimisticComment('post-1', baseCommentCount: 3, delta: 1);
      var state = container.read(postInteractionStateProvider);
      expect(state.commentCountFor('post-1'), 4);
      expect(state.shareCountFor('post-1', fallback: 2), 2);

      notifier.applyConfirmedCounters('post-1', commentCount: 3, shareCount: 2);

      state = container.read(postInteractionStateProvider);
      expect(state.commentCountFor('post-1'), 3);
      expect(state.shareCountFor('post-1', fallback: 2), 2);
    });

    test('PostInteractionState round-trip 只持久化权威计数与评论 pending', () {
      const state = PostInteractionState(
        confirmedShareCounts: <String, int>{'post-1': 5},
        confirmedCommentCounts: <String, int>{'post-1': 9},
        pendingCommentDeltas: <String, int>{'post-1': -1},
      );

      final restored = PostInteractionState.fromMap(state.toMap());

      expect(restored.shareCountFor('post-1'), 5);
      expect(restored.commentCountFor('post-1'), 8);
    });
  });
}
