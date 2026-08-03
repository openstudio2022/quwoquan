import 'user_operation_contracts.g.dart';

abstract interface class SubjectFollowCommandWriter {
  Future<SubjectFollowCommandResult> follow(FollowSubjectCommand command);
  Future<SubjectFollowCommandResult> unfollow(UnfollowSubjectCommand command);
}
