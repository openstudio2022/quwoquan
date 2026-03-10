import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';

class CallSettingsDto {
  const CallSettingsDto({
    required this.defaultIncomingCallRingtoneId,
    required this.allowCallerRingtoneOverride,
    required this.enableCallVibration,
    required this.enableGroupCallRing,
  });

  final String? defaultIncomingCallRingtoneId;
  final bool allowCallerRingtoneOverride;
  final bool enableCallVibration;
  final bool enableGroupCallRing;

  factory CallSettingsDto.fromMap(Map<String, dynamic> map) {
    return CallSettingsDto(
      defaultIncomingCallRingtoneId:
          map['defaultIncomingCallRingtoneId'] as String?,
      allowCallerRingtoneOverride:
          (map['allowCallerRingtoneOverride'] as bool?) ?? true,
      enableCallVibration: (map['enableCallVibration'] as bool?) ?? true,
      enableGroupCallRing: (map['enableGroupCallRing'] as bool?) ?? true,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      if (defaultIncomingCallRingtoneId != null)
        'defaultIncomingCallRingtoneId': defaultIncomingCallRingtoneId,
      'allowCallerRingtoneOverride': allowCallerRingtoneOverride,
      'enableCallVibration': enableCallVibration,
      'enableGroupCallRing': enableGroupCallRing,
    };
  }

  CallSettingsDto copyWith({
    String? defaultIncomingCallRingtoneId,
    bool? allowCallerRingtoneOverride,
    bool? enableCallVibration,
    bool? enableGroupCallRing,
  }) {
    return CallSettingsDto(
      defaultIncomingCallRingtoneId:
          defaultIncomingCallRingtoneId ?? this.defaultIncomingCallRingtoneId,
      allowCallerRingtoneOverride:
          allowCallerRingtoneOverride ?? this.allowCallerRingtoneOverride,
      enableCallVibration: enableCallVibration ?? this.enableCallVibration,
      enableGroupCallRing: enableGroupCallRing ?? this.enableGroupCallRing,
    );
  }
}

class OfficialCallRingtone {
  const OfficialCallRingtone({
    required this.id,
    required this.label,
    required this.callkitPath,
  });

  final String id;
  final String label;
  final String callkitPath;
}

abstract final class OfficialCallRingtoneCatalog {
  static const String defaultId = 'official.default';

  static const List<OfficialCallRingtone> items = <OfficialCallRingtone>[
    OfficialCallRingtone(
      id: defaultId,
      label: '趣聊默认',
      callkitPath: 'system_ringtone_default',
    ),
    OfficialCallRingtone(
      id: 'official.blue-wave',
      label: '蓝色回响',
      callkitPath: 'system_ringtone_default',
    ),
    OfficialCallRingtone(
      id: 'official.morning-light',
      label: '清晨微光',
      callkitPath: 'system_ringtone_default',
    ),
  ];

  static bool contains(String? id) {
    if (id == null || id.isEmpty) return false;
    return items.any((item) => item.id == id);
  }

  static String resolveCallkitPath(String? id) {
    final ringtone = items.where((item) => item.id == id).firstOrNull;
    return ringtone?.callkitPath ?? 'system_ringtone_default';
  }
}

abstract class CallSettingsRepository {
  Future<CallSettingsDto> getCallSettings();

  Future<CallSettingsDto> updateCallSettings(CallSettingsDto settings);

  List<OfficialCallRingtone> listOfficialRingtones();
}

class MockCallSettingsRepository implements CallSettingsRepository {
  CallSettingsDto _settings = const CallSettingsDto(
    defaultIncomingCallRingtoneId: OfficialCallRingtoneCatalog.defaultId,
    allowCallerRingtoneOverride: true,
    enableCallVibration: true,
    enableGroupCallRing: true,
  );

  @override
  Future<CallSettingsDto> getCallSettings() async => _settings;

  @override
  List<OfficialCallRingtone> listOfficialRingtones() =>
      OfficialCallRingtoneCatalog.items;

  @override
  Future<CallSettingsDto> updateCallSettings(CallSettingsDto settings) async {
    _settings = settings;
    return _settings;
  }
}

class RemoteCallSettingsRepository implements CallSettingsRepository {
  RemoteCallSettingsRepository({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final http.Client _client;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  Map<String, String> get _getHeaders =>
      CloudRequestHeaders.forPage(UserRequestPageIds.getCallSettings);

  Map<String, String> get _patchHeaders => <String, String>{
        ...CloudRequestHeaders.forPage(UserRequestPageIds.updateCallSettings),
        'Content-Type': 'application/json',
      };

  @override
  Future<CallSettingsDto> getCallSettings() async {
    final resp = await _client.get(
      _uri(UserApiMetadata.getCallSettingsPath),
      headers: _getHeaders,
    );
    if (resp.statusCode == 200) {
      return CallSettingsDto.fromMap(
        jsonDecode(resp.body) as Map<String, dynamic>,
      );
    }
    throw Exception('GetCallSettings failed: ${resp.statusCode}');
  }

  @override
  List<OfficialCallRingtone> listOfficialRingtones() =>
      OfficialCallRingtoneCatalog.items;

  @override
  Future<CallSettingsDto> updateCallSettings(CallSettingsDto settings) async {
    final resp = await _client.patch(
      _uri(UserApiMetadata.updateCallSettingsPath),
      headers: _patchHeaders,
      body: jsonEncode(settings.toMap()),
    );
    if (resp.statusCode == 200) {
      return CallSettingsDto.fromMap(
        jsonDecode(resp.body) as Map<String, dynamic>,
      );
    }
    throw Exception('UpdateCallSettings failed: ${resp.statusCode}');
  }
}
