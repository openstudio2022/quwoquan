// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_location_errors.g.dart';

void main() {
  test('Location internal failure uses its object-specific canonical code', () {
    const code = 'INTEGRATION.SYSTEM.location_internal_error';

    expect(IntegrationLocationErrorCode.locationInternalError.code, code);
    expect(
      IntegrationLocationErrorCode.fromCode(code),
      IntegrationLocationErrorCode.locationInternalError,
    );
    expect(
      IntegrationLocationErrorCode.fromCode(
        'INTEGRATION.SYSTEM.internal_error',
      ),
      IntegrationLocationErrorCode.unknown,
      reason: 'retired generic code must not remain as a dual-read alias',
    );
  });
}
