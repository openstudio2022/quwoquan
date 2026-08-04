import '../../../../cloud/runtime/codec/cloud_wire_json_types.dart';
import '../../../../cloud/runtime/errors/cloud_error_mapper.dart';
import '../../../../cloud/runtime/errors/cloud_exception.dart';

/// Entity Homepage JSON 子树收窄。
///
/// 该编解码逻辑属于 Cloud wire 边界；generated Homepage DTO 与 Remote
/// adapter 共同消费，不能反向依赖具体服务 adapter。
abstract final class HomepageWireCodec {
  HomepageWireCodec._();

  /// 缺省时返回空 Map；存在但不是对象时拒绝 wire 响应。
  static CloudJsonMap stringKeyMapOrEmpty(Object? value) {
    if (value == null) {
      return const <String, dynamic>{};
    }
    if (value is! Map) {
      throw _invalid('Expected object');
    }
    return Map<String, dynamic>.from(value);
  }

  /// 缺省时返回空列表；存在但不是列表或含坏元素时拒绝 wire 响应。
  static List<T> mapList<T>(Object? raw, T Function(CloudJsonMap m) build) {
    if (raw == null) {
      return List<T>.empty(growable: false);
    }
    if (raw is! List) {
      throw _invalid('Expected list');
    }
    final out = <T>[];
    for (var index = 0; index < raw.length; index++) {
      final item = raw[index];
      if (item is! Map) {
        throw _invalid('Expected object list element at index $index');
      }
      out.add(build(Map<String, dynamic>.from(item)));
    }
    return out;
  }

  /// 空串与仅空白视为 null。
  static String? optionalTrimmedString(Object? value) {
    if (value == null) {
      return null;
    }
    if (value is! String) {
      throw _invalid('Expected string');
    }
    final raw = value.trim();
    return raw.isEmpty ? null : raw;
  }

  static double? optionalDouble(Object? value) {
    if (value == null) {
      return null;
    }
    if (value is! num) {
      throw _invalid('Expected number');
    }
    return value.toDouble();
  }

  static DateTime? optionalDateTime(Object? value) {
    if (value == null) {
      return null;
    }
    if (value is! String) {
      throw _invalid('Expected ISO-8601 string');
    }
    final raw = value.trim();
    if (raw.isEmpty) {
      return null;
    }
    final parsed = DateTime.tryParse(raw);
    if (parsed == null) {
      throw _invalid('Invalid ISO-8601 date-time');
    }
    return parsed;
  }

  static CloudException _invalid(String message) {
    return CloudErrorMapper.invalidResponse(
      message: message,
      functionModule: 'homepage_wire_codec',
    );
  }
}
