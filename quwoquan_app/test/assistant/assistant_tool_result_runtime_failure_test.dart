import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  test('AssistantToolResult round trips runtimeFailure', () {
    const result = AssistantToolResult(
      success: false,
      message: 'timeout',
      errorCode: AssistantErrorCode.networkUnavailable,
      degraded: true,
      runtimeFailure: RuntimeFailure(
        code: 'ASSISTANT.NETWORK.network_unavailable',
        origin: RuntimeFailureOrigin.remoteDependency,
        kind: RuntimeFailureKind.network,
        nature: RuntimeFailureNature.transient,
        location: RuntimeFailureLocation(
          businessObject: 'assistant_tool',
          functionModule: 'web_search',
        ),
        context: RuntimeFailureContext(
          attributes: <RuntimeContextAttribute>[
            RuntimeContextAttribute(key: 'toolName', value: 'web_search'),
          ],
        ),
      ),
    );

    final restored = AssistantToolResult.fromJson(
      result.toJson().cast<String, dynamic>(),
    );

    expect(
      restored.runtimeFailure?.code,
      'ASSISTANT.NETWORK.network_unavailable',
    );
    expect(
      restored.runtimeFailure?.context.attributes.single.value,
      'web_search',
    );
  });

  test('failed AssistantToolResult serializes a fallback runtimeFailure', () {
    const result = AssistantToolResult(
      success: false,
      message: 'bad args',
      errorCode: AssistantErrorCode.invalidArguments,
    );

    final json = result.toJson();
    final failure = json['runtimeFailure'] as Map<String, Object?>?;

    expect(failure, isNotNull);
    expect(failure?['code'], 'ASSISTANT.VALIDATION.invalid_arguments');
    expect(result.effectiveRuntimeFailure?.kind, RuntimeFailureKind.validation);
  });

  test(
    'failed AssistantToolResult fromJson restores missing runtimeFailure',
    () {
      final restored = AssistantToolResult.fromJson(<String, dynamic>{
        'success': false,
        'message': 'network down',
        'errorCode': 'networkUnavailable',
      });

      expect(
        restored.runtimeFailure?.code,
        'ASSISTANT.NETWORK.network_unavailable',
      );
      expect(restored.runtimeFailure?.nature, RuntimeFailureNature.transient);
    },
  );
}
