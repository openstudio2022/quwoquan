import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/realtime/realtime_api_metadata.g.dart';

/// Configuration for realtime transport layer.
/// In production, fetched from `GET /config/realtime`.
class RealtimeConfig {
  final String wsUrl;
  final String gatewayBaseUrl;
  final int heartbeatIntervalSec;
  final int authAckTimeoutSec;
  final int wsIdleTimeoutSec;
  final int longPollHoldSec;
  final int maxReconnectAttempts;
  final int reconnectBaseDelayMs;
  final int reconnectMaxDelayMs;

  const RealtimeConfig({
    required this.wsUrl,
    this.gatewayBaseUrl = '',
    this.heartbeatIntervalSec = 15,
    this.authAckTimeoutSec = 5,
    this.wsIdleTimeoutSec = 120,
    this.longPollHoldSec = 60,
    this.maxReconnectAttempts = 10,
    this.reconnectBaseDelayMs = 1000,
    this.reconnectMaxDelayMs = 30000,
  });

  factory RealtimeConfig.fromRuntime({
    String? gatewayBaseUrl,
    String? realtimeBaseUrl,
  }) {
    final resolvedGatewayBaseUrl =
        gatewayBaseUrl ?? CloudRuntimeConfig.gatewayBaseUrl;
    final resolvedRealtimeBaseUrl =
        realtimeBaseUrl ?? CloudRuntimeConfig.realtimeConnectionUrl;
    return RealtimeConfig(
      wsUrl:
          '${resolvedRealtimeBaseUrl.replaceAll(RegExp(r'/+$'), '')}'
          '${RealtimeApiMetadata.webSocketUpgradePath}',
      gatewayBaseUrl: resolvedGatewayBaseUrl,
    );
  }

  factory RealtimeConfig.fromMap(Map<String, dynamic> map) {
    final canonical = RealtimeConfig.fromRuntime();
    final declaredWsUrl = (map['wsUrl'] as String? ?? '').trim();
    if (declaredWsUrl.isNotEmpty && declaredWsUrl != canonical.wsUrl) {
      throw const FormatException(
        'Realtime config cannot replace the topology WebSocket URL',
      );
    }
    return RealtimeConfig(
      wsUrl: canonical.wsUrl,
      gatewayBaseUrl: canonical.gatewayBaseUrl,
      heartbeatIntervalSec:
          (map['heartbeatIntervalSec'] as num?)?.toInt() ?? 15,
      authAckTimeoutSec: (map['authAckTimeoutSec'] as num?)?.toInt() ?? 5,
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
