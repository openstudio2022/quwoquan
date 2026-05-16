import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/realtime/realtime_api_metadata.g.dart';

/// Configuration for realtime transport layer.
/// In production, fetched from `GET /v1/config/realtime`.
class RealtimeConfig {
  final String wsUrl;
  final int heartbeatIntervalSec;
  final int wsIdleTimeoutSec;
  final int longPollHoldSec;
  final int maxReconnectAttempts;
  final int reconnectBaseDelayMs;
  final int reconnectMaxDelayMs;

  const RealtimeConfig({
    required this.wsUrl,
    this.heartbeatIntervalSec = 15,
    this.wsIdleTimeoutSec = 120,
    this.longPollHoldSec = 60,
    this.maxReconnectAttempts = 10,
    this.reconnectBaseDelayMs = 1000,
    this.reconnectMaxDelayMs = 30000,
  });

  factory RealtimeConfig.fromGateway() {
    final base = CloudRuntimeConfig.gatewayBaseUrl;
    final wsBase = base
        .replaceFirst('https://', 'wss://')
        .replaceFirst('http://', 'ws://');
    return RealtimeConfig(
      wsUrl: '$wsBase${RealtimeApiMetadata.webSocketUpgradePath}',
    );
  }

  factory RealtimeConfig.fromMap(Map<String, dynamic> map) {
    return RealtimeConfig(
      wsUrl: map['wsUrl'] as String? ?? '',
      heartbeatIntervalSec:
          (map['heartbeatIntervalSec'] as num?)?.toInt() ?? 15,
      wsIdleTimeoutSec: (map['wsIdleTimeoutSec'] as num?)?.toInt() ?? 120,
      longPollHoldSec: (map['longPollHoldSec'] as num?)?.toInt() ?? 60,
      maxReconnectAttempts:
          (map['maxReconnectAttempts'] as num?)?.toInt() ?? 10,
      reconnectBaseDelayMs:
          (map['reconnectBaseDelayMs'] as num?)?.toInt() ?? 1000,
      reconnectMaxDelayMs:
          (map['reconnectMaxDelayMs'] as num?)?.toInt() ?? 30000,
    );
  }
}
