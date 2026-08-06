// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-001

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_interaction_state.dart';
import 'package:quwoquan_app/runtime/di/post_interaction_state_dependencies.dart';

void main() {
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
