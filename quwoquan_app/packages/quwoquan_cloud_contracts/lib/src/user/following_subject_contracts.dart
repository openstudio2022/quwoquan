import 'user_operation_contracts.g.dart';

abstract interface class FollowingSubjectQuery {
  Future<FollowingSubjectSlice> listFollowingSubjects(
    ListFollowingSubjectsQuery query,
  );
}

abstract interface class FollowedSubjectVisitCommandWriter {
  Future<FollowedSubjectVisitResult> markFollowedSubjectVisited(
    MarkFollowedSubjectVisitedCommand command,
  );
}
