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
  test('服务侧失败文案直白归因为系统问题且三组标题说明互不相同', () {
    final connection = AppUserRecoveryContract.copyFor(
      AppUserRecoveryGroup.connectionUnavailable,
    );
    final timeout = AppUserRecoveryContract.copyFor(
      AppUserRecoveryGroup.requestTimedOut,
    );
    final service = AppUserRecoveryContract.copyFor(
      AppUserRecoveryGroup.serviceUnavailable,
    );

    expect(connection.title, '服务暂时连不上');
    expect(timeout.title, '服务响应超时');
    expect(service.title, '系统出了问题');
    expect(connection.message, '这次请求没有到达我们的服务，通常是我们这边的问题，请稍后再试。');
    expect(timeout.message, '我们的系统处理太慢，这次请求已停止等待。这是系统问题，不是你的操作导致的。');
    expect(service.message, '我们的服务暂时没能处理这次请求。这是系统问题，不是你的网络或操作导致的，请稍后再试。');
    expect({connection.title, timeout.title, service.title}, hasLength(3));
    expect({
      connection.message,
      timeout.message,
      service.message,
    }, hasLength(3));
    // REQ-013：服务侧失败必须把责任归到我们的系统，不得用不归因的模糊表述。
    for (final copy in <AppUserRecoveryCopy>[connection, timeout, service]) {
      expect(
        '${copy.title}${copy.message}',
        anyOf(contains('系统问题'), contains('我们这边的问题')),
      );
      expect(copy.title, isNot('暂时无法访问服务'));
      // 说明不得包含主动作完整文案。
      expect(copy.message, isNot(contains(SearchText.reload)));
    }
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
          anyOf(<Matcher>[
            contains('趣我圈'),
            contains('DNS'),
            contains('TLS'),
            contains('HTTP'),
            contains('上游'),
            contains('连接拒绝'),
            contains('契约'),
            contains('端口'),
            contains('证书'),
          ]),
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
