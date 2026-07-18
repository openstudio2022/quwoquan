import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_reaction_state.dart';
import 'package:quwoquan_app/cloud/runtime/models/post_engagement_counters.dart';

void main() {
  group('ContentReactionState.fromMap', () {
    test('parses liked and postId', () {
      final s = ContentReactionState.fromMap(<String, dynamic>{
        'found': true,
        'postId': 'p1',
        'liked': true,
        'version': 3,
      });
      expect(s.postId, 'p1');
      expect(s.found, isTrue);
      expect(s.liked, isTrue);
      expect(s.version, 3);
    });

    test('rejects retired mixed reaction/share aliases', () {
      expect(
        () => ContentReactionState.fromMap(<String, dynamic>{
          'found': true,
          'postId': 'p1',
          'liked': true,
          'version': 1,
          'shared': true,
        }),
        throwsFormatException,
      );
    });
  });

  group('PostEngagementCounters.fromMap', () {
    test('只解析 canonical 计数字段并拒绝 aliases', () {
      final canonical = PostEngagementCounters.fromMap(<String, dynamic>{
        'likeCount': 3,
        'commentCount': 7,
        'shareCount': 2,
      });
      final retired = PostEngagementCounters.fromMap(<String, dynamic>{
        'likesCount': 30,
        'commentsCount': 70,
        'shares': 20,
      });
      expect(canonical.likeCount, 3);
      expect(canonical.commentCount, 7);
      expect(canonical.shareCount, 2);
      expect(retired.likeCount, 0);
      expect(retired.commentCount, 0);
      expect(retired.shareCount, 0);
    });
  });
}
