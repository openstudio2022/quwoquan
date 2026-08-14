// media_upload_session 对象 generated 错误码的端侧断言覆盖:
// media_upload_session_expired 的枚举解析、恢复语义与
// CloudErrorMapper 映射负例。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart';

void main() {
  group('ContentErrorCode — media_upload_session 错误码契约', () {
    test('media_upload_session_expired 解析与恢复语义与声明一致', () {
      final parsed = ContentErrorCode.fromCode(
        'CONTENT.USER.media_upload_session_expired',
      );
      expect(parsed, ContentErrorCode.mediaUploadSessionExpired);
      expect(parsed.code, 'CONTENT.USER.media_upload_session_expired');
      expect(parsed.httpStatus, 409);
      // 上传凭证过期可通过重新准备会话自动恢复,声明为 retry。
      expect(parsed.recoveryAction, 'retry');
      expect(parsed.recoveryAfterSeconds, 0);
      expect(ContentErrorMessages.zh[parsed], isNotEmpty);
      expect(ContentErrorMessages.en[parsed], isNotEmpty);
    });
  });

  group('CloudErrorMapper — media_upload_session 代表性映射负例', () {
    test('409 media_upload_session_expired → typed 解析 + retry 恢复', () {
      final exception = CloudErrorMapper.fromStatusCode(
        409,
        body: canonicalRuntimeErrorBody(
          code: 'CONTENT.USER.media_upload_session_expired',
          origin: 'user',
          kind: 'validation',
          nature: 'transient',
          businessObject: 'media_upload_session',
          functionModule: 'content',
          recoveryAction: 'retry',
          requestId: 'req-upload-session-errors-1',
          traceId: 'trace-upload-session-errors-1',
        ),
        requestPath: '/content/media/upload-sessions',
      );

      expect(exception.code, 'CONTENT.USER.media_upload_session_expired');
      expect(exception.domainErrorCode?.domain, 'content');
      expect(
        exception.domainErrorCode?.value,
        ContentErrorCode.mediaUploadSessionExpired,
      );
      expect(exception.runtimeFailure.kind, RuntimeFailureKind.validation);
      expect(exception.runtimeFailure.transportStatus, 409);
      expect(exception.runtimeFailure.recovery.action, 'retry');
    });
  });
}
