// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
//
// EntityErrorCode 解码契约：wire code -> typed 枚举 + HTTP 语义，
// 未知码回退 unknown，锁定端云错误链路的 App 侧映射承诺。
// entity 域为单枚举文件，claim/status_report 对象的码一并在此锁定。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/entity/entity_errors.g.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart';

void main() {
  group('EntityErrorCode 解码契约', () {
    test('homepage_offline → homepageOffline / 410', () {
      final code = EntityErrorCode.fromCode('ENTITY.USER.homepage_offline');
      expect(code, EntityErrorCode.homepageOffline);
      expect(code.httpStatus, 410);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('claim_material_missing → claimMaterialMissing / 400', () {
      final code =
          EntityErrorCode.fromCode('ENTITY.USER.claim_material_missing');
      expect(code, EntityErrorCode.claimMaterialMissing);
      expect(code.httpStatus, 400);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('already_claimed → alreadyClaimed / 409', () {
      final code = EntityErrorCode.fromCode('ENTITY.USER.already_claimed');
      expect(code, EntityErrorCode.alreadyClaimed);
      expect(code.httpStatus, 409);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('claim_not_found → claimNotFound / 404', () {
      final code = EntityErrorCode.fromCode('ENTITY.USER.claim_not_found');
      expect(code, EntityErrorCode.claimNotFound);
      expect(code.httpStatus, 404);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('duplicate_pending_claim → duplicatePendingClaim / 409', () {
      final code =
          EntityErrorCode.fromCode('ENTITY.USER.duplicate_pending_claim');
      expect(code, EntityErrorCode.duplicatePendingClaim);
      expect(code.httpStatus, 409);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('invalid_claim_material_url → invalidClaimMaterialUrl / 400', () {
      final code =
          EntityErrorCode.fromCode('ENTITY.USER.invalid_claim_material_url');
      expect(code, EntityErrorCode.invalidClaimMaterialUrl);
      expect(code.httpStatus, 400);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('status_report_not_found → statusReportNotFound / 404', () {
      final code =
          EntityErrorCode.fromCode('ENTITY.USER.status_report_not_found');
      expect(code, EntityErrorCode.statusReportNotFound);
      expect(code.httpStatus, 404);
      expect(code.defaultMessage, isNotEmpty);
    });

    test(
        'invalid_status_report_evidence_url → invalidStatusReportEvidenceUrl / 400',
        () {
      final code = EntityErrorCode.fromCode(
        'ENTITY.USER.invalid_status_report_evidence_url',
      );
      expect(code, EntityErrorCode.invalidStatusReportEvidenceUrl);
      expect(code.httpStatus, 400);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('invalid_argument → invalidArgument / 400', () {
      final code = EntityErrorCode.fromCode('ENTITY.USER.invalid_argument');
      expect(code, EntityErrorCode.invalidArgument);
      expect(code.httpStatus, 400);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('idempotency_conflict → idempotencyConflict / 409', () {
      final code = EntityErrorCode.fromCode('ENTITY.USER.idempotency_conflict');
      expect(code, EntityErrorCode.idempotencyConflict);
      expect(code.httpStatus, 409);
      expect(code.defaultMessage, isNotEmpty);
    });

    test('未知码回退 unknown 兜底', () {
      expect(
        EntityErrorCode.fromCode('ENTITY.USER.__nonexistent__'),
        EntityErrorCode.unknown,
      );
    });
  });

  group('CloudErrorMapper canonical 负例', () {
    test('幂等冲突：typed domain code 解析 + retry 恢复语义', () {
      final exception = CloudErrorMapper.fromStatusCode(
        409,
        body: canonicalRuntimeErrorBody(
          code: EntityErrorCode.idempotencyConflict.code,
          origin: 'user',
          kind: 'validation',
          nature: 'transient',
          businessObject: 'homepage',
          functionModule: 'entity',
          userMessage: '请求重复提交，请稍后重试',
          requestId: 'req-entity-idempotency',
          traceId: 'trace-entity-idempotency',
          recoveryAction: 'retry',
          recoveryAfterSeconds: 3,
          disruptionLevel: 'recoverable',
        ),
        requestPath: '/entity/homepages',
      );

      expect(exception.domainErrorCode?.domain, 'entity');
      expect(
        exception.domainErrorCode?.code,
        'ENTITY.USER.idempotency_conflict',
      );
      expect(
        exception.domainErrorCode?.value,
        EntityErrorCode.idempotencyConflict,
      );
      expect(
        exception.runtimeFailure.code,
        EntityErrorCode.idempotencyConflict.code,
      );
      // 幂等冲突是 transient：wire 下发的 retry 指令必须被如实透传。
      expect(exception.runtimeFailure.recovery.isPresent, isTrue);
      expect(exception.runtimeFailure.recovery.action, 'retry');
      expect(exception.runtimeFailure.recovery.afterSeconds, 3);
      expect(exception.userMessage, '请求重复提交，请稍后重试');
    });

    test('参数校验失败：typed domain code 解析 + surface 恢复语义', () {
      final exception = CloudErrorMapper.fromStatusCode(
        400,
        body: canonicalRuntimeErrorBody(
          code: EntityErrorCode.invalidArgument.code,
          origin: 'user',
          kind: 'validation',
          nature: 'requiresUserAction',
          businessObject: 'homepage',
          functionModule: 'entity',
          userMessage: '请求参数有误，请检查后重试',
          requestId: 'req-entity-invalid-argument',
          traceId: 'trace-entity-invalid-argument',
          recoveryAction: 'surface',
          disruptionLevel: 'inlineCard',
        ),
        requestPath: '/entity/homepages',
      );

      expect(exception.domainErrorCode?.domain, 'entity');
      expect(
        exception.domainErrorCode?.value,
        EntityErrorCode.invalidArgument,
      );
      expect(exception.runtimeFailure.code, 'ENTITY.USER.invalid_argument');
      expect(exception.runtimeFailure.recovery.action, 'surface');
    });
  });
}
