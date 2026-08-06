import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// AssistantEntryView 的页面入口查询端口。
abstract class AssistantEntryViewQuery {
  Future<AssistantEntryResponse> getAssistantEntry({
    required AssistantOpenContext context,
  });
}
