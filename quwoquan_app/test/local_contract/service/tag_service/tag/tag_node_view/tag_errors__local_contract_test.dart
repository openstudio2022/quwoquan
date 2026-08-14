/// TagErrorCode generated 错误码断言覆盖：
///
/// tag 域为单枚举文件（tag/**/errors.yaml 聚合生成），标签查询、feedback、
/// taxonomy release 对象的码一并在此锁定：
///
/// 1. wire code -> typed 枚举 + generated httpStatus 声明逐码锁定；
/// 2. 恢复语义按类别锁定——feedback/release 的用户侧校验与冲突类为 4xx
///    surface 语义，storage 失败类为 5xx 可重试语义；
/// 3. 代表码走 CloudErrorMapper canonical RuntimeErrorResponse 负例，锁定
///    typed domain code 解析与 recovery 指令透传。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/tag/tag_errors.g.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart';

final class _TagErrorCodeCase {
  const _TagErrorCodeCase(this.wire, this.expected, this.httpStatus);

  final String wire;
  final TagErrorCode expected;
  final int httpStatus;
}

void main() {
  group('TagErrorCode 解码契约（generated 声明逐码锁定）', () {
    const cases = <_TagErrorCodeCase>[
      _TagErrorCodeCase(
        'TAG.USER.invalid_argument',
        TagErrorCode.tagInvalidArgument,
        400,
      ),
      _TagErrorCodeCase(
        'TAG.USER.feedback_invalid_action',
        TagErrorCode.tagFeedbackInvalidAction,
        400,
      ),
      _TagErrorCodeCase(
        'TAG.USER.feedback_idempotency_conflict',
        TagErrorCode.tagFeedbackIdempotencyConflict,
        409,
      ),
      _TagErrorCodeCase(
        'TAG.SYSTEM.feedback_storage_failed',
        TagErrorCode.tagFeedbackStorageFailed,
        500,
      ),
      _TagErrorCodeCase(
        'TAG.USER.release_not_found',
        TagErrorCode.tagReleaseNotFound,
        404,
      ),
      _TagErrorCodeCase(
        'TAG.USER.release_invalid_argument',
        TagErrorCode.tagReleaseInvalidArgument,
        400,
      ),
      _TagErrorCodeCase(
        'TAG.USER.release_invalid_transition',
        TagErrorCode.tagReleaseInvalidTransition,
        409,
      ),
      _TagErrorCodeCase(
        'TAG.USER.release_snapshot_incomplete',
        TagErrorCode.tagReleaseSnapshotIncomplete,
        409,
      ),
      _TagErrorCodeCase(
        'TAG.USER.release_version_conflict',
        TagErrorCode.tagReleaseVersionConflict,
        409,
      ),
      _TagErrorCodeCase(
        'TAG.USER.release_idempotency_conflict',
        TagErrorCode.tagReleaseIdempotencyConflict,
        409,
      ),
      _TagErrorCodeCase(
        'TAG.SYSTEM.release_storage_failed',
        TagErrorCode.tagReleaseStorageFailed,
        500,
      ),
    ];

    for (final testCase in cases) {
      test('${testCase.wire} → ${testCase.expected.name} / '
          '${testCase.httpStatus}', () {
        final code = TagErrorCode.fromCode(testCase.wire);
        expect(code, testCase.expected);
        expect(code.httpStatus, testCase.httpStatus);
        expect(code.defaultMessage, isNotEmpty);
      });
    }

    test('未知码回退 unknown 兜底', () {
      expect(
        TagErrorCode.fromCode('TAG.USER.__nonexistent__'),
        TagErrorCode.unknown,
      );
      expect(TagErrorCode.fromCode(''), TagErrorCode.unknown);
    });
  });

  group('TagErrorCode 恢复语义类别', () {
    test('用户侧校验/冲突/流转类为 4xx：surface 给用户，重试不改变结果', () {
      const userSurfaceLike = <TagErrorCode>[
        TagErrorCode.tagInvalidArgument,
        TagErrorCode.tagFeedbackInvalidAction,
        TagErrorCode.tagFeedbackIdempotencyConflict,
        TagErrorCode.tagReleaseInvalidArgument,
        TagErrorCode.tagReleaseInvalidTransition,
        TagErrorCode.tagReleaseSnapshotIncomplete,
        TagErrorCode.tagReleaseVersionConflict,
        TagErrorCode.tagReleaseIdempotencyConflict,
        TagErrorCode.tagReleaseNotFound,
      ];
      for (final code in userSurfaceLike) {
        expect(
          code.httpStatus,
          inInclusiveRange(400, 499),
          reason: '${code.name} 是用户侧终态拒绝，必须是 4xx 而非可重试的 5xx',
        );
        expect(code.code, startsWith('TAG.USER.'));
      }
    });

    test('storage 失败类为 5xx 系统语义（transient，可重试）', () {
      const storageFailures = <TagErrorCode>[
        TagErrorCode.tagFeedbackStorageFailed,
        TagErrorCode.tagReleaseStorageFailed,
      ];
      for (final code in storageFailures) {
        expect(
          code.httpStatus,
          500,
          reason: '${code.name} 是系统 storage 失败，必须是 500',
        );
        expect(code.code, startsWith('TAG.SYSTEM.'));
        expect(code.defaultMessage, contains('稍后重试'));
      }
    });
  });

  group('CloudErrorMapper canonical 负例', () {
    test('feedback storage 失败：typed domain code 解析 + retry 恢复语义', () {
      final exception = CloudErrorMapper.fromStatusCode(
        500,
        body: canonicalRuntimeErrorBody(
          code: TagErrorCode.tagFeedbackStorageFailed.code,
          origin: 'system',
          kind: 'storage',
          nature: 'transient',
          businessObject: 'tag_feedback_fact',
          functionModule: 'tag',
          requestId: 'req-tag-feedback-storage',
          traceId: 'trace-tag-feedback-storage',
          recoveryAction: 'retry',
          recoveryAfterSeconds: 5,
          disruptionLevel: 'recoverable',
        ),
        requestPath: '/tag/feedback',
      );

      expect(exception.domainErrorCode?.domain, 'tag');
      expect(
        exception.domainErrorCode?.code,
        'TAG.SYSTEM.feedback_storage_failed',
      );
      expect(
        exception.domainErrorCode?.value,
        TagErrorCode.tagFeedbackStorageFailed,
      );
      expect(
        exception.runtimeFailure.code,
        TagErrorCode.tagFeedbackStorageFailed.code,
      );
      // storage 失败是 transient：wire 下发的 retry 指令必须被如实透传。
      expect(exception.runtimeFailure.recovery.isPresent, isTrue);
      expect(exception.runtimeFailure.recovery.action, 'retry');
      expect(exception.runtimeFailure.recovery.afterSeconds, 5);
    });

    test('release 版本冲突：typed domain code 解析 + surface 恢复语义', () {
      final exception = CloudErrorMapper.fromStatusCode(
        409,
        body: canonicalRuntimeErrorBody(
          code: TagErrorCode.tagReleaseVersionConflict.code,
          origin: 'user',
          kind: 'validation',
          nature: 'requiresUserAction',
          businessObject: 'tag_taxonomy_release',
          functionModule: 'tag',
          userMessage: '标签发布已更新，请刷新后重试',
          requestId: 'req-tag-release-conflict',
          traceId: 'trace-tag-release-conflict',
          recoveryAction: 'surface',
          disruptionLevel: 'inlineCard',
        ),
        requestPath: '/tag/releases',
      );

      expect(exception.domainErrorCode?.domain, 'tag');
      expect(
        exception.domainErrorCode?.value,
        TagErrorCode.tagReleaseVersionConflict,
      );
      expect(
        exception.runtimeFailure.code,
        'TAG.USER.release_version_conflict',
      );
      expect(exception.runtimeFailure.recovery.action, 'surface');
      expect(exception.userMessage, '标签发布已更新，请刷新后重试');
    });
  });
}
