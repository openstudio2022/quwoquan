import 'package:quwoquan_app/cloud/runtime/generated/realtime/realtime_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/generated/realtime_contracts.dart'
    as realtime;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef RealtimeConnectionInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// Realtime Connection 对象的 typed HTTP 边界。
///
/// WebSocket frame 属于实时协议；签发一次性 ticket 与 long-poll HTTP 则必须
/// 统一走 generated operation client，禁止 transport 再拼 path/header/decoder。
abstract interface class RealtimeConnectionOperationGateway {
  Future<realtime.ConnectionTicket> issueConnectionTicket();

  Future<realtime.LongPollResponse> longPoll({int? timeout, String? cursor});
}

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
