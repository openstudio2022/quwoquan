import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show FollowingSubjectSlice, ListFollowingSubjectsQuery;

/// FollowingSubject 对象公开的关注主体读取边界。
abstract interface class FollowingSubjectReader {
  Future<FollowingSubjectSlice> listFollowingSubjects(
    ListFollowingSubjectsQuery query,
  );
}
