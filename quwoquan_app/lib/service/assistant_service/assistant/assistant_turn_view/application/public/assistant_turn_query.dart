// AssistantTurnView 的跨对象公开查询端口。
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// AssistantTurnView 历史窗口的默认 keyset 条数。
const int kAssistantTurnListDefaultLimit = 32;

/// AssistantTurnView 的终态轮次查询端口。
abstract class AssistantTurnQuery {
  Future<AssistantTurnListView> listSessionTurns({
    required String sessionId,
    int limit = kAssistantTurnListDefaultLimit,
    String cursor = '',
  });
}
