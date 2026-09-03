// post 对象 generated 错误码的端侧断言覆盖:
// 覆盖 post 对象声明、当前尚无断言证据的错误码(idempotency_conflict、
// research_identity_invalid、research_release_state_unavailable、
// gathering_participation_required、feed_capacity_unavailable),并以代表性码走
// CloudErrorMapper 映射负例。
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
      wire: 'CONTENT.USER.idempotency_conflict',
      value: ContentErrorCode.idempotencyConflict,
      recoveryAction: 'retry',
      recoveryAfterSeconds: 0,
      httpStatus: 409,
    ),
    (
      wire: 'CONTENT.USER.research_identity_invalid',
      value: ContentErrorCode.researchIdentityInvalid,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 403,
    ),
    (
      wire: 'CONTENT.SYSTEM.research_release_state_unavailable',
      value: ContentErrorCode.researchReleaseStateUnavailable,
      recoveryAction: 'retry',
      recoveryAfterSeconds: 5,
      httpStatus: 503,
    ),
    (
      wire: 'CONTENT.USER.gathering_participation_required',
      value: ContentErrorCode.gatheringParticipationRequired,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 403,
    ),
    (
      wire: 'CONTENT.SYSTEM.feed_capacity_unavailable',
      value: ContentErrorCode.feedCapacityUnavailable,
      recoveryAction: 'retry',
      recoveryAfterSeconds: 1,
      httpStatus: 503,
    ),
  ];

  group('ContentErrorCode — post 错误码契约', () {
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

    test('恢复语义横向不变量:503 必须 retry 且带退避,403 必须 surface', () {
      for (final entry in declared) {
        if (entry.httpStatus == 503) {
          expect(
            entry.value.recoveryAction,
            'retry',
            reason: '${entry.wire}: 系统容量不可用属可自动恢复,必须 retry',
          );
          expect(
            entry.value.recoveryAfterSeconds,
            greaterThan(0),
            reason: '${entry.wire}: retry 必须带退避秒数,避免打爆服务',
          );
        }
        if (entry.httpStatus == 403) {
          expect(
            entry.value.recoveryAction,
            'surface',
            reason: '${entry.wire}: 权限/身份类错误必须提示用户而非自动重试',
          );
        }
      }
    });

    test('未知 CONTENT 码解析为 unknown 兜底而非误配', () {
      expect(
        ContentErrorCode.fromCode('CONTENT.USER.nonexistent_reason'),
        ContentErrorCode.unknown,
      );
    });
  });

  group('CloudErrorMapper — post 代表性映射负例', () {
    test('409 idempotency_conflict → typed 解析 + retry 恢复', () {
      final exception = CloudErrorMapper.fromStatusCode(
        409,
        body: canonicalRuntimeErrorBody(
          code: 'CONTENT.USER.idempotency_conflict',
          origin: 'user',
          kind: 'validation',
          nature: 'transient',
          businessObject: 'post',
          functionModule: 'content',
          recoveryAction: 'retry',
          requestId: 'req-post-errors-1',
          traceId: 'trace-post-errors-1',
        ),
        requestPath: '/content/posts',
      );

      expect(exception.code, 'CONTENT.USER.idempotency_conflict');
      expect(exception.domainErrorCode?.domain, 'content');
      expect(
        exception.domainErrorCode?.value,
        ContentErrorCode.idempotencyConflict,
      );
      expect(exception.runtimeFailure.kind, RuntimeFailureKind.validation);
      expect(exception.runtimeFailure.transportStatus, 409);
      expect(exception.runtimeFailure.recovery.action, 'retry');
    });

    test('503 feed_capacity_unavailable → typed 解析 + 带退避的 retry 恢复', () {
      final exception = CloudErrorMapper.fromStatusCode(
        503,
        body: canonicalRuntimeErrorBody(
          code: 'CONTENT.SYSTEM.feed_capacity_unavailable',
          origin: 'system',
          kind: 'unavailable',
          nature: 'transient',
          businessObject: 'post',
          functionModule: 'content',
          recoveryAction: 'retry',
          recoveryAfterSeconds: 1,
          requestId: 'req-post-errors-2',
          traceId: 'trace-post-errors-2',
        ),
        requestPath: '/content/feed',
      );

      expect(exception.code, 'CONTENT.SYSTEM.feed_capacity_unavailable');
      expect(exception.domainErrorCode?.domain, 'content');
      expect(
        exception.domainErrorCode?.value,
        ContentErrorCode.feedCapacityUnavailable,
      );
      expect(exception.runtimeFailure.kind, RuntimeFailureKind.unavailable);
      expect(exception.runtimeFailure.transportStatus, 503);
      expect(exception.runtimeFailure.recovery.action, 'retry');
      expect(exception.runtimeFailure.recovery.afterSeconds, 1);
    });
  });
}
