// AssistantSession 的跨对象公开端口。
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// AssistantSession owner 列表的默认 keyset 窗口。
const int kAssistantSessionListDefaultLimit = 32;

/// AssistantSession 的唯一写端口。
abstract class AssistantSessionCommandWriter {
  /// [clientRequestId] 与 HTTP `Idempotency-Key` 必须是同一稳定 intent；
  /// 网络重试必须复用它。
  Future<AssistantSessionWire> createAssistantSession({
    String summary = '',
    required String clientRequestId,
  });
}

/// AssistantSession owner 查询端口。
abstract class AssistantSessionQuery {
  Future<AssistantSessionListView> listAssistantSessions({
    int limit = kAssistantSessionListDefaultLimit,
    String cursor = '',
  });

  Future<AssistantSessionWire> getAssistantSession({required String sessionId});
}
