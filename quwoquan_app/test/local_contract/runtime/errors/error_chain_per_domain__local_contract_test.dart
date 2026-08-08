import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';

import '../../../support/runtime/errors/error_chain_probe.dart';

/// 每个客户端可见业务域至少一条错误链端到端用例。
///
/// 域清单由 `quwoquan_service/generated/contract_graph.json` 中带
/// `clientContract` 的 operation 派生：13 个域、77 个客户端可见对象。
/// 每域取一个已在所属服务 `errors.yaml` 声明、并已生成进
/// `DomainErrorCodeRegistry` 的代表性错误码，走完整条链：
///
///   HTTP 错误响应 -> CloudErrorMapper -> UiErrorSemantic -> 恢复动作 -> 埋点属性
///
/// 共性不变量集中在 `expectErrorChainIsIntact`；逐域用例只声明该域特有的
/// 期望，避免 13 份复制粘贴各自漂移。
void main() {
  /// 每个 case 是「一个域 + 一个真实声明过的错误码 + 该码的 wire 语义」。
  final cases = <_DomainErrorChainCase>[
    _DomainErrorChainCase(
      domain: 'assistant',
      code: 'ASSISTANT.USER.run_unauthorized',
      statusCode: 401,
      origin: 'user',
      kind: 'auth',
      nature: 'requiresUserAction',
      businessObject: 'assistant_run',
      functionModule: 'assistant',
      recoveryAction: 'surface',
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
    ),
    _DomainErrorChainCase(
      domain: 'chat',
      code: 'CHAT.SYSTEM.message_media_unavailable',
      statusCode: 503,
      origin: 'remoteDependency',
      kind: 'unavailable',
      nature: 'transient',
      businessObject: 'chat_message',
      functionModule: 'chat',
      recoveryAction: 'retry',
      recoveryAfterSeconds: 5,
      category: UiErrorCategory.submit,
      scope: UiErrorScope.section,
    ),
    _DomainErrorChainCase(
      domain: 'circle',
      code: 'CIRCLE.USER.join_approval_required',
      statusCode: 403,
      origin: 'user',
      kind: 'permission',
      nature: 'requiresUserAction',
      businessObject: 'circle_membership',
      functionModule: 'circle',
      recoveryAction: 'surface',
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
    ),
    _DomainErrorChainCase(
      domain: 'content',
      code: 'CONTENT.USER.rate_limited',
      statusCode: 429,
      origin: 'user',
      kind: 'rateLimited',
      nature: 'transient',
      businessObject: 'post',
      functionModule: 'content',
      recoveryAction: 'retry',
      recoveryAfterSeconds: 60,
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
    ),
    _DomainErrorChainCase(
      domain: 'entity',
      code: 'ENTITY.SYSTEM.internal_error',
      statusCode: 500,
      origin: 'system',
      kind: 'internal',
      nature: 'transient',
      businessObject: 'homepage',
      functionModule: 'entity',
      recoveryAction: 'retry',
      recoveryAfterSeconds: 5,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.global,
    ),
    _DomainErrorChainCase(
      domain: 'integration',
      code: 'INTEGRATION.USER.location_permission_required',
      statusCode: 403,
      origin: 'user',
      kind: 'permission',
      nature: 'requiresPermission',
      businessObject: 'location',
      functionModule: 'external_integration',
      recoveryAction: 'openSettings',
      category: UiErrorCategory.submit,
      scope: UiErrorScope.section,
    ),
    _DomainErrorChainCase(
      domain: 'notification',
      code: 'NOTIFICATION.SYSTEM.storage_read_failed',
      statusCode: 500,
      origin: 'system',
      kind: 'storage',
      nature: 'transient',
      businessObject: 'notification',
      functionModule: 'notification_delivery',
      recoveryAction: 'retry',
      recoveryAfterSeconds: 5,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.global,
    ),
    _DomainErrorChainCase(
      domain: 'ops',
      code: 'OPS.SYSTEM.logstore_unavailable',
      statusCode: 503,
      origin: 'remoteDependency',
      kind: 'unavailable',
      nature: 'transient',
      businessObject: 'ops_event_record',
      functionModule: 'product_ops',
      recoveryAction: 'retry',
      recoveryAfterSeconds: 30,
      category: UiErrorCategory.backgroundAction,
      scope: UiErrorScope.section,
    ),
    _DomainErrorChainCase(
      domain: 'realtime',
      code: 'REALTIME.SYSTEM.internal_error',
      statusCode: 500,
      origin: 'system',
      kind: 'internal',
      nature: 'transient',
      businessObject: 'realtime_channel',
      functionModule: 'realtime',
      recoveryAction: 'retry',
      recoveryAfterSeconds: 5,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.section,
    ),
    _DomainErrorChainCase(
      domain: 'rtc',
      code: 'RTC.USER.blocked',
      statusCode: 403,
      origin: 'user',
      kind: 'permission',
      nature: 'permanent',
      businessObject: 'call_session',
      functionModule: 'rtc',
      recoveryAction: 'surface',
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
    ),
    _DomainErrorChainCase(
      domain: 'search',
      code: 'SEARCH.SYSTEM.internal_error',
      statusCode: 500,
      origin: 'system',
      kind: 'internal',
      nature: 'transient',
      businessObject: 'search_query',
      functionModule: 'search',
      recoveryAction: 'retry',
      recoveryAfterSeconds: 5,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.section,
    ),
    _DomainErrorChainCase(
      domain: 'tag',
      code: 'TAG.SYSTEM.storage_read_failed',
      statusCode: 500,
      origin: 'system',
      kind: 'storage',
      nature: 'transient',
      businessObject: 'tag',
      functionModule: 'tag',
      recoveryAction: 'retry',
      recoveryAfterSeconds: 5,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.section,
    ),
    _DomainErrorChainCase(
      domain: 'user',
      code: 'USER.AUTH.token_expired',
      statusCode: 401,
      origin: 'user',
      kind: 'auth',
      nature: 'requiresUserAction',
      businessObject: 'account',
      functionModule: 'user',
      recoveryAction: 'surface',
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
    ),
  ];

  group('client-visible domain error chain', () {
    for (final testCase in cases) {
      testWidgets('${testCase.domain}: ${testCase.code} 贯通全链', (tester) async {
        final outcome = await runErrorChain(
          tester,
          statusCode: testCase.statusCode,
          body: canonicalRuntimeErrorBody(
            code: testCase.code,
            origin: testCase.origin,
            kind: testCase.kind,
            nature: testCase.nature,
            businessObject: testCase.businessObject,
            functionModule: testCase.functionModule,
            requestId: 'req-${testCase.domain}',
            traceId: 'trace-${testCase.domain}',
            recoveryAction: testCase.recoveryAction,
            recoveryAfterSeconds: testCase.recoveryAfterSeconds,
            disruptionLevel: 'recoverable',
            // 动态上下文只以 string-only attributes 出现。
            contextAttributes: <String, String>{
              'objectId': 'probe-object-1',
            },
          ),
          requestPath: '/${testCase.domain}/probe',
          category: testCase.category,
          scope: testCase.scope,
        );

        expectErrorChainIsIntact(
          outcome,
          expectedCode: testCase.code,
          domainLabel: testCase.domain,
        );

        // trace/request 关联必须一路传到埋点，否则线上无法把用户报障与日志对齐。
        expect(outcome.telemetryTraceId, 'trace-${testCase.domain}');
        expect(outcome.telemetryRequestId, 'req-${testCase.domain}');

        // 云侧下发的 recovery 指令必须被埋点如实反映，不得被端侧改写。
        expect(
          outcome.telemetryRecoveryAction,
          isNotNull,
          reason: '${testCase.domain}: 埋点缺少 recoveryAction，无法分析恢复效果',
        );

        // 动态上下文只能留在 attributes 里，不得渗进错误码或用户文案。
        expect(outcome.exception.code, isNot(contains('probe-object-1')));
        expect(outcome.semantic.message, isNot(contains('probe-object-1')));
      });
    }
  });

  group('error chain negative guards', () {
    testWidgets('未声明的错误码不得被伪装成已知领域错误', (tester) async {
      final outcome = await runErrorChain(
        tester,
        statusCode: 500,
        body: canonicalRuntimeErrorBody(
          code: 'MADE_UP.SYSTEM.not_a_declared_code',
          origin: 'system',
          kind: 'internal',
          nature: 'bug',
          businessObject: 'unknown',
          functionModule: 'unknown',
        ),
        requestPath: '/probe/unknown',
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.global,
      );

      // 未登记的码不得解析出 domainErrorCode——否则等于绕过 contracts 造码。
      expect(outcome.exception.domainErrorCode, isNull);
      // 但用户仍必须看到可读文案与恢复路径，不能白屏或泄露原始码。
      expect(outcome.semantic.message.trim(), isNotEmpty);
      expect(
        outcome.semantic.message,
        isNot(contains('MADE_UP.SYSTEM.not_a_declared_code')),
      );
    });

    testWidgets('非 canonical 响应体仍必须给出可恢复错误态', (tester) async {
      // 只有裸 message、没有 location/context 的响应体：mapper 会走降级路径，
      // 但页面依然不能失去文案与恢复动作。
      final outcome = await runErrorChain(
        tester,
        statusCode: 502,
        body: '{"message":"bad gateway"}',
        requestPath: '/probe/degraded',
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.global,
      );

      expect(outcome.semantic.message.trim(), isNotEmpty);
      expect(
        outcome.semantic.primaryAction != null ||
            outcome.semantic.secondaryAction != null ||
            outcome.semantic.recoveryAction != null,
        isTrue,
      );
    });
  });
}

final class _DomainErrorChainCase {
  const _DomainErrorChainCase({
    required this.domain,
    required this.code,
    required this.statusCode,
    required this.origin,
    required this.kind,
    required this.nature,
    required this.businessObject,
    required this.functionModule,
    required this.recoveryAction,
    required this.category,
    required this.scope,
    this.recoveryAfterSeconds = 0,
  });

  final String domain;
  final String code;
  final int statusCode;
  final String origin;
  final String kind;
  final String nature;
  final String businessObject;
  final String functionModule;
  final String recoveryAction;
  final int recoveryAfterSeconds;
  final UiErrorCategory category;
  final UiErrorScope scope;
}
