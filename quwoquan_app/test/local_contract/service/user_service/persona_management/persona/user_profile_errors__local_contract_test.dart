import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart'
    show canonicalRuntimeErrorBody;

/// USER.PROFILE 资料编辑与二维码错误码契约。
///
/// 断言值以 `lib/runtime/errors/generated/user/user_errors.g.dart` 为准:
/// fromCode 解析、httpStatus、recoveryAction 恢复语义三件套,
/// 并对代表码走 CloudErrorMapper 映射负例。
void main() {
  group('UserErrorCode — 资料编辑校验契约(USER.PROFILE)', () {
    test('省市地区无效:400 surface', () {
      expect(
        UserErrorCode.fromCode('USER.PROFILE.invalid_region'),
        UserErrorCode.profileInvalidRegion,
      );
      expect(UserErrorCode.profileInvalidRegion.httpStatus, 400);
      expect(UserErrorCode.profileInvalidRegion.recoveryAction, 'surface');
    });

    test('标签引用不可用:400 surface,须重新选择', () {
      expect(
        UserErrorCode.fromCode('USER.PROFILE.invalid_tag_ref'),
        UserErrorCode.profileInvalidTagRef,
      );
      expect(UserErrorCode.profileInvalidTagRef.httpStatus, 400);
      expect(UserErrorCode.profileInvalidTagRef.recoveryAction, 'surface');
    });

    test('图片上传未完成:400 surface,须重新选择并保存', () {
      expect(
        UserErrorCode.fromCode('USER.PROFILE.invalid_media_asset'),
        UserErrorCode.profileInvalidMediaAsset,
      );
      expect(UserErrorCode.profileInvalidMediaAsset.httpStatus, 400);
      expect(UserErrorCode.profileInvalidMediaAsset.recoveryAction, 'surface');
    });
  });

  group('UserErrorCode — 资料并发冲突契约(USER.PROFILE)', () {
    test('标签目录已更新:409 retry,刷新后重选即可恢复', () {
      expect(
        UserErrorCode.fromCode('USER.PROFILE.taxonomy_release_conflict'),
        UserErrorCode.profileTaxonomyReleaseConflict,
      );
      expect(UserErrorCode.profileTaxonomyReleaseConflict.httpStatus, 409);
      expect(
        UserErrorCode.profileTaxonomyReleaseConflict.recoveryAction,
        'retry',
      );
    });

    test('资料版本冲突:409 retry,刷新后重试即可恢复', () {
      expect(
        UserErrorCode.fromCode('USER.PROFILE.version_conflict'),
        UserErrorCode.profileVersionConflict,
      );
      expect(UserErrorCode.profileVersionConflict.httpStatus, 409);
      expect(UserErrorCode.profileVersionConflict.recoveryAction, 'retry');
    });

    test('幂等冲突(重复保存内容不一致):409 surface', () {
      expect(
        UserErrorCode.fromCode('USER.PROFILE.idempotency_conflict'),
        UserErrorCode.profileIdempotencyConflict,
      );
      expect(UserErrorCode.profileIdempotencyConflict.httpStatus, 409);
      expect(
        UserErrorCode.profileIdempotencyConflict.recoveryAction,
        'surface',
      );
    });
  });

  group('UserErrorCode — 资料二维码契约(USER.PROFILE.qr_*)', () {
    test('二维码无效:404 surface,须让对方重新分享', () {
      expect(
        UserErrorCode.fromCode('USER.PROFILE.qr_token_invalid'),
        UserErrorCode.profileQrTokenInvalid,
      );
      expect(UserErrorCode.profileQrTokenInvalid.httpStatus, 404);
      expect(UserErrorCode.profileQrTokenInvalid.recoveryAction, 'surface');
    });

    test('二维码过期:410 下发即失效,surface 引导重新分享', () {
      expect(
        UserErrorCode.fromCode('USER.PROFILE.qr_token_expired'),
        UserErrorCode.profileQrTokenExpired,
      );
      expect(UserErrorCode.profileQrTokenExpired.httpStatus, 410);
      expect(UserErrorCode.profileQrTokenExpired.recoveryAction, 'surface');
    });
  });

  group('UserErrorCode — CloudErrorMapper 映射负例(USER.PROFILE)', () {
    test('version_conflict 响应解析为 typed user 域错误并保留重试语义', () {
      final exception = CloudErrorMapper.fromStatusCode(
        UserErrorCode.profileVersionConflict.httpStatus,
        body: canonicalRuntimeErrorBody(
          code: UserErrorCode.profileVersionConflict.code,
          origin: 'user',
          kind: 'validation',
          nature: 'transient',
          businessObject: 'user_profile',
          functionModule: 'user',
          userMessage: UserErrorCode.profileVersionConflict.defaultMessageZh,
          recoveryAction: UserErrorCode.profileVersionConflict.recoveryAction,
          disruptionLevel: UserErrorCode.profileVersionConflict.disruptionLevel,
        ),
        requestPath: '/user/profile',
      );

      expect(exception.domainErrorCode?.domain, 'user');
      expect(
        exception.domainErrorCode?.code,
        UserErrorCode.profileVersionConflict.code,
      );
      final recovery = exception.runtimeFailure.recovery;
      expect(recovery.isPresent, isTrue);
      expect(recovery.action, 'retry');
    });
  });
}
