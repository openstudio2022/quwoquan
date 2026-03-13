import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/providers/accessibility_provider.dart';
import 'package:quwoquan_app/cloud/services/user/appearance_settings_repository.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

class AppearanceSettingsState {
  const AppearanceSettingsState({
    required this.snapshot,
    this.isLoading = false,
    this.hasLoaded = false,
    this.pendingMutation,
    this.lastError,
  });

  factory AppearanceSettingsState.initial() {
    return AppearanceSettingsState(
      snapshot: AppearanceSettingsSnapshot(
        themeMode: AppearanceThemeMode.system,
        fontSizePreset: AppearanceFontSizePreset.md,
        source: AppearanceSettingsSource.systemDefault,
        ownerDefaultThemeMode: AppearanceThemeMode.system,
        ownerDefaultFontSizePreset: AppearanceFontSizePreset.md,
        hasSubAccountOverride: false,
        version: 0,
        updatedAt: DateTime.fromMillisecondsSinceEpoch(0),
      ),
    );
  }

  final AppearanceSettingsSnapshot snapshot;
  final bool isLoading;
  final bool hasLoaded;
  final AppearanceSettingsMutation? pendingMutation;
  final Object? lastError;

  bool get hasPendingSync => pendingMutation != null || snapshot.pendingSync;

  AppearanceSettingsState copyWith({
    AppearanceSettingsSnapshot? snapshot,
    bool? isLoading,
    bool? hasLoaded,
    AppearanceSettingsMutation? pendingMutation,
    bool clearPendingMutation = false,
    Object? lastError,
    bool clearLastError = false,
  }) {
    return AppearanceSettingsState(
      snapshot: snapshot ?? this.snapshot,
      isLoading: isLoading ?? this.isLoading,
      hasLoaded: hasLoaded ?? this.hasLoaded,
      pendingMutation: clearPendingMutation
          ? null
          : (pendingMutation ?? this.pendingMutation),
      lastError: clearLastError ? null : (lastError ?? this.lastError),
    );
  }
}

final appearanceSettingsControllerProvider =
    NotifierProvider<
      AppearanceSettingsController,
      AppearanceSettingsState
    >(AppearanceSettingsController.new);

class AppearanceSettingsController extends Notifier<AppearanceSettingsState> {
  bool _ensureLoadStarted = false;

  @override
  AppearanceSettingsState build() {
    final initial = AppearanceSettingsState.initial();
    if (!_ensureLoadStarted) {
      _ensureLoadStarted = true;
      Future<void>.microtask(ensureLoaded);
    }
    return initial;
  }

  Future<void> ensureLoaded() async {
    if (state.hasLoaded || state.isLoading) {
      return;
    }
    await load();
  }

  Future<void> load() async {
    state = state.copyWith(isLoading: true, clearLastError: true);
    try {
      final snapshot = await ref
          .read(appearanceSettingsRepositoryProvider)
          .getAppearanceSettings();
      _commitRemoteSnapshot(snapshot);
    } catch (error) {
      state = state.copyWith(
        isLoading: false,
        hasLoaded: true,
        lastError: error,
      );
    }
  }

  Future<void> refresh() async {
    if (state.pendingMutation != null) {
      await syncPending();
      return;
    }
    await load();
  }

  Future<void> updateSettings({
    AppearanceThemeMode? themeMode,
    AppearanceFontSizePreset? fontSizePreset,
    required AppearanceApplyScope applyScope,
  }) async {
    final current = state.snapshot;
    final mutation = AppearanceSettingsMutation(
      themeMode: themeMode ?? current.themeMode,
      fontSizePreset: fontSizePreset ?? current.fontSizePreset,
      applyScope: applyScope,
    );
    final optimisticSnapshot = _buildOptimisticSnapshot(
      current: current,
      mutation: mutation,
    );
    _applySnapshotToRuntime(optimisticSnapshot);
    state = state.copyWith(
      snapshot: optimisticSnapshot,
      pendingMutation: mutation,
      clearLastError: true,
      hasLoaded: true,
    );

    try {
      final remoteSnapshot = await ref
          .read(appearanceSettingsRepositoryProvider)
          .updateAppearanceSettings(mutation);
      _commitRemoteSnapshot(remoteSnapshot);
    } catch (error) {
      state = state.copyWith(
        snapshot: optimisticSnapshot.copyWith(pendingSync: true),
        pendingMutation: mutation,
        lastError: error,
        isLoading: false,
        hasLoaded: true,
      );
    }
  }

  Future<void> inheritOwnerDefault() async {
    await updateSettings(
      themeMode: state.snapshot.ownerDefaultThemeMode,
      fontSizePreset: state.snapshot.ownerDefaultFontSizePreset,
      applyScope: AppearanceApplyScope.inheritOwnerDefault,
    );
  }

  Future<void> syncPending() async {
    final mutation = state.pendingMutation;
    if (mutation == null) {
      return;
    }
    state = state.copyWith(isLoading: true, clearLastError: true);
    try {
      final remoteSnapshot = await ref
          .read(appearanceSettingsRepositoryProvider)
          .updateAppearanceSettings(mutation);
      _commitRemoteSnapshot(remoteSnapshot);
    } catch (error) {
      state = state.copyWith(
        isLoading: false,
        hasLoaded: true,
        lastError: error,
      );
    }
  }

  AppearanceSettingsSnapshot _buildOptimisticSnapshot({
    required AppearanceSettingsSnapshot current,
    required AppearanceSettingsMutation mutation,
  }) {
    final now = DateTime.now();
    switch (mutation.applyScope) {
      case AppearanceApplyScope.allAccounts:
        return current.copyWith(
          themeMode: mutation.themeMode,
          fontSizePreset: mutation.fontSizePreset,
          source: AppearanceSettingsSource.ownerDefault,
          ownerDefaultThemeMode: mutation.themeMode,
          ownerDefaultFontSizePreset: mutation.fontSizePreset,
          hasSubAccountOverride: false,
          version: current.version + 1,
          updatedAt: now,
          pendingSync: true,
        );
      case AppearanceApplyScope.currentSubAccount:
        return current.copyWith(
          themeMode: mutation.themeMode,
          fontSizePreset: mutation.fontSizePreset,
          source: AppearanceSettingsSource.subOverride,
          hasSubAccountOverride: true,
          version: current.version + 1,
          updatedAt: now,
          pendingSync: true,
        );
      case AppearanceApplyScope.inheritOwnerDefault:
        return current.copyWith(
          themeMode: current.ownerDefaultThemeMode,
          fontSizePreset: current.ownerDefaultFontSizePreset,
          source: AppearanceSettingsSource.ownerDefault,
          hasSubAccountOverride: false,
          version: current.version + 1,
          updatedAt: now,
          pendingSync: true,
        );
    }
  }

  void _commitRemoteSnapshot(AppearanceSettingsSnapshot snapshot) {
    _applySnapshotToRuntime(snapshot);
    state = state.copyWith(
      snapshot: snapshot.copyWith(pendingSync: false),
      isLoading: false,
      hasLoaded: true,
      clearPendingMutation: true,
      clearLastError: true,
    );
  }

  void _applySnapshotToRuntime(AppearanceSettingsSnapshot snapshot) {
    ref
        .read(themeProvider.notifier)
        .setThemeModeSetting(snapshot.themeMode.toAppThemeModeSetting());
    ref
        .read(accessibilityProvider.notifier)
        .setFontSizePreset(snapshot.fontSizePreset.toAppFontSizePreset());
  }
}

extension on AppearanceThemeMode {
  AppThemeModeSetting toAppThemeModeSetting() {
    return switch (this) {
      AppearanceThemeMode.system => AppThemeModeSetting.system,
      AppearanceThemeMode.light => AppThemeModeSetting.light,
      AppearanceThemeMode.dark => AppThemeModeSetting.dark,
    };
  }
}

extension on AppearanceFontSizePreset {
  AppFontSizePreset toAppFontSizePreset() {
    return switch (this) {
      AppearanceFontSizePreset.xs => AppFontSizePreset.xs,
      AppearanceFontSizePreset.sm => AppFontSizePreset.sm,
      AppearanceFontSizePreset.md => AppFontSizePreset.md,
      AppearanceFontSizePreset.lg => AppFontSizePreset.lg,
      AppearanceFontSizePreset.xl => AppFontSizePreset.xl,
    };
  }
}
