import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/footprint_repository.dart';

import '../../../../../support/service/content_service/content/post/content_footprint_typed_double.dart';
import '../../../../../support/service/content_service/content/post/content_post_test_builder.dart';

InMemoryFootprintRepository _repository() {
  final post = contentPostViewDataBuilder(postId: 'footprint-post');
  FootprintTestEntry entry(String type, String action, int hour) {
    return FootprintTestEntry(
      type: type,
      entry: FootprintEntry(
        postId: post.id,
        action: action,
        occurredAt: DateTime.utc(2026, 1, 1, hour).toIso8601String(),
        post: post,
      ),
    );
  }

  return InMemoryFootprintRepository(
    entries: <FootprintTestEntry>[
      entry('viewed', 'click', 10),
      entry('viewed', 'content_depth', 9),
      entry('liked', 'like', 8),
      entry('commented', 'comment', 7),
      entry('shared', 'share', 6),
    ],
  );
}

void main() {
  group('InMemoryFootprintRepository 契约', () {
    test('返回 suite 显式输入的五条 typed 足迹', () async {
      final page = await _repository().getMyFootprint();

      expect(page.items, hasLength(5));
      expect(page.nextCursor, isNull);
      for (final entry in page.items) {
        expect(entry.postId, 'footprint-post');
        expect(entry.action, isNotEmpty);
        expect(DateTime.tryParse(entry.occurredAt), isNotNull);
        expect(entry.post, isNotNull);
      }
    });

    test('type 过滤不解释 action 语义', () async {
      final repo = _repository();
      expect((await repo.getMyFootprint(type: 'viewed')).items, hasLength(2));
      expect((await repo.getMyFootprint(type: 'liked')).items, hasLength(1));
      expect((await repo.getMyFootprint(type: 'unknown_type')).items, isEmpty);
    });

    test('cursor 分页窗口完整且不重复', () async {
      final repo = _repository();
      final first = await repo.getMyFootprint(limit: 2);
      final second = await repo.getMyFootprint(
        cursor: first.nextCursor,
        limit: 10,
      );

      expect(first.items, hasLength(2));
      expect(second.items, hasLength(3));
      final allIds = <String>[
        for (final entry in first.items) '${entry.postId}/${entry.action}',
        for (final entry in second.items) '${entry.postId}/${entry.action}',
      ];
      expect(allIds.toSet(), hasLength(5));
    });
  });
}
