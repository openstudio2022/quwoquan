import 'package:quwoquan_app/assistant/intent_bridge/assistant_intent_bridge_runtime.dart';
import 'package:quwoquan_app/assistant/tool/impl/device/local_context_tool_contract.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

class LocalContextTool implements AssistantTool {
  LocalContextTool(this._channelAdapter);

  final MethodChannelAdapter _channelAdapter;

  @override
  String get name => 'local_context';

  @override
  String get description => '获取设备上下文与地理位置信息（不包含相册数据）。';

  @override
  Future<AssistantToolResult> execute(AssistantToolArguments arguments) async {
    final request = LocalContextToolArgumentsContract.fromAssistantArguments(
      arguments,
    );
    final result = await _channelAdapter.invoke(
      'getLocalContext',
      request.toAssistantArguments().toDynamicJson(),
    );
    if (result.containsKey('error')) {
      final failure = LocalContextToolFailureData(
        userMessage: '本地上下文暂不可用',
        internalError: (result['error'] ?? '').toString().trim(),
      );
      return AssistantToolResult(
        success: false,
        message: failure.userMessage,
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
        data: failure.toResultData(),
      );
    }
    final normalized = _normalizeContextResult(result);
    final city = normalized.city.trim();
    final message = city.isEmpty
        ? 'Local context fetched'
        : 'Local context fetched: city=$city';
    return AssistantToolResult(
      success: true,
      message: message,
      data: normalized.toResultData(),
    );
  }

  LocalContextToolSuccessData _normalizeContextResult(Map<String, dynamic> raw) {
    final locationRaw = (raw['location'] as Map?)?.cast<String, dynamic>() ??
        (raw['gpsLocation'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final permissionsRaw =
        (raw['permissions'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final deviceRaw = (raw['device'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final city = _firstNonEmpty(<String?>[
      raw['city']?.toString(),
      locationRaw['city']?.toString(),
      raw['currentCity']?.toString(),
    ]);
    return LocalContextToolSuccessData(
      city: city,
      location: LocalContextLocationSnapshot(
        city: city,
        latitude: _toDouble(
          locationRaw['latitude']?.toString() ?? locationRaw['lat']?.toString(),
        ),
        longitude: _toDouble(
          locationRaw['longitude']?.toString() ?? locationRaw['lon']?.toString(),
        ),
        accuracyM: _toDouble(
          locationRaw['accuracyM']?.toString() ??
              locationRaw['accuracy']?.toString(),
        ),
        source: _firstNonEmpty(<String?>[
          locationRaw['source']?.toString(),
          raw['locationSource']?.toString(),
        ]),
      ),
      permissions: LocalContextPermissionSnapshot(
        location: _toBool(permissionsRaw['location']?.toString()),
        photos: _toBool(permissionsRaw['photos']?.toString()),
        camera: _toBool(permissionsRaw['camera']?.toString()),
        notification: _toBool(permissionsRaw['notification']?.toString()),
      ),
      device: LocalContextDeviceSnapshot(
        os: _firstNonEmpty(<String?>[
          deviceRaw['os']?.toString(),
          raw['os']?.toString(),
        ]),
        model: _firstNonEmpty(<String?>[
          deviceRaw['model']?.toString(),
          raw['model']?.toString(),
        ]),
        locale: _firstNonEmpty(<String?>[
          deviceRaw['locale']?.toString(),
          raw['locale']?.toString(),
        ]),
        timezone: _firstNonEmpty(<String?>[
          deviceRaw['timezone']?.toString(),
          raw['timezone']?.toString(),
        ]),
      ),
      // 显式声明边界：local_context 不返回相册内容。
      media: const LocalContextMediaBoundary(included: false),
    );
  }

  String _firstNonEmpty(List<String?> candidates) {
    for (final value in candidates) {
      final text = (value ?? '').trim();
      if (text.isNotEmpty) return text;
    }
    return '';
  }

  bool? _toBool(String? value) {
    final text = (value ?? '').trim().toLowerCase();
    if (text.isEmpty) return null;
    if (text == 'true' || text == '1' || text == 'granted') return true;
    if (text == 'false' || text == '0' || text == 'denied') return false;
    return null;
  }

  double? _toDouble(String? value) {
    final text = (value ?? '').trim();
    if (text.isEmpty) return null;
    return double.tryParse(text);
  }
}
