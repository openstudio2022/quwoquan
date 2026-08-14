// filter_catalog_release 对象 generated 错误码的端侧断言覆盖:
// filter_catalog_* 六个码的枚举解析、恢复语义,并以
// filter_catalog_storage_unavailable 走 CloudErrorMapper 映射负例。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart';

typedef _DeclaredCase = ({
  String wire,
  ContentErrorCode value,
  String recoveryAction,
  int recoveryAfterSeconds,
  int httpStatus,
});

void main() {
  const declared = <_DeclaredCase>[
    (
      wire: 'CONTENT.USER.filter_catalog_release_not_found',
      value: ContentErrorCode.filterCatalogReleaseNotFound,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 404,
    ),
    (
      wire: 'CONTENT.USER.filter_catalog_invalid_argument',
      value: ContentErrorCode.filterCatalogInvalidArgument,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 400,
    ),
    (
      wire: 'CONTENT.USER.filter_catalog_digest_mismatch',
      value: ContentErrorCode.filterCatalogDigestMismatch,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 400,
    ),
    (
      wire: 'CONTENT.USER.filter_catalog_invalid_transition',
      value: ContentErrorCode.filterCatalogInvalidTransition,
      recoveryAction: 'retry',
      recoveryAfterSeconds: 0,
      httpStatus: 409,
    ),
    (
      wire: 'CONTENT.USER.filter_catalog_idempotency_conflict',
      value: ContentErrorCode.filterCatalogIdempotencyConflict,
      recoveryAction: 'retry',
      recoveryAfterSeconds: 0,
      httpStatus: 409,
    ),
    (
      wire: 'CONTENT.SYSTEM.filter_catalog_storage_unavailable',
      value: ContentErrorCode.filterCatalogStorageUnavailable,
      recoveryAction: 'retry',
      recoveryAfterSeconds: 3,
      httpStatus: 503,
    ),
  ];

  group('ContentErrorCode — filter_catalog_release 错误码契约', () {
    for (final entry in declared) {
      test('${entry.wire} 解析与恢复语义与声明一致', () {
        final parsed = ContentErrorCode.fromCode(entry.wire);
        expect(parsed, entry.value);
        expect(parsed.code, entry.wire);
        expect(parsed.httpStatus, entry.httpStatus);
        expect(parsed.recoveryAction, entry.recoveryAction);
        expect(parsed.recoveryAfterSeconds, entry.recoveryAfterSeconds);
        expect(ContentErrorMessages.zh[parsed], isNotEmpty);
        expect(ContentErrorMessages.en[parsed], isNotEmpty);
      });
    }

    test('恢复语义横向不变量:503 必须 retry 且带退避,409 为 retry/surface 之一', () {
      for (final entry in declared) {
        if (entry.httpStatus == 503) {
          expect(entry.value.recoveryAction, 'retry');
          expect(
            entry.value.recoveryAfterSeconds,
            greaterThan(0),
            reason: '${entry.wire}: 系统不可用 retry 必须带退避秒数',
          );
        }
        if (entry.httpStatus == 409) {
          expect(
            <String>{'retry', 'surface'},
            contains(entry.value.recoveryAction),
            reason: '${entry.wire}: 冲突类错误恢复动作必须是 retry 或 surface',
          );
        }
      }
    });
  });

  group('CloudErrorMapper — filter_catalog_release 代表性映射负例', () {
    test('503 filter_catalog_storage_unavailable → typed 解析 + retry 恢复', () {
      final exception = CloudErrorMapper.fromStatusCode(
        503,
        body: canonicalRuntimeErrorBody(
          code: 'CONTENT.SYSTEM.filter_catalog_storage_unavailable',
          origin: 'system',
          kind: 'unavailable',
          nature: 'transient',
          businessObject: 'filter_catalog_release',
          functionModule: 'content',
          recoveryAction: 'retry',
          recoveryAfterSeconds: 3,
          requestId: 'req-filter-catalog-errors-1',
          traceId: 'trace-filter-catalog-errors-1',
        ),
        requestPath: '/content/filter-catalog/releases',
      );

      expect(
        exception.code,
        'CONTENT.SYSTEM.filter_catalog_storage_unavailable',
      );
      expect(exception.domainErrorCode?.domain, 'content');
      expect(
        exception.domainErrorCode?.value,
        ContentErrorCode.filterCatalogStorageUnavailable,
      );
      expect(exception.runtimeFailure.kind, RuntimeFailureKind.unavailable);
      expect(exception.runtimeFailure.transportStatus, 503);
      expect(exception.runtimeFailure.recovery.action, 'retry');
      expect(exception.runtimeFailure.recovery.afterSeconds, 3);
    });
  });
}
