// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-001

import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/post_interaction_state_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_relationship_state_dependencies.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_hub_feed_post_entry.dart';

import '../../../support/service/content_service/content/post/content_post_test_builder.dart';

/// 跨页互动一致性旅程：详情/沉浸式改点赞、任意入口改关注后，
/// 首页 feed 卡片、圈子 Hub、作者栏等所有消费共享投影的界面必须立即一致。
///
/// 单一真相源契约：
/// - 点赞/分享/评论计数 → `postInteractionStateProvider`
/// - 关注关系 → `userRelationshipStateProvider`
/// - discovery / 圈子 Hub 等页面级状态不得再维护第二份副本。
void main() {
  group('跨页互动一致性（详情 → 列表/圈子）', () {
    test('详情点赞写入共享投影后，feed 卡片消费口径立即一致', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      // 详情/沉浸式侧：乐观点赞（syncPostLikeIntent 最终落到 setLiked）。
      container
          .read(postInteractionStateProvider.notifier)
          .setLiked('post-1', true, likeCount: 8);

      // 首页 feed 卡片的消费口径（home_multi_form_feed_post_cards）。
      final state = container.read(postInteractionStateProvider);
      expect(state.isLiked('post-1'), isTrue);
      expect(state.likeCountFor('post-1', fallback: 7), 8);

      // 取消点赞同样即时一致。
      container
          .read(postInteractionStateProvider.notifier)
          .setLiked('post-1', false, likeCount: 7);
      final next = container.read(postInteractionStateProvider);
      expect(next.isLiked('post-1'), isFalse);
      expect(next.likeCountFor('post-1', fallback: 0), 7);
    });

    test('圈子 Hub 未经过 viewer pop-merge 时也从共享投影取到最新点赞', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final entry = CircleHubFeedPostEntry.fromPost(
        circleId: 'circle-1',
        post: contentPostViewDataBuilder(postId: 'post-hub', likeCount: 3),
      );

      // 其他页面点赞（未打开圈子 Hub 的 viewer，entry 快照不更新）。
      container
          .read(postInteractionStateProvider.notifier)
          .setLiked('post-hub', true, likeCount: 4);

      // 圈子 Hub 渲染消费口径（home_circles_category_tab / section_creations）：
      // 共享投影优先，entry 快照只作未命中兜底。
      final state = container.read(postInteractionStateProvider);
      expect(
        state.likeCountFor(entry.postId, fallback: entry.likeCount),
        4,
      );
      expect(
        state.hasLikeStateFor(entry.postId)
            ? state.isLiked(entry.postId)
            : entry.isLiked,
        isTrue,
      );
    });

    test('关注在任意入口权威确认后回写共享投影，作者栏消费口径立即一致', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      // 联系人搜索/确认/通讯录/关注列表在权威回读后统一回写 setFollowing。
      container
          .read(userRelationshipStateProvider.notifier)
          .setFollowing('persona-1', true);

      // feed 卡片作者栏 / 沉浸式 / 主页的消费口径。
      expect(
        container.read(userRelationshipStateProvider).isFollowing('persona-1'),
        isTrue,
      );

      // 取关同样即时一致。
      container
          .read(userRelationshipStateProvider.notifier)
          .setFollowing('persona-1', false);
      expect(
        container.read(userRelationshipStateProvider).isFollowing('persona-1'),
        isFalse,
      );
    });
  });

  group('单一真相源静态契约（禁止第二副本回归）', () {
    test('discovery 状态不得再承载点赞/分享副本', () {
      final source = File(
        'lib/service/content_service/content/post/application/'
        'discovery_state_provider.dart',
      ).readAsStringSync();
      for (final banned in <String>[
        'likedPosts',
        'postLikesCount',
        'postSharesCount',
        'setLikeState',
        'toggleLike(',
        'incrementShares',
      ]) {
        expect(
          source.contains(banned),
          isFalse,
          reason: 'discovery_state_provider 重新引入了点赞/分享副本符号：$banned；'
              '互动事实唯一真相源是 postInteractionStateProvider',
        );
      }
    });

    test('媒体交互门面不得双写 discovery 副本', () {
      final source = File(
        'lib/runtime/di/media_viewer_interaction_facade.dart',
      ).readAsStringSync();
      expect(
        source.contains('discoveryStateProvider'),
        isFalse,
        reason: '媒体交互门面重新引入 discovery 双写；'
            '互动事实唯一真相源是 postInteractionStateProvider',
      );
    });

    test('关注直写页面必须回写共享关系投影', () {
      const writeThroughPages = <String>[
        'lib/service/user_service/relationship/persona_relationship/'
            'presentation/profile_stats_page_actions.dart',
        'lib/service/user_service/relationship/persona_relationship/'
            'presentation/contact_search_result_page.dart',
        'lib/service/user_service/relationship/persona_relationship/'
            'presentation/contact_confirm_page.dart',
        'lib/service/user_service/relationship/contact_discovery_record/'
            'presentation/phone_contacts_page.dart',
      ];
      for (final page in writeThroughPages) {
        final source = File(page).readAsStringSync();
        if (!source.contains('personaRelationshipCommandWriterProvider')) {
          continue;
        }
        expect(
          source.contains('userRelationshipStateProvider.notifier'),
          isTrue,
          reason: '$page 直写 PersonaRelationship 命令但未回写 '
              'userRelationshipStateProvider，跨页关注状态会漂移',
        );
      }
    });
  });
}
