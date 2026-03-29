import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';

typedef PersonaContextLoader = Future<ActivePersonaContextViewData> Function();

class LocalSearchNamespace {
  const LocalSearchNamespace({
    required this.ownerUserId,
    required this.profileSubjectId,
    required this.subAccountId,
    required this.subjectType,
    required this.personaContextVersion,
  });

  final String ownerUserId;
  final String profileSubjectId;
  final String subAccountId;
  final String subjectType;
  final String personaContextVersion;

  String get actorId {
    final subAccount = subAccountId.trim();
    if (subAccount.isNotEmpty) {
      return subAccount;
    }
    final subjectId = profileSubjectId.trim();
    if (subjectId.isNotEmpty) {
      return subjectId;
    }
    return ownerUserId.trim();
  }

  String get key => '${ownerUserId.trim()}::$actorId';

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'key': key,
      'ownerUserId': ownerUserId,
      'profileSubjectId': profileSubjectId,
      'subAccountId': subAccountId,
      'subjectType': subjectType,
      'personaContextVersion': personaContextVersion,
      'actorId': actorId,
    };
  }

  factory LocalSearchNamespace.fromActivePersonaContext(
    ActivePersonaContextViewData context,
  ) {
    return LocalSearchNamespace(
      ownerUserId: context.ownerUserId.trim(),
      profileSubjectId: context.profileSubjectId.trim(),
      subAccountId: context.subAccountId.trim(),
      subjectType: context.subjectType.trim(),
      personaContextVersion: context.personaContextVersion.trim(),
    );
  }
}
