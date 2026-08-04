import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers_client_sync.dart';
const String _clientInteractionStateBoxName = 'client_interaction_state';
const String _userRelationshipStateStorageKey = 'user_relationship_state';
const String _postInteractionStateStorageKey = 'post_interaction_state';
const String clientStateSyncOutboxStorageKey = 'client_state_sync_outbox';
int _clientInteractionStateEpoch = 0;

Future<Box<String>> _ensureClientInteractionStateBox() async {
  if (!Hive.isBoxOpen(_clientInteractionStateBoxName)) {
    try {
      await Hive.initFlutter();
    } catch (_) {
      /* best-effort: Hive 可能已被全局初始化，重复初始化抛错可安全忽略，随后直接打开盒子 */
    }
    return Hive.openBox<String>(_clientInteractionStateBoxName);
  }
  return Hive.box<String>(_clientInteractionStateBoxName);
}

Future<Map<String, dynamic>?> readPersistedInteractionMap(String key) async {
  final epoch = _clientInteractionStateEpoch;
  try {
    final box = await _ensureClientInteractionStateBox();
    if (epoch != _clientInteractionStateEpoch) {
      return null;
    }
    final raw = box.get(key);
    if (raw == null || raw.isEmpty) {
      return null;
    }
    final decoded = jsonDecode(raw);
    if (decoded is Map<String, dynamic>) {
      return decoded;
    }
    if (decoded is Map) {
      return decoded.cast<String, dynamic>();
    }
  } catch (_) {
    /* best-effort: 本地交互状态损坏时回退到 null，由调用方按未持久化态初始化 */
  }
  return null;
}

Future<void> writePersistedInteractionMap(
  String key,
  Map<String, dynamic> value,
) async {
  final epoch = _clientInteractionStateEpoch;
  try {
    final box = await _ensureClientInteractionStateBox();
    if (epoch != _clientInteractionStateEpoch) {
      return;
    }
    await box.put(key, jsonEncode(value));
  } catch (_) {
    /* best-effort: 本地交互状态持久化失败仅丢失离线缓存，云端同步仍为真相源 */
  }
}

/// 云侧账号 closed 后清除关系、内容交互投影及其待同步 outbox。
Future<void> clearClientInteractionStateForTerminalAccountClosure() async {
  _clientInteractionStateEpoch += 1;
  final box = await _ensureClientInteractionStateBox();
  await box.clear();
  if (box.isNotEmpty) {
    throw StateError('client interaction state cleanup verification failed');
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

  void mergeInteractionSnapshot(MediaViewerInteractionSnapshot snapshot) {
    final scopeProfileIds = snapshot.effectiveScopeProfileIds;
    if (scopeProfileIds.isEmpty && snapshot.followingUsers.isEmpty) {
      return;
    }
    final effectiveScope = scopeProfileIds.isEmpty
        ? snapshot.followingUsers
        : scopeProfileIds;
    final nextFollowing = Set<String>.from(state.followingPersonaIds);
    final nextKnown = Set<String>.from(state.knownPersonaIds)
      ..addAll(effectiveScope);
    for (final profileId in effectiveScope) {
      if (snapshot.followingUsers.contains(profileId)) {
        nextFollowing.add(profileId);
      } else {
        nextFollowing.remove(profileId);
      }
    }
    state = state.copyWith(
      followingPersonaIds: nextFollowing,
      knownPersonaIds: nextKnown,
    );
    unawaited(_persistState());
  }

  void applyViewerResult(MediaViewerResult result) {
    mergeInteractionSnapshot(result);
  }

  Future<void> _persistState() async {
    await writePersistedInteractionMap(
      _userRelationshipStateStorageKey,
      state.toMap(),
    );
  }
}

class PostInteractionState {
  const PostInteractionState({
    this.likedPostIds = const <String>{},
    this.likeCounts = const <String, int>{},
    this.confirmedShareCounts = const <String, int>{},
    this.confirmedCommentCounts = const <String, int>{},
    this.pendingCommentDeltas = const <String, int>{},
  });

  final Set<String> likedPostIds;
  final Map<String, int> likeCounts;
  final Map<String, int> confirmedShareCounts;
  final Map<String, int> confirmedCommentCounts;
  final Map<String, int> pendingCommentDeltas;

  bool isLiked(String postId) => likedPostIds.contains(postId);
  bool hasLikeStateFor(String postId) {
    return likedPostIds.contains(postId) || likeCounts.containsKey(postId);
  }

  int likeCountFor(String postId, {int fallback = 0}) {
    return likeCounts[postId] ?? fallback;
  }

  int shareCountFor(String postId, {int fallback = 0}) {
    return confirmedShareCounts[postId] ?? fallback;
  }

  int commentCountFor(String postId, {int fallback = 0}) {
    final confirmed = confirmedCommentCounts[postId] ?? fallback;
    final pending = pendingCommentDeltas[postId] ?? 0;
    return math.max(0, confirmed + pending);
  }

  PostInteractionState copyWith({
    Set<String>? likedPostIds,
    Map<String, int>? likeCounts,
    Map<String, int>? confirmedShareCounts,
    Map<String, int>? confirmedCommentCounts,
    Map<String, int>? pendingCommentDeltas,
  }) {
    return PostInteractionState(
      likedPostIds: likedPostIds ?? this.likedPostIds,
      likeCounts: likeCounts ?? this.likeCounts,
      confirmedShareCounts: confirmedShareCounts ?? this.confirmedShareCounts,
      confirmedCommentCounts:
          confirmedCommentCounts ?? this.confirmedCommentCounts,
      pendingCommentDeltas: pendingCommentDeltas ?? this.pendingCommentDeltas,
    );
  }

  factory PostInteractionState.fromMap(Map<String, dynamic> map) {
    Set<String> readSet(String key) {
      final raw = map[key];
      if (raw is List) {
        return raw.map((item) => item.toString()).toSet();
      }
      return const <String>{};
    }

    Map<String, int> readIntMap(String key) {
      final raw = map[key];
      if (raw is Map) {
        return raw.map(
          (entryKey, value) => MapEntry(
            entryKey.toString(),
            value is num ? value.toInt() : int.tryParse(value.toString()) ?? 0,
          ),
        );
      }
      return const <String, int>{};
    }

    return PostInteractionState(
      likedPostIds: readSet('likedPostIds'),
      likeCounts: readIntMap('likeCounts'),
      confirmedShareCounts: readIntMap('confirmedShareCounts'),
      confirmedCommentCounts: readIntMap('confirmedCommentCounts').isNotEmpty
          ? readIntMap('confirmedCommentCounts')
          : readIntMap('commentCounts'),
      pendingCommentDeltas: readIntMap('pendingCommentDeltas'),
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'likedPostIds': likedPostIds.toList(growable: false),
      'likeCounts': likeCounts,
      'confirmedShareCounts': confirmedShareCounts,
      'confirmedCommentCounts': confirmedCommentCounts,
      'pendingCommentDeltas': pendingCommentDeltas,
    };
  }
}

class PostInteractionStateNotifier extends Notifier<PostInteractionState> {
  @override
  PostInteractionState build() {
    unawaited(_hydratePersistedState());
    return const PostInteractionState();
  }

  Future<void> _hydratePersistedState() async {
    final raw = await readPersistedInteractionMap(
      _postInteractionStateStorageKey,
    );
    if (!ref.mounted) {
      return;
    }
    if (raw == null) {
      return;
    }
    state = PostInteractionState.fromMap(raw);
  }

  void setLiked(String postId, bool isLiked, {int? likeCount}) {
    final nextLiked = Set<String>.from(state.likedPostIds);
    final nextCounts = Map<String, int>.from(state.likeCounts);
    if (isLiked) {
      nextLiked.add(postId);
    } else {
      nextLiked.remove(postId);
    }
    if (likeCount != null) {
      nextCounts[postId] = likeCount;
    }
    state = state.copyWith(likedPostIds: nextLiked, likeCounts: nextCounts);
    unawaited(_persistState());
  }

  void applyConfirmedCounters(
    String postId, {
    int? shareCount,
    int? commentCount,
  }) {
    final nextConfirmedShareCounts = Map<String, int>.from(
      state.confirmedShareCounts,
    );
    final nextConfirmedCommentCounts = Map<String, int>.from(
      state.confirmedCommentCounts,
    );
    final nextPendingCommentDeltas = Map<String, int>.from(
      state.pendingCommentDeltas,
    );
    if (shareCount != null) {
      nextConfirmedShareCounts[postId] = shareCount;
    }
    if (commentCount != null) {
      nextConfirmedCommentCounts[postId] = commentCount;
      nextPendingCommentDeltas.remove(postId);
    }
    state = state.copyWith(
      confirmedShareCounts: nextConfirmedShareCounts,
      confirmedCommentCounts: nextConfirmedCommentCounts,
      pendingCommentDeltas: nextPendingCommentDeltas,
    );
    unawaited(_persistState());
  }

  void setShareCount(String postId, int shareCount) {
    applyConfirmedCounters(postId, shareCount: shareCount);
  }

  void setCommentCount(String postId, int commentCount) {
    applyConfirmedCounters(postId, commentCount: commentCount);
  }

  void applyConfirmedPosts(Iterable<ContentPostViewData> posts) {
    final nextConfirmedShareCounts = Map<String, int>.from(
      state.confirmedShareCounts,
    );
    final nextConfirmedCommentCounts = Map<String, int>.from(
      state.confirmedCommentCounts,
    );
    final nextPendingCommentDeltas = Map<String, int>.from(
      state.pendingCommentDeltas,
    );
    for (final post in posts) {
      if (post.id.trim().isEmpty) {
        continue;
      }
      nextConfirmedShareCounts[post.id] = post.shareCount;
      nextConfirmedCommentCounts[post.id] = post.commentCount;
      nextPendingCommentDeltas.remove(post.id);
    }
    state = state.copyWith(
      confirmedShareCounts: nextConfirmedShareCounts,
      confirmedCommentCounts: nextConfirmedCommentCounts,
      pendingCommentDeltas: nextPendingCommentDeltas,
    );
    unawaited(_persistState());
  }

  void stageOptimisticComment(
    String postId, {
    required int baseCommentCount,
    required int delta,
  }) {
    final nextConfirmed = Map<String, int>.from(state.confirmedCommentCounts);
    final nextPending = Map<String, int>.from(state.pendingCommentDeltas);
    nextConfirmed.putIfAbsent(postId, () => baseCommentCount);
    nextPending[postId] = (nextPending[postId] ?? 0) + delta;
    state = state.copyWith(
      confirmedCommentCounts: nextConfirmed,
      pendingCommentDeltas: nextPending,
    );
    unawaited(_persistState());
  }

  void rollbackOptimisticComment(
    String postId, {
    required int baseCommentCount,
    required int delta,
  }) {
    final nextConfirmed = Map<String, int>.from(state.confirmedCommentCounts);
    final nextPending = Map<String, int>.from(state.pendingCommentDeltas);
    nextConfirmed.putIfAbsent(postId, () => baseCommentCount);
    final reverted = (nextPending[postId] ?? 0) - delta;
    if (reverted == 0) {
      nextPending.remove(postId);
    } else {
      nextPending[postId] = reverted;
    }
    state = state.copyWith(
      confirmedCommentCounts: nextConfirmed,
      pendingCommentDeltas: nextPending,
    );
    unawaited(_persistState());
  }

  void mergeInteractionSnapshot(MediaViewerInteractionSnapshot snapshot) {
    final scopePostIds = snapshot.effectiveScopePostIds;
    if (scopePostIds.isEmpty) {
      return;
    }
    final nextLiked = Set<String>.from(state.likedPostIds);
    final nextLikeCounts = Map<String, int>.from(state.likeCounts);
    final nextConfirmedShareCounts = Map<String, int>.from(
      state.confirmedShareCounts,
    );
    final nextConfirmedCommentCounts = Map<String, int>.from(
      state.confirmedCommentCounts,
    );
    final nextPendingCommentDeltas = Map<String, int>.from(
      state.pendingCommentDeltas,
    );
    for (final postId in scopePostIds) {
      if (snapshot.likedPosts.contains(postId)) {
        nextLiked.add(postId);
      } else {
        nextLiked.remove(postId);
      }
      final likeCount = snapshot.postLikesCount[postId];
      if (likeCount != null) {
        nextLikeCounts[postId] = likeCount;
      }
      final shareCount = snapshot.postSharesCount[postId];
      if (shareCount != null) {
        nextConfirmedShareCounts[postId] = shareCount;
      }
      final commentCount = snapshot.postCommentCount[postId];
      if (commentCount != null) {
        nextConfirmedCommentCounts[postId] = commentCount;
        nextPendingCommentDeltas.remove(postId);
      }
    }
    state = state.copyWith(
      likedPostIds: nextLiked,
      likeCounts: nextLikeCounts,
      confirmedShareCounts: nextConfirmedShareCounts,
      confirmedCommentCounts: nextConfirmedCommentCounts,
      pendingCommentDeltas: nextPendingCommentDeltas,
    );
    unawaited(_persistState());
  }

  void applyViewerResult(MediaViewerResult result) {
    mergeInteractionSnapshot(result);
  }

  Future<void> _persistState() async {
    await writePersistedInteractionMap(
      _postInteractionStateStorageKey,
      state.toMap(),
    );
  }
}
