import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_read_surface_id.g.dart';
import 'package:quwoquan_app/ui/content/post_read_projection_facade.dart';

void main() {
  group('PostReadProjectionFacade', () {
    test('presentationFor matches fromPostBase for feedCard', () {
      final dto = MomentPostDto.fromMap(<String, dynamic>{
        '_id': 'p1',
        'postId': 'p1',
        'type': 'moment',
        'contentType': 'micro',
        'authorId': 'a1',
        'authorProfileSubjectId': 'a1',
        'displayName': 'User',
        'authorAvatarUrl': '',
        'body': 'hello',
        'likeCount': 1,
        'commentCount': 2,
        'shareCount': 3,
        'favoriteCount': 0,
        'createdAt': '2026-01-01T00:00:00.000Z',
      });
      final pres = PostReadProjectionFacade.presentationFor(
        dto,
        PostReadSurfaceId.feedCard,
      );
      expect(pres.postId, 'p1');
      expect(pres.body, 'hello');
    });

    test('wire articleTemplate flows through immersive surface', () {
      final dto = ArticlePostDto.fromMap(<String, dynamic>{
        '_id': 'a1',
        'postId': 'a1',
        'type': 'article',
        'contentType': 'article',
        'authorId': 'u',
        'authorProfileSubjectId': 'u',
        'displayName': 'U',
        'authorAvatarUrl': '',
        'title': 'T',
        'body': 'B',
        'likeCount': 0,
        'commentCount': 0,
        'shareCount': 0,
        'favoriteCount': 0,
        'createdAt': '2026-01-01T00:00:00.000Z',
      });
      final pres = PostReadProjectionFacade.presentationFor(
        dto,
        PostReadSurfaceId.detailArticle,
        wire: <String, dynamic>{'articleTemplate': 'modern'},
      );
      expect(pres.articleTemplate, 'modern');
    });
  });

  group('PostReadUiBundle', () {
    test('fromPost carries surface', () {
      final dto = MomentPostDto.fromMap(<String, dynamic>{
        '_id': 'p1',
        'postId': 'p1',
        'type': 'moment',
        'contentType': 'micro',
        'authorId': 'a1',
        'authorProfileSubjectId': 'a1',
        'displayName': 'User',
        'authorAvatarUrl': '',
        'body': 'x',
        'likeCount': 0,
        'commentCount': 0,
        'shareCount': 0,
        'favoriteCount': 0,
        'createdAt': '2026-01-01T00:00:00.000Z',
      });
      final bundle = PostReadUiBundle.fromPost(
        dto,
        PostReadSurfaceId.searchCard,
      );
      expect(bundle.surface, PostReadSurfaceId.searchCard);
      expect(bundle.post.id, dto.id);
      expect(bundle.presentation.postId, dto.id);
    });
  });
}
