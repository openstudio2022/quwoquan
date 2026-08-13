import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';

typedef PersonaContextLoader = Future<ActivePersonaContextViewData> Function();

class LocalSearchNamespace {
  const LocalSearchNamespace({
    required this.ownerUserId,
    required this.personaId,
    required this.subjectType,
    required this.personaContextVersion,
  });

  final String ownerUserId;
  final String personaId;
  final String subjectType;
  final String personaContextVersion;

  String get actorId {
    final persona = personaId.trim();
    if (persona.isNotEmpty) {
      return persona;
    }
    return ownerUserId.trim();
  }

  String get key => '${ownerUserId.trim()}::$actorId';

  Map<String, Object?> toMap() {
    return <String, Object?>{
      'key': key,
      'ownerUserId': ownerUserId,
      'personaId': personaId,
      'subjectType': subjectType,
      'personaContextVersion': personaContextVersion,
      'actorId': actorId,
    };
  }

  factory LocalSearchNamespace.fromActivePersonaContext(
    ActivePersonaContextViewData context,
  ) {
    final personaId = context.personaId.trim().isNotEmpty
        ? context.personaId.trim()
        : context.ownerUserId.trim();
    return LocalSearchNamespace(
      ownerUserId: context.ownerUserId.trim(),
      personaId: personaId,
      subjectType: context.subjectType.trim(),
      personaContextVersion: context.contextVersion.toString(),
    );
  }
}
