import 'dart:math' as math;

import 'package:quwoquan_app/assistant/contracts/assistant_subagent_run_record.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

class AssistantPipelineUsageStats {
  const AssistantPipelineUsageStats({
    required this.modelCallCount,
    required this.totalTokens,
    required this.maxTokensPerCall,
    required this.inputTokens,
    required this.outputTokens,
    required this.tokenSource,
    required this.tokenSampleCount,
    this.usageLedger = const <Map<String, dynamic>>[],
  });

  final int modelCallCount;
  final int totalTokens;
  final int maxTokensPerCall;
  final int inputTokens;
  final int outputTokens;
  final String tokenSource;
  final int tokenSampleCount;
  final List<Map<String, dynamic>> usageLedger;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'modelCallCount': modelCallCount,
        'totalTokens': totalTokens,
        'maxTokensPerCall': maxTokensPerCall,
        'inputTokens': inputTokens,
        'outputTokens': outputTokens,
        'tokenSource': tokenSource,
        'tokenSampleCount': tokenSampleCount,
        if (usageLedger.isNotEmpty) 'usageLedger': usageLedger,
      };
}

Map<String, dynamic> buildUiUsageStats({
  required List<AssistantTraceEvent> traces,
  required AssistantRunRequest request,
  required List<AssistantSubagentRunRecord> subagentRuns,
  required String outputText,
}) {
  final inputText = request.messages.map((item) => item.content).join('\n');
  final mainUsage = buildUsageStatsFromTraces(
    traces: traces,
    fallbackInputText: inputText,
    fallbackOutputText: outputText,
  );
  final mainLedger = mainUsage.usageLedger;
  final mainCalls = mainUsage.modelCallCount;
  final mainTokens = mainUsage.totalTokens;
  final mainMaxTokens = mainUsage.maxTokensPerCall;
  final mainTokenSamples = mainUsage.tokenSampleCount;
  final mainInputTokens = mainUsage.inputTokens;
  final mainOutputTokens = mainUsage.outputTokens;

  var subagentCalls = 0;
  var subagentTokens = 0;
  var subagentMaxTokens = 0;
  var subagentTokenSamples = 0;
  var subagentInputTokens = 0;
  var subagentOutputTokens = 0;
  final usageLedger = <Map<String, dynamic>>[...mainLedger];
  for (final run in subagentRuns) {
    subagentCalls += run.modelCallCount;
    subagentTokens += run.totalTokens;
    final maxTokens = run.maxTokensPerCall;
    if (maxTokens > subagentMaxTokens) subagentMaxTokens = maxTokens;
    subagentTokenSamples += run.tokenSampleCount;
    subagentInputTokens += run.inputTokens;
    subagentOutputTokens += run.outputTokens;
    usageLedger.addAll(run.usageLedger);
  }

  final tokenSampleCount = mainTokenSamples + subagentTokenSamples;
  final modelCalls = math.max(1, mainCalls + subagentCalls);
  final totalTokens = mainTokens + subagentTokens;
  final maxTokens = math.max(mainMaxTokens, subagentMaxTokens);

  return <String, dynamic>{
    'modelCallCount': modelCalls,
    'totalTokens': totalTokens,
    'maxTokensPerCall': maxTokens,
    'inputTokens': mainInputTokens + subagentInputTokens,
    'outputTokens': mainOutputTokens + subagentOutputTokens,
    'tokenSource': tokenSampleCount > 0 ? 'trace_or_subagent' : 'estimated',
    'tokenSampleCount': tokenSampleCount,
    if (usageLedger.isNotEmpty) 'usageLedger': usageLedger,
  };
}

AssistantPipelineUsageStats buildUsageStatsFromTraces({
  required List<AssistantTraceEvent> traces,
  required String fallbackInputText,
  required String fallbackOutputText,
}) {
  final usageLedger = <Map<String, dynamic>>[];
  for (final trace in traces) {
    final entries =
        (trace.data?['usageEntries'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    if (entries.isEmpty) continue;
    usageLedger.addAll(entries);
  }
  if (usageLedger.isNotEmpty) {
    var totalTokens = 0;
    var maxTokens = 0;
    var inputTokens = 0;
    var outputTokens = 0;
    final sources = <String>{};
    for (final entry in usageLedger) {
      final total = _safeNonNegativeInt(entry['totalTokens'] ?? entry['tokenUsage']);
      final input = _safeNonNegativeInt(entry['inputTokens']);
      final output = _safeNonNegativeInt(entry['outputTokens']);
      totalTokens += total;
      inputTokens += input;
      outputTokens += output;
      if (total > maxTokens) maxTokens = total;
      final source = (entry['source'] as String?)?.trim() ?? '';
      if (source.isNotEmpty) {
        sources.add(source);
      }
    }
    return AssistantPipelineUsageStats(
      modelCallCount: usageLedger.length,
      totalTokens: totalTokens,
      maxTokensPerCall: maxTokens,
      inputTokens: inputTokens,
      outputTokens: outputTokens,
      tokenSource: sources.isEmpty
          ? 'usage_ledger'
          : (sources.length == 1 ? sources.first : 'mixed_ledger'),
      tokenSampleCount: usageLedger.length,
      usageLedger: usageLedger,
    );
  }

  int totalTokensFromTrace = 0;
  int maxTokensFromTrace = 0;
  var tokenSampleCount = 0;

  void collectTokenValues(Object? node) {
    if (node is Map) {
      for (final entry in node.entries) {
        final key = entry.key.toString().toLowerCase();
        final value = entry.value;
        if (value is num &&
            (key.contains('token') ||
                key.contains('input_tokens') ||
                key.contains('output_tokens'))) {
          final token = value.toInt();
          if (token > 0) {
            tokenSampleCount += 1;
            totalTokensFromTrace += token;
            if (token > maxTokensFromTrace) maxTokensFromTrace = token;
          }
        } else {
          collectTokenValues(value);
        }
      }
    } else if (node is List) {
      for (final item in node) {
        collectTokenValues(item);
      }
    }
  }

  for (final trace in traces) {
    collectTokenValues(trace.data);
  }

  final estimatedInputTokens = estimateTokenCount(fallbackInputText);
  final estimatedOutputTokens = estimateTokenCount(fallbackOutputText);
  final estimatedTotalTokens = estimatedInputTokens + estimatedOutputTokens;
  final estimatedMaxTokens = math.max(
    estimatedInputTokens,
    estimatedOutputTokens,
  );

  final totalTokens = tokenSampleCount > 0
      ? totalTokensFromTrace
      : estimatedTotalTokens;
  final maxTokens = tokenSampleCount > 0
      ? maxTokensFromTrace
      : estimatedMaxTokens;
  final modelCalls = _countModelCallsFromTraces(traces);

  return AssistantPipelineUsageStats(
    modelCallCount: modelCalls,
    totalTokens: totalTokens,
    maxTokensPerCall: maxTokens,
    inputTokens: estimatedInputTokens,
    outputTokens: estimatedOutputTokens,
    tokenSource: tokenSampleCount > 0 ? 'trace' : 'estimated',
    tokenSampleCount: tokenSampleCount,
  );
}

int _countModelCallsFromTraces(List<AssistantTraceEvent> traces) {
  final calls = traces
      .where(
        (trace) =>
            trace.type == AssistantTraceEventType.lifecycleStart &&
            (trace.message.startsWith('llm request iteration ') ||
                trace.message.startsWith('llm request synthesis ')),
      )
      .length;
  return math.max(1, calls);
}

int estimateTokenCount(String text) {
  final trimmed = text.trim();
  if (trimmed.isEmpty) return 0;
  return (trimmed.length / 4).ceil();
}

int _safeNonNegativeInt(Object? value) {
  if (value is num) return value.toInt() < 0 ? 0 : value.toInt();
  final parsed = int.tryParse(value?.toString() ?? '');
  if (parsed == null || parsed < 0) return 0;
  return parsed;
}
