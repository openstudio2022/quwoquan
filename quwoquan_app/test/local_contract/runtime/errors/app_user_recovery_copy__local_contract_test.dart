// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-errors/error-code-and-response-envelope/spec.md#gwt-002

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/app_user_recovery.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  test('首页服务访问失败文案共享标题但保留分因说明', () {
    final connection = AppUserRecoveryContract.copyFor(
      AppUserRecoveryGroup.connectionUnavailable,
    );
    final timeout = AppUserRecoveryContract.copyFor(
      AppUserRecoveryGroup.requestTimedOut,
    );
    final service = AppUserRecoveryContract.copyFor(
      AppUserRecoveryGroup.serviceUnavailable,
    );

    expect(connection.title, '暂时无法访问服务');
    expect(timeout.title, connection.title);
    expect(service.title, connection.title);
    expect(connection.message, '本次内容请求未能到达服务。');
    expect(timeout.message, '服务响应时间较长，这次请求已停止等待。');
    expect(service.message, '服务暂时没有完成这次内容请求。');
    expect({
      connection.message,
      timeout.message,
      service.message,
    }, hasLength(3));
  });

  test('全部恢复组不重复标题说明动作且不泄露品牌或技术字段', () {
    for (final group in AppUserRecoveryGroup.values) {
      final copy = AppUserRecoveryContract.copyFor(group, retryAfterSeconds: 3);
      final visible = '${copy.title}${copy.message}${copy.action.label}';
      expect(copy.title.trim(), isNot(copy.message.trim()), reason: group.name);
      expect(
        copy.title.trim(),
        isNot(copy.action.label.trim()),
        reason: group.name,
      );
      expect(
        visible,
        isNot(
          anyOf(
            contains('趣我圈'),
            contains('DNS'),
            contains('TLS'),
            contains('HTTP'),
          ),
        ),
        reason: group.name,
      );
    }
  });

  // spec_ref: specs/feature-tree/runtime/runtime-errors/error-code-and-response-envelope/spec.md#gwt-002.t1
  // spec_ref: specs/feature-tree/runtime/runtime-errors/error-code-and-response-envelope/spec.md#gwt-002.t2
  test('canonical code 经恢复契约产出一致的组、动作并保留错误上下文', () {
    // GWT-002：服务以 canonical error code 返回失败，调用方解析信封并呈现
    // 恢复动作时，错误上下文、稳定 code 与恢复语义必须一致，失败不被掩盖。
    final exception = CloudErrorMapper.fromStatusCode(
      404,
      body: jsonEncode(<String, dynamic>{
        'code': 'CONTENT.USER.post_not_found',
        'origin': 'user',
        'kind': 'notFound',
        'nature': 'permanent',
        'requestId': 'req-recovery-1',
        'traceId': 'trace-recovery-1',
        'location': <String, dynamic>{
          'businessObject': 'content_post',
          'functionModule': 'post_query',
        },
        'context': <String, dynamic>{'attributes': <Map<String, String>>[]},
      }),
      requestPath: '/content/posts/missing',
    );
    final failure = exception.runtimeFailure;
    // 信封解析后失败事实完整，不以成功形态出现。
    expect(failure.code, 'CONTENT.USER.post_not_found');
    expect(failure.kind, RuntimeFailureKind.notFound);

    final group = AppUserRecoveryContract.classify(
      error: exception,
      failure: failure,
      category: UiErrorCategory.pageLoad,
    );
    final semantic = AppUserRecoveryContract.semanticFor(
      group: group,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
      sourceCode: failure.code,
      failureKind: failure.kind,
      requestId: exception.requestId,
      traceId: exception.traceId,
    );

    // 稳定 code 与观测上下文原样保留，恢复语义与该组契约逐项一致。
    expect(semantic.sourceCode, 'CONTENT.USER.post_not_found');
    expect(semantic.failureKind, RuntimeFailureKind.notFound);
    expect(semantic.requestId, 'req-recovery-1');
    expect(semantic.traceId, 'trace-recovery-1');
    expect(semantic.userRecoveryGroup, group);
    final copy = AppUserRecoveryContract.copyFor(group);
    expect(semantic.title, copy.title);
    expect(semantic.message, copy.message);
    expect(semantic.primaryAction?.type, copy.action.type);
    expect(semantic.primaryAction?.label, copy.action.label);
    expect(semantic.recoveryAction, copy.recoveryAction);
  });

  test('页面重试动作统一为重新加载且不提供次级圈子操作', () {
    for (final group in <AppUserRecoveryGroup>{
      AppUserRecoveryGroup.connectNetwork,
      AppUserRecoveryGroup.connectionUnavailable,
      AppUserRecoveryGroup.requestTimedOut,
      AppUserRecoveryGroup.serviceUnavailable,
      AppUserRecoveryGroup.invalidContent,
      AppUserRecoveryGroup.guestSessionUnavailable,
      AppUserRecoveryGroup.reloadLater,
    }) {
      final copy = AppUserRecoveryContract.copyFor(group);
      expect(copy.action.type, UiErrorActionType.retry, reason: group.name);
      expect(copy.action.label, SearchText.reload, reason: group.name);
    }
  });
}
