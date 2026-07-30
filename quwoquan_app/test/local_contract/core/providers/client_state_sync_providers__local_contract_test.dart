// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-001

import 'dart:io';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/core/models/client_state_sync.dart';
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
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final notifier = container.read(clientStateSyncOutboxProvider.notifier);

      notifier.enqueueFollow(
        personaId: 'profile-1',
        currentFollowing: false,
        shouldFollow: true,
        sourceSurfaceId: 'userProfile',
      );

      var state = container.read(clientStateSyncOutboxProvider);
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

      state = container.read(clientStateSyncOutboxProvider);
      expect(state.entries, isEmpty);
    });

    test('旧 needsRemoteSync 持久化形态失效清除且不迁移', () async {
      final box = await Hive.openBox<String>('client_interaction_state');
      await box.put(
        'client_state_sync_outbox',
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

      container.read(clientStateSyncOutboxProvider);
      await Future<void>.delayed(const Duration(milliseconds: 30));

      final state = container.read(clientStateSyncOutboxProvider);
      expect(state.entries, isEmpty);
      final persistedBox = Hive.isBoxOpen('client_interaction_state')
          ? Hive.box<String>('client_interaction_state')
          : await Hive.openBox<String>('client_interaction_state');
      final persisted = jsonDecode(
        persistedBox.get('client_state_sync_outbox')!,
      );
      expect(persisted, <String, Object?>{'entries': <Object?>[]});
    });

    test('账号 closed 终态清除交互投影与 outbox 并停止旧 notifier 入队', () async {
      final container = ProviderContainer();
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
      expect(
        container.read(postInteractionStateProvider).likedPostIds,
        isEmpty,
      );
      expect(container.read(clientStateSyncOutboxProvider).entries, isEmpty);
      outbox.enqueuePostLike(
        postId: 'post-after-closed',
        currentLiked: false,
        isLiked: true,
      );
      expect(box, isEmpty);
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
