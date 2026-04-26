import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_state_keys.dart';

/// Typed read boundary for `AssistantRunRequest.contextScopeHint`.
///
/// The request field is still a serde map because it crosses app/runtime
/// boundaries. Pipeline code should read known keys through this projection.
class AssistantPipelineContextScopeHintView {
  const AssistantPipelineContextScopeHintView(this._raw);

  final Map<String, dynamic> _raw;

  Map<String, dynamic> get raw => _raw;

  bool get forceRefreshCatalog =>
      _raw[AssistantPipelineStateKeys.forceRefreshCatalog] == true;

  Object? value(String key) => _raw[key];

  String stringValue(String key) => (_raw[key] as String?)?.trim() ?? '';

  Map<String, dynamic> mapValue(String key) {
    final raw = _raw[key];
    if (raw is Map) {
      return raw.cast<String, dynamic>();
    }
    return const <String, dynamic>{};
  }

  Map<String, dynamic> get precomputedBootstrap =>
      mapValue(AssistantPipelineStateKeys.precomputedBootstrap);

  Map<String, dynamic> get previousUnderstandingSnapshot =>
      mapValue(AssistantPipelineStateKeys.previousUnderstandingSnapshot);

  Map<String, dynamic> get historicalThinkingSnapshot =>
      mapValue(AssistantPipelineStateKeys.historicalThinkingSnapshot);

  Map<String, dynamic> get understandingResult =>
      mapValue(AssistantPipelineStateKeys.understandingResult);

  Map<String, dynamic> get precomputedUnderstandingResult =>
      mapValue(AssistantPipelineStateKeys.precomputedUnderstandingResult);

  Map<String, dynamic> get taskGraph =>
      mapValue(AssistantPipelineStateKeys.taskGraph);

  Map<String, dynamic> get precomputedTaskGraph =>
      mapValue(AssistantPipelineStateKeys.precomputedTaskGraph);
}
