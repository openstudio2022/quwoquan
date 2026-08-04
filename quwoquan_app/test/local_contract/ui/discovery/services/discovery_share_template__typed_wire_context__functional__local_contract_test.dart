import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/content/content/post/presentation/discovery_share_template.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'discovery share template uses only declared presentation wire fields',
    () {
      final template = buildDiscoveryShareTemplate(
        post: ContentPostViewData.fromWire(
          ContentPostProjection(
            postId: 'discovery-share-post',
            contentType: 'image',
            contentIdentity: 'work',
            authorId: 'author-1',
            authorDisplayName: '作者',
            authorAvatarUrl: '',
            body: '发现流分享正文',
            mediaUrls: const <String>['https://example.test/photo.jpg'],
            coverUrl: 'https://example.test/cover.jpg',
            likeCount: 0,
            commentCount: 0,
            shareCount: 0,
            createdAt: DateTime.utc(2026, 7, 15),
          ),
        ),
        enableIdentityTemplate: true,
        visibility: 'public',
        tags: const <String>['travel'],
      );

      expect(template.permission, 'public');
      expect(template.shareSummary, contains('#travel'));
    },
  );
}
