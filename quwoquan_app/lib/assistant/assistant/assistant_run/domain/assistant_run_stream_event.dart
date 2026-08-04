import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AssistantRunVisibleProcessView,
        AssistantRunVisibleReferenceView,
        AssistantStreamEventWire,
        AssistantStreamEventType,
        AssistantStreamEventTypeX,
        CitationDestination,
        parseAssistantStreamEventType;
import 'package:quwoquan_app/assistant/assistant/assistant_turn_view/domain/citation_destination_resolver.dart';

/// AssistantRun 用户可见 SSE 事件的唯一端侧投影。
///
/// `payload` 是 transport 信封的扩展槽；所有动态 wire 解析都必须在本文件收口，
/// UI/Provider 只能消费下面的强类型字段，不能读取模型推理、tool 入参或未知 payload。
typedef AssistantRunStreamEventType = AssistantStreamEventType;

AssistantRunStreamEventType parseAssistantRunStreamEventType(String raw) {
  return parseAssistantStreamEventType(raw);
}

extension AssistantRunStreamEventTypeWire on AssistantRunStreamEventType {
  bool get isTerminal => switch (this) {
    AssistantRunStreamEventType.completed ||
    AssistantRunStreamEventType.failed ||
    AssistantRunStreamEventType.cancelled => true,
    _ => false,
  };
}

class AssistantRunVisibleReference {
  const AssistantRunVisibleReference({
    required this.destination,
    this.title = '',
    this.source = '',
    this.snippet = '',
  });

  final CitationDestination destination;
  final String title;
  final String source;
  final String snippet;

  factory AssistantRunVisibleReference.fromTerminalView(
    AssistantRunVisibleReferenceView view,
  ) {
    return AssistantRunVisibleReference(
      destination: view.destination,
      title: view.title.trim(),
      source: view.source.trim(),
      snippet: view.snippet.trim(),
    );
  }

  static AssistantRunVisibleReference? fromWire(Object? raw) {
    final object = _wireObject(raw);
    if (object == null) {
      return null;
    }
    final rawDestination = object['destination'];
    if (rawDestination is! Map) {
      return null;
    }
    late final CitationDestination destination;
    try {
      destination = citationDestinationFromWireObject(rawDestination);
    } on FormatException {
      return null;
    }
    if (CitationDestinationResolver.resolve(destination) == null) {
      return null;
    }
    return AssistantRunVisibleReference(
      destination: destination,
      title: _wireString(object['title']),
      source: _wireString(object['source']),
      snippet: _wireString(object['snippet']),
    );
  }
}

class AssistantRunVisibleProcess {
  const AssistantRunVisibleProcess({
    required this.processId,
    required this.scope,
    required this.stage,
    required this.status,
    required this.order,
    this.summary = '',
    this.skillId = '',
    this.domainId = '',
    this.searchedDocumentCount = 0,
    this.processedDocumentCount = 0,
    this.acceptedDocumentCount = 0,
    this.acceptedReferences = const <AssistantRunVisibleReference>[],
  });

  final String processId;
  final String scope;
  final String stage;
  final String status;
  final int order;
  final String summary;
  final String skillId;
  final String domainId;
  final int searchedDocumentCount;
  final int processedDocumentCount;
  final int acceptedDocumentCount;
  final List<AssistantRunVisibleReference> acceptedReferences;

  factory AssistantRunVisibleProcess.fromTerminalView(
    AssistantRunVisibleProcessView view,
  ) {
    return AssistantRunVisibleProcess(
      processId: view.processId,
      scope: view.scope,
      stage: view.stage,
      status: view.status,
      order: view.order,
      summary: view.summary.trim(),
      skillId: view.skillId.trim(),
      domainId: view.domainId.trim(),
      searchedDocumentCount: view.searchedDocumentCount,
      processedDocumentCount: view.processedDocumentCount,
      acceptedDocumentCount: view.acceptedDocumentCount,
      acceptedReferences: view.acceptedReferences
          .map(AssistantRunVisibleReference.fromTerminalView)
          .where(
            (reference) =>
                CitationDestinationResolver.resolve(reference.destination) !=
                null,
          )
          .toList(growable: false),
    );
  }

  AssistantRunVisibleProcess copyWith({
    String? status,
    String? summary,
    int? searchedDocumentCount,
    int? processedDocumentCount,
    int? acceptedDocumentCount,
    List<AssistantRunVisibleReference>? acceptedReferences,
  }) {
    return AssistantRunVisibleProcess(
      processId: processId,
      scope: scope,
      stage: stage,
      status: status ?? this.status,
      order: order,
      summary: summary ?? this.summary,
      skillId: skillId,
      domainId: domainId,
      searchedDocumentCount:
          searchedDocumentCount ?? this.searchedDocumentCount,
      processedDocumentCount:
          processedDocumentCount ?? this.processedDocumentCount,
      acceptedDocumentCount:
          acceptedDocumentCount ?? this.acceptedDocumentCount,
      acceptedReferences: acceptedReferences ?? this.acceptedReferences,
    );
  }

  static AssistantRunVisibleProcess? fromWire(Object? raw) {
    final object = _wireObject(raw);
    if (object == null) {
      return null;
    }
    final processId = _wireString(object['processId']);
    final scope = _wireString(object['scope']);
    final stage = _wireString(object['stage']);
    final status = _wireString(object['status']);
    if (processId.isEmpty || scope.isEmpty || stage.isEmpty || status.isEmpty) {
      return null;
    }
    final references = _wireList(object['acceptedReferences'])
        .map(AssistantRunVisibleReference.fromWire)
        .whereType<AssistantRunVisibleReference>()
        .toList(growable: false);
    return AssistantRunVisibleProcess(
      processId: processId,
      scope: scope,
      stage: stage,
      status: status,
      order: _wireInt(object['order']),
      summary: _wireString(object['summary']),
      skillId: _wireString(object['skillId']),
      domainId: _wireString(object['domainId']),
      searchedDocumentCount: _wireInt(object['searchedDocumentCount']),
      processedDocumentCount: _wireInt(object['processedDocumentCount']),
      acceptedDocumentCount: _wireInt(object['acceptedDocumentCount']),
      acceptedReferences: references,
    );
  }
}

class AssistantRunStreamEvent {
  const AssistantRunStreamEvent._({
    required this.wire,
    required this.type,
    required this.restarted,
    required this.processes,
    required this.process,
    required this.text,
    required this.finalAnswer,
    required this.emergedTags,
    required this.runStatus,
  });

  final AssistantStreamEventWire wire;
  final AssistantRunStreamEventType type;
  final bool restarted;
  final List<AssistantRunVisibleProcess> processes;
  final AssistantRunVisibleProcess? process;
  final String text;
  final String finalAnswer;
  final List<String> emergedTags;
  final String runStatus;

  bool get isAnswerEvent =>
      type == AssistantRunStreamEventType.answerDelta ||
      type == AssistantRunStreamEventType.completed;

  factory AssistantRunStreamEvent.fromWire(AssistantStreamEventWire wire) {
    final payload = wire.payload;
    final processes = _wireList(payload['processes'])
        .map(AssistantRunVisibleProcess.fromWire)
        .whereType<AssistantRunVisibleProcess>()
        .toList(growable: false);
    return AssistantRunStreamEvent._(
      wire: wire,
      type: parseAssistantRunStreamEventType(wire.eventType.wireName),
      restarted: payload['restarted'] == true,
      processes: processes,
      process: AssistantRunVisibleProcess.fromWire(payload['process']),
      text: _wireString(payload['text']),
      finalAnswer: _wireString(payload['finalAnswer']),
      runStatus: _wireString(payload['status']),
      emergedTags: _wireList(payload['emergedTags'])
          .map(_wireString)
          .where((item) => item.isNotEmpty)
          .toSet()
          .toList(growable: false),
    );
  }
}

Map<String, Object?>? _wireObject(Object? raw) {
  if (raw is! Map) {
    return null;
  }
  final result = <String, Object?>{};
  for (final entry in raw.entries) {
    if (entry.key is! String) {
      return null;
    }
    result[entry.key as String] = entry.value;
  }
  return result;
}

List<Object?> _wireList(Object? raw) {
  return raw is List ? raw.cast<Object?>() : const <Object?>[];
}

String _wireString(Object? raw) => raw is String ? raw.trim() : '';

int _wireInt(Object? raw) => raw is num ? raw.toInt() : 0;
