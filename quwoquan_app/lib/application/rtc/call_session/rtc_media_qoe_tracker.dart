enum RtcMediaQoeResult {
  completed('completed'),
  connectFailed('connect_failed'),
  connectionLost('connection_lost'),
  abandoned('abandoned');

  const RtcMediaQoeResult(this.wireValue);

  final String wireValue;
}

enum RtcMediaDisconnectReason {
  endpointUnavailable('endpoint_unavailable'),
  connectFailed('connect_failed'),
  unexpectedDisconnect('unexpected_disconnect');

  const RtcMediaDisconnectReason(this.wireValue);

  final String wireValue;
}

enum RtcMediaNetworkQuality {
  excellent('excellent'),
  good('good'),
  poor('poor'),
  unknown('unknown');

  const RtcMediaNetworkQuality(this.wireValue);

  final String wireValue;
}

final class RtcMediaQoeTerminal {
  const RtcMediaQoeTerminal({
    required this.callType,
    required this.result,
    required this.connectTimeMs,
    required this.mediaConnected,
    required this.reconnectCount,
    required this.networkQuality,
    required this.participantCount,
    this.disconnectReason,
    this.failReasonCode,
  });

  final String callType;
  final RtcMediaQoeResult result;
  final int connectTimeMs;
  final bool mediaConnected;
  final int reconnectCount;
  final RtcMediaNetworkQuality networkQuality;
  final int participantCount;
  final RtcMediaDisconnectReason? disconnectReason;
  final String? failReasonCode;
}

/// 单次通话媒体 QoE 的内存状态机。
///
/// CallSession 仍是业务生命周期真相源；本对象只把一个客户端媒体尝试压缩成一个
/// 低基数终态事件。重复结束、重复信令和重连不会产生第二条终态记录。
final class RtcMediaQoeTracker {
  RtcMediaQoeTracker({DateTime Function()? now}) : _now = now ?? DateTime.now;

  final DateTime Function() _now;

  String? _callId;
  DateTime? _connectStartedAt;
  int _connectTimeMs = 0;
  int _reconnectCount = 0;
  RtcMediaNetworkQuality _networkQuality = RtcMediaNetworkQuality.unknown;
  RtcMediaDisconnectReason? _disconnectReason;
  bool _attempted = false;
  bool _connected = false;
  bool _reported = false;

  void beginAttempt(String callId) {
    if (_callId != callId) {
      _reset(callId);
    }
    _attempted = true;
    _connectStartedAt ??= _now();
  }

  void markMediaConnected() {
    if (!_attempted || _connected) return;
    _connected = true;
    _disconnectReason = null;
    _connectTimeMs = _now()
        .difference(_connectStartedAt ?? _now())
        .inMilliseconds;
  }

  void markReconnectStarted() {
    if (_attempted) {
      _reconnectCount += 1;
    }
  }

  void markReconnectRecovered() {
    if (_connected &&
        _disconnectReason == RtcMediaDisconnectReason.unexpectedDisconnect) {
      _disconnectReason = null;
    }
  }

  void updateNetworkQuality(RtcMediaNetworkQuality quality) {
    if (_attempted) {
      _networkQuality = quality;
    }
  }

  void markDisconnect(RtcMediaDisconnectReason reason) {
    if (_attempted) {
      _disconnectReason = reason;
    }
  }

  RtcMediaQoeTerminal? finish({
    required String callId,
    required String callType,
    required int participantCount,
    required bool abandonedBeforeAcceptance,
    bool aggregateReachedInCall = false,
    String? failReasonCode,
  }) {
    if (!_attempted || _reported || _callId != callId) {
      return null;
    }
    if (!_connected && aggregateReachedInCall) {
      markMediaConnected();
    }
    _reported = true;
    final result = abandonedBeforeAcceptance
        ? RtcMediaQoeResult.abandoned
        : !_connected
        ? RtcMediaQoeResult.connectFailed
        : _disconnectReason == RtcMediaDisconnectReason.unexpectedDisconnect
        ? RtcMediaQoeResult.connectionLost
        : RtcMediaQoeResult.completed;
    return RtcMediaQoeTerminal(
      callType: callType,
      result: result,
      connectTimeMs: _connectTimeMs,
      mediaConnected: _connected,
      reconnectCount: _reconnectCount,
      networkQuality: _networkQuality,
      participantCount: participantCount,
      disconnectReason: _disconnectReason,
      failReasonCode: _connected ? null : failReasonCode,
    );
  }

  void _reset(String callId) {
    _callId = callId;
    _connectStartedAt = null;
    _connectTimeMs = 0;
    _reconnectCount = 0;
    _networkQuality = RtcMediaNetworkQuality.unknown;
    _disconnectReason = null;
    _attempted = false;
    _connected = false;
    _reported = false;
  }
}
