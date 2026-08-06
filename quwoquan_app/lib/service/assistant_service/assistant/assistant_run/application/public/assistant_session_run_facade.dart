import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_run_ports.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/application/public/assistant_session_ports.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_turn_query.dart';

/// Assistant 对话页所需的跨 Session/Run/Turn 显式 public facade。
///
/// 对象级 adapter 仍分别实现各自 port；只有 runtime composition 可以组装本
/// facade，避免把跨对象 transport 重新塞回聚合 Repository。
abstract interface class AssistantSessionRunFacade
    implements
        AssistantSessionCommandWriter,
        AssistantSessionQuery,
        AssistantTurnQuery,
        AssistantAnswerRunCommandWriter,
        AssistantRunQuery,
        AssistantRunEventStream {}

/// runtime/di 内一次构造、向 Provider 投影窄 port 的显式 composition。
abstract interface class AssistantSessionRunComposition
    implements
        AssistantSessionRunFacade,
        AssistantRunControlFacet,
        AssistantCreationRunCommandWriter {}
