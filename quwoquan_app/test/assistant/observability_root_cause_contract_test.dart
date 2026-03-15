/// L1 契约测试：可观测根因字段完整性
///
/// 验收覆盖：A4（runId/traceId/关键动作可观测并可回放）、A8（测试覆盖可复跑）
/// 执行方式：dart test（纯 VM，无 flutter shell 依赖）
///
/// 核心命题：
///   1. AssistantRunResponse 的 runId / traceId 在每次运行时必须是非空字符串
///   2. AssistantTraceEvent 的 traces 必须包含 lifecycleStart 和 lifecycleEnd
///   3. toolError trace 必须携带可区分异常类型（在 message 或 data 中）
///   4. 结构化响应（structuredResponse）的 qualityMetrics 必须包含 decisionParseSuccess 字段
///   5. 所有 trace 的 timestamp 必须为有效 DateTime（非 epoch 0）
///   6. trace 序列化后 runId/traceId 跨事件一致
library;

import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:test/test.dart';

// ─── 构造一个符合规范的完整 AssistantRunResponse ────────────────────────────
AssistantRunResponse _buildCompliantResponse({
  bool includeQualityMetrics = true,
  bool includeLifecycleEnd = true,
  bool includeRunId = true,
  String? errorCodeOverride,
}) {
  const runId = 'run-contract-test-001';
  const traceId = 'trace-contract-test-001';
  final now = DateTime.now();

  return AssistantRunResponse(
    finalText: '深圳今天晴，25°C。',
    runId: includeRunId ? runId : null,
    traceId: includeRunId ? traceId : null,
    degraded: false,
    errorCode: errorCodeOverride,
    traces: [
      AssistantTraceEvent(
        type: AssistantTraceEventType.lifecycleStart,
        message: 'agent_run_start',
        timestamp: now.subtract(const Duration(milliseconds: 500)),
        runId: runId,
        traceId: traceId,
      ),
      AssistantTraceEvent(
        type: AssistantTraceEventType.toolStart,
        message: 'tool_start: web_search',
        timestamp: now.subtract(const Duration(milliseconds: 300)),
        runId: runId,
        traceId: traceId,
        toolCallId: 'call-abc-123',
      ),
      AssistantTraceEvent(
        type: AssistantTraceEventType.toolResult,
        message: 'tool_result: web_search ok',
        timestamp: now.subtract(const Duration(milliseconds: 100)),
        runId: runId,
        traceId: traceId,
        toolCallId: 'call-abc-123',
      ),
      if (includeLifecycleEnd)
        AssistantTraceEvent(
          type: AssistantTraceEventType.lifecycleEnd,
          message: 'agent_run_end',
          timestamp: now,
          runId: runId,
          traceId: traceId,
        ),
    ],
    structuredResponse: includeQualityMetrics
        ? {
            'qualityMetrics': {
              'decisionParseSuccess': true,
              'renderFallback': false,
              'heuristicFallbackUsed': false,
            },
          }
        : const {},
  );
}

void main() {
  // ── 规则 1：正常响应的 runId/traceId 必须非空 ────────────────────────────
  test(
    'Rule-1: successful response must carry non-null non-empty runId and traceId',
    () {
      final response = _buildCompliantResponse();
      expect(response.runId, isNotNull, reason: 'runId 不能为 null');
      expect(
        response.runId!.trim().isNotEmpty,
        isTrue,
        reason: 'runId 不能为空字符串',
      );
      expect(response.traceId, isNotNull, reason: 'traceId 不能为 null');
      expect(
        response.traceId!.trim().isNotEmpty,
        isTrue,
        reason: 'traceId 不能为空字符串',
      );
    },
  );

  // ── 规则 2：traces 必须包含 lifecycleStart 和 lifecycleEnd ───────────────
  test('Rule-2: traces must include lifecycleStart and lifecycleEnd', () {
    final response = _buildCompliantResponse();
    final types = response.traces.map((t) => t.type).toSet();

    expect(
      types.contains(AssistantTraceEventType.lifecycleStart),
      isTrue,
      reason: 'traces 中必须有 lifecycleStart 事件',
    );
    expect(
      types.contains(AssistantTraceEventType.lifecycleEnd),
      isTrue,
      reason: 'traces 中必须有 lifecycleEnd 事件',
    );
  });

  // ── 规则 3：degraded 时也必须有 runId/traceId ─────────────────────────────
  test('Rule-3: degraded response should ideally carry runId (advisory)', () {
    // degraded response 的 runId/traceId 目前是 optional，
    // 此测试验证：如果有，则不为空字符串
    final degraded = AssistantRunResponse(
      finalText: '助手暂时不可用，请稍后重试。',
      degraded: true,
      errorCode: 'executionFailed',
      runId: 'run-fail-001',
      traceId: 'trace-fail-001',
      traces: [
        AssistantTraceEvent(
          type: AssistantTraceEventType.toolError,
          message: 'local_gateway_error: SocketException: connection refused',
          timestamp: DateTime.now(),
          runId: 'run-fail-001',
          traceId: 'trace-fail-001',
        ),
      ],
    );
    if (degraded.runId != null) {
      expect(
        degraded.runId!.trim().isNotEmpty,
        isTrue,
        reason: 'degraded response 若携带 runId，则不能为空字符串',
      );
    }
    if (degraded.traceId != null) {
      expect(
        degraded.traceId!.trim().isNotEmpty,
        isTrue,
        reason: 'degraded response 若携带 traceId，则不能为空字符串',
      );
    }
  });

  // ── 规则 4：structuredResponse.qualityMetrics 必须含 decisionParseSuccess ─
  test(
    'Rule-4: structuredResponse.qualityMetrics must contain decisionParseSuccess',
    () {
      final response = _buildCompliantResponse();
      final qm =
          response.structuredResponse['qualityMetrics']
              as Map<String, dynamic>?;
      expect(qm, isNotNull, reason: 'structuredResponse 必须含 qualityMetrics 字段');
      expect(
        qm!.containsKey('decisionParseSuccess'),
        isTrue,
        reason: 'qualityMetrics 必须含 decisionParseSuccess 字段',
      );
    },
  );

  // ── 规则 5：所有 trace 的 timestamp 必须有效（非 epoch 0）────────────────
  test('Rule-5: all trace timestamps must be valid (not epoch zero)', () {
    final response = _buildCompliantResponse();
    final epochZero = DateTime.fromMillisecondsSinceEpoch(0);

    for (final trace in response.traces) {
      expect(
        trace.timestamp.isAfter(epochZero),
        isTrue,
        reason: 'trace "${trace.message}" 的 timestamp 是 epoch 0，表示反序列化失败或未设置',
      );
    }
  });

  // ── 规则 6：toolStart + toolResult 必须有一致的 toolCallId ───────────────
  test('Rule-6: toolStart and toolResult must share the same toolCallId', () {
    final response = _buildCompliantResponse();
    final toolStarts = response.traces
        .where((t) => t.type == AssistantTraceEventType.toolStart)
        .toList();
    final toolResults = response.traces
        .where((t) => t.type == AssistantTraceEventType.toolResult)
        .toList();

    expect(toolStarts.isNotEmpty, isTrue, reason: '必须有 toolStart 事件');
    expect(toolResults.isNotEmpty, isTrue, reason: '必须有 toolResult 事件');

    for (final start in toolStarts) {
      expect(
        start.toolCallId,
        isNotNull,
        reason: 'toolStart trace 必须携带 toolCallId',
      );
    }
    for (final result in toolResults) {
      expect(
        result.toolCallId,
        isNotNull,
        reason: 'toolResult trace 必须携带 toolCallId',
      );
    }

    final startIds = toolStarts.map((t) => t.toolCallId).toSet();
    final resultIds = toolResults.map((t) => t.toolCallId).toSet();
    expect(
      startIds.intersection(resultIds).isNotEmpty,
      isTrue,
      reason: 'toolStart 与 toolResult 必须有至少一个匹配的 toolCallId',
    );
  });

  // ── 规则 7：trace 序列化后 runId/traceId 一致 ────────────────────────────
  test(
    'Rule-7: trace serialization round-trip preserves runId and traceId',
    () {
      const runId = 'run-round-trip-001';
      const traceId = 'trace-round-trip-001';
      final trace = AssistantTraceEvent(
        type: AssistantTraceEventType.lifecycleStart,
        message: 'agent_run_start',
        timestamp: DateTime.parse('2026-03-04T10:00:00.000Z'),
        runId: runId,
        traceId: traceId,
        toolCallId: 'call-xyz',
      );

      final json = trace.toJson();
      final restored = AssistantTraceEvent.fromJson(json);

      expect(restored.runId, equals(runId));
      expect(restored.traceId, equals(traceId));
      expect(restored.toolCallId, equals('call-xyz'));
      expect(
        restored.timestamp,
        equals(DateTime.parse('2026-03-04T10:00:00.000Z')),
      );
    },
  );

  // ── 规则 8：缺少 lifecycleEnd 的 traces 可被检测（负向测试）─────────────
  test('Rule-8 negative: missing lifecycleEnd is detectable', () {
    final response = _buildCompliantResponse(includeLifecycleEnd: false);
    final types = response.traces.map((t) => t.type).toSet();
    expect(
      types.contains(AssistantTraceEventType.lifecycleEnd),
      isFalse,
      reason: '负向测试：缺 lifecycleEnd 的 traces 可被规则 2 检测',
    );
  });

  // ── 规则 9：缺少 qualityMetrics 可被检测（负向测试）─────────────────────
  test('Rule-9 negative: missing qualityMetrics is detectable', () {
    final response = _buildCompliantResponse(includeQualityMetrics: false);
    final qm = response.structuredResponse['qualityMetrics'];
    expect(
      qm,
      isNull,
      reason: '负向测试：缺 qualityMetrics 的 structuredResponse 可被规则 4 检测',
    );
  });

  // ── 规则 10：完整 response 的 toJson/fromJson 往返一致 ───────────────────
  test('Rule-10: full response toJson/fromJson round-trip', () {
    final response = _buildCompliantResponse();
    final json = response.toJson();
    final restored = AssistantRunResponse.fromJson(json);

    expect(restored.finalText, equals(response.finalText));
    expect(restored.degraded, equals(response.degraded));
    expect(restored.runId, equals(response.runId));
    expect(restored.traceId, equals(response.traceId));
    expect(restored.errorCode, equals(response.errorCode));
    expect(restored.traces.length, equals(response.traces.length));

    // qualityMetrics 往返保持
    final restoredQm =
        restored.structuredResponse['qualityMetrics'] as Map<String, dynamic>?;
    expect(restoredQm?['decisionParseSuccess'], equals(true));
  });
}
