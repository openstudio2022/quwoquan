final class SearchActorScope {
  const SearchActorScope({
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
    return persona.isNotEmpty ? persona : ownerUserId.trim();
  }

  String get key => '${ownerUserId.trim()}::$actorId';
}

typedef SearchActorScopeLoader = Future<SearchActorScope> Function();

/// Public write seam used by Chat's avatar-patch synchronization.
///
/// SQLite schema, rows and the complete local-search store remain private to
/// the Search adapter. Chat can advance only its own bounded avatar cursor and
/// projections through this interface.
abstract interface class ConversationAvatarSearchIndex {
  Future<void> ensureConversationAvatarIndexReady();

  Future<int> lastConversationAvatarSyncSeq({required SearchActorScope scope});

  Future<void> saveConversationAvatarSyncSeq({
    required SearchActorScope scope,
    required int syncSeq,
  });

  Future<void> updateConversationAvatarProjection({
    required SearchActorScope scope,
    required String conversationId,
    required String avatarUrl,
    int? groupAvatarVersion,
    String? groupAvatarSourceHash,
  });

  Future<void> updateContactAvatarProjection({
    required SearchActorScope scope,
    required String userId,
    required String avatarUrl,
    required int avatarVersion,
  });
}
