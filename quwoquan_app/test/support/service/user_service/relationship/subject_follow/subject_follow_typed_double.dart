import 'package:quwoquan_app/service/user_service/relationship/subject_follow/application/public/subject_follow_writer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 测试期内存 SubjectFollow facet：set/unset 幂等，与 user.SubjectFollow
/// 聚合语义同构（重复 follow 返回 idempotentReplay）。
final class SubjectFollowTypedDouble implements SubjectFollowWriter {
  SubjectFollowTypedDouble({
    this._activePersonaId = 'subject-follow-fixture-persona',
  });

  final String _activePersonaId;
  final Set<String> _following = <String>{};

  static String _key(SubjectFollowTargetKind type, String id) =>
      '${type.wireName}\u0000$id';

  bool isFollowing(SubjectFollowTargetKind type, String subjectId) =>
      _following.contains(_key(type, subjectId));

  @override
  Future<SubjectFollowCommandResult> follow(
    FollowSubjectCommand command,
  ) async {
    final key = _key(command.subjectType, command.subjectId);
    final replayed = !_following.add(key);
    return SubjectFollowCommandResult(
      personaId: _activePersonaId,
      subjectType: command.subjectType,
      subjectId: command.subjectId,
      state: SubjectFollowState.following,
      idempotentReplay: replayed,
      updatedAt: DateTime.now().toUtc(),
    );
  }

  @override
  Future<SubjectFollowCommandResult> unfollow(
    UnfollowSubjectCommand command,
  ) async {
    final key = _key(command.subjectType, command.subjectId);
    final removed = _following.remove(key);
    return SubjectFollowCommandResult(
      personaId: _activePersonaId,
      subjectType: command.subjectType,
      subjectId: command.subjectId,
      state: SubjectFollowState.unfollowed,
      idempotentReplay: !removed,
      updatedAt: DateTime.now().toUtc(),
    );
  }
}
