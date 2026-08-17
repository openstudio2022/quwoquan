// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-004.t7
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

ContentPostViewData _post({
  required String id,
  required String contentType,
  required String authorId,
  required String displayName,
  String? title,
  required String body,
  String? summary,
  String articleTemplate = '',
  String articleFontPreset = '',
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
    summary: summary,
    articleTemplate: articleTemplate,
    articleFontPreset: articleFontPreset,
    likeCount: contentType == 'micro' ? 1 : 0,
    commentCount: contentType == 'micro' ? 2 : 0,
    shareCount: contentType == 'micro' ? 3 : 0,
    createdAt: DateTime.utc(2026),
  ),
);

void main() {
  group('ContentPostViewData canonical projection', () {
    test('personaId 与 authorId 保持同一真相源', () {
      final post = _post(
        id: 'p_canonical',
        contentType: 'micro',
        authorId: 'current_author',
        displayName: 'User',
        body: 'hello',
      );

      expect(post.authorId, 'current_author');
      expect(post.personaId, 'current_author');
    });

    test('canonical fields carry feed-card facts without a second DTO', () {
      final post = _post(
        id: 'p1',
        contentType: 'micro',
        authorId: 'a1',
        displayName: 'User',
        body: 'hello',
      );

      expect(post.id, 'p1');
      expect(post.normalizedBody, 'hello');
      expect(post.likeCount, 1);
      expect(post.commentCount, 2);
      expect(post.shareCount, 3);
    });

    test('article presentation fields come from canonical projection', () {
      final post = _post(
        id: 'a1',
        contentType: 'article',
        authorId: 'u',
        displayName: 'U',
        title: 'T',
        body: 'B',
        articleTemplate: 'modern',
        articleFontPreset: 'editorial',
      );

      expect(post.normalizedTitle, 'T');
      expect(post.normalizedBody, 'B');
      expect(post.articleTemplate, 'modern');
      expect(post.articleFontPreset, 'editorial');
    });

    test('article preview stays empty when canonical summary is absent', () {
      final post = _post(
        id: 'a_body_only',
        contentType: 'article',
        authorId: 'u',
        displayName: 'U',
        body: '正文承担无摘要文章的预览内容。',
      );

      expect(post.articlePreviewText, isEmpty);
    });

    test('article preview uses canonical summary instead of distinct body', () {
      final post = _post(
        id: 'a_summary',
        contentType: 'article',
        authorId: 'u',
        displayName: 'U',
        body: '# 详情正文',
        summary: '列表摘要',
      );

      expect(post.articlePreviewText, '列表摘要');
    });
  });
}
