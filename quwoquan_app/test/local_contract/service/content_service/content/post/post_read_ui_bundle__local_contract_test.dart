// spec_ref: specs/feature-tree/discovery-content/content-type-framework/unified-presentation-model/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_projection_codec.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_projection_mapper.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/post_read_ui_bundle.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/post_read_surface_id.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

ContentPostViewData _post({
  required String id,
  required String contentType,
  required String authorId,
  required String displayName,
  String? title,
  required String body,
  String? articleTemplate,
  String? articleFontPreset,
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
    articleTemplate: articleTemplate,
    articleFontPreset: articleFontPreset,
    likeCount: contentType == 'micro' ? 1 : 0,
    commentCount: contentType == 'micro' ? 2 : 0,
    shareCount: contentType == 'micro' ? 3 : 0,
    createdAt: DateTime.utc(2026),
  ),
);

void main() {
  group('ContentPostProjection single-rail presentation', () {
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

    test('generated projection mapper 投射 feedCard 字段', () {
      final dto = _post(
        id: 'p1',
        contentType: 'micro',
        authorId: 'a1',
        displayName: 'User',
        body: 'hello',
      );
      expect(dto.id, 'p1');
      expect(dto.normalizedBody, 'hello');
    });

    test('codec 与 mapper 对 article presentation 字段单轨往返', () {
      final source = _post(
        id: 'a1',
        contentType: 'article',
        authorId: 'u',
        displayName: 'U',
        title: 'T',
        body: 'B',
        articleTemplate: 'modern',
        articleFontPreset: 'serif',
      );
      final encoded = contentPostProjectionFromViewData(source);
      final decoded = const ContentPostProjectionMapper().toDto(
        ContentPostProjection.fromWire(encoded.toWire()),
      );

      expect(decoded.id, 'a1');
      expect(decoded.normalizedTitle, 'T');
      expect(decoded.normalizedBody, 'B');
      expect(decoded.articleTemplate, 'modern');
      expect(decoded.articleFontPreset, 'serif');
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
      expect(bundle.presentation, same(dto));
    });
  });
}
