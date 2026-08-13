// spec_ref: specs/feature-tree/runtime/runtime-errors/spec.md#sit-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/generated/assistant/assistant_errors.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/assistant_presentation_action_dispatcher.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('Unavailable device executor 保持 fail-closed 且 failureCode 与 codegen 枚举同源', () async {
    const executor = UnavailableAssistantDeviceActionExecutor();
    final intent = AssistantExecuteDeviceActionIntentWire(
      runId: 'arn_action',
      toolInvocationId: 'tool_calendar',
      installationId: 'installation_test',
      deviceId: 'device_test',
      capability: 'calendar_create_reminder',
      inputDigest: 'digest_test',
      idempotencyKey: 'execute_action_once',
      deviceActionPermit: 'opaque_device_action_permit_0123456789',
    );

    expect(executor.canExecute(intent), isFalse);

    final result = await executor.execute(intent);
    expect(result.outcome, 'unavailable');
    expect(
      result.failureCode,
      AssistantErrorCode.deviceActionUnavailable.code,
    );
  });
}
