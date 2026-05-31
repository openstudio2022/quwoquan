import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/post_read_ui_bundle.dart';

void main() {
  // S2 内容投影单轨：PostReadProjectionFacade 已删除，投影统一经
  // PostReadPresentation.fromPostBase（DTO + wire 单一真相源）。
  group('PostReadPresentation single-rail projection', () {
    test('subAccountId 与 authorId 保持同一真相源', () {
      final dto = MicroPostDto.fromMap(<String, dynamic>{
        '_id': 'p_canonical',
        'postId': 'p_canonical',
        'type': 'micro',
        'contentType': 'micro',
        'authorId': 'current_author',
        'displayName': 'User',
        'authorAvatarUrl': '',
        'body': 'hello',
        'likeCount': 1,
        'commentCount': 2,
        'shareCount': 3,
        'favoriteCount': 0,
        'createdAt': '2026-01-01T00:00:00.000Z',
      });
      expect(dto.authorId, 'current_author');
      expect(dto.subAccountId, 'current_author');
    });

    test('fromPostBase 投射 feedCard 字段', () {
      final dto = MicroPostDto.fromMap(<String, dynamic>{
        '_id': 'p1',
        'postId': 'p1',
        'type': 'micro',
        'contentType': 'micro',
        'authorId': 'a1',
        'displayName': 'User',
        'authorAvatarUrl': '',
        'body': 'hello',
        'likeCount': 1,
        'commentCount': 2,
        'shareCount': 3,
        'favoriteCount': 0,
        'createdAt': '2026-01-01T00:00:00.000Z',
      });
      final pres = PostReadPresentation.fromPostBase(dto);
      expect(pres.postId, 'p1');
      expect(pres.body, 'hello');
    });

    test('wire articleTemplate 经 fromPostBase 透传', () {
      final dto = ArticlePostDto.fromMap(<String, dynamic>{
        '_id': 'a1',
        'postId': 'a1',
        'type': 'article',
        'contentType': 'article',
        'authorId': 'u',
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
      final pres = PostReadPresentation.fromPostBase(
        dto,
        wire: <String, dynamic>{'articleTemplate': 'modern'},
      );
      expect(pres.articleTemplate, 'modern');
    });
  });

  group('PostReadUiBundle', () {
    test('fromPost carries surface', () {
      final dto = MicroPostDto.fromMap(<String, dynamic>{
        '_id': 'p1',
        'postId': 'p1',
        'type': 'micro',
        'contentType': 'micro',
        'authorId': 'a1',
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
