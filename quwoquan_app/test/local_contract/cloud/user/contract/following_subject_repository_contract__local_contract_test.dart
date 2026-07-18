import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/user/following_subject_repository.dart';

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

    test('mock seed includes user, circle and homepage unread states', () async {
      final repo = MockFollowingSubjectRepository();
      final items = await repo.listFollowingSubjects();

      expect(items.map((e) => e.subjectType).toSet(), {
        FollowingSubjectType.user,
        FollowingSubjectType.circle,
        FollowingSubjectType.homepage,
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

    test('mark visited clears unread flag in mock repository', () async {
      final repo = MockFollowingSubjectRepository();
      final before = await repo.listFollowingSubjects();
      final target = before.firstWhere((item) => item.hasUnreadChanges);

      final result = await repo.markFollowingSubjectVisited(subject: target);
      final after = await repo.listFollowingSubjects();
      final updated = after.firstWhere(
        (item) =>
            item.subjectId == target.subjectId &&
            item.subjectType == target.subjectType,
      );

      expect(result.hasUnreadChanges, isFalse);
      expect(updated.hasUnreadChanges, isFalse);
      expect(updated.unreadChangeCount, equals(0));
      expect(updated.lastVisitedAt, isNotEmpty);
    });
  });
}
