import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/photo_post_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/video_post_dto.g.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';

void main() {
  group('PostSummaryView.fromDto', () {
    test('photo dto 的 body 会投影到 summary view', () {
      final dto = PhotoPostDto(
        id: 'photo-1',
        type: 'photo',
        identity: 'work',
        assistantUsePolicy: 'inherit',
        authorId: 'author-1',
        displayName: '作者',
        avatarUrl: 'https://example.com/avatar.jpg',
        body: '图片配文',
        coverUrl: 'https://example.com/cover.jpg',
        imageUrls: <String>['https://example.com/1.jpg'],
        likeCount: 1,
        commentCount: 2,
        favoriteCount: 3,
        shareCount: 4,
        createdAt: DateTime(2026, 3, 18),
      );

      final view = PostSummaryView.fromDto(dto);

      expect(view.body, '图片配文');
    });

    test('video dto 的 body 会投影到 summary view', () {
      final dto = VideoPostDto(
        id: 'video-1',
        type: 'video',
        identity: 'work',
        assistantUsePolicy: 'inherit',
        authorId: 'author-2',
        displayName: '作者',
        avatarUrl: 'https://example.com/avatar.jpg',
        body: '视频简介',
        videoUrl: 'https://example.com/video.mp4',
        thumbnailUrl: 'https://example.com/thumb.jpg',
        durationMs: 3200,
        likeCount: 5,
        commentCount: 6,
        favoriteCount: 7,
        shareCount: 8,
        createdAt: DateTime(2026, 3, 18),
      );

      final view = PostSummaryView.fromDto(dto);

      expect(view.body, '视频简介');
    });
  });
}
