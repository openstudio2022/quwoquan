import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';

void main() {
  group('MediaViewerCommentContext.fromQueryParameters', () {
    test('会解析 work browser 评论直达 query', () {
      final context = MediaViewerCommentContext.fromQueryParameters({
        'openComments': 'true',
        'commentId': 'comment-1',
        'parentCommentId': 'parent-1',
        'replyToCommentId': 'reply-1',
      });

      expect(context.openComments, isTrue);
      expect(context.commentId, 'comment-1');
      expect(context.parentCommentId, 'parent-1');
      expect(context.replyToCommentId, 'reply-1');
      expect(context.shouldOpen, isTrue);
    });

    test('空 query 不应误触发评论分屏', () {
      final context = MediaViewerCommentContext.fromQueryParameters(
        const <String, String>{},
      );

      expect(context.openComments, isFalse);
      expect(context.commentId, isNull);
      expect(context.parentCommentId, isNull);
      expect(context.replyToCommentId, isNull);
      expect(context.shouldOpen, isFalse);
    });
  });
}
