import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha 内存 SubjectFollow facet：set/unset 幂等，与 user.SubjectFollow
/// 聚合语义同构（重复 follow 返回 idempotentReplay）。
final class AlphaSubjectFollowFacet implements SubjectFollowCommandWriter {
  AlphaSubjectFollowFacet({String activePersonaId = 'alpha-persona'})
    : _activePersonaId = activePersonaId;

  final String _activePersonaId;
  final Set<String> _following = <String>{};

  static String _key(SubjectFollowSubjectType type, String id) =>
      '${type.wire}\u0000$id';

  bool isFollowing(SubjectFollowSubjectType type, String subjectId) =>
      _following.contains(_key(type, subjectId));

  @override
  Future<SubjectFollowCommandResult> follow(
    FollowSubjectCommand command,
  ) async {
    final key = _key(command.subjectType, command.subjectId);
    final replayed = !_following.add(key);
    return SubjectFollowCommandResult(
      personaId: _activePersonaId,
      subjectType: command.subjectType.wire,
      subjectId: command.subjectId,
      state: 'following',
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
      subjectType: command.subjectType.wire,
      subjectId: command.subjectId,
      state: 'unfollowed',
      idempotentReplay: !removed,
      updatedAt: DateTime.now().toUtc(),
    );
  }
}
