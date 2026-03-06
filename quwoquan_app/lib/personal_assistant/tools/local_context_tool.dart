import 'package:quwoquan_app/personal_assistant/intent_bridge/method_channel_adapter.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

class LocalContextTool implements AssistantTool {
  LocalContextTool(this._channelAdapter);

  final MethodChannelAdapter _channelAdapter;

  @override
  String get name => 'local_context';

  @override
  String get description => '获取设备上下文与地理位置信息（不包含相册数据）。';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final result = await _channelAdapter.invoke(
      'getLocalContext',
      arguments,
    );
    if (result.containsKey('error')) {
      return AssistantToolResult(
        success: false,
        message: 'Local context failed: ${result['error']}',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
      );
    }
    final normalized = _normalizeContextResult(result);
    final city = _extractCity(normalized);
    final message = city.isEmpty
        ? 'Local context fetched'
        : 'Local context fetched: city=$city';
    return AssistantToolResult(
      success: true,
      message: message,
      data: normalized,
    );
  }

  Map<String, dynamic> _normalizeContextResult(Map<String, dynamic> raw) {
    final locationRaw = (raw['location'] as Map?)?.cast<String, dynamic>() ??
        (raw['gpsLocation'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final permissionsRaw =
        (raw['permissions'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final deviceRaw = (raw['device'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final city = _firstNonEmpty(<Object?>[
      raw['city'],
      locationRaw['city'],
      raw['currentCity'],
    ]);
    return <String, dynamic>{
      'contextVersion': 'local_context_v1',
      'city': city,
      'location': <String, dynamic>{
        'city': city,
        'latitude': _toDouble(locationRaw['latitude'] ?? locationRaw['lat']),
        'longitude': _toDouble(locationRaw['longitude'] ?? locationRaw['lon']),
        'accuracyM':
            _toDouble(locationRaw['accuracyM'] ?? locationRaw['accuracy']),
        'source': _firstNonEmpty(<Object?>[
          locationRaw['source'],
          raw['locationSource'],
        ]),
      },
      'permissions': <String, dynamic>{
        'location': _toBool(permissionsRaw['location']),
        'photos': _toBool(permissionsRaw['photos']),
        'camera': _toBool(permissionsRaw['camera']),
        'notification': _toBool(permissionsRaw['notification']),
      },
      'device': <String, dynamic>{
        'os': _firstNonEmpty(<Object?>[deviceRaw['os'], raw['os']]),
        'model': _firstNonEmpty(<Object?>[deviceRaw['model'], raw['model']]),
        'locale': _firstNonEmpty(<Object?>[deviceRaw['locale'], raw['locale']]),
        'timezone': _firstNonEmpty(
          <Object?>[deviceRaw['timezone'], raw['timezone']],
        ),
      },
      // 显式声明边界：local_context 不返回相册内容。
      'media': const <String, dynamic>{'included': false},
    };
  }

  String _extractCity(Map<String, dynamic> data) {
    final top = (data['city'] ?? '').toString().trim();
    if (top.isNotEmpty) return top;
    final location = data['location'];
    if (location is Map) {
      final nested = (location['city'] ?? '').toString().trim();
      if (nested.isNotEmpty) return nested;
    }
    final gps = data['gpsLocation'];
    if (gps is Map) {
      final nested = (gps['city'] ?? '').toString().trim();
      if (nested.isNotEmpty) return nested;
    }
    return '';
  }

  String _firstNonEmpty(List<Object?> candidates) {
    for (final value in candidates) {
      final text = (value ?? '').toString().trim();
      if (text.isNotEmpty) return text;
    }
    return '';
  }

  bool? _toBool(Object? value) {
    if (value is bool) return value;
    if (value == null) return null;
    final text = value.toString().trim().toLowerCase();
    if (text == 'true' || text == '1' || text == 'granted') return true;
    if (text == 'false' || text == '0' || text == 'denied') return false;
    return null;
  }

  double? _toDouble(Object? value) {
    if (value is num) return value.toDouble();
    final parsed = double.tryParse((value ?? '').toString().trim());
    return parsed;
  }
}
