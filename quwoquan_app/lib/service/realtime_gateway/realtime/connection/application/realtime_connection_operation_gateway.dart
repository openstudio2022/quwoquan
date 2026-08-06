import 'package:quwoquan_cloud_contracts/generated/realtime_contracts.dart'
    as realtime;

/// Realtime Connection 对象的 typed HTTP 边界。
///
/// WebSocket frame 属于实时协议；签发一次性 ticket 与 long-poll HTTP 则必须
/// 统一走 generated operation client，禁止 transport 再拼 path/header/decoder。
abstract interface class RealtimeConnectionOperationGateway {
  Future<realtime.ConnectionTicket> issueConnectionTicket();

  Future<realtime.LongPollResponse> longPoll({int? timeout, String? cursor});
}
