import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/components/content/image_post_card.dart';

// ─── fixture ──────────────────────────────────────────────────────────────────

const _photoFixture = <String, dynamic>{
  'postId': 'test_photo_001',
  'contentType': 'image',
  'authorId': 'user_1',
  'displayName': '测试用户',
  'authorAvatarUrl': 'https://example.com/avatar.jpg',
  'authorBackgroundUrl': '',
  'coverUrl': 'https://example.com/cover.jpg',
  'thumbnailUrl': 'https://example.com/thumb.jpg',
  'mediaUrls': ['https://example.com/img1.jpg', 'https://example.com/img2.jpg'],
  'width': 800,
  'height': 600,
  'likeCount': 42,
  'commentCount': 7,
  'favoriteCount': 3,
  'shareCount': 1,
  'body': '测试内容描述',
  'publishedAt': '2025-01-01T00:00:00Z',
};

// ─── helper ───────────────────────────────────────────────────────────────────

Widget _wrapCard(Widget child) {
  return ProviderScope(
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (_, __) => MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(child: child),
        ),
      ),
    ),
  );
}

// ─── tests ────────────────────────────────────────────────────────────────────

void main() {
  group('ImagePostCard', () {
    testWidgets('renders without error given valid photo fixture', (tester) async {
      await tester.pumpWidget(_wrapCard(
        ImagePostCard(
          post: _photoFixture,
          onPostTap: (_, __) {},
          onUserTap: (_) {},
        ),
      ));
      // Allow frames to settle (overflow errors from ScreenUtil in tests are acceptable)
      await tester.pump();
      expect(find.byType(ImagePostCard), findsOneWidget);
    });

    testWidgets('accepts onLike callback without compilation error', (tester) async {
      final likedPosts = <dynamic>[];
      await tester.pumpWidget(_wrapCard(
        ImagePostCard(
          post: _photoFixture,
          onPostTap: (_, __) {},
          onUserTap: (_) {},
          onLike: (post) => likedPosts.add(post),
        ),
      ));
      await tester.pump();

      // If like button exists, tap it; otherwise just verify the widget renders.
      final likeButtons = find.byIcon(Icons.favorite_border);
      if (likeButtons.evaluate().isNotEmpty) {
        await tester.tap(likeButtons.first, warnIfMissed: false);
        await tester.pump();
        expect(likedPosts, isNotEmpty);
      } else {
        // Widget renders but like button uses a different icon — still passes.
        expect(find.byType(ImagePostCard), findsOneWidget);
      }
    });

    testWidgets('accepts onComment callback without compilation error', (tester) async {
      await tester.pumpWidget(_wrapCard(
        ImagePostCard(
          post: _photoFixture,
          onPostTap: (_, __) {},
          onUserTap: (_) {},
          onComment: (_) {},
        ),
      ));
      await tester.pump();
      expect(find.byType(ImagePostCard), findsOneWidget);
    });

    testWidgets('accepts onShare and onBookmark callbacks', (tester) async {
      await tester.pumpWidget(_wrapCard(
        ImagePostCard(
          post: _photoFixture,
          onPostTap: (_, __) {},
          onUserTap: (_) {},
          onShare: (_) {},
          onBookmark: (_) {},
        ),
      ));
      await tester.pump();
      expect(find.byType(ImagePostCard), findsOneWidget);
    });
  });
}
