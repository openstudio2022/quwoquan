export 'package:quwoquan_app/assistant/generated/contracts/assistant_journey.g.dart';

import 'package:quwoquan_app/assistant/generated/contracts/assistant_journey.g.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';

extension AssistantJourneyCompat on AssistantJourney {
  bool get isEmpty =>
      stages.isEmpty && entries.isEmpty && summary.trim().isEmpty;

  AssistantJourneyStage? stageFor(JourneyStageId stageId) {
    for (final stage in stages) {
      if (stage.stageId == stageId) return stage;
    }
    return null;
  }

  JourneyStageId get activeStageId {
    for (final stage in stages) {
      if (stage.status == JourneyStageStatus.active ||
          stage.status == JourneyStageStatus.blocked) {
        return stage.stageId;
      }
    }
    return JourneyStageId.unknown;
  }
}

extension AssistantJourneyStageCompat on AssistantJourneyStage {
  bool get isVisible => stageId != JourneyStageId.unknown;
  bool get isCompleted => status == JourneyStageStatus.completed;
  bool get isActive =>
      status == JourneyStageStatus.active || status == JourneyStageStatus.blocked;
}
