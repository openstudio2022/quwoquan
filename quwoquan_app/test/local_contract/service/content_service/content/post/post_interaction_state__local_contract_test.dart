// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-001

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_interaction_state.dart';
import 'package:quwoquan_app/runtime/di/post_interaction_state_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AssistantUsePolicy;

ContentPostViewData _confirmedPost(
  String id, {
  bool? viewerLiked,
  int likeCount = 3,
  int commentCount = 2,
  int shareCount = 1,
}) {
  return ContentPostViewData(
    id: id,
    type: 'image',
    identity: 'work',
    displayFormat: 'image',
    assistantUsePolicy: AssistantUsePolicy.inherit,
    authorId: 'author-1',
    displayName: 'author',
    avatarUrl: '',
    authorRoleLabel: '',
    authorIdentityTags: const <String>[],
    authorVerified: false,
    likeCount: likeCount,
    commentCount: commentCount,
    shareCount: shareCount,
    viewerLiked: viewerLiked,
    createdAt: DateTime.utc(2026, 8, 12),
  );
}

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

  group('viewerLiked hydrate 合并语义', () {
    // spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-001.t4
    test('服务端 viewerLiked=true/false hydrate 本地点赞态', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);
      final notifier = container.read(postInteractionStateProvider.notifier);

      // 本地存在过期 liked（换设备前的残留），服务端权威 false 收敛它。
      notifier.setLiked('post-stale', true);

      notifier.applyConfirmedPosts(<ContentPostViewData>[
        _confirmedPost('post-liked', viewerLiked: true),
        _confirmedPost('post-stale', viewerLiked: false),
      ]);

      final state = container.read(postInteractionStateProvider);
      expect(state.isLiked('post-liked'), isTrue);
      expect(state.isLiked('post-stale'), isFalse);
    });

    // spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-001.t5
    test('viewerLiked=null（未附着）不得回滚本地状态', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);
      final notifier = container.read(postInteractionStateProvider.notifier);

      notifier.setLiked('post-local', true);

      notifier.applyConfirmedPosts(<ContentPostViewData>[
        _confirmedPost('post-local'),
      ]);

      final state = container.read(postInteractionStateProvider);
      expect(state.isLiked('post-local'), isTrue);
    });

    // spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-001.t5
    test('本地 pending like 意图优先于服务端 viewerLiked', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);
      final notifier = container.read(postInteractionStateProvider.notifier);

      // 用户刚点了赞（意图尚未 flush），旧的服务端页面还是 false——
      // pending 意图优先，不得被权威投影抹掉乐观态。
      notifier.setLiked('post-pending', true);

      notifier.applyConfirmedPosts(
        <ContentPostViewData>[
          _confirmedPost('post-pending', viewerLiked: false),
        ],
        pendingLikePostIds: const <String>{'post-pending'},
      );

      final state = container.read(postInteractionStateProvider);
      expect(state.isLiked('post-pending'), isTrue);
      // 计数仍无条件采纳权威值。
      expect(state.commentCountFor('post-pending'), 2);
      expect(state.shareCountFor('post-pending'), 1);
    });
  });
}
