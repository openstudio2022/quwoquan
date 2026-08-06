import 'package:quwoquan_app/service/assistant_service/assistant/assistant_entry_view/application/assistant_entry_query.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/page_context_command_writer.dart';

/// 页面上下文上报与入口投影查询的显式 public composition facade。
abstract interface class AssistantPersonalizationFacade
    implements PageContextCommandWriter, AssistantEntryViewQuery {}
