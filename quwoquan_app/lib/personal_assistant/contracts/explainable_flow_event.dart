// Unified UI-facing flow event protocol.
//
// All process-drawer rendering, answer-gate decisions, and timeline
// persistence flow through this single type. It replaces the previous
// three parallel paths: `UserPhaseEventType`, `UserEvent` (process*),
// and `AssistantProcessState`.

// ---------------------------------------------------------------------------
// Phase identifiers
// ---------------------------------------------------------------------------

abstract class PhaseId {
  // Shared top-level phases (both single-agent & multi-agent)
  static const understand = 'understand';
  static const classify = 'classify';
  static const plan = 'plan';
  static const execute = 'execute';
  static const aggregate = 'aggregate';
  static const answer = 'answer';

  // Multi-agent only
  static const dispatch = 'dispatch';
  static const subExecute = 'sub_execute';
  static const merge = 'merge';

  // Optional / extension (complex_reasoning, recall scenarios)
  static const recall = 'recall';
  static const expand = 'expand';
  static const clarify = 'clarify';
}

enum ExplainablePhaseStatus {
  active,
  completed,
  skipped,
  failed,
}

// ---------------------------------------------------------------------------
// Reference attached to a phase
// ---------------------------------------------------------------------------

class FlowReference {
  const FlowReference({
    required this.title,
    required this.url,
    this.source = '',
  });

  final String title;
  final String url;
  final String source;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'title': title,
        'url': url,
        'source': source,
      };

  factory FlowReference.fromJson(Map<String, dynamic> json) {
    return FlowReference(
      title: (json['title'] as String?)?.trim() ?? '',
      url: (json['url'] as String?)?.trim() ?? '',
      source: (json['source'] as String?)?.trim() ?? '',
    );
  }
}

// ---------------------------------------------------------------------------
// Core event
// ---------------------------------------------------------------------------

class ExplainableFlowEvent {
  const ExplainableFlowEvent({
    required this.phaseId,
    required this.phaseOrder,
    required this.phaseStatus,
    required this.headline,
    this.detail = '',
    this.agentId = 'main',
    this.parentPhaseId = '',
    this.references = const <FlowReference>[],
    this.payload = const <String, dynamic>{},
  });

  final String phaseId;
  final int phaseOrder;
  final ExplainablePhaseStatus phaseStatus;

  /// One-liner in natural user language (Chinese).
  final String headline;

  /// Optional detail shown when the phase row is expanded.
  final String detail;

  /// `'main'` for single-agent; sub-agent id for multi-agent children.
  final String agentId;

  /// Non-empty when this phase is a child of another (multi-agent tree).
  final String parentPhaseId;

  final List<FlowReference> references;
  final Map<String, dynamic> payload;

  ExplainableFlowEvent copyWith({
    String? phaseId,
    int? phaseOrder,
    ExplainablePhaseStatus? phaseStatus,
    String? headline,
    String? detail,
    String? agentId,
    String? parentPhaseId,
    List<FlowReference>? references,
    Map<String, dynamic>? payload,
  }) {
    return ExplainableFlowEvent(
      phaseId: phaseId ?? this.phaseId,
      phaseOrder: phaseOrder ?? this.phaseOrder,
      phaseStatus: phaseStatus ?? this.phaseStatus,
      headline: headline ?? this.headline,
      detail: detail ?? this.detail,
      agentId: agentId ?? this.agentId,
      parentPhaseId: parentPhaseId ?? this.parentPhaseId,
      references: references ?? this.references,
      payload: payload ?? this.payload,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'phaseId': phaseId,
        'phaseOrder': phaseOrder,
        'phaseStatus': phaseStatus.name,
        'headline': headline,
        'detail': detail,
        'agentId': agentId,
        'parentPhaseId': parentPhaseId,
        'references':
            references.map((r) => r.toJson()).toList(growable: false),
        'payload': payload,
      };

  factory ExplainableFlowEvent.fromJson(Map<String, dynamic> json) {
    return ExplainableFlowEvent(
      phaseId: (json['phaseId'] as String?)?.trim() ?? '',
      phaseOrder: (json['phaseOrder'] as num?)?.toInt() ?? 0,
      phaseStatus: _statusFromName(
        (json['phaseStatus'] as String?)?.trim() ?? '',
      ),
      headline: (json['headline'] as String?)?.trim() ?? '',
      detail: (json['detail'] as String?)?.trim() ?? '',
      agentId: (json['agentId'] as String?)?.trim() ?? 'main',
      parentPhaseId: (json['parentPhaseId'] as String?)?.trim() ?? '',
      references: (json['references'] as List?)
              ?.whereType<Map>()
              .map((m) => FlowReference.fromJson(m.cast<String, dynamic>()))
              .toList(growable: false) ??
          const <FlowReference>[],
      payload: (json['payload'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
    );
  }

  static ExplainablePhaseStatus _statusFromName(String name) {
    for (final v in ExplainablePhaseStatus.values) {
      if (v.name == name) return v;
    }
    return ExplainablePhaseStatus.active;
  }
}

// ---------------------------------------------------------------------------
// Phase visibility per problem class
// ---------------------------------------------------------------------------

abstract class PhaseVisibility {
  static const realtimeInfo = <String>[
    PhaseId.understand,
    PhaseId.execute,
    PhaseId.answer,
  ];

  static const simpleQa = <String>[
    PhaseId.understand,
    PhaseId.plan,
    PhaseId.execute,
    PhaseId.answer,
  ];

  static const taskExecution = <String>[
    PhaseId.understand,
    PhaseId.plan,
    PhaseId.execute,
    PhaseId.aggregate,
    PhaseId.answer,
  ];

  static const complexReasoningSingle = <String>[
    PhaseId.understand,
    PhaseId.classify,
    PhaseId.plan,
    PhaseId.execute,
    PhaseId.aggregate,
    PhaseId.answer,
  ];

  static const complexReasoningMulti = <String>[
    PhaseId.understand,
    PhaseId.classify,
    PhaseId.dispatch,
    PhaseId.subExecute,
    PhaseId.merge,
    PhaseId.aggregate,
    PhaseId.answer,
  ];

  static List<String> forProblemClass(
    String problemClass, {
    bool multiAgent = false,
  }) {
    switch (problemClass) {
      case 'realtime_info':
        return realtimeInfo;
      case 'simple_qa':
        return simpleQa;
      case 'task_execution':
        return taskExecution;
      case 'complex_reasoning':
        return multiAgent ? complexReasoningMulti : complexReasoningSingle;
      default:
        return simpleQa;
    }
  }
}
