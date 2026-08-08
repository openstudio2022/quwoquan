import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/remote_realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/adapters/realtime_connection_operation_remote.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_notifier.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_operation_gateway.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/domain/realtime_connection_delegate.dart';
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

  static RealtimeConnectionDelegate connectionDelegate({
    required Ref ref,
    required RealtimeConnectionStateListener onStateChanged,
    required RealtimeCurrentUserIdResolver currentUserIdResolver,
    required RealtimeConnectionOperationGateway operations,
  }) {
    return RemoteRealtimeConnectionDelegate(
      read: ref.read,
      invalidate: ref.invalidate,
      currentUserIdResolver: () => currentUserIdResolver(ref),
      authTokenProvider: ProviderBackedCloudAuthTokenProvider(
        () => ref
            .read(authSessionControllerProvider.notifier)
            .accessTokenForRequest(),
      ),
      operations: operations,
      onStateChanged: onStateChanged,
      telemetryRecorder:
          ({
            required transport,
            required result,
            required durationMs,
            failReasonCode,
          }) async {
            try {
              await ref
                  .read(appTelemetryReporterProvider)
                  .record(
                    AppTelemetryPayload.realtimeConnectResult(
                      transport: transport,
                      result: result,
                      durationMs: durationMs,
                      failReasonCode: failReasonCode,
                    ),
                  );
            } catch (error, stackTrace) {
              developer.log(
                'realtime connect telemetry failed',
                name: 'RealtimeProductionComposition',
                error: error,
                stackTrace: stackTrace,
              );
            }
          },
    );
  }
}
