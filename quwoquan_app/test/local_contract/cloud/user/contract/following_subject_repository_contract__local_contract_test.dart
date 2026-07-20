import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

void main() {
  group('FollowingSubject contract', () {
    test('metadata exposes required list and mark visited APIs', () {
      expect(
        UserApiMetadata.operationToPathTemplate['ListFollowingSubjects'],
        equals('/user/following-subjects'),
      );
      expect(
        UserApiMetadata.operationToPathTemplate['MarkFollowedSubjectVisited'],
        equals(
          '/user/followed-subjects/{subjectType}/{subjectId}:mark-visited',
        ),
      );
      expect(
        UserApiMetadata.operationToAuthMode['ListFollowingSubjects'],
        equals('required'),
      );
      expect(
        UserApiMetadata.operationToAuthMode['MarkFollowedSubjectVisited'],
        equals('required'),
      );
      expect(
        UserRequestPageIds.listFollowingSubjects,
        equals('user.list.following.subjects'),
      );
      expect(
        UserRequestPageIds.markFollowedSubjectVisited,
        equals('user.mark.followed.subject.visited'),
      );
    });

    test('alpha typed facet 包含 user、circle 与 homepage 状态', () async {
      final facet = AlphaFollowingSubjectFacet();
      final slice = await facet.listFollowingSubjects(
        const ListFollowingSubjectsQuery(limit: 20),
      );
      final items = slice.items;

      expect(items.map((e) => e.subjectType).toSet(), {
        'user',
        'circle',
        'homepage',
      });
      expect(
        items.where((item) => item.hasUnreadChanges),
        isNotEmpty,
        reason: 'fixture 应包含上次访问后变化样例',
      );
      expect(
        items.every((item) => item.targetObjectId.isNotEmpty),
        isTrue,
        reason: '三类对象都必须能跳转到目标主页',
      );
    });

    test('typed visit command 清除未读并可由 query 回读', () async {
      final facet = AlphaFollowingSubjectFacet();
      final before = await facet.listFollowingSubjects(
        const ListFollowingSubjectsQuery(limit: 20),
      );
      final target = before.items.firstWhere((item) => item.hasUnreadChanges);
      final visitedAt = DateTime.utc(2026, 7, 20, 8);

      final result = await facet.markFollowedSubjectVisited(
        MarkFollowedSubjectVisitedCommand(
          subjectId: target.subjectId,
          subjectType: target.subjectType,
          visitedAt: visitedAt,
          clientRequestId: 'visit-contract-1',
        ),
      );
      final after = await facet.listFollowingSubjects(
        const ListFollowingSubjectsQuery(limit: 20),
      );
      final updated = after.items.firstWhere(
        (item) =>
            item.subjectId == target.subjectId &&
            item.subjectType == target.subjectType,
      );

      expect(result.hasUnreadChanges, isFalse);
      expect(updated.hasUnreadChanges, isFalse);
      expect(updated.unreadChangeCount, equals(0));
      expect(result.lastVisitedAt, visitedAt);
      expect(updated.lastVisitedAt, visitedAt);
    });
  });
}
