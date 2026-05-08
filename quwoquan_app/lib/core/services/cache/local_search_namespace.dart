import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';

typedef PersonaContextLoader = Future<ActivePersonaContextViewData> Function();

class LocalSearchNamespace {
  const LocalSearchNamespace({
    required this.ownerUserId,
    required this.subAccountId,
    required this.subjectType,
    required this.personaContextVersion,
  });

  final String ownerUserId;
  final String subAccountId;
  final String subjectType;
  final String personaContextVersion;

  String get actorId {
    final subAccount = subAccountId.trim();
    if (subAccount.isNotEmpty) {
      return subAccount;
    }
    return ownerUserId.trim();
  }

  String get key => '${ownerUserId.trim()}::$actorId';

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'key': key,
      'ownerUserId': ownerUserId,
      'subAccountId': subAccountId,
      'subjectType': subjectType,
      'personaContextVersion': personaContextVersion,
      'actorId': actorId,
    };
  }

  factory LocalSearchNamespace.fromActivePersonaContext(
    ActivePersonaContextViewData context,
  ) {
    final subAccountId = context.subAccountId.trim().isNotEmpty
        ? context.subAccountId.trim()
        : context.ownerUserId.trim();
    return LocalSearchNamespace(
      ownerUserId: context.ownerUserId.trim(),
      subAccountId: subAccountId,
      subjectType: context.subjectType.trim(),
      personaContextVersion: context.personaContextVersion.trim(),
    );
  }
}
