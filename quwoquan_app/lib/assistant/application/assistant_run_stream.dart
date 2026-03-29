import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

enum AssistantRunStreamEventType {
  trace,
  chunk,
  completed,
  failed,
  answerDelta,
  journeyUpdate,
  processTimelineUpdate,
}

class AssistantRunStreamEvent {
  const AssistantRunStreamEvent._({
    required this.type,
    this.trace,
    this.chunkText,
    this.response,
    this.errorMessage,
    this.journey,
    this.processTimeline,
  });

  factory AssistantRunStreamEvent.trace(AssistantTraceEvent trace) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.trace,
        trace: trace,
      );

  factory AssistantRunStreamEvent.chunk(String chunkText) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.chunk,
        chunkText: chunkText,
      );

  factory AssistantRunStreamEvent.completed(AssistantRunResponse response) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.completed,
        response: response,
      );

  factory AssistantRunStreamEvent.failed(String errorMessage) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.failed,
        errorMessage: errorMessage,
      );

  factory AssistantRunStreamEvent.answerDelta(String delta) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.answerDelta,
        chunkText: delta,
      );

  factory AssistantRunStreamEvent.journey(AssistantJourney journey) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.journeyUpdate,
        journey: journey,
      );

  factory AssistantRunStreamEvent.processTimeline(
    List<ProcessTimelineFrame> processTimeline,
  ) => AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.processTimelineUpdate,
        processTimeline: processTimeline,
      );

  final AssistantRunStreamEventType type;
  final AssistantTraceEvent? trace;
  final String? chunkText;
  final AssistantRunResponse? response;
  final String? errorMessage;
  final AssistantJourney? journey;
  final List<ProcessTimelineFrame>? processTimeline;
}
