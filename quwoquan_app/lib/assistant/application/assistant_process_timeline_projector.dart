import 'dart:math' as math;

import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

class AssistantProcessTimelineProjector {
  final Map<ProcessStepId, ProcessTimelineFrame> _frames =
      <ProcessStepId, ProcessTimelineFrame>{};

  List<ProcessTimelineFrame> get snapshot =>
      normalizeProcessTimeline(_frames.values.toList(growable: false));

  List<ProcessTimelineFrame> consumeTrace(AssistantTraceEvent event) {
    if (event.visibility == TraceVisibility.internal) {
      return snapshot;
    }
    final userEvent = _syntheticUserEventFromTrace(event);
    if (userEvent == null) {
      return snapshot;
    }
    return consumeUserEvent(userEvent);
  }

  List<ProcessTimelineFrame> consumeUserEvent(UserEvent event) {
    switch (event.type) {
      case UserEventType.processReplace:
      case UserEventType.processAppend:
      case UserEventType.processCommit:
        break;
      case UserEventType.answerDelta:
      case UserEventType.unknown:
        return snapshot;
    }
    final payload = event.payload;
    final stepId = _processStepIdFromPayload(payload);
    if (stepId == ProcessStepId.unknown) {
      return snapshot;
    }
    final current =
        _frames[stepId] ??
        buildProcessTimelineFrame(
          stepId: stepId,
          status: JourneyStageStatus.pending,
        );
    final incomingHeadline = _resolveText(
      (payload['headline'] as String?) ?? (payload['summary'] as String?) ?? '',
    );
    final incomingDetail = _resolveText((payload['detail'] as String?) ?? '');
    final mergedHeadline = switch (event.type) {
      UserEventType.processReplace => incomingHeadline,
      UserEventType.processAppend => _mergeProcessText(
        current: current.headline,
        incoming: incomingHeadline,
        payload: payload,
      ),
      UserEventType.processCommit =>
        incomingHeadline.isNotEmpty ? incomingHeadline : current.headline,
      _ => incomingHeadline,
    };
    final mergedDetail = switch (event.type) {
      UserEventType.processReplace => incomingDetail,
      UserEventType.processAppend => _mergeProcessText(
        current: current.detail,
        incoming: incomingDetail,
        payload: payload,
      ),
      UserEventType.processCommit =>
        incomingDetail.isNotEmpty ? incomingDetail : current.detail,
      _ => incomingDetail,
    };
    final mergedFrame = current.copyWith(
      status: _resolveFrameStatus(event.type, payload),
      headline: mergedHeadline,
      detail: mergedDetail,
      references: _referencesFromPayload(payload, current),
      understandingSnapshot: _understandingSnapshotFromPayload(
        payload,
        current,
      ),
      retrievalProcessing: _retrievalProcessingFromPayload(payload, current),
      answerProcessing: _answerProcessingFromPayload(payload, current),
    );
    _frames[stepId] = mergedFrame;
    return snapshot;
  }

  static List<ProcessTimelineFrame> replay({
    required List<AssistantTraceEvent> traces,
  }) {
    final projector = AssistantProcessTimelineProjector();
    for (final trace in traces) {
      projector.consumeTrace(trace);
    }
    return projector.snapshot;
  }

  UserEvent? _syntheticUserEventFromTrace(AssistantTraceEvent event) {
    final data = event.data ?? const <String, dynamic>{};
    if (data['syntheticUserEvent'] != true) return null;
    return UserEvent(
      type: _syntheticUserEventType(
        (data['userEventType'] as String?)?.trim() ?? '',
      ),
      scope: _syntheticUserEventScope(
        (data['userEventScope'] as String?)?.trim() ?? '',
      ),
      message: event.message,
      nodeId: (data['nodeId'] as String?)?.trim() ?? '',
      runId: event.runId ?? '',
      payload: data,
    );
  }

  ProcessStepId _processStepIdFromPayload(Map<String, dynamic> payload) {
    final direct = parseProcessStepId(
      (payload['processStepId'] as String?)?.trim() ?? '',
    );
    if (direct != ProcessStepId.unknown) {
      return direct;
    }
    final stageId = parseJourneyStageId(
      (payload['stageId'] as String?)?.trim() ?? '',
    );
    switch (stageId) {
      case JourneyStageId.analyze:
        return ProcessStepId.understanding;
      case JourneyStageId.search:
      case JourneyStageId.verify:
        return ProcessStepId.retrievalProcessing;
      case JourneyStageId.answer:
        return ProcessStepId.answerOrganization;
      case JourneyStageId.unknown:
        return ProcessStepId.unknown;
    }
  }

  List<RetrievalProcessingReference> _referencesFromPayload(
    Map<String, dynamic> payload,
    ProcessTimelineFrame current,
  ) {
    final raw = (payload['references'] as List?)
        ?.whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList(growable: false);
    if (raw == null || raw.isEmpty) {
      return current.references;
    }
    return raw
        .map(RetrievalProcessingReference.fromJson)
        .where(
          (item) =>
              item.title.trim().isNotEmpty ||
              item.url.trim().isNotEmpty ||
              item.source.trim().isNotEmpty,
        )
        .toList(growable: false);
  }

  RunArtifactsUnderstandingSnapshot _understandingSnapshotFromPayload(
    Map<String, dynamic> payload,
    ProcessTimelineFrame current,
  ) {
    final raw = (payload['understandingSnapshot'] as Map?)
        ?.cast<String, dynamic>();
    if (raw == null || raw.isEmpty) {
      return current.understandingSnapshot;
    }
    return RunArtifactsUnderstandingSnapshot.fromJson(raw);
  }

  RetrievalProcessingSnapshot _retrievalProcessingFromPayload(
    Map<String, dynamic> payload,
    ProcessTimelineFrame current,
  ) {
    final raw = (payload['retrievalProcessing'] as Map?)
        ?.cast<String, dynamic>();
    if (raw == null || raw.isEmpty) {
      return current.retrievalProcessing;
    }
    return RetrievalProcessingSnapshot.fromJson(raw);
  }

  RunArtifactsAnswerProcessing _answerProcessingFromPayload(
    Map<String, dynamic> payload,
    ProcessTimelineFrame current,
  ) {
    final raw = (payload['answerProcessing'] as Map?)?.cast<String, dynamic>();
    if (raw == null || raw.isEmpty) {
      return current.answerProcessing;
    }
    return RunArtifactsAnswerProcessing.fromJson(raw);
  }

  static UserEventType _syntheticUserEventType(String raw) {
    switch (raw) {
      case 'process_replace':
        return UserEventType.processReplace;
      case 'process_append':
        return UserEventType.processAppend;
      case 'process_commit':
        return UserEventType.processCommit;
      case 'answer_delta':
        return UserEventType.answerDelta;
      default:
        return UserEventType.unknown;
    }
  }

  static UserEventScope _syntheticUserEventScope(String raw) {
    switch (raw) {
      case 'root':
        return UserEventScope.root;
      case 'skill':
        return UserEventScope.skill;
      case 'aggregation':
        return UserEventScope.aggregation;
      default:
        return UserEventScope.unknown;
    }
  }
}

JourneyStageStatus _resolveFrameStatus(
  UserEventType eventType,
  Map<String, dynamic> payload,
) {
  final explicit = parseJourneyStageStatus(
    (payload['status'] as String?)?.trim() ?? '',
  );
  if (explicit != JourneyStageStatus.unknown) {
    return explicit;
  }
  return eventType == UserEventType.processCommit
      ? JourneyStageStatus.completed
      : JourneyStageStatus.active;
}

String _resolveText(String raw) => raw.trim();

String _mergeProcessText({
  required String current,
  required String incoming,
  required Map<String, dynamic> payload,
}) {
  if (((payload['fieldPath'] as String?)?.trim() ?? '').isNotEmpty) {
    return _mergeStreamFieldText(current: current, incoming: incoming);
  }
  return _mergeNarrativeText(current: current, incoming: incoming);
}

String _mergeStreamFieldText({
  required String current,
  required String incoming,
}) {
  final left = current.trim();
  final right = incoming.trim();
  if (right.isEmpty) return left;
  if (left.isEmpty) return right;
  if (left == right || left.contains(right)) return left;
  if (right.contains(left)) return right;
  final overlap = _suffixPrefixOverlap(left, right);
  if (overlap > 0) {
    return left + right.substring(overlap);
  }
  return left + right;
}

String _mergeNarrativeText({
  required String current,
  required String incoming,
}) {
  final left = current.trim();
  final right = incoming.trim();
  if (right.isEmpty) return left;
  if (left.isEmpty) return right;
  if (left == right || left.contains(right)) return left;
  if (right.contains(left)) return right;
  if (left.endsWith(right)) return left;
  return '$left\n$right';
}

int _suffixPrefixOverlap(String left, String right) {
  final maxOverlap = math.min(left.length, right.length);
  for (var size = maxOverlap; size > 0; size--) {
    if (left.substring(left.length - size) == right.substring(0, size)) {
      return size;
    }
  }
  return 0;
}
