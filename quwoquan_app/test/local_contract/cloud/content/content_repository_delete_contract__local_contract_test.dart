import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';

void main() {
  group('MockContentRepository 删除旅程契约 (T1/T2)', () {
    // 取一个「删除前 getPost 可读」的种子帖 id：直达兜底走 getPost，因此契约
    // 必须建立在 getPost 可读的帖上。
    Future<String> firstReadablePostId(MockContentRepository repo) async {
      for (final category in <String>['article', 'photo', 'video', 'moment']) {
        final posts = await repo.listDiscoveryFeed(
          category: category,
          limit: 8,
        );
        for (final post in posts) {
          try {
            await repo.getPost(postId: post.id);
            return post.id;
          } catch (_) {
            // feed 可见但详情不可读：跳过，继续找可读帖。
          }
        }
      }
      fail('seed feed 中应至少有一个 getPost 可读的帖');
    }

    test('deletePost 后 getPost 抛错（软删墓碑语义，与云侧一致）', () async {
      final repo = MockContentRepository();
      final postId = await firstReadablePostId(repo);

      // 删除前可读。
      final before = await repo.getPost(postId: postId);
      expect(before.post.id, postId);

      await repo.deletePost(postId: postId);

      // 删除后读取必须失败（呈现删除态/错误态，而非回退到旧内容）。
      await expectLater(
        repo.getPost(postId: postId),
        throwsA(
          isA<CloudException>()
              .having((e) => e.type, 'type', CloudErrorType.notFound)
              .having((e) => e.code, 'code', 'CONTENT.USER.post_not_found'),
        ),
      );
    });

    test('未知 postId 直接 getPost 抛错（直达兜底的错误态来源）', () async {
      final repo = MockContentRepository();
      await expectLater(
        repo.getPost(postId: 'definitely-missing-post-id'),
        throwsA(
          isA<CloudException>()
              .having((e) => e.type, 'type', CloudErrorType.notFound)
              .having((e) => e.code, 'code', 'CONTENT.USER.post_not_found'),
        ),
      );
    });

    test('空 id 删除是安全幂等空操作', () async {
      final repo = MockContentRepository();
      await repo.deletePost(postId: '');
      // 不影响既有可读帖。
      final postId = await firstReadablePostId(repo);
      final detail = await repo.getPost(postId: postId);
      expect(detail.post.id, postId);
    });
  });
}
