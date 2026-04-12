import 'package:quwoquan_app/assistant/contracts/assistant_run_structured_bundle.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_structured_response_wire.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';

/// 模型交互：`AssistantRunResponse.structuredResponse` 大图上的只读投影。
///
/// 不替代持久化 Map；用于下游以具名字段访问 wire 与 [RunArtifacts]，避免在长路径上手写键名。
final class AssistantRunStructuredInteractionView {
  const AssistantRunStructuredInteractionView(this.structuredResponse);

  final Map<String, dynamic> structuredResponse;

  AssistantStructuredResponseWire get assistantStructured =>
      assistantStructuredWireFromStructuredRoot(structuredResponse);

  AssistantRunStructuredBundle get bundle =>
      AssistantRunStructuredBundle.fromStructuredResponseRoot(structuredResponse);

  RunArtifacts? get runArtifacts {
    final raw = (structuredResponse['runArtifacts'] as Map?)
        ?.cast<String, dynamic>();
    if (raw == null) return null;
    return parseRunArtifacts(raw);
  }
}
