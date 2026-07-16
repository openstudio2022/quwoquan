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
    test('parses counts with aliases', () {
      final c = PostEngagementCounters.fromMap(<String, dynamic>{
        'likeCount': 3,
        'commentCount': 7,
        'shareCount': 2,
      });
      expect(c.likeCount, 3);
      expect(c.commentCount, 7);
      expect(c.shareCount, 2);
    });
  });
}
