import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

class PersonaManagementState {
  const PersonaManagementState({
    this.items = const <PersonaManagementItemViewData>[],
    this.quota,
    this.activeContext,
    this.isLoading = false,
    this.isMutating = false,
    this.rawError,
    this.pendingSyncSuggestion,
  });

  final List<PersonaManagementItemViewData> items;
  final PersonaManagementQuotaViewData? quota;
  final ActivePersonaContextViewData? activeContext;
  final bool isLoading;
  final bool isMutating;
  final Object? rawError;
  final PersonaSyncSuggestionViewData? pendingSyncSuggestion;

  String? get error =>
      rawError == null ? null : runtimeErrorDisplayMessage(rawError!).trim();

  PersonaManagementState copyWith({
    List<PersonaManagementItemViewData>? items,
    PersonaManagementQuotaViewData? quota,
    ActivePersonaContextViewData? activeContext,
    bool? isLoading,
    bool? isMutating,
    Object? Function()? rawError,
    PersonaSyncSuggestionViewData? Function()? pendingSyncSuggestion,
  }) {
    return PersonaManagementState(
      items: items ?? this.items,
      quota: quota ?? this.quota,
      activeContext: activeContext ?? this.activeContext,
      isLoading: isLoading ?? this.isLoading,
      isMutating: isMutating ?? this.isMutating,
      rawError: rawError != null ? rawError() : this.rawError,
      pendingSyncSuggestion: pendingSyncSuggestion != null
          ? pendingSyncSuggestion()
          : this.pendingSyncSuggestion,
    );
  }
}

class PersonaManagementNotifier extends Notifier<PersonaManagementState> {
  /// 读投影（列表/配额/激活上下文/生命周期守卫）。
  PersonaQuery get _query =>
      ref.read(personaQueryProvider(AppUiSurfaces.profilePersonas));

  /// 命令面：Persona 聚合 typed facet（generated client，
  /// timeout/retry/idempotency 由 metadata descriptor 驱动）。
  contracts.PersonaManagementCommandWriter get _commands =>
      ref.read(personaCommandWriterProvider);

  AnalyticsService get _analytics => ref.read(analyticsProvider);

  bool get _syncEnabled => ref.read(personaProfileSyncFeatureFlagProvider);

  @override
  PersonaManagementState build() {
    ref.watch(personaQueryProvider(AppUiSurfaces.profilePersonas));
    return const PersonaManagementState();
  }

  Future<void> load() async {
    if (state.isLoading) {
      return;
    }
    state = state.copyWith(isLoading: true, rawError: () => null);
    try {
      final summary = await _query.getPersonaManagementSummary();
      state = state.copyWith(
        items: summary.items,
        quota: summary.quota,
        activeContext: summary.activeContext,
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, rawError: () => e);
    }
  }

  Future<PersonaManagementItemViewData?> createPersona({
    required String displayName,
    String isolationLevel = 'open',
    String? purposeHint,
  }) async {
    state = state.copyWith(isMutating: true, rawError: () => null);
    try {
      final created = await _commands.createPersona(
        contracts.CreatePersonaCommand(
          displayName: displayName,
          isolationLevel: isolationLevel,
          purposeHint: purposeHint,
        ),
      );
      await _reloadAfterMutation();
      await _track('create_succeeded', <String, dynamic>{
        'personaId': created.personaId,
      });
      return _itemById(created.personaId);
    } catch (e) {
      await _track('create_failed', <String, dynamic>{
        'message': runtimeErrorDisplayMessage(e),
      });
      state = state.copyWith(isMutating: false, rawError: () => e);
      rethrow;
    }
  }

  Future<void> activatePersona(String personaId) async {
    state = state.copyWith(isMutating: true, rawError: () => null);
    try {
      await _commands.activatePersona(
        contracts.ActivatePersonaCommand(personaId: personaId),
      );
      await ref
          .read(authSessionControllerProvider.notifier)
          .updateActivePersona(personaId);
      await _reloadAfterMutation();
      await _track('activate_succeeded', <String, dynamic>{
        'personaId': personaId,
      });
    } catch (e) {
      await _track('activate_failed', <String, dynamic>{
        'message': runtimeErrorDisplayMessage(e),
      });
      state = state.copyWith(isMutating: false, rawError: () => e);
      rethrow;
    }
  }

  Future<PersonaManagementItemViewData?> updatePersona(
    String personaId, {
    String? displayName,
    String? isolationLevel,
    String? purposeHint,
  }) async {
    state = state.copyWith(isMutating: true, rawError: () => null);
    final changedFields = <String>[if (displayName != null) 'displayName'];
    try {
      final receipt = await _commands.updatePersona(
        contracts.UpdatePersonaCommand(
          personaId: personaId,
          displayName: displayName,
          isolationLevel: isolationLevel,
          purposeHint: purposeHint,
        ),
      );
      await _reloadAfterMutation();
      final updated = _itemById(receipt.personaId);
      if (updated != null && _syncEnabled && changedFields.isNotEmpty) {
        _setPendingSyncSuggestion(updated, changedFields);
      }
      return updated;
    } catch (e) {
      state = state.copyWith(isMutating: false, rawError: () => e);
      rethrow;
    }
  }

  Future<PersonaLifecycleGuardViewData> getLifecycleGuard(String personaId) {
    return _query.getPersonaLifecycleGuard(personaId);
  }

  Future<void> retirePersona(String personaId) async {
    state = state.copyWith(isMutating: true, rawError: () => null);
    try {
      await _commands.retirePersona(
        contracts.RetirePersonaCommand(personaId: personaId),
      );
      await _track('retired_count', <String, dynamic>{'retiredCount': 1});
      await _reloadAfterMutation();
      await _track('retire_succeeded', <String, dynamic>{
        'personaId': personaId,
      });
    } catch (e) {
      state = state.copyWith(isMutating: false, rawError: () => e);
      rethrow;
    }
  }

  Future<int> applySyncSuggestion({
    required PersonaSyncSuggestionViewData suggestion,
    List<String>? targetPersonaIds,
  }) async {
    state = state.copyWith(isMutating: true, rawError: () => null);
    try {
      final result = await _commands.applyPersonaProfileSync(
        contracts.ApplyPersonaProfileSyncCommand(
          personaId: suggestion.sourcePersonaId,
          fieldsMask: suggestion.fieldKeys,
          applyScope:
              targetPersonaIds == null ||
                  targetPersonaIds.length == suggestion.targetPersonaIds.length
              ? 'all_personas'
              : 'selected_subjects',
          syncTargetIds: targetPersonaIds ?? suggestion.targetPersonaIds,
        ),
      );
      final appliedCount = result.appliedCount;
      await _track('profile_sync_applied', <String, dynamic>{
        'appliedCount': appliedCount,
      });
      await _reloadAfterMutation();
      state = state.copyWith(pendingSyncSuggestion: () => null);
      return appliedCount;
    } catch (e) {
      state = state.copyWith(isMutating: false, rawError: () => e);
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

  Future<void> trackQuotaReached(int maxPersonas) {
    return _track('quota_reached', <String, dynamic>{
      'maxPersonas': maxPersonas,
    });
  }

  Future<void> _reloadAfterMutation() async {
    final summary = await _query.getPersonaManagementSummary();
    state = state.copyWith(
      items: summary.items,
      quota: summary.quota,
      activeContext: summary.activeContext,
      isLoading: false,
      isMutating: false,
      rawError: () => null,
    );
  }

  PersonaManagementItemViewData? _itemById(String personaId) {
    for (final item in state.items) {
      if (item.personaId == personaId) {
        return item;
      }
    }
    return null;
  }

  void _setPendingSyncSuggestion(
    PersonaManagementItemViewData source,
    List<String> changedFields,
  ) {
    final targets = <PersonaManagementItemViewData>[];
    for (final item in state.items) {
      if (item.personaId == source.personaId) {
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
      sourcePersonaId: source.personaId,
      sourceDisplayName: source.displayName,
      targetPersonaIds: targets.map((e) => e.personaId).toList(growable: false),
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
          'routeId': AppRoutePaths.profilePersonas,
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
