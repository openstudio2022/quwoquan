import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:test/test.dart';

void main() {
  test('alpha Post lifecycle fixture keeps create and publish on typed port', () async {
    final writer = AlphaContentPostLifecycleWriter();
    final created = await writer.createPost(
      CreateContentPostCommand(
        contentType: ContentPostType.micro,
        body: 'alpha typed post',
        visibility: ContentPostVisibility.public,
      ),
    );
    final published = await writer.publishPost(
      PublishContentPostCommand(
        postId: created.post.postId,
        visibility: ContentPostVisibility.public,
      ),
    );

    expect(published.post.postId, created.post.postId);
    expect(published.post.body, 'alpha typed post');
    expect(published.post.publishedAt, isNotNull);
  });
}
