import 'dart:async';
import 'dart:convert';

import 'package:quwoquan_app/assistant/application/assistant_journey_projector.dart';
import 'package:quwoquan_app/assistant/application/assistant_process_timeline_projector.dart';
import 'package:quwoquan_app/assistant/application/assistant_run_stream.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

class AssistantStreamingProjector {
  AssistantStreamingProjector(
    AssistantRunRequest request, {
    required ToolMetadataRegistry toolMetadataRegistry,
  }) : _journeyProjector = AssistantJourneyProjector(
         toolMetadataRegistry: toolMetadataRegistry,
       ),
       _processTimelineProjector = AssistantProcessTimelineProjector();

  final AssistantJourneyProjector _journeyProjector;
  final AssistantProcessTimelineProjector _processTimelineProjector;
  bool _sawAnswerDelta = false;
  String _lastProcessTimelineSignature = '';

  bool get sawAnswerDelta => _sawAnswerDelta;

  void emitTrace(
    AssistantTraceEvent event,
    StreamController<AssistantRunStreamEvent> controller,
  ) {
    if (controller.isClosed) return;
    final delta = _traceAnswerDelta(event);
    if (delta.isNotEmpty) {
      _sawAnswerDelta = true;
      controller.add(AssistantRunStreamEvent.answerDelta(delta));
    }
    _journeyProjector.consumeTrace(event);
    _emitProcessTimeline(
      controller,
      _processTimelineProjector.consumeTrace(event),
    );
  }

  void emitUserEvent(
    UserEvent event,
    StreamController<AssistantRunStreamEvent> controller,
  ) {
    if (controller.isClosed) return;
    if (event.type == UserEventType.answerDelta &&
        event.message.trim().isNotEmpty) {
      _sawAnswerDelta = true;
      controller.add(AssistantRunStreamEvent.answerDelta(event.message));
    }
    if (event.type == UserEventType.answerDelta) {
      _journeyProjector.consumeUserEvent(event);
    }
    if (event.type == UserEventType.processReplace ||
        event.type == UserEventType.processAppend ||
        event.type == UserEventType.processCommit) {
      _emitProcessTimeline(
        controller,
        _processTimelineProjector.consumeUserEvent(event),
      );
    }
  }

  void emitRemoteChunk(
    String chunkText,
    StreamController<AssistantRunStreamEvent> controller,
  ) {
    if (controller.isClosed || chunkText.trim().isEmpty) return;
    _sawAnswerDelta = true;
    controller.add(AssistantRunStreamEvent.answerDelta(chunkText));
    _journeyProjector.consumeUserEvent(
      const UserEvent(
        type: UserEventType.answerDelta,
        scope: UserEventScope.aggregation,
      ),
    );
  }

  String resolveCompletedDisplayText(AssistantRunResponse response) {
    final structured = response.structuredResponse;
    final decision = AssistantTurnDecision.fromMaps(structured: structured);
    if (decision.nextAction != AssistantNextAction.unknown &&
        decision.nextAction != AssistantNextAction.answer) {
      return '';
    }
    if (decision.messageKind == AssistantMessageKind.progress) return '';

    final artifactMarkdown =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
          response.displayMarkdown,
        );
    if (!_isUnsafeChunkDisplayCandidate(artifactMarkdown)) {
      return artifactMarkdown;
    }
    final artifactPlain =
        AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
          response.displayPlainText,
        );
    if (!_isUnsafeChunkDisplayCandidate(artifactPlain)) {
      return artifactPlain;
    }
    return '';
  }

  AssistantJourney resolveCompletedJourney(AssistantRunResponse response) {
    final direct = _journeyFromResponse(response);
    if (!direct.isEmpty) {
      return direct;
    }
    return _journeyProjector.snapshot;
  }

  List<ProcessTimelineFrame> resolveCompletedProcessTimeline(
    AssistantRunResponse response,
  ) {
    final direct = resolveAssistantProcessTimelineFromRunResponse(response);
    final projected = _processTimelineProjector.snapshot;
    if (hasStructuredProcessTimeline(projected) &&
        (!hasStructuredProcessTimeline(direct) ||
            projected.length >= direct.length)) {
      return projected;
    }
    if (direct.isNotEmpty) {
      return direct;
    }
    return projected;
  }

  bool _isUnsafeChunkDisplayCandidate(String raw) {
    final text =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(raw);
    if (text.isEmpty) {
      return true;
    }
    if (AssistantContentFilters.isNotDisplayable(text)) {
      return true;
    }
    return AssistantDisplayTextResolver.containsUnsafeDisplayProtocolLeak(text);
  }

  String _traceAnswerDelta(AssistantTraceEvent event) {
    if (event.type != AssistantTraceEventType.answerDelta &&
        event.type != AssistantTraceEventType.streamDelta) {
      return '';
    }
    return ((event.data?['delta'] as String?) ?? event.message).trim();
  }

  void _emitProcessTimeline(
    StreamController<AssistantRunStreamEvent> controller,
    List<ProcessTimelineFrame> processTimeline,
  ) {
    final visibleTimeline = buildVisibleProcessTimeline(processTimeline);
    if (controller.isClosed || visibleTimeline.isEmpty) return;
    final signature = jsonEncode(
      visibleTimeline.map((item) => item.toJson()).toList(growable: false),
    );
    if (signature == _lastProcessTimelineSignature) return;
    _lastProcessTimelineSignature = signature;
    controller.add(AssistantRunStreamEvent.processTimeline(visibleTimeline));
  }

  AssistantJourney _journeyFromResponse(AssistantRunResponse response) {
    return resolveAssistantJourneyFromRunResponse(response);
  }
}
