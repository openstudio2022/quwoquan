import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/providers/author_impact_provider.dart';
import 'package:quwoquan_app/ui/user/providers/my_intersection_inbox_provider.dart';

/// A2：Provider 级短时去重——同一会话内 rebuild / 重订阅不重复打服务
/// （backlog R-ID09 验收项④）。
void main() {
  group('myIntersectionPreviewProvider 短时去重', () {
    test('同一实例内重复 load 仅取数一次', () async {
      final repo = _CountingIntersectionRepository();
      final container = ProviderContainer(
        overrides: [intersectionRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final notifier = container.read(myIntersectionPreviewProvider.notifier);
      await notifier.load();
      await notifier.load();
      await notifier.load();

      expect(repo.listCalls, 1);
    });

    test('TTL 窗口内取消订阅再订阅复用结果，不重复取数', () async {
      final repo = _CountingIntersectionRepository();
      final container = ProviderContainer(
        overrides: [intersectionRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      // 首次挂载消费方：listen 保持订阅，触发首帧 build 的 keepAlive。
      final sub1 = container.listen(myIntersectionPreviewProvider, (_, _) {});
      await container.read(myIntersectionPreviewProvider.notifier).load();
      expect(repo.listCalls, 1);

      // 模拟卡片被销毁（push 进入详情）。keepAlive 在 TTL 内保活，状态不丢。
      sub1.close();

      // 模拟返回主页卡片重建：新的 initState 再次触发 load。
      final sub2 = container.listen(myIntersectionPreviewProvider, (_, _) {});
      addTearDown(sub2.close);
      await container.read(myIntersectionPreviewProvider.notifier).load();

      expect(repo.listCalls, 1);
    });

    test('force 显式刷新绕过去重', () async {
      final repo = _CountingIntersectionRepository();
      final container = ProviderContainer(
        overrides: [intersectionRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final notifier = container.read(myIntersectionPreviewProvider.notifier);
      await notifier.load();
      await notifier.load(force: true);

      expect(repo.listCalls, 2);
    });

    test('pending load 在 provider dispose 后完成时不写已释放 Ref', () async {
      final repo = _PendingIntersectionRepository();
      final container = ProviderContainer(
        overrides: [intersectionRepositoryProvider.overrideWithValue(repo)],
      );

      final loadFuture = container
          .read(myIntersectionPreviewProvider.notifier)
          .load();
      await Future<void>.delayed(Duration.zero);

      container.dispose();
      repo.completeList(const <IntersectionReason>[]);

      await expectLater(loadFuture, completes);
    });
  });

  group('authorImpactProvider 短时去重', () {
    test('TTL 窗口内重复读取仅触发一次 GetAuthorImpact', () async {
      final repo = _CountingUserProfileRepository();
      final container = ProviderContainer(
        overrides: [userProfileRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(authorImpactProvider('u_demo').future);
      // 无监听者：若非 keepAlive，autoDispose 会销毁并在二次读取时重新取数。
      await container.read(authorImpactProvider('u_demo').future);
      await container.read(authorImpactProvider('u_demo').future);

      expect(repo.impactCalls['u_demo'], 1);
    });

    test('不同 userId 各自取数互不串用', () async {
      final repo = _CountingUserProfileRepository();
      final container = ProviderContainer(
        overrides: [userProfileRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(authorImpactProvider('u_a').future);
      await container.read(authorImpactProvider('u_b').future);

      expect(repo.impactCalls['u_a'], 1);
      expect(repo.impactCalls['u_b'], 1);
    });
  });
}

class _CountingIntersectionRepository implements IntersectionRepository {
  int listCalls = 0;

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return IntersectionInboxSummary(totalCount: 0, totalNewCount: 0);
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) async {
    listCalls += 1;
    return const <IntersectionReason>[];
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {}

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}

class _PendingIntersectionRepository extends _CountingIntersectionRepository {
  final Completer<List<IntersectionReason>> _listCompleter =
      Completer<List<IntersectionReason>>();

  void completeList(List<IntersectionReason> items) {
    _listCompleter.complete(items);
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) {
    listCalls += 1;
    return _listCompleter.future;
  }
}

class _CountingUserProfileRepository extends MockUserProfileRepository {
  _CountingUserProfileRepository() : super();

  final Map<String, int> impactCalls = <String, int>{};

  @override
  Future<AuthorImpactSummary> getAuthorImpact(String userId) async {
    impactCalls[userId] = (impactCalls[userId] ?? 0) + 1;
    return AuthorImpactSummary(
      authorId: userId,
      total: 0,
      items: const <AuthorImpactItem>[],
    );
  }
}
