import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/user_relationship_state.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/di/client_state_sync_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_relationship_state_storage_dependencies.dart';

class UserRelationshipStateNotifier extends Notifier<UserRelationshipState> {
  /// 本地写入的代际。磁盘 hydrate 只有在读取期间没有新写入时才可落地。
  int _stateRevision = 0;

  @override
  UserRelationshipState build() {
    ref.watch(userRelationshipStateStorageProvider);
    unawaited(_hydratePersistedState());
    return const UserRelationshipState();
  }

  /// 关系投影的持久化边界按 actor 分区解析：切账号或切分身后不得读到上一个
  /// 主体的快照。
  UserRelationshipStateStorage get _storage =>
      ref.read(userRelationshipStateStorageProvider);

  Future<void> _hydratePersistedState() async {
    final revision = _stateRevision;
    final raw = await _storage.read();
    // 读取是异步的：期间发生的关注/取关是更新的事实。旧快照整包覆盖会让
    // 用户刚点的关注被磁盘态回滚，这是跨页面关注态丢失的根因。
    if (!ref.mounted || revision != _stateRevision) {
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
    final outbox = ref.read(clientStateSyncOutboxProvider.notifier);
    final canonicalPersonaId = await outbox.enqueueFollow(
      personaId: personaId,
      currentFollowing: currentFollowing,
      shouldFollow: shouldFollow,
      sourceSurfaceId: sourceSurface.id,
      flushImmediately: flushImmediately,
    );
    // Publish the optimistic overlay only after the command identity and basis
    // crossed the durable local acceptance boundary.
    setFollowing(canonicalPersonaId, shouldFollow);
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
    _stateRevision++;
    await _storage.write(state.toMap());
  }
}
