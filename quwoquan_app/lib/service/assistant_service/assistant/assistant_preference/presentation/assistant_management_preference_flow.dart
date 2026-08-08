part of 'assistant_management_page.dart';

sealed class _AssistantPreferenceMutationAttempt {
  const _AssistantPreferenceMutationAttempt();

  Future<AssistantPreference> execute(AssistantPreferenceFacet facet);

  bool acceptsResult(AssistantPreference result);

  bool isReflectedBy(
    AssistantPreference result,
    List<AssistantPreference> canonical,
  );

  bool canonicalContains(
    AssistantPreference result,
    List<AssistantPreference> canonical,
    AssistantPreferenceStatus status,
  ) {
    return canonical.any(
      (item) =>
          item.preferenceId == result.preferenceId && item.status == status,
    );
  }
}

final class _SetAssistantPreferenceAttempt
    extends _AssistantPreferenceMutationAttempt {
  const _SetAssistantPreferenceAttempt({
    required this.kind,
    required this.value,
  });

  final AssistantPreferenceKind kind;
  final String value;

  @override
  Future<AssistantPreference> execute(AssistantPreferenceFacet facet) {
    return facet.setAssistantPreference(
      scope: AssistantPreferenceScope.longTerm,
      kind: kind,
      value: value,
      sourceType: AssistantPreferenceSourceType.management,
    );
  }

  @override
  bool acceptsResult(AssistantPreference result) {
    return result.preferenceId.trim().isNotEmpty &&
        result.scope == AssistantPreferenceScope.longTerm &&
        result.kind == kind &&
        result.value == value &&
        result.status == AssistantPreferenceStatus.active;
  }

  @override
  bool isReflectedBy(
    AssistantPreference result,
    List<AssistantPreference> canonical,
  ) {
    return canonicalContains(
      result,
      canonical,
      AssistantPreferenceStatus.active,
    );
  }
}

final class _RevokeAssistantPreferenceAttempt
    extends _AssistantPreferenceMutationAttempt {
  const _RevokeAssistantPreferenceAttempt({required this.preferenceId});

  final String preferenceId;

  @override
  Future<AssistantPreference> execute(AssistantPreferenceFacet facet) {
    return facet.revokeAssistantPreference(preferenceId: preferenceId);
  }

  @override
  bool acceptsResult(AssistantPreference result) {
    return result.preferenceId == preferenceId &&
        result.status == AssistantPreferenceStatus.revoked;
  }

  @override
  bool isReflectedBy(
    AssistantPreference result,
    List<AssistantPreference> canonical,
  ) {
    return canonicalContains(
          result,
          canonical,
          AssistantPreferenceStatus.revoked,
        ) &&
        !canonical.any(
          (item) =>
              item.preferenceId == preferenceId &&
              item.status == AssistantPreferenceStatus.active,
        );
  }
}

final class _RestoreAssistantPreferenceAttempt
    extends _AssistantPreferenceMutationAttempt {
  const _RestoreAssistantPreferenceAttempt({required this.preferenceId});

  final String preferenceId;

  @override
  Future<AssistantPreference> execute(AssistantPreferenceFacet facet) {
    return facet.restoreAssistantPreference(preferenceId: preferenceId);
  }

  @override
  bool acceptsResult(AssistantPreference result) {
    return result.preferenceId == preferenceId &&
        result.status == AssistantPreferenceStatus.active;
  }

  @override
  bool isReflectedBy(
    AssistantPreference result,
    List<AssistantPreference> canonical,
  ) {
    return canonicalContains(
          result,
          canonical,
          AssistantPreferenceStatus.active,
        ) &&
        !canonical.any(
          (item) =>
              item.preferenceId == preferenceId &&
              item.status == AssistantPreferenceStatus.revoked,
        );
  }
}

mixin _AssistantManagementPreferenceFlow
    on ConsumerState<AssistantManagementPage> {
  List<AssistantPreference>? _lastConfirmedPreferences;
  _AssistantPreferenceMutationAttempt? _pendingPreferenceMutation;
  Object? _preferenceReadError;
  Object? _preferenceMutationError;
  bool _preferenceReadInFlight = false;
  bool _preferenceMutationInFlight = false;

  bool get _preferenceActionsBlocked =>
      _lastConfirmedPreferences == null ||
      _preferenceReadInFlight ||
      _preferenceMutationInFlight ||
      _pendingPreferenceMutation != null;

  Future<List<AssistantPreference>> _fetchAssistantPreferences() async {
    return loadAssistantPreferences(ref.read(assistantPreferenceFacetProvider));
  }

  Future<void> _readAssistantPreferences() async {
    if (_preferenceReadInFlight || _preferenceMutationInFlight) return;
    setState(() {
      _preferenceReadInFlight = true;
      _preferenceReadError = null;
    });
    try {
      final preferences = await _fetchAssistantPreferences();
      if (!mounted) return;
      setState(() {
        _lastConfirmedPreferences = preferences;
        _preferenceReadError = null;
        _preferenceReadInFlight = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _preferenceReadError = error;
        _preferenceReadInFlight = false;
      });
    }
  }

  Future<void> _startPreferenceMutation(
    _AssistantPreferenceMutationAttempt attempt,
  ) async {
    if (_preferenceActionsBlocked) return;
    _pendingPreferenceMutation = attempt;
    await _executePendingPreferenceMutation();
  }

  Future<void> _retryPendingPreferenceMutation() async {
    if (_preferenceMutationInFlight || _preferenceReadInFlight) return;
    await _executePendingPreferenceMutation();
  }

  Future<void> _executePendingPreferenceMutation() async {
    final attempt = _pendingPreferenceMutation;
    if (attempt == null || _preferenceMutationInFlight) return;
    setState(() {
      _preferenceMutationInFlight = true;
      _preferenceMutationError = null;
      _preferenceReadError = null;
    });
    try {
      final result = await attempt.execute(
        ref.read(assistantPreferenceFacetProvider),
      );
      if (!attempt.acceptsResult(result)) {
        throw StateError(
          'AssistantPreference mutation returned a mismatched typed result',
        );
      }
      final canonical = await _fetchAssistantPreferences();
      if (!attempt.isReflectedBy(result, canonical)) {
        throw StateError(
          'AssistantPreference mutation did not converge in canonical list',
        );
      }
      if (!mounted || !identical(_pendingPreferenceMutation, attempt)) return;
      setState(() {
        _lastConfirmedPreferences = canonical;
        _pendingPreferenceMutation = null;
        _preferenceMutationError = null;
        _preferenceMutationInFlight = false;
      });
    } catch (error) {
      if (!mounted || !identical(_pendingPreferenceMutation, attempt)) return;
      setState(() {
        _preferenceMutationError = error;
        _preferenceMutationInFlight = false;
      });
    }
  }
}
