import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AppCloudOperationIds, appCloudOperationContracts;

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
    final webSocketUpgrade =
        appCloudOperationContracts[AppCloudOperationIds
            .realtimeConnectionWebSocketUpgrade];
    if (webSocketUpgrade == null ||
        webSocketUpgrade.method != 'GET' ||
        webSocketUpgrade.requestBodyKind != 'none' ||
        webSocketUpgrade.responseBodyKind != 'upgrade' ||
        !webSocketUpgrade.pathTemplate.startsWith('/')) {
      throw StateError(
        'canonical realtime WebSocket upgrade operation is unavailable',
      );
    }
    return RealtimeConfig(
      wsUrl:
          '${resolvedRealtimeBaseUrl.replaceAll(RegExp(r'/+$'), '')}'
          '${webSocketUpgrade.pathTemplate}',
      gatewayBaseUrl: resolvedGatewayBaseUrl,
    );
  }
}
