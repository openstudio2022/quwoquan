// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
//
// OpsEventRecordErrorCode 解码契约：wire code -> typed 枚举 + HTTP 语义，
// 未知码回退 unknown，锁定端云错误链路的 App 侧映射承诺。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/generated/ops/ops_event_record_errors.g.dart';

void main() {
  group('OpsEventRecordErrorCode 解码契约', () {
    test('event_batch_invalid → eventBatchInvalid / 422', () {
      final code =
          OpsEventRecordErrorCode.fromCode('OPS.USER.event_batch_invalid');
      expect(code, OpsEventRecordErrorCode.eventBatchInvalid);
      expect(code.httpStatus, 422);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('runtime_log_batch_invalid → runtimeLogBatchInvalid / 422', () {
      final code = OpsEventRecordErrorCode.fromCode(
        'OPS.USER.runtime_log_batch_invalid',
      );
      expect(code, OpsEventRecordErrorCode.runtimeLogBatchInvalid);
      expect(code.httpStatus, 422);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('idempotency_key_invalid → idempotencyKeyInvalid / 400', () {
      final code =
          OpsEventRecordErrorCode.fromCode('OPS.USER.idempotency_key_invalid');
      expect(code, OpsEventRecordErrorCode.idempotencyKeyInvalid);
      expect(code.httpStatus, 400);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('query_window_invalid → queryWindowInvalid / 400', () {
      final code =
          OpsEventRecordErrorCode.fromCode('OPS.USER.query_window_invalid');
      expect(code, OpsEventRecordErrorCode.queryWindowInvalid);
      expect(code.httpStatus, 400);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('event_drilldown_forbidden → eventDrilldownForbidden / 403', () {
      final code = OpsEventRecordErrorCode.fromCode(
        'OPS.USER.event_drilldown_forbidden',
      );
      expect(code, OpsEventRecordErrorCode.eventDrilldownForbidden);
      expect(code.httpStatus, 403);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('event_projection_unavailable → eventProjectionUnavailable / 503',
        () {
      final code = OpsEventRecordErrorCode.fromCode(
        'OPS.SYSTEM.event_projection_unavailable',
      );
      expect(code, OpsEventRecordErrorCode.eventProjectionUnavailable);
      expect(code.httpStatus, 503);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('runtime_logstore_unavailable → runtimeLogstoreUnavailable / 503',
        () {
      final code = OpsEventRecordErrorCode.fromCode(
        'OPS.SYSTEM.runtime_logstore_unavailable',
      );
      expect(code, OpsEventRecordErrorCode.runtimeLogstoreUnavailable);
      expect(code.httpStatus, 503);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('startup_event_invalid → startupEventInvalid / 400', () {
      final code =
          OpsEventRecordErrorCode.fromCode('OPS.USER.startup_event_invalid');
      expect(code, OpsEventRecordErrorCode.startupEventInvalid);
      expect(code.httpStatus, 400);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('startup_telemetry_unavailable → startupTelemetryUnavailable / 503',
        () {
      final code = OpsEventRecordErrorCode.fromCode(
        'OPS.SYSTEM.startup_telemetry_unavailable',
      );
      expect(code, OpsEventRecordErrorCode.startupTelemetryUnavailable);
      expect(code.httpStatus, 503);
      expect(code.defaultMessage, isNotEmpty);
    });

    test(
        'startup_native_first_frame_timeout → startupNativeFirstFrameTimeout（非 HTTP 面，status 0）',
        () {
      final code = OpsEventRecordErrorCode.fromCode(
        'OPS.SYSTEM.startup_native_first_frame_timeout',
      );
      expect(code, OpsEventRecordErrorCode.startupNativeFirstFrameTimeout);
      expect(code.httpStatus, 0);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('未知码回退 unknown 兜底', () {
      expect(
        OpsEventRecordErrorCode.fromCode('OPS.USER.__nonexistent__'),
        OpsEventRecordErrorCode.unknown,
      );
    });
  });
}
