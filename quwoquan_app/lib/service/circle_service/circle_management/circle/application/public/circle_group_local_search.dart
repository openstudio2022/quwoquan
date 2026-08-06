import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/conversation_avatar_search_index.dart';

/// Circle-owned account/persona partition for its rebuildable group index.
final class CircleLocalSearchScope {
  const CircleLocalSearchScope({
    required this.ownerUserId,
    required this.personaId,
    required this.subjectType,
    required this.personaContextVersion,
  });

  factory CircleLocalSearchScope.fromSearchActorScope(SearchActorScope scope) {
    return CircleLocalSearchScope(
      ownerUserId: scope.ownerUserId.trim(),
      personaId: scope.personaId.trim(),
      subjectType: scope.subjectType.trim(),
      personaContextVersion: scope.personaContextVersion.trim(),
    );
  }

  final String ownerUserId;
  final String personaId;
  final String subjectType;
  final String personaContextVersion;

  String get actorId {
    final persona = personaId.trim();
    return persona.isNotEmpty ? persona : ownerUserId.trim();
  }

  String get key => '${ownerUserId.trim()}::$actorId';
}

/// Public, storage-agnostic hit returned by Circle's local group index.
final class CircleGroupLocalSearchHit {
  const CircleGroupLocalSearchHit({
    required this.groupId,
    required this.circleId,
    required this.name,
    this.description = '',
    this.circleName = '',
    required this.groupType,
    this.memberCount = 0,
    this.highlightText,
    this.matchedField,
  });

  final String groupId;
  final String circleId;
  final String name;
  final String description;
  final String circleName;
  final String groupType;
  final int memberCount;
  final String? highlightText;
  final String? matchedField;
}

/// Public Circle seam used by Search's hybrid suggestion composition.
abstract interface class CircleGroupLocalSearchIndex {
  Future<bool> sync();

  Future<List<CircleGroupLocalSearchHit>> searchGroups({
    required String query,
    int limit = 20,
  });
}
