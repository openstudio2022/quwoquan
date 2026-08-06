import 'package:flutter_test/flutter_test.dart';
import '../../../../../support/service/content_service/content/post/mock_content_repository.dart';

/// 我的足迹 · Mock 契约（T1/T2）：
/// - fixture footprint_core 单一真相源（5 条：viewed×2 / liked / commented / shared）。
/// - type 过滤透传云侧枚举字符串，端侧不解析 action 语义。
/// - cursor 分页 offset 语义：窗口拼接完整且不重复。
/// - postRef join content_discovery_core.posts：足迹不复制第二套内容数据。
void main() {
  group('MockFootprintRepository 契约', () {
    test('默认全量返回 fixture 5 条，并 join 出 post 内容', () async {
      final repo = MockFootprintRepository();
      final page = await repo.getMyFootprint();

      expect(page.items, hasLength(5));
      expect(page.nextCursor, isNull);
      for (final entry in page.items) {
        expect(entry.postId, isNotEmpty);
        expect(entry.action, isNotEmpty);
        expect(DateTime.tryParse(entry.occurredAt), isNotNull);
        expect(
          entry.post,
          isNotNull,
          reason: '${entry.postId} 应能 join 到 content_discovery_core 内容',
        );
      }
    });

    test('type 过滤：viewed 2 条，liked/commented/shared 各 1 条', () async {
      final repo = MockFootprintRepository();
      expect((await repo.getMyFootprint(type: 'viewed')).items, hasLength(2));
      expect((await repo.getMyFootprint(type: 'liked')).items, hasLength(1));
      expect(
        (await repo.getMyFootprint(type: 'commented')).items,
        hasLength(1),
      );
      expect((await repo.getMyFootprint(type: 'shared')).items, hasLength(1));
    });

    test('未知 type 返回空列表（端侧不解释枚举语义，不抛错）', () async {
      final repo = MockFootprintRepository();
      final page = await repo.getMyFootprint(type: 'unknown_type');
      expect(page.items, isEmpty);
      expect(page.nextCursor, isNull);
    });

    test('cursor 分页：窗口拼接完整且不重复', () async {
      final repo = MockFootprintRepository();
      final first = await repo.getMyFootprint(limit: 2);
      expect(first.items, hasLength(2));
      expect(first.nextCursor, isNotNull);

      final second = await repo.getMyFootprint(
        cursor: first.nextCursor,
        limit: 10,
      );
      expect(second.items, hasLength(3));
      expect(second.nextCursor, isNull);

      final allIds = <String>[
        for (final e in first.items) '${e.postId}/${e.action}',
        for (final e in second.items) '${e.postId}/${e.action}',
      ];
      expect(allIds.toSet(), hasLength(5), reason: '分页窗口不得重复或丢条目');
    });
  });
}
