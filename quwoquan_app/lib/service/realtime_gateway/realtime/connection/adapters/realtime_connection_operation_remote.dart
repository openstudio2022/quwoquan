import 'package:quwoquan_app/runtime/transport/generated/realtime/realtime_request_page_ids.g.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_operation_gateway.dart';
import 'package:quwoquan_cloud_contracts/generated/realtime_contracts.dart'
    as realtime;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef RealtimeConnectionInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// Realtime Connection 对象拥有的 generated HTTP adapter。
///
/// WebSocket frame 仍由 transport adapter 处理；一次性 ticket 与 long-poll
/// 必须经 generated operation client，禁止在 transport 中拼 path/header/decoder。
final class RemoteRealtimeConnectionOperationGateway
    implements RealtimeConnectionOperationGateway {
  const RemoteRealtimeConnectionOperationGateway({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final RealtimeConnectionInvocationContextFactory invocationContext;

  @override
  Future<realtime.ConnectionTicket> issueConnectionTicket() =>
      client.realtimeConnectionIssueConnectionTicket(
        const realtime.IssueConnectionTicketRequest(),
        context: invocationContext(
          RealtimeRequestPageIds.issueConnectionTicket,
        ),
      );

  @override
  Future<realtime.LongPollResponse> longPoll({int? timeout, String? cursor}) =>
      client.realtimeConnectionLongPoll(
        realtime.LongPollRequest(timeout: timeout, cursor: cursor),
        context: invocationContext(RealtimeRequestPageIds.longPoll),
      );
}
