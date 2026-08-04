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

}
