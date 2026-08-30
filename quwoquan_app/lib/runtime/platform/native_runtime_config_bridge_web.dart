import 'dart:convert';
import 'dart:js_interop';

@JS('__qwqReadRuntimeConfigPackage')
external JSString? _readRuntimeConfigPackage();

Map<String, Object?>? readVerifiedRuntimeConfigPackage() {
  final raw = _readRuntimeConfigPackage()?.toDart;
  if (raw == null) {
    return null;
  }
  final decoded = jsonDecode(raw);
  if (decoded is! Map) {
    throw const FormatException('runtime config package must be an object');
  }
  return Map<String, Object?>.from(decoded);
}
