import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_read_surface_id.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/cloud/runtime/models/post_read_presentation_mapper.dart';
import 'package:quwoquan_app/ui/content/models/post_read_ui_bundle.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

ContentPostViewData _post({
  required String id,
  required String contentType,
  required String authorId,
  required String displayName,
  String? title,
  required String body,
}) => ContentPostViewData.fromWire(
  ContentPostProjection(
    postId: id,
    contentType: contentType,
    contentIdentity: contentType == 'micro' ? 'moment' : 'work',
    authorId: authorId,
    authorDisplayName: displayName,
    authorAvatarUrl: '',
    title: title,
    body: body,
    likeCount: contentType == 'micro' ? 1 : 0,
    commentCount: contentType == 'micro' ? 2 : 0,
    shareCount: contentType == 'micro' ? 3 : 0,
    createdAt: DateTime.utc(2026),
  ),
);

void main() {
  // S2 内容投影单轨：PostReadProjectionFacade 已删除，投影统一经
  // PostReadPresentationMapper.fromViewData（DTO + wire 单一真相源）。
  group('PostReadPresentation single-rail projection', () {
    test('personaId 与 authorId 保持同一真相源', () {
      final dto = _post(
        id: 'p_canonical',
        contentType: 'micro',
        authorId: 'current_author',
        displayName: 'User',
        body: 'hello',
      );
      expect(dto.authorId, 'current_author');
      expect(dto.personaId, 'current_author');
    });

    test('fromPostBase 投射 feedCard 字段', () {
      final dto = _post(
        id: 'p1',
        contentType: 'micro',
        authorId: 'a1',
        displayName: 'User',
        body: 'hello',
      );
      final pres = PostReadPresentationMapper.fromViewData(dto);
      expect(pres.postId, 'p1');
      expect(pres.body, 'hello');
    });

    test('wire articleTemplate 经 fromPostBase 透传', () {
      final dto = _post(
        id: 'a1',
        contentType: 'article',
        authorId: 'u',
        displayName: 'U',
        title: 'T',
        body: 'B',
      );
      final pres = PostReadPresentationMapper.fromViewData(
        dto,
        wire: <String, dynamic>{'articleTemplate': 'modern'},
      );
      expect(pres.articleTemplate, 'modern');
    });
  });

  group('PostReadUiBundle', () {
    test('fromPost carries surface', () {
      final dto = _post(
        id: 'p1',
        contentType: 'micro',
        authorId: 'a1',
        displayName: 'User',
        body: 'x',
      );
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
