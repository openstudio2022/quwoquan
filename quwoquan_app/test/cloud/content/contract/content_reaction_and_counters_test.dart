import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_reaction_state.dart';
import 'package:quwoquan_app/cloud/runtime/models/post_engagement_counters.dart';

void main() {
  group('ContentReactionState.fromMap', () {
    test('parses liked/favorited and postId', () {
      final s = ContentReactionState.fromMap(<String, dynamic>{
        'postId': 'p1',
        'userId': 'u1',
        'liked': true,
        'favorited': false,
      });
      expect(s.postId, 'p1');
      expect(s.userId, 'u1');
      expect(s.liked, isTrue);
      expect(s.favorited, isFalse);
    });
  });

  group('PostEngagementCounters.fromMap', () {
    test('parses counts with aliases', () {
      final c = PostEngagementCounters.fromMap(<String, dynamic>{
        'likeCount': 3,
        'commentCount': 7,
        'favoriteCount': 1,
        'shareCount': 2,
      });
      expect(c.likeCount, 3);
      expect(c.commentCount, 7);
      expect(c.favoriteCount, 1);
      expect(c.shareCount, 2);
    });
  });
}
