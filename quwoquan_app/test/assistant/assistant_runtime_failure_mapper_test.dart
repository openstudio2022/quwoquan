import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_runtime_failure_mapper.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  const mapper = AssistantRuntimeFailureMapper();

  test('maps assistant error code to runtime failure facts', () {
    final failure = mapper.fromAssistantErrorCode(
      errorCode: AssistantErrorCode.permissionDenied,
      boundary: 'assistant_tool',
      stage: 'execute',
      functionModule: 'intent_bridge',
      businessObject: 'assistant_tool',
    );

    expect(failure.code, 'ASSISTANT.PERMISSION.permission_denied');
    expect(failure.kind, RuntimeFailureKind.permission);
    expect(failure.nature, RuntimeFailureNature.requiresPermission);
    expect(failure.location.functionModule, 'intent_bridge');
    expect(
      failure.context.attributes.map((item) => item.key),
      containsAll(<String>['boundary', 'stage', 'assistantErrorCode']),
    );
  });

  test(
    'normalizes string runtime code and infers transient network failure',
    () {
      final failure = mapper.fromRuntimeCode(
        'ASSISTANT.NETWORK.network_unavailable',
        boundary: 'assistant_turn',
        stage: 'stream',
        functionModule: 'remote_entry',
      );

      expect(failure.kind, RuntimeFailureKind.network);
      expect(failure.origin, RuntimeFailureOrigin.remoteDependency);
      expect(failure.nature, RuntimeFailureNature.transient);
    },
  );

  test('fromToolResult preserves existing runtime failure', () {
    const existing = RuntimeFailure(
      code: 'ASSISTANT.RATE_LIMITED.rate_limited',
      origin: RuntimeFailureOrigin.remoteDependency,
      kind: RuntimeFailureKind.rateLimited,
      nature: RuntimeFailureNature.transient,
      location: RuntimeFailureLocation(
        businessObject: 'assistant_tool',
        functionModule: 'web_search',
      ),
      context: RuntimeFailureContext(),
    );
    const result = AssistantToolResult(
      success: false,
      message: 'limited',
      errorCode: AssistantErrorCode.rateLimited,
      degraded: true,
      runtimeFailure: existing,
    );

    final failure = mapper.fromToolResult(
      toolName: 'web_search',
      result: result,
      stage: 'react_runtime',
    );

    expect(failure.code, existing.code);
    expect(failure.kind, existing.kind);
  });
}
