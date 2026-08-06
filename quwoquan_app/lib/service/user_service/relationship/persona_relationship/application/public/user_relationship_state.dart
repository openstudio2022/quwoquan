class UserRelationshipInteractionInput {
  const UserRelationshipInteractionInput({
    this.scopePersonaIds = const <String>{},
    this.followingPersonaIds = const <String>{},
  });

  final Set<String> scopePersonaIds;
  final Set<String> followingPersonaIds;

  Set<String> get effectiveScopePersonaIds {
    if (scopePersonaIds.isNotEmpty) {
      return scopePersonaIds;
    }
    return followingPersonaIds;
  }
}

class UserRelationshipState {
  const UserRelationshipState({
    this.followingPersonaIds = const <String>{},
    this.knownPersonaIds = const <String>{},
  });

  final Set<String> followingPersonaIds;
  final Set<String> knownPersonaIds;

  bool isFollowing(String personaId) {
    return followingPersonaIds.contains(personaId);
  }

  bool hasRelationshipStateFor(String personaId) {
    return knownPersonaIds.contains(personaId);
  }

  UserRelationshipState copyWith({
    Set<String>? followingPersonaIds,
    Set<String>? knownPersonaIds,
  }) {
    return UserRelationshipState(
      followingPersonaIds: followingPersonaIds ?? this.followingPersonaIds,
      knownPersonaIds: knownPersonaIds ?? this.knownPersonaIds,
    );
  }

  factory UserRelationshipState.fromMap(Map<String, dynamic> map) {
    Set<String> readSet(String key) {
      final raw = map[key];
      if (raw is List) {
        return raw.map((item) => item.toString()).toSet();
      }
      return const <String>{};
    }

    final following = readSet('followingPersonaIds');
    final known = readSet('knownPersonaIds');
    return UserRelationshipState(
      followingPersonaIds: following,
      knownPersonaIds: known.isEmpty ? following : known,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'followingPersonaIds': followingPersonaIds.toList(growable: false),
      'knownPersonaIds': knownPersonaIds.toList(growable: false),
    };
  }
}
