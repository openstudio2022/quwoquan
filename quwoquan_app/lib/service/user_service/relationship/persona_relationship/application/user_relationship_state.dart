import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/user_relationship_state.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/di/client_state_sync_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/storage/client_interaction_state_store.dart';

const String _userRelationshipStateStorageKey = 'user_relationship_state';

class UserRelationshipStateNotifier extends Notifier<UserRelationshipState> {
  @override
  UserRelationshipState build() {
    unawaited(_hydratePersistedState());
    return const UserRelationshipState();
  }

  Future<void> _hydratePersistedState() async {
    final raw = await readPersistedInteractionMap(
      _userRelationshipStateStorageKey,
    );
    if (!ref.mounted) {
      return;
    }
    if (raw == null) {
      return;
    }
    state = UserRelationshipState.fromMap(raw);
  }

  void seedFollowing(
    Iterable<String> personaIds, {
    Iterable<String>? knownPersonaIds,
  }) {
    state = UserRelationshipState(
      followingPersonaIds: Set<String>.from(personaIds),
      knownPersonaIds: Set<String>.from(knownPersonaIds ?? personaIds),
    );
    unawaited(_persistState());
  }

  void setFollowing(String personaId, bool isFollowing) {
    final next = Set<String>.from(state.followingPersonaIds);
    final nextKnown = Set<String>.from(state.knownPersonaIds)..add(personaId);
    if (isFollowing) {
      next.add(personaId);
    } else {
      next.remove(personaId);
    }
    state = state.copyWith(
      followingPersonaIds: next,
      knownPersonaIds: nextKnown,
    );
    unawaited(_persistState());
  }

  /// 单一关注意图入口：先更新本地关系快照，再把同一目标态写入持久 outbox。
  /// 页面不得绕过该方法直接调用 PersonaRelationshipCommandWriter。
  Future<void> setFollowingWithSync(
    String personaId, {
    required bool currentFollowing,
    required bool shouldFollow,
    required AppUiSurface sourceSurface,
    bool flushImmediately = true,
  }) async {
    setFollowing(personaId, shouldFollow);
    final outbox = ref.read(clientStateSyncOutboxProvider.notifier);
    outbox.enqueueFollow(
      personaId: personaId,
      currentFollowing: currentFollowing,
      shouldFollow: shouldFollow,
      sourceSurfaceId: sourceSurface.id,
      flushImmediately: flushImmediately,
    );
    if (flushImmediately) {
      await outbox.flushNow();
    }
  }

  void mergeInteractionState(UserRelationshipInteractionInput input) {
    final scopePersonaIds = input.effectiveScopePersonaIds;
    if (scopePersonaIds.isEmpty && input.followingPersonaIds.isEmpty) {
      return;
    }
    final nextFollowing = Set<String>.from(state.followingPersonaIds);
    final nextKnown = Set<String>.from(state.knownPersonaIds)
      ..addAll(scopePersonaIds);
    for (final personaId in scopePersonaIds) {
      if (input.followingPersonaIds.contains(personaId)) {
        nextFollowing.add(personaId);
      } else {
        nextFollowing.remove(personaId);
      }
    }
    state = state.copyWith(
      followingPersonaIds: nextFollowing,
      knownPersonaIds: nextKnown,
    );
    unawaited(_persistState());
  }

  void applyInteractionState(UserRelationshipInteractionInput input) {
    mergeInteractionState(input);
  }

  Future<void> _persistState() async {
    await writePersistedInteractionMap(
      _userRelationshipStateStorageKey,
      state.toMap(),
    );
  }
}
