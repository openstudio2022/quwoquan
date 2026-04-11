import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/appearance_settings_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';

enum AppearanceThemeMode {
  system('system'),
  light('light'),
  dark('dark');

  const AppearanceThemeMode(this.wireValue);

  final String wireValue;

  static AppearanceThemeMode fromWire(String? value) {
    return AppearanceThemeMode.values.firstWhere(
      (mode) => mode.wireValue == value,
      orElse: () => AppearanceThemeMode.system,
    );
  }
}

enum AppearanceFontSizePreset {
  xs('xs'),
  sm('sm'),
  md('md'),
  lg('lg'),
  xl('xl');

  const AppearanceFontSizePreset(this.wireValue);

  final String wireValue;

  static AppearanceFontSizePreset fromWire(String? value) {
    return AppearanceFontSizePreset.values.firstWhere(
      (preset) => preset.wireValue == value,
      orElse: () => AppearanceFontSizePreset.md,
    );
  }
}

enum AppearanceSettingsSource {
  ownerDefault('owner_default'),
  subOverride('sub_override'),
  systemDefault('system_default');

  const AppearanceSettingsSource(this.wireValue);

  final String wireValue;

  static AppearanceSettingsSource fromWire(String? value) {
    return AppearanceSettingsSource.values.firstWhere(
      (source) => source.wireValue == value,
      orElse: () => AppearanceSettingsSource.systemDefault,
    );
  }
}

enum AppearanceApplyScope {
  allAccounts('all_accounts'),
  currentSubAccount('current_sub_account'),
  inheritOwnerDefault('inherit_owner_default');

  const AppearanceApplyScope(this.wireValue);

  final String wireValue;
}

class AppearanceSettingsSnapshot {
  const AppearanceSettingsSnapshot({
    required this.themeMode,
    required this.fontSizePreset,
    required this.source,
    required this.ownerDefaultThemeMode,
    required this.ownerDefaultFontSizePreset,
    required this.hasSubAccountOverride,
    required this.version,
    required this.updatedAt,
    this.pendingSync = false,
  });

  final AppearanceThemeMode themeMode;
  final AppearanceFontSizePreset fontSizePreset;
  final AppearanceSettingsSource source;
  final AppearanceThemeMode ownerDefaultThemeMode;
  final AppearanceFontSizePreset ownerDefaultFontSizePreset;
  final bool hasSubAccountOverride;
  final int version;
  final DateTime updatedAt;
  final bool pendingSync;

  factory AppearanceSettingsSnapshot.fromAppearanceSettingsWire(
    AppearanceSettingsWireDto w,
  ) {
    return AppearanceSettingsSnapshot(
      themeMode: AppearanceThemeMode.fromWire(w.themeMode),
      fontSizePreset: AppearanceFontSizePreset.fromWire(w.fontSizePreset),
      source: AppearanceSettingsSource.fromWire(w.source),
      ownerDefaultThemeMode: AppearanceThemeMode.fromWire(
        w.ownerDefaultThemeMode,
      ),
      ownerDefaultFontSizePreset: AppearanceFontSizePreset.fromWire(
        w.ownerDefaultFontSizePreset,
      ),
      hasSubAccountOverride: w.hasSubAccountOverride,
      version: w.version,
      updatedAt: w.updatedAt,
    );
  }

  factory AppearanceSettingsSnapshot.fromJson(Map<String, dynamic> json) {
    return AppearanceSettingsSnapshot.fromAppearanceSettingsWire(
      AppearanceSettingsWireDto.fromMap(json),
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'themeMode': themeMode.wireValue,
        'fontSizePreset': fontSizePreset.wireValue,
        'source': source.wireValue,
        'ownerDefaultThemeMode': ownerDefaultThemeMode.wireValue,
        'ownerDefaultFontSizePreset': ownerDefaultFontSizePreset.wireValue,
        'hasSubAccountOverride': hasSubAccountOverride,
        'version': version,
        'updatedAt': updatedAt.toIso8601String(),
      };

  AppearanceSettingsSnapshot copyWith({
    AppearanceThemeMode? themeMode,
    AppearanceFontSizePreset? fontSizePreset,
    AppearanceSettingsSource? source,
    AppearanceThemeMode? ownerDefaultThemeMode,
    AppearanceFontSizePreset? ownerDefaultFontSizePreset,
    bool? hasSubAccountOverride,
    int? version,
    DateTime? updatedAt,
    bool? pendingSync,
  }) {
    return AppearanceSettingsSnapshot(
      themeMode: themeMode ?? this.themeMode,
      fontSizePreset: fontSizePreset ?? this.fontSizePreset,
      source: source ?? this.source,
      ownerDefaultThemeMode:
          ownerDefaultThemeMode ?? this.ownerDefaultThemeMode,
      ownerDefaultFontSizePreset:
          ownerDefaultFontSizePreset ?? this.ownerDefaultFontSizePreset,
      hasSubAccountOverride:
          hasSubAccountOverride ?? this.hasSubAccountOverride,
      version: version ?? this.version,
      updatedAt: updatedAt ?? this.updatedAt,
      pendingSync: pendingSync ?? this.pendingSync,
    );
  }
}

class AppearanceSettingsMutation {
  const AppearanceSettingsMutation({
    required this.themeMode,
    required this.fontSizePreset,
    required this.applyScope,
  });

  final AppearanceThemeMode themeMode;
  final AppearanceFontSizePreset fontSizePreset;
  final AppearanceApplyScope applyScope;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'themeMode': themeMode.wireValue,
        'fontSizePreset': fontSizePreset.wireValue,
        'applyScope': applyScope.wireValue,
      };
}

abstract class AppearanceSettingsRepository {
  Future<AppearanceSettingsSnapshot> getAppearanceSettings();

  Future<AppearanceSettingsSnapshot> updateAppearanceSettings(
    AppearanceSettingsMutation mutation,
  );
}

class MockAppearanceSettingsRepository implements AppearanceSettingsRepository {
  AppearanceThemeMode _ownerDefaultThemeMode = AppearanceThemeMode.system;
  AppearanceFontSizePreset _ownerDefaultFontSizePreset =
      AppearanceFontSizePreset.md;
  AppearanceThemeMode? _themeModeOverride;
  AppearanceFontSizePreset? _fontSizePresetOverride;
  int _version = 1;
  DateTime _updatedAt = DateTime.utc(2026, 1, 1);

  @override
  Future<AppearanceSettingsSnapshot> getAppearanceSettings() async {
    return _buildSnapshot();
  }

  @override
  Future<AppearanceSettingsSnapshot> updateAppearanceSettings(
    AppearanceSettingsMutation mutation,
  ) async {
    switch (mutation.applyScope) {
      case AppearanceApplyScope.allAccounts:
        _ownerDefaultThemeMode = mutation.themeMode;
        _ownerDefaultFontSizePreset = mutation.fontSizePreset;
        _themeModeOverride = null;
        _fontSizePresetOverride = null;
        break;
      case AppearanceApplyScope.currentSubAccount:
        _themeModeOverride = mutation.themeMode;
        _fontSizePresetOverride = mutation.fontSizePreset;
        break;
      case AppearanceApplyScope.inheritOwnerDefault:
        _themeModeOverride = null;
        _fontSizePresetOverride = null;
        break;
    }
    _version += 1;
    _updatedAt = DateTime.now();
    return _buildSnapshot();
  }

  AppearanceSettingsSnapshot _buildSnapshot() {
    final hasOverride =
        _themeModeOverride != null || _fontSizePresetOverride != null;
    return AppearanceSettingsSnapshot(
      themeMode: _themeModeOverride ?? _ownerDefaultThemeMode,
      fontSizePreset: _fontSizePresetOverride ?? _ownerDefaultFontSizePreset,
      source: hasOverride
          ? AppearanceSettingsSource.subOverride
          : AppearanceSettingsSource.ownerDefault,
      ownerDefaultThemeMode: _ownerDefaultThemeMode,
      ownerDefaultFontSizePreset: _ownerDefaultFontSizePreset,
      hasSubAccountOverride: hasOverride,
      version: _version,
      updatedAt: _updatedAt,
    );
  }
}

class RemoteAppearanceSettingsRepository
    implements AppearanceSettingsRepository {
  RemoteAppearanceSettingsRepository({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final http.Client _client;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  Map<String, String> get _getHeaders =>
      CloudRequestHeaders.forPage(UserRequestPageIds.getAppearanceSettings);

  Map<String, String> get _patchHeaders => <String, String>{
        ...CloudRequestHeaders.forPage(
          UserRequestPageIds.updateAppearanceSettings,
        ),
        'Content-Type': 'application/json',
      };

  @override
  Future<AppearanceSettingsSnapshot> getAppearanceSettings() async {
    final resp = await _client.get(
      _uri(UserApiMetadata.getAppearanceSettingsPath),
      headers: _getHeaders,
    );
    if (resp.statusCode == 200) {
      return AppearanceSettingsSnapshot.fromJson(
        CloudResponseDecoder.asObject(
          jsonDecode(resp.body),
          context: UserRequestPageIds.getAppearanceSettings,
        ),
      );
    }
    throw Exception('GetAppearanceSettings failed: ${resp.statusCode}');
  }

  @override
  Future<AppearanceSettingsSnapshot> updateAppearanceSettings(
    AppearanceSettingsMutation mutation,
  ) async {
    final resp = await _client.patch(
      _uri(UserApiMetadata.updateAppearanceSettingsPath),
      headers: _patchHeaders,
      body: jsonEncode(mutation.toJson()),
    );
    if (resp.statusCode == 200) {
      return AppearanceSettingsSnapshot.fromJson(
        CloudResponseDecoder.asObject(
          jsonDecode(resp.body),
          context: UserRequestPageIds.updateAppearanceSettings,
        ),
      );
    }
    throw Exception('UpdateAppearanceSettings failed: ${resp.statusCode}');
  }
}
