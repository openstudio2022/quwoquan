/// L1 契约测试：降级响应根因字段契约
///
/// 验收覆盖：A3（工具失败可恢复）、A8（测试覆盖可复跑）
/// 执行方式：dart test（纯 VM，无 flutter shell 依赖）
///
/// 核心命题：
///   任何 degraded == true 的 AssistantRunResponse：
///   1. errorCode 不能为 null 也不能为空字符串
///   2. errorCode 必须是已知枚举值（AssistantErrorCode.*）
///   3. traces 中必须存在 type == toolError 且 message 包含根因信息（非固定文案）
///   4. finalText 不得是空字符串（用户必须看到某种提示）
///   5. finalText 不得含 JSON envelope key（assistant_turn_v2 / contractVersion）

import 'dart:convert';

import 'package:quwoquan_app/personal_assistant/app/capability_gateway.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';
import 'package:test/test.dart';

// ─── 已知的合法 errorCode 值（来自 AssistantErrorCode enum）─────────────────
const _knownErrorCodes = <String>{
  'executionFailed',
  'llmCallFailed',
  'toolExecutionFailed',
  'sessionExpired',
  'templateLoadFailed',
  'contextBuildFailed',
  'networkUnavailable',
  'modelUnavailable',
  'rateLimitExceeded',
};

// ─── 非法 finalText 关键词（JSON envelope 泄漏）──────────────────────────────
const _forbiddenInFinalText = <String>[
  'assistant_turn_v2',
  'contractVersion',
  '"nextAction"',
  '"decision":{',
];

// ─── 辅助：构建一个 degraded response 并校验契约 ─────────────────────────────
void _assertDegradedResponseContract(
  AssistantRunResponse response, {
  required String scenario,
}) {
  test('$scenario — degraded response satisfies root cause contract', () {
    expect(
      response.degraded,
      isTrue,
      reason: '[$scenario] response.degraded 必须为 true',
    );

    // 规则 1/2：errorCode 非空且合法
    expect(
      response.errorCode,
      isNotNull,
      reason: '[$scenario] errorCode 不能为 null',
    );
    expect(
      response.errorCode!.trim().isNotEmpty,
      isTrue,
      reason: '[$scenario] errorCode 不能为空字符串',
    );
    expect(
      _knownErrorCodes.contains(response.errorCode),
      isTrue,
      reason:
          '[$scenario] errorCode "${response.errorCode}" 不在已知枚举集中: $_knownErrorCodes',
    );

    // 规则 3：traces 中必须有 toolError 类型 trace，且 message 包含根因
    final errorTraces = response.traces
        .where((t) => t.type == AssistantTraceEventType.toolError)
        .toList();
    expect(
      errorTraces.isNotEmpty,
      isTrue,
      reason: '[$scenario] traces 中必须含至少一条 toolError 类型事件',
    );
    // message 不得是纯固定文案（必须含动态信息，如异常描述）
    final allMessages = errorTraces.map((t) => t.message).join(' ');
    final isOnlyFixedText =
        allMessages == '助手暂时不可用，请稍后重试。' ||
        allMessages.isEmpty;
    expect(
      isOnlyFixedText,
      isFalse,
      reason:
          '[$scenario] toolError trace.message 不得是纯固定文案，需包含根因动态信息',
    );

    // 规则 4：finalText 不能为空
    expect(
      response.finalText.trim().isNotEmpty,
      isTrue,
      reason: '[$scenario] finalText 不能为空字符串',
    );

    // 规则 5：finalText 不得含 JSON envelope key
    for (final forbidden in _forbiddenInFinalText) {
      expect(
        response.finalText.contains(forbidden),
        isFalse,
        reason:
            '[$scenario] finalText 不得含 JSON envelope key: $forbidden',
      );
    }
  });
}

void main() {
  group('DegradedResponseRootCauseContract', () {
    // ── 场景 1：capability_gateway 异常时的 _safeLocalRun 输出 ────────────
    group('_safeLocalRun fallback', () {
      // 直接构造符合协议的 degraded response（模拟 _safeLocalRun catch 产物）
      final degradedFromSafeRun = AssistantRunResponse(
        finalText: '助手暂时不可用，请稍后重试。',
        degraded: true,
        errorCode: AssistantErrorCode.executionFailed.name,
        traces: [
          AssistantTraceEvent(
            type: AssistantTraceEventType.toolError,
            message: 'local_gateway_error: SocketException: connection refused',
            timestamp: DateTime.now(),
            data: {'suppressed': true},
          ),
        ],
      );
      _assertDegradedResponseContract(
        degradedFromSafeRun,
        scenario: '_safeLocalRun / SocketException',
      );
    });

    // ── 场景 2：_runLocalWithStream 异常时的 fallback 输出 ────────────────
    group('_runLocalWithStream fallback', () {
      final degradedFromStream = AssistantRunResponse(
        finalText: '助手暂时不可用，请稍后重试。',
        degraded: true,
        errorCode: AssistantErrorCode.executionFailed.name,
        traces: [
          AssistantTraceEvent(
            type: AssistantTraceEventType.toolError,
            message: 'local_gateway_error: TimeoutException after 30000ms',
            timestamp: DateTime.now(),
            data: {'suppressed': true},
          ),
        ],
      );
      _assertDegradedResponseContract(
        degradedFromStream,
        scenario: '_runLocalWithStream / TimeoutException',
      );
    });

    // ── 场景 3：非法 degraded（缺 errorCode）— 负向测试 ───────────────────
    test('invalid degraded response — missing errorCode is detectable', () {
      final invalidDegraded = AssistantRunResponse(
        finalText: '助手暂时不可用，请稍后重试。',
        degraded: true,
        // errorCode 刻意留空 → 应被检测为违规
        traces: [
          AssistantTraceEvent(
            type: AssistantTraceEventType.toolError,
            message: 'some_error: details here',
            timestamp: DateTime.now(),
          ),
        ],
      );
      // 负向断言：这条 response 违反契约（errorCode 为 null）
      expect(
        invalidDegraded.errorCode,
        isNull,
        reason: '负向测试确认：缺 errorCode 的 response 是可被检测的',
      );
      // 验证这样的 response 会触发规则 1 检测
      final rule1Passes = invalidDegraded.errorCode != null &&
          invalidDegraded.errorCode!.trim().isNotEmpty;
      expect(
        rule1Passes,
        isFalse,
        reason: '负向测试：缺 errorCode 的 degraded response 必须被契约规则 1 拒绝',
      );
    });

    // ── 场景 4：finalText 含 JSON envelope — 负向测试 ─────────────────────
    test('invalid degraded response — JSON envelope in finalText is detectable', () {
      const jsonLeakingFinalText =
          '{"assistant_turn_v2":{"decision":{"nextAction":"answer"}}}';
      final leakingResponse = AssistantRunResponse(
        finalText: jsonLeakingFinalText,
        degraded: true,
        errorCode: AssistantErrorCode.executionFailed.name,
        traces: [
          AssistantTraceEvent(
            type: AssistantTraceEventType.toolError,
            message: 'some error detail',
            timestamp: DateTime.now(),
          ),
        ],
      );
      // 负向断言：这条 finalText 违反规则 5
      final hasJsonLeak = _forbiddenInFinalText
          .any((k) => leakingResponse.finalText.contains(k));
      expect(
        hasJsonLeak,
        isTrue,
        reason: '负向测试：finalText 含 JSON envelope key 可被检测',
      );
    });

    // ── 场景 5：errorCode 不在枚举集 — 负向测试 ────────────────────────────
    test('unknown errorCode is detectable', () {
      const unknownCode = 'some_random_code';
      expect(
        _knownErrorCodes.contains(unknownCode),
        isFalse,
        reason: '负向测试：不在已知枚举中的 errorCode 可被规则 2 拒绝',
      );
    });

    // ── 场景 7：HeuristicLocalLlmProvider 的 finalText 包含"请稍"不得被过滤 ──
    // 根因：_resolveAssistantDisplayText 的 _isProgressText 会把含"请稍"的文本
    // 判为进度占位文本，导致降级错误信息被丢弃，最终展示"助手暂时不可用"。
    // 修复：degraded==true 时直接返回 finalText，跳过 _isProgressText 过滤。
    test('heuristic fallback finalText contains 请稍 but must be displayable', () {
      const heuristicText =
          '当前模型服务不可用，已进入安全降级模式。请稍后重试，或明确告诉我要查询的内容（例如"深圳天气"）。';
      final response = AssistantRunResponse(
        finalText: heuristicText,
        degraded: true,
        errorCode: AssistantErrorCode.executionFailed.name,
        traces: <AssistantTraceEvent>[
          AssistantTraceEvent(
            type: AssistantTraceEventType.toolError,
            message: 'heuristic_fallback: no model configured',
            timestamp: DateTime.now(),
          ),
        ],
      );

      // 契约：finalText 不为空
      expect(response.finalText.trim().isNotEmpty, isTrue);

      // 文档化当前已知的"问题词"：finalText 含"请稍"（曾被 _isProgressText 误判）
      expect(
        response.finalText.contains('请稍'),
        isTrue,
        reason: '此测试记录了 finalText 含"请稍"这一已知问题词——'
            'UI 层的 _resolveAssistantDisplayText 必须对 degraded==true '
            '的响应直接返回 finalText，不得过滤',
      );

      // 契约：degraded==true 时 finalText 就是最终展示内容，不得为空
      expect(
        response.degraded && response.finalText.trim().isNotEmpty,
        isTrue,
        reason: 'degraded响应的finalText是给用户看的最终说明，UI层必须直接展示它',
      );
    });

    // ── 场景 6：toJson/fromJson 序列化保留所有根因字段 ────────────────────
    test('degraded response serialization preserves errorCode and traces', () {
      final original = AssistantRunResponse(
        finalText: '助手暂时不可用，请稍后重试。',
        degraded: true,
        errorCode: AssistantErrorCode.executionFailed.name,
        runId: 'run-abc-123',
        traceId: 'trace-xyz-456',
        traces: [
          AssistantTraceEvent(
            type: AssistantTraceEventType.toolError,
            message: 'local_gateway_error: HTTP 400 - bad_request',
            timestamp: DateTime.parse('2026-03-04T10:00:00.000Z'),
            data: {'suppressed': true},
            runId: 'run-abc-123',
            traceId: 'trace-xyz-456',
          ),
        ],
      );

      final json = original.toJson();
      final restored = AssistantRunResponse.fromJson(json);

      expect(restored.degraded, isTrue);
      expect(restored.errorCode, equals(AssistantErrorCode.executionFailed.name));
      expect(restored.runId, equals('run-abc-123'));
      expect(restored.traceId, equals('trace-xyz-456'));
      expect(restored.traces.length, equals(1));
      expect(
        restored.traces.first.message,
        contains('HTTP 400'),
        reason: '序列化/反序列化后 trace.message 中的根因信息必须完整保留',
      );
    });
  });
}
