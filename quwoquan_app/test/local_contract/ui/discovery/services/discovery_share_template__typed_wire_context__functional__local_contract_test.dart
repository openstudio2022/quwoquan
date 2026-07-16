import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_presentation_wire.dart';
import 'package:quwoquan_app/ui/discovery/services/discovery_share_template.dart';

void main() {
  test(
    'discovery share template uses only declared presentation wire fields',
    () {
      final template = buildDiscoveryShareTemplate(
        post: PhotoPostDto.fromMap(<String, dynamic>{
          '_id': 'discovery-share-post',
          'postId': 'discovery-share-post',
          'type': 'photo',
          'contentType': 'image',
          'identity': 'work',
          'authorId': 'author-1',
          'displayName': '作者',
          'authorAvatarUrl': '',
          'body': '发现流分享正文',
          'imageUrls': <String>['https://example.test/photo.jpg'],
          'coverUrl': 'https://example.test/cover.jpg',
          'likeCount': 0,
          'commentCount': 0,
          'shareCount': 0,
          'createdAt': '2026-07-15T00:00:00Z',
        }),
        wire: const DiscoveryPresentationWire(<String, dynamic>{
          'visibility': 'public',
          'tagRefs': <String>['travel'],
          'circleName': 'uncontracted-circle',
        }),
        enableIdentityTemplate: true,
      );

      expect(template.permission, 'public');
      expect(template.shareSummary, contains('#travel'));
      expect(template.shareSummary, isNot(contains('uncontracted-circle')));
    },
  );
}
