import 'package:quwoquan_app/assistant/orchestration/pipelines/response_materializer.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_draft.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

/// Legacy shim — delegates to [ResponseMaterializer].
@Deprecated('Use ResponseMaterializer directly')
class SynthesisMaterializer {
  const SynthesisMaterializer(this._materializer);

  final ResponseMaterializer _materializer;

  Future<AssistantRunResponse> materialize(
    AssistantRunRequest request, {
    required SynthesisDraft draft,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) {
    return _materializer.materialize(
      request,
      draft: draft,
      onTraceEvent: onTraceEvent,
    );
  }
}
