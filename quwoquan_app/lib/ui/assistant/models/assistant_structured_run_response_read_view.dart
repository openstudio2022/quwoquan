// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — `AssistantRunResponse.structuredResponse` 仍为 Map。

import 'package:quwoquan_app/assistant/transcript/assistant_answer/assistant_quality_metrics_read_view.dart';

/// 完成态 run 的 `structuredResponse` 常用键只读投影（减少 controller 内散列访问）。
class AssistantStructuredRunResponseReadView {
  AssistantStructuredRunResponseReadView(this._raw);

  final Map<String, dynamic> _raw;

  String get effectiveSessionIdOrEmpty =>
      (_raw['effectiveSessionId'] as String?)?.trim() ?? '';

  String? get activeTopicTitleOrNull =>
      (_raw['activeTopicTitle'] as String?)?.trim();

  Map<String, dynamic> get dialogueRuntime =>
      (_raw['dialogueRuntime'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  List<Map<String, dynamic>> get uiReferences =>
      (_raw['uiReferences'] as List?)
          ?.whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false) ??
      const <Map<String, dynamic>>[];

  List<Map<String, dynamic>> get uiActions =>
      (_raw['uiActions'] as List?)
          ?.whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false) ??
      const <Map<String, dynamic>>[];

  Map<String, dynamic> get uiUsageStats =>
      (_raw['uiUsageStats'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  String get templateVersionUsedOrEmpty =>
      (_raw['templateVersionUsed'] as String?)?.trim() ?? '';

  Map<String, dynamic> get phaseOneRoutingDiagnosticsMap =>
      (_raw['phaseOneRoutingDiagnostics'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  Map<String, dynamic> get qualityMetricsMap =>
      (_raw['qualityMetrics'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  bool get heuristicFallbackUsedFromQualityMetrics =>
      AssistantQualityMetricsReadView(qualityMetricsMap).heuristicFallbackUsed;
}
