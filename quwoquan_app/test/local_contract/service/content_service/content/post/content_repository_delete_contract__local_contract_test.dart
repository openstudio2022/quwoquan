import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_delete.dart'
    show contentPostDeleteIdempotencyKey;
import '../../../../../support/service/content_service/content/post/mock_content_repository.dart';

void main() {
  group('MockContentRepository 删除旅程 local_contract', () {
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

    test('deletePost 后 getPost 返回 410 墓碑语义', () async {
      final repo = MockContentRepository();
      final postId = await firstReadablePostId(repo);

      // 删除前可读。
      final before = await repo.getPost(postId: postId);
      expect(before.post.id, postId);

      final idempotencyKey = contentPostDeleteIdempotencyKey(postId);
      await repo.deletePost(postId: postId, idempotencyKey: idempotencyKey);
      await repo.deletePost(postId: postId, idempotencyKey: idempotencyKey);

      // 删除后读取必须失败（呈现删除态/错误态，而非回退到旧内容）。
      await expectLater(
        repo.getPost(postId: postId),
        throwsA(
          isA<CloudException>()
              .having((e) => e.statusCode, 'statusCode', 410)
              .having(
                (e) => e.code,
                'code',
                ContentErrorCode.contentDeleted.code,
              ),
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
              .having(
                (e) => e.code,
                'code',
                ContentErrorCode.postNotFound.code,
              ),
        ),
      );
    });

    test('删除命令拒绝空 postId 或空 caller-owned idempotency key', () async {
      final repo = MockContentRepository();
      final postId = await firstReadablePostId(repo);
      await expectLater(
        repo.deletePost(postId: '', idempotencyKey: 'delete-empty-post'),
        throwsArgumentError,
      );
      await expectLater(
        repo.deletePost(postId: postId, idempotencyKey: ''),
        throwsArgumentError,
      );
    });
  });
}
