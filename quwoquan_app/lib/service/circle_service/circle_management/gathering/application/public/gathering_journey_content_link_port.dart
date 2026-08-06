import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';

enum GatheringJourneyContentTargetKind { gathering, day, planItem }

enum GatheringJourneyContentVisibility { participants, public }

final class GatheringJourneyContentTarget {
  const GatheringJourneyContentTarget.gathering()
    : kind = GatheringJourneyContentTargetKind.gathering,
      dayIndex = null,
      planItemId = null;

  const GatheringJourneyContentTarget.day(this.dayIndex)
    : kind = GatheringJourneyContentTargetKind.day,
      planItemId = null;

  const GatheringJourneyContentTarget.planItem({
    required this.dayIndex,
    required this.planItemId,
  }) : kind = GatheringJourneyContentTargetKind.planItem;

  final GatheringJourneyContentTargetKind kind;
  final int? dayIndex;
  final String? planItemId;
}

final class GatheringJourneyContentReferenceInput {
  const GatheringJourneyContentReferenceInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.contentRef,
    required this.sourceVersion,
    required this.sourceDigest,
    required this.target,
    required this.visibility,
  });

  final String idempotencyKey;
  final String gatheringId;
  final GatheringCanonicalObjectRef contentRef;
  final int sourceVersion;
  final String sourceDigest;
  final GatheringJourneyContentTarget target;
  final GatheringJourneyContentVisibility visibility;
}

final class GatheringJourneyContentReference {
  const GatheringJourneyContentReference({
    required this.referenceId,
    required this.gatheringId,
    required this.contentRef,
    required this.sourceVersion,
    required this.sourceDigest,
    required this.target,
    required this.visibility,
  });

  final String referenceId;
  final String gatheringId;
  final GatheringCanonicalObjectRef contentRef;
  final int sourceVersion;
  final String sourceDigest;
  final GatheringJourneyContentTarget target;
  final GatheringJourneyContentVisibility visibility;
}

abstract interface class GatheringJourneyContentReferenceWriter {
  Future<GatheringJourneyContentReference> put(
    GatheringJourneyContentReferenceInput input,
  );
}
