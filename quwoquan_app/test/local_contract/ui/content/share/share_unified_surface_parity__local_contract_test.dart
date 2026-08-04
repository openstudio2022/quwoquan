import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

ContentPostViewData _post({
  required String id,
  required String contentType,
  required String identity,
  required String authorId,
  required String displayName,
  String? title,
  String? body,
  String? coverUrl,
  List<String> mediaUrls = const <String>[],
  String? videoUrl,
  String? thumbnailUrl,
}) => ContentPostViewData.fromWire(
  ContentPostProjection(
    postId: id,
    contentType: contentType,
    contentIdentity: identity,
    authorId: authorId,
    authorDisplayName: displayName,
    authorAvatarUrl: '',
    title: title,
    body: body,
    coverUrl: coverUrl,
    mediaUrls: mediaUrls,
    videoUrl: videoUrl,
    thumbnailUrl: thumbnailUrl,
    likeCount: 0,
    commentCount: 0,
    shareCount: 0,
    createdAt: DateTime.utc(2026),
  ),
);

void main() {
  group('分享模板：统一 model 单路径产出 (D1b/T2)', () {
    void expectSurfaceTemplate(
      ContentPostViewData dto, {
      Map<String, dynamic>? wire,
    }) {
      final template = ContentShareTemplateBuilder.build(
        surfaceView: ContentSurfaceViewMapper.fromDto(dto, wire: wire),
        enableIdentityTemplate: true,
      );
      expect(
        template.shareTitle,
        isNotEmpty,
        reason: 'shareTitle 必须由 surfaceView 种子产出',
      );
      expect(template.coverUrl, isNotNull);
      expect(template.layout, isNotEmpty);
      expect(template.permission, 'public');
    }

    test('image 帖同源', () {
      expectSurfaceTemplate(
        _post(
          id: 'p1',
          contentType: 'image',
          identity: 'work',
          authorId: 'a1',
          displayName: '作者甲',
          body: '美图配文',
          mediaUrls: const <String>['https://img/1.jpg'],
          coverUrl: 'https://img/cover.jpg',
        ),
      );
    });

    test('video 帖同源', () {
      expectSurfaceTemplate(
        _post(
          id: 'video-post',
          contentType: 'video',
          identity: 'work',
          authorId: 'a2',
          displayName: '作者乙',
          body: '视频配文',
          videoUrl: 'https://v/1.mp4',
          thumbnailUrl: 'https://v/thumb.jpg',
        ),
      );
    });

    test('article 帖同源', () {
      expectSurfaceTemplate(
        _post(
          id: 'art1',
          contentType: 'article',
          identity: 'work',
          authorId: 'a3',
          displayName: '作者丙',
          title: '长文标题',
          body: '长文正文摘要内容',
          coverUrl: 'https://img/art-cover.jpg',
        ),
      );
    });

    test('micro 帖同源', () {
      expectSurfaceTemplate(
        _post(
          id: 'm1',
          contentType: 'micro',
          identity: 'moment',
          authorId: 'a4',
          displayName: '作者丁',
          body: '随手一条点滴',
        ),
      );
    });
  });
}
