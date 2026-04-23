import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

class PersonaManagementState {
  const PersonaManagementState({
    this.items = const <PersonaManagementItemViewData>[],
    this.quota,
    this.activeContext,
    this.isLoading = false,
    this.isMutating = false,
    this.error,
    this.pendingSyncSuggestion,
  });

  final List<PersonaManagementItemViewData> items;
  final PersonaManagementQuotaViewData? quota;
  final ActivePersonaContextViewData? activeContext;
  final bool isLoading;
  final bool isMutating;
  final String? error;
  final PersonaSyncSuggestionViewData? pendingSyncSuggestion;

  PersonaManagementState copyWith({
    List<PersonaManagementItemViewData>? items,
    PersonaManagementQuotaViewData? quota,
    ActivePersonaContextViewData? activeContext,
    bool? isLoading,
    bool? isMutating,
    String? Function()? error,
    PersonaSyncSuggestionViewData? Function()? pendingSyncSuggestion,
  }) {
    return PersonaManagementState(
      items: items ?? this.items,
      quota: quota ?? this.quota,
      activeContext: activeContext ?? this.activeContext,
      isLoading: isLoading ?? this.isLoading,
      isMutating: isMutating ?? this.isMutating,
      error: error != null ? error() : this.error,
      pendingSyncSuggestion: pendingSyncSuggestion != null
          ? pendingSyncSuggestion()
          : this.pendingSyncSuggestion,
    );
  }
}

class PersonaManagementNotifier extends Notifier<PersonaManagementState> {
  UserRepository get _repo => ref.read(userRepositoryProvider);

  AnalyticsService get _analytics => ref.read(analyticsProvider);

  bool get _syncEnabled => ref.read(personaProfileSyncFeatureFlagProvider);

  @override
  PersonaManagementState build() {
    ref.watch(userRepositoryProvider);
    return const PersonaManagementState();
  }

  Future<void> load() async {
    if (state.isLoading) {
      return;
    }
    state = state.copyWith(isLoading: true, error: () => null);
    try {
      final summary = await _repo.getPersonaManagementSummary();
      state = state.copyWith(
        items: summary.items,
        quota: summary.quota,
        activeContext: summary.activeContext,
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: () => e.toString());
    }
  }

  Future<PersonaManagementItemViewData?> createPersona({
    required String displayName,
    String? userHandle,
    String isolationLevel = 'open',
    String? purposeHint,
  }) async {
    state = state.copyWith(isMutating: true, error: () => null);
    try {
      final created = await _repo.createPersona(
        displayName: displayName,
        userHandle: userHandle,
        isolationLevel: isolationLevel,
        purposeHint: purposeHint,
      );
      await _reloadAfterMutation();
      await _track('create_succeeded', <String, dynamic>{
        'personaId': created.subAccountId,
      });
      return created;
    } catch (e) {
      await _track('create_failed', <String, dynamic>{'message': e.toString()});
      state = state.copyWith(isMutating: false, error: () => e.toString());
      rethrow;
    }
  }

  Future<void> activatePersona(String personaId) async {
    state = state.copyWith(isMutating: true, error: () => null);
    try {
      await _repo.activatePersona(personaId);
      await _reloadAfterMutation();
      await _track('activate_succeeded', <String, dynamic>{
        'personaId': personaId,
      });
    } catch (e) {
      await _track('activate_failed', <String, dynamic>{
        'message': e.toString(),
      });
      state = state.copyWith(isMutating: false, error: () => e.toString());
      rethrow;
    }
  }

  Future<PersonaManagementItemViewData?> updatePersona(
    String personaId, {
    String? displayName,
    String? userHandle,
    String? phone,
    String? email,
    String? isolationLevel,
    String? purposeHint,
  }) async {
    state = state.copyWith(isMutating: true, error: () => null);
    final changedFields = <String>[
      if (displayName != null) 'displayName',
      if (userHandle != null) 'userHandle',
      if (phone != null) 'phone',
      if (email != null) 'email',
    ];
    try {
      final updated = await _repo.updatePersona(
        personaId,
        displayName: displayName,
        userHandle: userHandle,
        phone: phone,
        email: email,
        isolationLevel: isolationLevel,
        purposeHint: purposeHint,
      );
      await _reloadAfterMutation();
      if (_syncEnabled && changedFields.isNotEmpty) {
        _setPendingSyncSuggestion(updated, changedFields);
      }
      return updated;
    } catch (e) {
      state = state.copyWith(isMutating: false, error: () => e.toString());
      rethrow;
    }
  }

  Future<PersonaLifecycleGuardViewData> getLifecycleGuard(String personaId) {
    return _repo.getPersonaLifecycleGuard(personaId);
  }

  Future<void> deletePersona(String personaId) async {
    state = state.copyWith(isMutating: true, error: () => null);
    try {
      await _repo.deleteEmptyPersona(personaId);
      await _reloadAfterMutation();
    } catch (e) {
      await _track('delete_blocked', <String, dynamic>{
        'message': e.toString(),
      });
      state = state.copyWith(isMutating: false, error: () => e.toString());
      rethrow;
    }
  }

  Future<void> retirePersona(String personaId) async {
    state = state.copyWith(isMutating: true, error: () => null);
    try {
      await _repo.retirePersona(personaId);
      await _track('retired_count', <String, dynamic>{'retiredCount': 1});
      await _reloadAfterMutation();
      await _track('retire_succeeded', <String, dynamic>{
        'personaId': personaId,
      });
    } catch (e) {
      state = state.copyWith(isMutating: false, error: () => e.toString());
      rethrow;
    }
  }

  Future<int> applySyncSuggestion({
    required PersonaSyncSuggestionViewData suggestion,
    List<String>? targetPersonaIds,
  }) async {
    state = state.copyWith(isMutating: true, error: () => null);
    try {
      final appliedCount = await _repo.applyPersonaProfileSync(
        suggestion.sourcePersonaId,
        fieldsMask: suggestion.fieldKeys,
        applyScope:
            targetPersonaIds == null ||
                targetPersonaIds.length == suggestion.targetPersonaIds.length
            ? 'all_sub_accounts'
            : 'selected_subjects',
        syncTargetIds: targetPersonaIds ?? suggestion.targetPersonaIds,
      );
      await _track('profile_sync_applied', <String, dynamic>{
        'appliedCount': appliedCount,
      });
      await _reloadAfterMutation();
      state = state.copyWith(pendingSyncSuggestion: () => null);
      return appliedCount;
    } catch (e) {
      state = state.copyWith(isMutating: false, error: () => e.toString());
      rethrow;
    }
  }

  Future<void> ignorePendingSuggestion() async {
    if (state.pendingSyncSuggestion == null) {
      return;
    }
    await _track('profile_sync_rejected', const <String, dynamic>{});
    state = state.copyWith(pendingSyncSuggestion: () => null);
  }

  Future<void> trackQuotaReached(int maxSubAccounts) {
    return _track('quota_reached', <String, dynamic>{
      'maxSubAccounts': maxSubAccounts,
    });
  }

  Future<void> _reloadAfterMutation() async {
    final summary = await _repo.getPersonaManagementSummary();
    state = state.copyWith(
      items: summary.items,
      quota: summary.quota,
      activeContext: summary.activeContext,
      isLoading: false,
      isMutating: false,
      error: () => null,
    );
  }

  void _setPendingSyncSuggestion(
    PersonaManagementItemViewData source,
    List<String> changedFields,
  ) {
    final targets = <PersonaManagementItemViewData>[];
    for (final item in state.items) {
      if (item.subAccountId == source.subAccountId) {
        continue;
      }
      if (_hasDivergentField(item, source, changedFields)) {
        targets.add(item);
      }
    }
    if (targets.isEmpty) {
      state = state.copyWith(pendingSyncSuggestion: () => null);
      return;
    }
    final suggestion = PersonaSyncSuggestionViewData(
      sourcePersonaId: source.subAccountId,
      sourceDisplayName: source.displayName,
      targetPersonaIds: targets
          .map((e) => e.subAccountId)
          .toList(growable: false),
      targetDisplayNames: targets
          .map((e) => e.displayName)
          .toList(growable: false),
      fieldKeys: changedFields,
    );
    state = state.copyWith(pendingSyncSuggestion: () => suggestion);
    _track('profile_sync_suggested', <String, dynamic>{
      'targetCount': targets.length,
      'fieldCount': changedFields.length,
    });
  }

  bool _hasDivergentField(
    PersonaManagementItemViewData target,
    PersonaManagementItemViewData source,
    List<String> fields,
  ) {
    for (final field in fields) {
      switch (field) {
        case 'displayName':
          if (target.displayName != source.displayName) {
            return true;
          }
        case 'userHandle':
          if (target.userHandle != source.userHandle) {
            return true;
          }
        case 'phone':
          if (target.phone != source.phone) {
            return true;
          }
        case 'email':
          if (target.email != source.email) {
            return true;
          }
      }
    }
    return false;
  }

  Future<void> _track(String eventName, Map<String, dynamic> properties) {
    return _analytics.trackEvent(
      AnalyticsEvent(
        eventType: 'persona_management',
        eventName: eventName,
        properties: <String, dynamic>{
          'pageName': 'persona_management',
          'surfaceId': 'persona_management_page',
          'routeId': '/profile/personas',
          ...properties,
        },
      ),
    );
  }
}

final personaManagementProvider =
    NotifierProvider<PersonaManagementNotifier, PersonaManagementState>(
      PersonaManagementNotifier.new,
    );
