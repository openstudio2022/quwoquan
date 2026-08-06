/// GatheringPlan 的 App typed port。
///
/// 这些类型只表达 App application intent/slice，不承担 wire 解码。Circle
/// generated handoff 交付前，production provider 会结构化 fail-fast。
enum GatheringPlanItemKind {
  agenda,
  place,
  routeSegment,
  task,
  checklist,
  note,
}

enum GatheringPlanProposalStatus { pending, committed, rejected }

sealed class GatheringPlanItemPayload {
  const GatheringPlanItemPayload();
}

final class GatheringPlanAgendaPayload extends GatheringPlanItemPayload {
  const GatheringPlanAgendaPayload({
    required this.startAt,
    required this.endAt,
    required this.summary,
  });

  final DateTime startAt;
  final DateTime endAt;
  final String summary;
}

final class GatheringPlanPlacePayload extends GatheringPlanItemPayload {
  const GatheringPlanPlacePayload({
    required this.placeRef,
    required this.arrivalNote,
  });

  final String placeRef;
  final String arrivalNote;
}

final class GatheringPlanRoutePayload extends GatheringPlanItemPayload {
  const GatheringPlanRoutePayload({
    required this.fromPlaceRef,
    required this.toPlaceRef,
    required this.transportMode,
  });

  final String fromPlaceRef;
  final String toPlaceRef;
  final String transportMode;
}

final class GatheringPlanTaskPayload extends GatheringPlanItemPayload {
  const GatheringPlanTaskPayload({
    required this.description,
    this.assigneeParticipationRef,
  });

  final String description;
  final String? assigneeParticipationRef;
}

final class GatheringPlanChecklistPayload extends GatheringPlanItemPayload {
  GatheringPlanChecklistPayload({required Iterable<String> entries})
    : entries = List<String>.unmodifiable(entries);

  final List<String> entries;
}

final class GatheringPlanNotePayload extends GatheringPlanItemPayload {
  const GatheringPlanNotePayload({required this.text});

  final String text;
}

final class GatheringPlanItem {
  GatheringPlanItem({
    required this.itemId,
    required this.title,
    required this.kind,
    required this.payload,
    Iterable<String> sourceRefs = const <String>[],
  }) : sourceRefs = List<String>.unmodifiable(sourceRefs);

  final String itemId;
  final String title;
  final GatheringPlanItemKind kind;
  final GatheringPlanItemPayload payload;
  final List<String> sourceRefs;
}

final class GatheringPlan {
  GatheringPlan({
    required this.gatheringId,
    required this.aggregateVersion,
    required this.currentRevisionId,
    required this.currentRevisionNumber,
    required this.currentRevisionDigest,
    required Iterable<GatheringPlanItem> items,
  }) : items = List<GatheringPlanItem>.unmodifiable(items);

  final String gatheringId;
  final int aggregateVersion;
  final String currentRevisionId;
  final int currentRevisionNumber;
  final String currentRevisionDigest;
  final List<GatheringPlanItem> items;
}

final class GatheringPlanProposal {
  GatheringPlanProposal({
    required this.proposalId,
    required this.gatheringId,
    required this.baseRevisionNumber,
    required this.baseRevisionDigest,
    required this.proposalDigest,
    required this.status,
    required Iterable<GatheringPlanItem> items,
  }) : items = List<GatheringPlanItem>.unmodifiable(items);

  final String proposalId;
  final String gatheringId;
  final int baseRevisionNumber;
  final String baseRevisionDigest;
  final String proposalDigest;
  final GatheringPlanProposalStatus status;
  final List<GatheringPlanItem> items;
}

final class GatheringPlanRevisionSummary {
  const GatheringPlanRevisionSummary({
    required this.revisionId,
    required this.revisionNumber,
    required this.digest,
    required this.createdAt,
  });

  final String revisionId;
  final int revisionNumber;
  final String digest;
  final DateTime createdAt;
}

final class GatheringPlanRevisionPage {
  GatheringPlanRevisionPage({
    required Iterable<GatheringPlanRevisionSummary> revisions,
    this.nextCursor,
  }) : revisions = List<GatheringPlanRevisionSummary>.unmodifiable(revisions);

  final List<GatheringPlanRevisionSummary> revisions;
  final String? nextCursor;
}

final class CreateGatheringPlanInput {
  CreateGatheringPlanInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required Iterable<GatheringPlanItem> items,
    Iterable<String> affectedParticipationRefs = const <String>[],
  }) : items = List<GatheringPlanItem>.unmodifiable(items),
       affectedParticipationRefs = List<String>.unmodifiable(
         affectedParticipationRefs,
       );

  final String idempotencyKey;
  final String gatheringId;
  final List<GatheringPlanItem> items;
  final List<String> affectedParticipationRefs;
}

final class ProposeGatheringPlanInput {
  ProposeGatheringPlanInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.expectedPlanVersion,
    required this.baseRevisionNumber,
    required this.baseRevisionDigest,
    required Iterable<GatheringPlanItem> items,
    Iterable<String> affectedParticipationRefs = const <String>[],
  }) : items = List<GatheringPlanItem>.unmodifiable(items),
       affectedParticipationRefs = List<String>.unmodifiable(
         affectedParticipationRefs,
       );

  final String idempotencyKey;
  final String gatheringId;
  final int expectedPlanVersion;
  final int baseRevisionNumber;
  final String baseRevisionDigest;
  final List<GatheringPlanItem> items;
  final List<String> affectedParticipationRefs;
}

final class CommitGatheringPlanProposalInput {
  const CommitGatheringPlanProposalInput({
    required this.idempotencyKey,
    required this.gatheringId,
    required this.proposalId,
    required this.expectedPlanVersion,
    required this.baseRevisionNumber,
    required this.baseRevisionDigest,
    required this.proposalDigest,
  });

  final String idempotencyKey;
  final String gatheringId;
  final String proposalId;
  final int expectedPlanVersion;
  final int baseRevisionNumber;
  final String baseRevisionDigest;
  final String proposalDigest;
}

abstract interface class GatheringPlanCommandWriter {
  Future<GatheringPlan> create(CreateGatheringPlanInput input);

  Future<GatheringPlanProposal> propose(ProposeGatheringPlanInput input);

  Future<GatheringPlan> commit(CommitGatheringPlanProposalInput input);
}

abstract interface class GatheringPlanQueryReader {
  Future<GatheringPlan?> getByGatheringId(String gatheringId);

  Future<GatheringPlanRevisionPage> listRevisions({
    required String gatheringId,
    String? cursor,
    int limit = 20,
  });
}
