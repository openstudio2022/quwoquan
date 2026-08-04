import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/content/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/content/content/post/adapters/create_draft_local_storage.dart';

@immutable
class CreateDraftStoreState {
  const CreateDraftStoreState({
    this.drafts = const <CreateDraft>[],
    this.currentDraftId,
  });

  final List<CreateDraft> drafts;
  final String? currentDraftId;

  CreateDraftStoreState copyWith({
    List<CreateDraft>? drafts,
    String? currentDraftId,
    bool clearCurrentDraftId = false,
  }) {
    return CreateDraftStoreState(
      drafts: drafts ?? this.drafts,
      currentDraftId: clearCurrentDraftId
          ? null
          : (currentDraftId ?? this.currentDraftId),
    );
  }

  CreateDraft? draftById(String id) {
    final normalized = id.trim();
    for (final draft in drafts) {
      if (draft.id == normalized) {
        return draft;
      }
    }
    return null;
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) {
      return true;
    }
    return other is CreateDraftStoreState &&
        currentDraftId == other.currentDraftId &&
        _draftFingerprints(drafts) == _draftFingerprints(other.drafts);
  }

  @override
  int get hashCode => Object.hash(currentDraftId, _draftFingerprints(drafts));
}

String _draftFingerprints(List<CreateDraft> drafts) {
  return drafts
      .map(
        (draft) => [
          draft.id,
          draft.updatedAtMs,
          draft.state.editorKind.name,
          draft.state.mediaKind.name,
          draft.state.title,
          draft.state.body,
          draft.state.imagePaths.join('|'),
          draft.state.videoPath,
          draft.state.videoThumbnail,
          draft.publicationContinuation?.operationId ?? '',
          draft.publicationContinuation?.sourceEntityRef ?? '',
          draft.state.isOneTapMovie,
          draft.state.oneTapMoviePath,
          draft.state.oneTapMovieEffectId,
        ].join('::'),
      )
      .join('||');
}

abstract interface class CreateDraftRepository {
  Future<CreateDraftStoreState> load();

  Future<CreateDraft?> loadDraft(String draftId);

  Future<CreateDraftStoreState> upsertDraft(
    CreateDraft draft, {
    String? currentDraftId,
  });

  Future<CreateDraftStoreState> deleteDraft(String draftId);

  Future<CreateDraftStoreState> setCurrentDraftId(String? draftId);
}

class SharedPreferencesCreateDraftRepository implements CreateDraftRepository {
  const SharedPreferencesCreateDraftRepository({required this.scopeKey});

  final String scopeKey;

  @override
  Future<CreateDraftStoreState> load() async {
    final snapshot =
        await CreateDraftLocalStorage.loadScopedDraftsWithCurrentId(scopeKey);
    return CreateDraftStoreState(
      drafts: snapshot.drafts,
      currentDraftId: snapshot.currentId,
    );
  }

  @override
  Future<CreateDraft?> loadDraft(String draftId) async {
    return CreateDraftLocalStorage.loadScopedDraft(scopeKey, draftId);
  }

  @override
  Future<CreateDraftStoreState> upsertDraft(
    CreateDraft draft, {
    String? currentDraftId,
  }) async {
    final current = await load();
    final normalizedId = draft.id.trim();
    final nextDrafts = <CreateDraft>[
      draft,
      ...current.drafts.where((entry) => entry.id != normalizedId),
    ]..sort((a, b) => b.updatedAtMs.compareTo(a.updatedAtMs));
    final nextCurrentId = _normalizeDraftId(currentDraftId ?? normalizedId);
    await CreateDraftLocalStorage.persistScopedDrafts(
      scopeKey,
      nextDrafts,
      currentId: nextCurrentId,
    );
    return CreateDraftStoreState(
      drafts: nextDrafts,
      currentDraftId: nextCurrentId,
    );
  }

  @override
  Future<CreateDraftStoreState> deleteDraft(String draftId) async {
    final normalizedId = draftId.trim();
    await CreateDraftLocalStorage.removeScopedDraftById(scopeKey, normalizedId);
    final next = await load();
    return next.copyWith(
      currentDraftId: next.currentDraftId == normalizedId
          ? null
          : next.currentDraftId,
      clearCurrentDraftId: next.currentDraftId == normalizedId,
    );
  }

  @override
  Future<CreateDraftStoreState> setCurrentDraftId(String? draftId) async {
    final normalizedId = _normalizeDraftId(draftId);
    await CreateDraftLocalStorage.persistScopedCurrentDraftId(
      scopeKey,
      normalizedId,
    );
    final current = await load();
    return current.copyWith(
      currentDraftId: normalizedId,
      clearCurrentDraftId: normalizedId == null,
    );
  }
}

String? _normalizeDraftId(String? draftId) {
  final normalized = draftId?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}

final createDraftRepositoryProvider = Provider<CreateDraftRepository>((ref) {
  final currentUserId = ref.watch(currentUserIdProvider);
  return SharedPreferencesCreateDraftRepository(
    scopeKey: CreateDraftLocalStorage.scopeKeyForUser(currentUserId),
  );
});

class CreateDraftStoreController extends AsyncNotifier<CreateDraftStoreState> {
  CreateDraftRepository get _repository =>
      ref.read(createDraftRepositoryProvider);

  @override
  Future<CreateDraftStoreState> build() async {
    ref.watch(currentUserIdProvider);
    return _repository.load();
  }

  Future<void> reload() async {
    state = const AsyncLoading<CreateDraftStoreState>();
    state = AsyncData(await _repository.load());
  }

  Future<CreateDraftStoreState> saveDraft(
    CreateDraft draft, {
    String? currentDraftId,
  }) async {
    final next = await _repository.upsertDraft(
      draft,
      currentDraftId: currentDraftId,
    );
    state = AsyncData(next);
    return next;
  }

  Future<CreateDraftStoreState> deleteDraft(String draftId) async {
    final next = await _repository.deleteDraft(draftId);
    state = AsyncData(next);
    return next;
  }

  Future<CreateDraftStoreState> deleteCurrentDraft() async {
    final snapshot = state is AsyncData<CreateDraftStoreState>
        ? (state as AsyncData<CreateDraftStoreState>).value
        : null;
    final currentId = snapshot?.currentDraftId;
    if (currentId == null || currentId.isEmpty) {
      return snapshot ?? const CreateDraftStoreState();
    }
    return deleteDraft(currentId);
  }

  Future<CreateDraftStoreState> setCurrentDraftId(String? draftId) async {
    final next = await _repository.setCurrentDraftId(draftId);
    state = AsyncData(next);
    return next;
  }

  Future<CreateDraft?> getDraft(String draftId) async {
    final snapshot = state is AsyncData<CreateDraftStoreState>
        ? (state as AsyncData<CreateDraftStoreState>).value
        : null;
    final cached = snapshot?.draftById(draftId);
    if (cached != null) {
      return cached;
    }
    return _repository.loadDraft(draftId);
  }
}

final createDraftStoreProvider =
    AsyncNotifierProvider<CreateDraftStoreController, CreateDraftStoreState>(
      CreateDraftStoreController.new,
    );
