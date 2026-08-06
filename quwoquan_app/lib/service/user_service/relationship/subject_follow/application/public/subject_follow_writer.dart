import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        FollowSubjectCommand,
        SubjectFollowCommandResult,
        UnfollowSubjectCommand;

/// SubjectFollow 对象的公开 set/unset 命令端口。
abstract interface class SubjectFollowWriter {
  Future<SubjectFollowCommandResult> follow(FollowSubjectCommand command);

  Future<SubjectFollowCommandResult> unfollow(UnfollowSubjectCommand command);
}
