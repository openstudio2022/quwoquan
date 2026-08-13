import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_delete.dart'
    show contentPostDeleteIdempotencyKey;

import '../../../../../support/service/content_service/content/post/content_post_test_builder.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

InMemoryContentPostStore _store() {
  final post = contentPostViewDataBuilder(postId: 'delete-contract-post');
  return InMemoryContentPostStore(posts: [post]);
}

void main() {
  group('对象级删除 typed doubles', () {
    test('delete 后 detail reader 返回 410 墓碑语义', () async {
      final store = _store();
      final reader = InMemoryContentPostDetailReader(store);
      final writer = InMemoryContentPostDeleteCommandWriter(store);
      const postId = 'delete-contract-post';

      expect((await reader.getPost(postId: postId)).post.id, postId);
      final key = contentPostDeleteIdempotencyKey(postId);
      await writer.deletePost(postId: postId, idempotencyKey: key);
      await writer.deletePost(postId: postId, idempotencyKey: key);

      await expectLater(
        reader.getPost(postId: postId),
        throwsA(
          isA<CloudException>()
              .having((error) => error.statusCode, 'statusCode', 410)
              .having(
                (error) => error.code,
                'code',
                ContentErrorCode.contentDeleted.code,
              ),
        ),
      );
    });

    test('未知 postId 返回 canonical 404', () async {
      final reader = InMemoryContentPostDetailReader(
        InMemoryContentPostStore(),
      );

      await expectLater(
        reader.getPost(postId: 'definitely-missing-post-id'),
        throwsA(
          isA<CloudException>()
              .having((error) => error.type, 'type', CloudErrorType.notFound)
              .having(
                (error) => error.code,
                'code',
                ContentErrorCode.postNotFound.code,
              ),
        ),
      );
    });

    test('删除命令拒绝空 canonical 参数', () async {
      final writer = InMemoryContentPostDeleteCommandWriter(_store());

      await expectLater(
        writer.deletePost(postId: '', idempotencyKey: 'delete-empty-post'),
        throwsArgumentError,
      );
      await expectLater(
        writer.deletePost(postId: 'delete-contract-post', idempotencyKey: ''),
        throwsArgumentError,
      );
    });
  });
}
