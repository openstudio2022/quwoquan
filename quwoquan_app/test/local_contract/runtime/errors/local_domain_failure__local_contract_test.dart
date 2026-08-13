import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/domain_error_code.dart';
import 'package:quwoquan_app/runtime/errors/generated/ops/ops_event_record_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/generated/rtc/rtc_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/generated/search/search_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/generated/tag/tag_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/local_domain_failure.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';

import '../../../support/runtime/errors/error_chain_probe.dart';

/// `localDomainCloudException` 的核心契约：**端侧本地判定与云端返回不可分叉**。
///
/// 这是任务 D 的防回退证据。过去端侧本地判定（关系已拉黑、人数已满）会直接手写
/// `UiErrorSemantic(title: ..., message: ...)`，于是同一个业务失败有两套语义，
/// 埋点里本地这一半没有 `sourceCode`，线上按错误码聚合直接漏掉。
void main() {
  test('未声明的错误码必须被拒绝，不得成为绕过 contracts 的造码后门', () {
    expect(
      () => localDomainCloudException('MADE_UP.SYSTEM.not_declared'),
      throwsA(isA<ArgumentError>()),
    );
    expect(() => localDomainCloudException(''), throwsA(isA<ArgumentError>()));
  });

  test('已声明的错误码解析出 canonical code 与 runtimeFailure', () {
    final exception = localDomainCloudException(RtcErrorCode.blocked.code);

    expect(exception.code, 'RTC.USER.blocked');
    expect(exception.statusCode, RtcErrorCode.blocked.httpStatus);
    expect(exception.domainErrorCode, isNotNull);
    expect(exception.runtimeFailure, isNotNull);
  });

  test('SEARCH/TAG/OPS 域已注册进 registry，本地判定不再 ArgumentError', () {
    final searchCode = DomainErrorCodeRegistry.fromCode(
      SearchErrorCode.searchHotQueryUnavailable.code,
    );
    expect(searchCode, isNotNull);
    expect(searchCode!.domain, 'search');
    expect(
      searchCode.defaultMessage,
      SearchErrorCode.searchHotQueryUnavailable.defaultMessage,
    );

    final tagCode = DomainErrorCodeRegistry.fromCode(
      TagErrorCode.tagNotFound.code,
    );
    expect(tagCode, isNotNull);
    expect(tagCode!.domain, 'tag');
    expect(tagCode.httpStatus, TagErrorCode.tagNotFound.httpStatus);

    final opsCode = DomainErrorCodeRegistry.fromCode(
      OpsEventRecordErrorCode.logstoreUnavailable.code,
    );
    expect(opsCode, isNotNull);
    expect(opsCode!.domain, 'ops');

    for (final code in <String>[
      SearchErrorCode.searchHotQueryUnavailable.code,
      TagErrorCode.tagNotFound.code,
      OpsEventRecordErrorCode.logstoreUnavailable.code,
    ]) {
      final exception = localDomainCloudException(code);
      expect(exception.code, code);
      expect(exception.runtimeFailure, isNotNull);
    }
  });

  testWidgets('本地判定与云端返回同一个码时，展示语义与埋点完全一致', (tester) async {
    const code = 'RTC.USER.blocked';

    // 云端返回该码时的完整链路产物。
    final remote = await runErrorChain(
      tester,
      statusCode: RtcErrorCode.blocked.httpStatus,
      body: canonicalRuntimeErrorBody(
        code: code,
        origin: 'user',
        kind: 'permission',
        nature: 'permanent',
        businessObject: 'call_session',
        functionModule: 'rtc',
      ),
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
      allowRetry: false,
    );

    // 端侧本地判定同一件事时的链路产物。
    final local = await runErrorChainForError(
      tester,
      error: localDomainCloudException(code),
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
      allowRetry: false,
    );

    expect(local.semantic.sourceCode, remote.semantic.sourceCode);
    expect(local.semantic.message, remote.semantic.message);
    expect(local.semantic.title, remote.semantic.title);
    expect(local.semantic.recoveryAction, remote.semantic.recoveryAction);
    expect(local.semantic.failureKind, remote.semantic.failureKind);
    expect(
      local.telemetrySourceCode,
      code,
      reason: '本地判定的失败也必须能在埋点里按错误码聚合',
    );
    expect(local.telemetryFailureKind, remote.telemetryFailureKind);
  });
}
