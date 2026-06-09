import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/ui/user/models/creator_impact_summary.dart';

UserProfileStatsViewData _stats({
  int followers = 0,
  int likes = 0,
  int posts = 0,
  int circles = 0,
}) {
  return UserProfileStatsViewData(
    followingCount: 0,
    circleCount: circles,
    followerCount: followers,
    likeCount: likes,
    postCount: posts,
  );
}

void main() {
  group('CreatorImpactSummary', () {
    test('全为 0 时摘要为空，无占位事实', () {
      final summary = CreatorImpactSummary.fromStats(_stats());
      expect(summary.isEmpty, isTrue);
      expect(summary.facts, isEmpty);
      expect(summary.headline, isEmpty);
    });

    test('仅保留非 0 维度并按计数降序', () {
      final summary = CreatorImpactSummary.fromStats(
        _stats(followers: 12, likes: 480, posts: 0, circles: 3),
      );

      expect(summary.facts.length, 3);
      expect(summary.facts.first.category, CreatorImpactCategory.appreciation);
      expect(summary.facts.first.count, 480);
      expect(summary.facts.map((f) => f.count).toList(), <int>[480, 12, 3]);
      expect(
        summary.facts.any(
          (f) => f.category == CreatorImpactCategory.contribution,
        ),
        isFalse,
      );
    });

    test('headline 取计数最高事实的叙事', () {
      final summary = CreatorImpactSummary.fromStats(
        _stats(followers: 1200, likes: 30),
      );
      expect(summary.headline, summary.facts.first.narrative);
      expect(summary.headline, contains('1200'));
    });

    test('叙事携带真实计数', () {
      final summary = CreatorImpactSummary.fromStats(_stats(posts: 7));
      expect(summary.facts.single.count, 7);
      expect(summary.facts.single.narrative, contains('7'));
    });

    test('fromReadModel 聚合 rm_author_impact helpType 并按计数排序', () {
      final model = CreatorImpactReadModel.fromMap(<String, dynamic>{
        'authorId': 'author_1',
        'total': 5,
        'items': <Map<String, dynamic>>[
          <String, dynamic>{
            'helpType': 'relationship_help',
            'action': 'follow',
            'intersectionDimension': 'identity',
            'count': 2,
          },
          <String, dynamic>{
            'helpType': 'community_help',
            'action': 'join_circle',
            'intersectionDimension': 'interest',
            'count': 3,
          },
        ],
      });

      final summary = CreatorImpactSummary.fromReadModel(model);

      expect(summary.facts.length, 2);
      expect(summary.facts.first.category, CreatorImpactCategory.community);
      expect(summary.facts.first.count, 3);
      expect(summary.facts.last.category, CreatorImpactCategory.relationship);
      expect(summary.headline, contains('3'));
    });
  });
}
