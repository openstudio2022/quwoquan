import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show FollowedSubjectVisitResult, MarkFollowedSubjectVisitedCommand;

/// FollowedSubjectVisitState 对象公开的访问水位写入边界。
abstract interface class FollowedSubjectVisitStateWriter {
  Future<FollowedSubjectVisitResult> markFollowedSubjectVisited(
    MarkFollowedSubjectVisitedCommand command,
  );
}
