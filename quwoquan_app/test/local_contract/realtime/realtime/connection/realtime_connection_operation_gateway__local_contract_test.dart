// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/realtime-gateway/realtime-channel-delivery/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/realtime/realtime/connection/application/realtime_connection_operation_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'ticket 与 long-poll 仅由 Realtime Connection generated owner 执行',
    () async {
      final executor = _RecordingExecutor();
      final gateway = RemoteRealtimeConnectionOperationGateway(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.appShell.id,
          routeId: AppUiSurfaces.appShell.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(accountId: 'account-1'),
        ),
      );

      final ticket = await gateway.issueConnectionTicket();
      final poll = await gateway.longPoll(timeout: 30, cursor: '100-0');

      expect(ticket.ticket, 'one-time-ticket');
      expect(poll.nextCursor, '101-0');
      expect(executor.operations, <String>[
        AppCloudOperationIds.realtimeConnectionIssueConnectionTicket,
        AppCloudOperationIds.realtimeConnectionLongPoll,
      ]);
      expect(executor.requests.first.body, isNull);
      expect(executor.requests.last.queryParameters, <String, String>{
        'timeout': '30',
        'cursor': '100-0',
      });
    },
  );
}

final class _RecordingExecutor implements CloudOperationExecutor {
  final List<String> operations = <String>[];
  final List<CloudOperationRequestPayload> requests =
      <CloudOperationRequestPayload>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    operations.add(operation.canonicalOperationId);
    requests.add(requestEncoder());
    if (operation.canonicalOperationId ==
        AppCloudOperationIds.realtimeConnectionIssueConnectionTicket) {
      return responseDecoder(<String, Object?>{
        'ticket': 'one-time-ticket',
        'expiresAt': '2026-08-04T00:00:30Z',
      });
    }
    return responseDecoder(<String, Object?>{
      'events': const <Object?>[],
      'nextCursor': '101-0',
      'transportResumed': false,
    });
  }
}
