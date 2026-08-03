part of 'app_providers.dart';

class PersonalContentAccessState {
  const PersonalContentAccessState({
    required this.granted,
    required this.isHydrating,
    required this.isSyncing,
    required this.grantedScope,
    required this.source,
    this.updatedAt,
    this.errorMessage,
  });

  final bool granted;
  final bool isHydrating;
  final bool isSyncing;
  final String grantedScope;
  final String source;
  final DateTime? updatedAt;
  final String? errorMessage;

  String get summaryLabel => granted ? '已允许' : '未允许';

  PersonalContentAccessState copyWith({
    bool? granted,
    bool? isHydrating,
    bool? isSyncing,
    String? grantedScope,
    String? source,
    DateTime? updatedAt,
    String? errorMessage,
    bool clearError = false,
    bool clearUpdatedAt = false,
  }) {
    return PersonalContentAccessState(
      granted: granted ?? this.granted,
      isHydrating: isHydrating ?? this.isHydrating,
      isSyncing: isSyncing ?? this.isSyncing,
      grantedScope: grantedScope ?? this.grantedScope,
      source: source ?? this.source,
      updatedAt: clearUpdatedAt ? null : (updatedAt ?? this.updatedAt),
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
    );
  }

  factory PersonalContentAccessState.initial() {
    return const PersonalContentAccessState(
      granted: false,
      isHydrating: true,
      isSyncing: false,
      grantedScope: kPersonalContentAccessScope,
      source: 'bootstrap',
    );
  }
}

class PersonalContentAccessNotifier
    extends Notifier<PersonalContentAccessState> {
  bool _didScheduleHydration = false;

  @override
  PersonalContentAccessState build() {
    final initial = PersonalContentAccessState.initial();
    if (!_didScheduleHydration) {
      _didScheduleHydration = true;
      Future<void>.microtask(refresh);
    }
    return initial;
  }

  Future<void> refresh() async {
    state = state.copyWith(isHydrating: true, clearError: true);
    try {
      final consents = await ref
          .read(assistantSkillConsentFacetProvider)
          .listConsents();
      final current = consents.cast<SkillConsent?>().firstWhere(
        (item) => item?.skillId == kPersonalContentAccessSkillId,
        orElse: () => null,
      );
      if (current == null) {
        state = state.copyWith(
          granted: false,
          isHydrating: false,
          grantedScope: kPersonalContentAccessScope,
          source: 'repository',
          updatedAt: null,
          clearError: true,
        );
        return;
      }
      state = state.copyWith(
        granted:
            current.granted == true &&
            current.revokedAt == null &&
            current.grantedScopes.contains(kPersonalContentAccessScope),
        isHydrating: false,
        grantedScope: kPersonalContentAccessScope,
        source: 'repository',
        updatedAt: DateTime.tryParse(current.grantedAt)?.toUtc(),
        clearError: true,
      );
    } catch (error) {
      state = state.copyWith(
        granted: false,
        isHydrating: false,
        source: 'remote_unavailable',
        errorMessage: runtimeErrorDisplayMessage(error),
      );
    }
  }

  Future<void> setGranted(bool granted) async {
    state = state.copyWith(isSyncing: true, clearError: true);
    try {
      if (granted) {
        final consent = await ref
            .read(assistantSkillConsentFacetProvider)
            .grantSkillConsent(
              skillId: kPersonalContentAccessSkillId,
              grantedScopes: const <String>[kPersonalContentAccessScope],
              clientRequestId: const Uuid().v4(),
            );
        state = state.copyWith(
          granted:
              consent.granted == true &&
              consent.revokedAt == null &&
              consent.grantedScopes.contains(kPersonalContentAccessScope),
          grantedScope: kPersonalContentAccessScope,
          updatedAt: DateTime.tryParse(consent.grantedAt)?.toUtc(),
          source: 'repository',
          isHydrating: false,
          isSyncing: false,
          clearError: true,
        );
        return;
      }
      await ref
          .read(assistantSkillConsentFacetProvider)
          .revokeSkillConsent(
            skillId: kPersonalContentAccessSkillId,
            clientRequestId: const Uuid().v4(),
          );
      state = state.copyWith(
        granted: false,
        grantedScope: kPersonalContentAccessScope,
        clearUpdatedAt: true,
        source: 'repository',
        isHydrating: false,
        isSyncing: false,
        clearError: true,
      );
    } catch (error) {
      state = state.copyWith(
        isSyncing: false,
        errorMessage: runtimeErrorDisplayMessage(error),
      );
    }
  }
}
