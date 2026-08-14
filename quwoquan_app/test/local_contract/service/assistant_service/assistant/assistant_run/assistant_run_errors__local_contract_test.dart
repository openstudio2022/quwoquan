// assistant 域 generated 错误码断言覆盖:
//
// 声明源是 `lib/runtime/errors/generated/assistant/assistant_errors.g.dart`
// (由 assistant/assistant/assistant_run/errors.yaml codegen,禁止手改)。
// 本套件对每个客户端可见错误码断言:
//   1. `AssistantErrorCode.fromCode('<wire>')` 解析到正确枚举常量;
//   2. `httpStatus` 与 generated 声明一致(0 表示经 run 流事件/设备本地
//      路径下发、无 HTTP 状态位);
//   3. zh/en 默认文案存在且 enum 内嵌 defaultMessage 与 zh map 同源;
//   4. 每组代表码走 CloudErrorMapper 映射负例:canonical
//      RuntimeErrorResponse body -> CloudException.domainErrorCode 解析
//      -> 恢复语义如实消费 -> UiErrorSemantic -> 埋点(错误链探针)。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/assistant/assistant_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart';

/// 一条错误码契约:wire 字面量 + 枚举常量 + generated 声明的 httpStatus。
typedef _CodeCase = ({String wire, AssistantErrorCode value, int httpStatus});

/// MIDDLEWARE:provider/tool/web 依赖不可用与预算耗尽类(暂态,可重试)。
const List<_CodeCase> _middlewareCases = <_CodeCase>[
  (
    wire: 'ASSISTANT.MIDDLEWARE.finance_provider_unavailable',
    value: AssistantErrorCode.financeProviderUnavailable,
    httpStatus: 0,
  ),
  (
    wire: 'ASSISTANT.MIDDLEWARE.intersection_evidence_unavailable',
    value: AssistantErrorCode.intersectionEvidenceUnavailable,
    httpStatus: 503,
  ),
  (
    wire: 'ASSISTANT.MIDDLEWARE.model_provider_unavailable',
    value: AssistantErrorCode.modelProviderUnavailable,
    httpStatus: 0,
  ),
  (
    wire: 'ASSISTANT.MIDDLEWARE.public_search_provider_unavailable',
    value: AssistantErrorCode.publicSearchProviderUnavailable,
    httpStatus: 0,
  ),
  (
    wire: 'ASSISTANT.MIDDLEWARE.tool_unavailable',
    value: AssistantErrorCode.toolUnavailable,
    httpStatus: 0,
  ),
  (
    wire: 'ASSISTANT.MIDDLEWARE.weather_provider_unavailable',
    value: AssistantErrorCode.weatherProviderUnavailable,
    httpStatus: 0,
  ),
  (
    wire: 'ASSISTANT.MIDDLEWARE.web_budget_exhausted',
    value: AssistantErrorCode.webBudgetExhausted,
    httpStatus: 0,
  ),
  (
    wire: 'ASSISTANT.MIDDLEWARE.web_fetch_unavailable',
    value: AssistantErrorCode.webFetchUnavailable,
    httpStatus: 0,
  ),
];

/// SYSTEM:run/stream/connector/web 侧系统失败类(暂态,可重试)。
const List<_CodeCase> _systemCases = <_CodeCase>[
  (
    wire: 'ASSISTANT.SYSTEM.connector_gateway_unavailable',
    value: AssistantErrorCode.connectorGatewayUnavailable,
    httpStatus: 0,
  ),
  (
    wire: 'ASSISTANT.SYSTEM.device_action_failed',
    value: AssistantErrorCode.deviceActionFailed,
    httpStatus: 0,
  ),
  (
    wire: 'ASSISTANT.SYSTEM.run_execution_failed',
    value: AssistantErrorCode.runExecutionFailed,
    httpStatus: 0,
  ),
  (
    wire: 'ASSISTANT.SYSTEM.run_policy_unavailable',
    value: AssistantErrorCode.runPolicyUnavailable,
    httpStatus: 503,
  ),
  (
    wire: 'ASSISTANT.SYSTEM.run_reasoning_profile_unavailable',
    value: AssistantErrorCode.runReasoningProfileUnavailable,
    httpStatus: 0,
  ),
  (
    wire: 'ASSISTANT.SYSTEM.run_skill_package_unavailable',
    value: AssistantErrorCode.runSkillPackageUnavailable,
    httpStatus: 503,
  ),
  (
    wire: 'ASSISTANT.SYSTEM.stream_unavailable',
    value: AssistantErrorCode.streamUnavailable,
    httpStatus: 503,
  ),
  (
    wire: 'ASSISTANT.SYSTEM.web_budget_unavailable',
    value: AssistantErrorCode.webBudgetUnavailable,
    httpStatus: 0,
  ),
  (
    wire: 'ASSISTANT.SYSTEM.web_evidence_unavailable',
    value: AssistantErrorCode.webEvidenceUnavailable,
    httpStatus: 0,
  ),
];

/// USER:device_action permit / run / connector / web 用户侧失败类
/// (需要用户动作,恢复语义以 surface 呈现为主)。
const List<_CodeCase> _userCases = <_CodeCase>[
  (
    wire: 'ASSISTANT.USER.connector_capability_required',
    value: AssistantErrorCode.connectorCapabilityRequired,
    httpStatus: 0,
  ),
  (
    wire: 'ASSISTANT.USER.delegated_approval_invalid',
    value: AssistantErrorCode.delegatedApprovalInvalid,
    httpStatus: 403,
  ),
  (
    wire: 'ASSISTANT.USER.device_action_permission_denied',
    value: AssistantErrorCode.deviceActionPermissionDenied,
    httpStatus: 0,
  ),
  (
    wire: 'ASSISTANT.USER.device_action_permit_expired',
    value: AssistantErrorCode.deviceActionPermitExpired,
    httpStatus: 410,
  ),
  (
    wire: 'ASSISTANT.USER.device_action_permit_invalid',
    value: AssistantErrorCode.deviceActionPermitInvalid,
    httpStatus: 403,
  ),
  (
    wire: 'ASSISTANT.USER.device_action_permit_replayed',
    value: AssistantErrorCode.deviceActionPermitReplayed,
    httpStatus: 409,
  ),
  (
    wire: 'ASSISTANT.USER.intersection_evidence_not_found',
    value: AssistantErrorCode.intersectionEvidenceNotFound,
    httpStatus: 404,
  ),
  (
    wire: 'ASSISTANT.USER.run_idempotency_conflict',
    value: AssistantErrorCode.runIdempotencyConflict,
    httpStatus: 409,
  ),
  (
    wire: 'ASSISTANT.USER.run_invalid_argument',
    value: AssistantErrorCode.runInvalidArgument,
    httpStatus: 400,
  ),
  (
    wire: 'ASSISTANT.USER.run_not_found',
    value: AssistantErrorCode.runNotFound,
    httpStatus: 404,
  ),
  (
    wire: 'ASSISTANT.USER.run_skill_disabled',
    value: AssistantErrorCode.runSkillDisabled,
    httpStatus: 409,
  ),
  (
    wire: 'ASSISTANT.USER.web_target_rejected',
    value: AssistantErrorCode.webTargetRejected,
    httpStatus: 0,
  ),
];

void _expectCaseMatchesGeneratedDeclaration(_CodeCase testCase) {
  final parsed = AssistantErrorCode.fromCode(testCase.wire);
  expect(parsed, testCase.value);
  expect(parsed.code, testCase.wire);
  expect(
    parsed.httpStatus,
    testCase.httpStatus,
    reason: '${testCase.wire}: httpStatus 必须与 generated 声明一致',
  );
  expect(parsed.defaultMessage, isNotEmpty);
  // enum 内嵌 defaultMessage 与 zh map 必须同源,en 文案必须存在。
  expect(AssistantErrorMessages.zh[parsed], parsed.defaultMessage);
  expect(AssistantErrorMessages.en[parsed], isNotNull);
  expect(AssistantErrorMessages.en[parsed], isNotEmpty);
}

void main() {
  group('AssistantErrorCode — MIDDLEWARE 依赖不可用类', () {
    for (final testCase in _middlewareCases) {
      test('fromCode(${testCase.wire}) → ${testCase.value.name}', () {
        _expectCaseMatchesGeneratedDeclaration(testCase);
      });
    }

    test('组不变量:MIDDLEWARE 类均为暂态依赖失败,状态位只能是 0 或 503', () {
      for (final testCase in _middlewareCases) {
        expect(testCase.value.code, startsWith('ASSISTANT.MIDDLEWARE.'));
        // 0 = 经 run 流事件下发无 HTTP 状态;503 = HTTP 依赖不可用。
        // 两者都是"稍后重试/降级"语义,不得出现 4xx 用户错误状态位。
        expect(
          testCase.value.httpStatus,
          anyOf(0, 503),
          reason: '${testCase.wire}: 依赖不可用类不应声明用户错误状态位',
        );
      }
    });
  });

  group('AssistantErrorCode — SYSTEM run/stream/connector 类', () {
    for (final testCase in _systemCases) {
      test('fromCode(${testCase.wire}) → ${testCase.value.name}', () {
        _expectCaseMatchesGeneratedDeclaration(testCase);
      });
    }

    test('组不变量:SYSTEM 类均为系统侧失败,状态位只能是 0 或 503', () {
      for (final testCase in _systemCases) {
        expect(testCase.value.code, startsWith('ASSISTANT.SYSTEM.'));
        expect(
          testCase.value.httpStatus,
          anyOf(0, 503),
          reason: '${testCase.wire}: 系统失败类不应声明用户错误状态位',
        );
      }
    });
  });

  group('AssistantErrorCode — USER device_action/run/connector 类', () {
    for (final testCase in _userCases) {
      test('fromCode(${testCase.wire}) → ${testCase.value.name}', () {
        _expectCaseMatchesGeneratedDeclaration(testCase);
      });
    }

    test('组不变量:USER 类状态位只能是 0 或 4xx,禁止伪装成系统错误', () {
      for (final testCase in _userCases) {
        expect(testCase.value.code, startsWith('ASSISTANT.USER.'));
        expect(
          testCase.value.httpStatus,
          anyOf(0, inInclusiveRange(400, 499)),
          reason: '${testCase.wire}: 用户侧失败不得声明 5xx 状态位',
        );
      }
    });

    test('permit 失效三态(invalid/expired/replayed)状态位语义可区分', () {
      // permit 类必须能按状态位区分"不匹配/过期/重放",端侧才能给出
      // 不同恢复引导(重新确认 vs 不再重复提交)。
      expect(AssistantErrorCode.deviceActionPermitInvalid.httpStatus, 403);
      expect(AssistantErrorCode.deviceActionPermitExpired.httpStatus, 410);
      expect(AssistantErrorCode.deviceActionPermitReplayed.httpStatus, 409);
    });
  });

  group('AssistantErrorCode — 单轨与全量契约', () {
    test('每个已声明 code round-trip:fromCode(value.code) == value', () {
      for (final value in AssistantErrorCode.values) {
        if (value == AssistantErrorCode.unknown) continue;
        expect(
          AssistantErrorCode.fromCode(value.code),
          value,
          reason: 'round-trip failed for ${value.code}',
        );
      }
    });

    test('未知码与他域码 → unknown 兜底,不得伪装成已声明错误', () {
      expect(
        AssistantErrorCode.fromCode('ASSISTANT.USER.nonexistent_error'),
        AssistantErrorCode.unknown,
      );
      expect(
        AssistantErrorCode.fromCode('CHAT.USER.unauthorized'),
        AssistantErrorCode.unknown,
      );
      expect(
        AssistantErrorCode.fromCode('abc.def.ghi'),
        AssistantErrorCode.unknown,
      );
    });
  });

  group('CloudErrorMapper — assistant 域映射负例', () {
    test('三组补齐码全部解析出 assistant 域 typed DomainErrorCode 并如实消费恢复语义', () {
      final groups =
          <
            ({
              List<_CodeCase> cases,
              String origin,
              String kind,
              String nature,
              String recoveryAction,
              int fallbackStatus,
            })
          >[
            (
              cases: _middlewareCases,
              origin: 'remoteDependency',
              kind: 'unavailable',
              nature: 'transient',
              recoveryAction: 'retry',
              fallbackStatus: 503,
            ),
            (
              cases: _systemCases,
              origin: 'system',
              kind: 'unavailable',
              nature: 'transient',
              recoveryAction: 'retry',
              fallbackStatus: 503,
            ),
            (
              cases: _userCases,
              origin: 'user',
              kind: 'validation',
              nature: 'requiresUserAction',
              recoveryAction: 'surface',
              fallbackStatus: 403,
            ),
          ];

      for (final group in groups) {
        for (final testCase in group.cases) {
          // httpStatus == 0 的码经流事件/本地路径下发;此处模拟其经网关
          // 以组语义状态位落到 HTTP 错误响应时,mapper 仍必须解析 typed code。
          final status = testCase.httpStatus == 0
              ? group.fallbackStatus
              : testCase.httpStatus;
          final exception = CloudErrorMapper.fromStatusCode(
            status,
            body: canonicalRuntimeErrorBody(
              code: testCase.wire,
              origin: group.origin,
              kind: group.kind,
              nature: group.nature,
              businessObject: 'assistant_run',
              functionModule: 'assistant',
              recoveryAction: group.recoveryAction,
            ),
            requestPath: '/assistant/run',
          );

          expect(
            exception.code,
            testCase.wire,
            reason: '${testCase.wire}: mapper 未识别 canonical stable code',
          );
          expect(
            exception.domainErrorCode?.domain,
            'assistant',
            reason: '${testCase.wire}: 未解析出 assistant 域 DomainErrorCode',
          );
          expect(
            exception.domainErrorCode?.value,
            testCase.value,
            reason: '${testCase.wire}: DomainErrorCode 未落到正确枚举常量',
          );
          expect(
            exception.runtimeFailure.recovery.action,
            group.recoveryAction,
            reason: '${testCase.wire}: 云侧下发的 recovery.action 被端侧改写',
          );
        }
      }
    });

    testWidgets('MIDDLEWARE 代表码 model_provider_unavailable 贯通错误链且恢复语义为 retry', (
      tester,
    ) async {
      final outcome = await runErrorChain(
        tester,
        statusCode: 503,
        body: canonicalRuntimeErrorBody(
          code: AssistantErrorCode.modelProviderUnavailable.code,
          origin: 'remoteDependency',
          kind: 'unavailable',
          nature: 'transient',
          businessObject: 'assistant_run',
          functionModule: 'assistant',
          requestId: 'req-assistant-middleware',
          traceId: 'trace-assistant-middleware',
          recoveryAction: 'retry',
          recoveryAfterSeconds: 30,
          disruptionLevel: 'recoverable',
        ),
        requestPath: '/assistant/run',
        category: UiErrorCategory.submit,
        scope: UiErrorScope.section,
      );

      expectErrorChainIsIntact(
        outcome,
        expectedCode: AssistantErrorCode.modelProviderUnavailable.code,
        domainLabel: 'assistant',
      );
      expect(outcome.exception.domainErrorCode?.domain, 'assistant');
      expect(
        outcome.exception.domainErrorCode?.value,
        AssistantErrorCode.modelProviderUnavailable,
      );
      // provider 不可用类:云侧下发 retry(30s 后),端侧不得改写成 surface。
      expect(outcome.exception.runtimeFailure.recovery.action, 'retry');
      expect(outcome.exception.runtimeFailure.recovery.afterSeconds, 30);
      expect(outcome.telemetryRecoveryAction, isNotNull);
    });

    testWidgets('SYSTEM 代表码 stream_unavailable 贯通错误链且恢复语义为 retry', (
      tester,
    ) async {
      final outcome = await runErrorChain(
        tester,
        statusCode: 503,
        body: canonicalRuntimeErrorBody(
          code: AssistantErrorCode.streamUnavailable.code,
          origin: 'system',
          kind: 'unavailable',
          nature: 'transient',
          businessObject: 'assistant_run',
          functionModule: 'assistant',
          requestId: 'req-assistant-system',
          traceId: 'trace-assistant-system',
          recoveryAction: 'retry',
          recoveryAfterSeconds: 5,
          disruptionLevel: 'recoverable',
        ),
        requestPath: '/assistant/run',
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.section,
      );

      expectErrorChainIsIntact(
        outcome,
        expectedCode: AssistantErrorCode.streamUnavailable.code,
        domainLabel: 'assistant',
      );
      expect(outcome.exception.domainErrorCode?.domain, 'assistant');
      expect(
        outcome.exception.domainErrorCode?.value,
        AssistantErrorCode.streamUnavailable,
      );
      expect(outcome.exception.runtimeFailure.recovery.action, 'retry');
      expect(outcome.exception.runtimeFailure.recovery.afterSeconds, 5);
    });

    testWidgets('USER 代表码 device_action_permit_expired 贯通错误链且恢复语义为 surface', (
      tester,
    ) async {
      final outcome = await runErrorChain(
        tester,
        statusCode: 410,
        body: canonicalRuntimeErrorBody(
          code: AssistantErrorCode.deviceActionPermitExpired.code,
          origin: 'user',
          kind: 'validation',
          nature: 'requiresUserAction',
          businessObject: 'assistant_run',
          functionModule: 'assistant',
          requestId: 'req-assistant-user',
          traceId: 'trace-assistant-user',
          recoveryAction: 'surface',
          disruptionLevel: 'recoverable',
        ),
        requestPath: '/assistant/run',
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );

      expectErrorChainIsIntact(
        outcome,
        expectedCode: AssistantErrorCode.deviceActionPermitExpired.code,
        domainLabel: 'assistant',
      );
      expect(outcome.exception.domainErrorCode?.domain, 'assistant');
      expect(
        outcome.exception.domainErrorCode?.value,
        AssistantErrorCode.deviceActionPermitExpired,
      );
      // permit 失效类:需要用户重新确认,恢复语义必须 surface 而非静默重试。
      expect(outcome.exception.runtimeFailure.recovery.action, 'surface');
    });
  });
}
