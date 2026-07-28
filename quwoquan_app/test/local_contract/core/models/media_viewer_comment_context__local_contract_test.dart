import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';

void main() {
  group('MediaViewerCommentContext 单一方言', () {
    Map<String, String> workBrowserQuery({
      required String entrySource,
      String? targetCommentId,
      String? targetParentCommentId,
      String? targetReplyId,
      String? replyToCommentId,
    }) {
      return Uri.parse(
        AppRoutePaths.workBrowser(
          workId: 'post_1',
          openComments: 'true',
          commentEntrySource: entrySource,
          targetCommentId: targetCommentId,
          targetParentCommentId: targetParentCommentId,
          targetReplyId: targetReplyId,
          replyToCommentId: replyToCommentId,
        ),
      ).queryParameters;
    }

    test('generated workBrowser route：一级评论目标只产出 targetCommentId', () {
      final query = workBrowserQuery(
        entrySource: MediaViewerCommentContext.entrySourceProfileInteraction,
        targetCommentId: 'comment_top_1',
      );

      expect(query, <String, String>{
        MediaViewerCommentContext.queryOpenComments: 'true',
        MediaViewerCommentContext.queryEntrySource: 'profile-interaction',
        MediaViewerCommentContext.queryTargetCommentId: 'comment_top_1',
      });
      // 一级目标不带父/回复键，杜绝旧的 commentId/parentCommentId。
      expect(
        query.containsKey(MediaViewerCommentContext.queryTargetReplyId),
        isFalse,
      );
      expect(query.containsKey('commentId'), isFalse);
      expect(query.containsKey('parentCommentId'), isFalse);
      expect(query.containsKey('targetKind'), isFalse);
    });

    test(
      'generated workBrowser route：二级回复目标产出 targetParentCommentId+targetReplyId',
      () {
        final query = workBrowserQuery(
          entrySource: MediaViewerCommentContext.entrySourceProfileComments,
          targetParentCommentId: 'parent_1',
          targetReplyId: 'reply_9',
          replyToCommentId: 'reply_9',
        );

        expect(query, <String, String>{
          MediaViewerCommentContext.queryOpenComments: 'true',
          MediaViewerCommentContext.queryEntrySource: 'profile-comments',
          MediaViewerCommentContext.queryTargetParentCommentId: 'parent_1',
          MediaViewerCommentContext.queryTargetReplyId: 'reply_9',
          MediaViewerCommentContext.queryReplyToCommentId: 'reply_9',
        });
        expect(
          query.containsKey(MediaViewerCommentContext.queryTargetCommentId),
          isFalse,
        );
      },
    );

    test('两个入口同方言：相同逻辑目标 → 相同 target* 键值（仅 entrySource 区分）', () {
      // 我的互动 tab：回复目标 = (parent_1, reply_9)
      final interactionQuery = workBrowserQuery(
        entrySource: MediaViewerCommentContext.entrySourceProfileInteraction,
        targetParentCommentId: 'parent_1',
        targetReplyId: 'reply_9',
      );
      // 我的评论页：同一回复目标，附带回复态。
      final commentsQuery = workBrowserQuery(
        entrySource: MediaViewerCommentContext.entrySourceProfileComments,
        targetParentCommentId: 'parent_1',
        targetReplyId: 'reply_9',
      );

      // 除 entrySource 外，定位键完全一致。
      Map<String, String> withoutSource(Map<String, String> q) => {
        for (final entry in q.entries)
          if (entry.key != MediaViewerCommentContext.queryEntrySource)
            entry.key: entry.value,
      };
      expect(withoutSource(interactionQuery), withoutSource(commentsQuery));
    });

    test('fromQueryParameters：解析一级评论 canonical 方言', () {
      final context = MediaViewerCommentContext.fromQueryParameters(
        workBrowserQuery(
          entrySource: MediaViewerCommentContext.entrySourceProfileInteraction,
          targetCommentId: 'comment_top_1',
        ),
      );

      expect(context.openComments, isTrue);
      expect(context.targetCommentId, 'comment_top_1');
      expect(context.targetParentCommentId, isNull);
      expect(context.targetReplyId, isNull);
      expect(context.entrySource, 'profile-interaction');
      expect(context.usesProfileInteractionMode, isTrue);
      expect(context.shouldOpen, isTrue);
    });

    test('fromQueryParameters：解析二级回复 canonical 方言', () {
      final context = MediaViewerCommentContext.fromQueryParameters(
        workBrowserQuery(
          entrySource: MediaViewerCommentContext.entrySourceProfileComments,
          targetParentCommentId: 'parent_1',
          targetReplyId: 'reply_9',
          replyToCommentId: 'reply_9',
        ),
      );

      expect(context.openComments, isTrue);
      expect(context.targetParentCommentId, 'parent_1');
      expect(context.targetReplyId, 'reply_9');
      expect(context.replyToCommentId, 'reply_9');
      expect(context.targetCommentId, isNull);
      expect(context.entrySource, 'profile-comments');
      // 我的评论页深链也必须落到 profileInteraction mode（口径与互动 tab 一致）。
      expect(context.usesProfileInteractionMode, isTrue);
    });

    test('两类个人页入口都解析为 profileInteraction mode', () {
      for (final source in <String>[
        MediaViewerCommentContext.entrySourceProfileInteraction,
        MediaViewerCommentContext.entrySourceProfileComments,
      ]) {
        final context = MediaViewerCommentContext.fromQueryParameters(
          workBrowserQuery(entrySource: source, targetCommentId: 'comment_x'),
        );
        expect(context.usesProfileInteractionMode, isTrue, reason: source);
      }
    });

    test('非个人页 / 未知入口不落 profileInteraction mode', () {
      final context =
          MediaViewerCommentContext.fromQueryParameters(const <String, String>{
            'openComments': 'true',
            'commentEntrySource': 'feed-card',
            'targetCommentId': 'comment_x',
          });
      expect(context.usesProfileInteractionMode, isFalse);
    });

    test('空 query 不应误触发评论分屏', () {
      final context = MediaViewerCommentContext.fromQueryParameters(
        const <String, String>{},
      );

      expect(context.openComments, isFalse);
      expect(context.targetCommentId, isNull);
      expect(context.targetParentCommentId, isNull);
      expect(context.targetReplyId, isNull);
      expect(context.replyToCommentId, isNull);
      expect(context.shouldOpen, isFalse);
      expect(context.usesProfileInteractionMode, isFalse);
    });

    test('Router 将 metadata 声明的 workBrowser query 交给 typed context', () {
      final routerSource = File(
        'lib/app/navigation/app_router.dart',
      ).readAsStringSync();
      expect(
        routerSource,
        contains('MediaViewerCommentContext.fromQueryParameters('),
      );
      expect(
        routerSource,
        contains('commentContext: commentContext'),
        reason:
            'the workBrowser Router branch must pass its parsed context to the '
            'direct-entry page and preloaded immersive viewer.',
      );
    });

    test('comment deep links use the generated workBrowser builder', () {
      for (final path in <String>[
        'lib/ui/user/utils/profile_comment_detail_route.dart',
        'lib/cloud/services/notification/app_message_navigation.dart',
      ]) {
        final source = File(path).readAsStringSync();
        expect(source, contains('AppRoutePaths.workBrowser('));
        expect(source, isNot(contains('Uri.parse(')));
        expect(source, isNot(contains('.replace(')));
      }
    });
  });
}
