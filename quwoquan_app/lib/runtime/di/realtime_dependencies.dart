import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/realtime_connection_operation_remote.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_operation_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// realtime domain 的唯一 production 装配入口。
final class RealtimeProductionComposition {
  const RealtimeProductionComposition._();

  static RealtimeConnectionOperationGateway connectionOperations({
    required GeneratedCloudOperationClient client,
    required RealtimeConnectionInvocationContextFactory invocationContext,
  }) {
    return RemoteRealtimeConnectionOperationGateway(
      client: client,
      invocationContext: invocationContext,
    );
  }
}
