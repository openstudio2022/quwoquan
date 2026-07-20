import 'dart:math';

import 'package:quwoquan_app/core/telemetry/app_telemetry_session_store.dart';

class AppTraceContextStore {
  AppTraceContextStore._();

  static final AppTraceContextStore instance = AppTraceContextStore._();
  final Random _random = Random();
  late final String _localDiagnosticSessionId = _newId('local_session');

  String get sessionId {
    final telemetrySession = AppTelemetrySessionStore.instance;
    return telemetrySession.isInitialized
        ? telemetrySession.sessionId
        : _localDiagnosticSessionId;
  }

  /// 隐私安全的派生设备标识（installId hash 派生，非原始设备 ID）。
  /// 由鉴权会话恢复时设置一次；用于游客设备态点赞/分享的设备维度统一标识，
  /// 经 `X-Client-Device-Actor-Id` 随请求注入。未设置时不注入设备头。
  String? _deviceActorId;

  String? get deviceActorId => _deviceActorId;

  set deviceActorId(String? value) {
    final trimmed = value?.trim();
    _deviceActorId = (trimmed == null || trimmed.isEmpty) ? null : trimmed;
  }

  /// 灰度路由地域维度（GB/T 2260 六位省级码）。仅接受端侧真实来源
  /// （定位授权后的行政区划解析或云端网络探测回执）；无真实值时保持 null，
  /// 请求不携带 `X-Client-Region-Code`，地域维度对该设备不匹配。
  String? _grayRegionCode;

  String? get grayRegionCode => _grayRegionCode;

  set grayRegionCode(String? value) {
    final trimmed = value?.trim();
    _grayRegionCode =
        (trimmed == null || !RegExp(r'^[1-9][0-9]{5}$').hasMatch(trimmed))
            ? null
            : trimmed;
  }

  /// 灰度路由运营商维度（chinamobile/chinaunicom/chinatelecom/chinabroadnet）。
  /// 语义同 [grayRegionCode]：无真实来源时保持 null。
  String? _grayCarrier;

  String? get grayCarrier => _grayCarrier;

  static const Set<String> _allowedCarriers = {
    'chinamobile',
    'chinaunicom',
    'chinatelecom',
    'chinabroadnet',
  };

  set grayCarrier(String? value) {
    final trimmed = value?.trim();
    _grayCarrier =
        (trimmed == null || !_allowedCarriers.contains(trimmed)) ? null : trimmed;
  }

  /// 共享「当前页访问」上下文：每次铸造新的 page visit id 时同步更新，
  /// 供没有直接持有 visit id 的旁路埋点（如 [JourneyEventTracker]）按当前页归因。
  String? _currentPageVisitId;

  String? get currentPageVisitId => _currentPageVisitId;

  String newPageVisitId() {
    final id = _newId('visit');
    _currentPageVisitId = id;
    return id;
  }

  String newRequestId() => _newId('req');

  String _newId(String prefix) {
    final ts = DateTime.now().millisecondsSinceEpoch;
    final r = _random.nextInt(0xFFFFFF).toRadixString(16).padLeft(6, '0');
    return '${prefix}_$ts$r';
  }
}
