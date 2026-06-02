import 'dart:math';

class AppTraceContextStore {
  AppTraceContextStore._();

  static final AppTraceContextStore instance = AppTraceContextStore._();
  final Random _random = Random();

  String? _sessionId;

  String get sessionId => _sessionId ??= _newId('sess');

  /// 隐私安全的派生设备标识（installId hash 派生，非原始设备 ID）。
  /// 由鉴权会话恢复时设置一次；用于游客设备态点赞/分享的设备维度统一标识，
  /// 经 `X-Client-Device-Actor-Id` 随请求注入。未设置时不注入设备头。
  String? _deviceActorId;

  String? get deviceActorId => _deviceActorId;

  set deviceActorId(String? value) {
    final trimmed = value?.trim();
    _deviceActorId = (trimmed == null || trimmed.isEmpty) ? null : trimmed;
  }

  String newPageVisitId() => _newId('visit');
  String newRequestId() => _newId('req');

  String _newId(String prefix) {
    final ts = DateTime.now().millisecondsSinceEpoch;
    final r = _random.nextInt(0xFFFFFF).toRadixString(16).padLeft(6, '0');
    return '${prefix}_$ts$r';
  }
}
