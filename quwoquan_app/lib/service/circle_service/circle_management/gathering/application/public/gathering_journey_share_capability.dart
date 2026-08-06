import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_query.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';

/// 用户选择的分享范围；只描述意图，不复制 Journey 事实。
enum GatheringJourneyShareScope {
  full,
  route,
  day,
  planItem,
  experienceCollection,
}

enum GatheringJourneyShareVisibility { participants, public }

final class GatheringJourneyShareSelection {
  const GatheringJourneyShareSelection._({
    required this.scope,
    required this.visibility,
    this.dayIndex,
    this.planItemId,
    this.experienceIds = const <String>[],
  });

  const GatheringJourneyShareSelection.full({
    GatheringJourneyShareVisibility visibility =
        GatheringJourneyShareVisibility.public,
  }) : this._(scope: GatheringJourneyShareScope.full, visibility: visibility);

  const GatheringJourneyShareSelection.route({
    GatheringJourneyShareVisibility visibility =
        GatheringJourneyShareVisibility.public,
  }) : this._(scope: GatheringJourneyShareScope.route, visibility: visibility);

  const GatheringJourneyShareSelection.day({
    required int dayIndex,
    GatheringJourneyShareVisibility visibility =
        GatheringJourneyShareVisibility.public,
  }) : this._(
         scope: GatheringJourneyShareScope.day,
         visibility: visibility,
         dayIndex: dayIndex,
       );

  const GatheringJourneyShareSelection.planItem({
    required int dayIndex,
    required String planItemId,
    GatheringJourneyShareVisibility visibility =
        GatheringJourneyShareVisibility.public,
  }) : this._(
         scope: GatheringJourneyShareScope.planItem,
         visibility: visibility,
         dayIndex: dayIndex,
         planItemId: planItemId,
       );

  GatheringJourneyShareSelection.experiences({
    required List<String> experienceIds,
    GatheringJourneyShareVisibility visibility =
        GatheringJourneyShareVisibility.public,
  }) : this._(
         scope: GatheringJourneyShareScope.experienceCollection,
         visibility: visibility,
         experienceIds: List<String>.unmodifiable(experienceIds),
       );

  final GatheringJourneyShareScope scope;
  final GatheringJourneyShareVisibility visibility;
  final int? dayIndex;
  final String? planItemId;
  final List<String> experienceIds;
}

final class GatheringJourneyShareEntry {
  const GatheringJourneyShareEntry({
    required this.sourceRef,
    required this.sourceVersion,
    required this.sourceDigest,
    required this.title,
    this.dayIndex,
    this.planItemId,
  });

  final GatheringCanonicalObjectRef sourceRef;
  final int sourceVersion;
  final String sourceDigest;
  final String title;
  final int? dayIndex;
  final String? planItemId;
}

final class GatheringJourneyShareSnapshot {
  GatheringJourneyShareSnapshot({
    required this.snapshotId,
    required this.version,
    required this.gatheringId,
    required this.sourceDigest,
    required this.privacyPolicyDigest,
    required this.selection,
    required Iterable<GatheringJourneyShareEntry> entries,
  }) : entries = List<GatheringJourneyShareEntry>.unmodifiable(entries);

  final String snapshotId;
  final int version;
  final String gatheringId;
  final String sourceDigest;
  final String privacyPolicyDigest;
  final GatheringJourneyShareSelection selection;
  final List<GatheringJourneyShareEntry> entries;
}

final class CreateGatheringJourneyShareInput {
  const CreateGatheringJourneyShareInput({
    required this.idempotencyKey,
    required this.snapshot,
    required this.selection,
  });

  final String idempotencyKey;
  final GatheringJourneySnapshot snapshot;
  final GatheringJourneyShareSelection selection;
}

abstract interface class GatheringJourneyShareSnapshotQuery {
  Future<GatheringJourneyShareSnapshot?> get(String snapshotId);
}

abstract interface class GatheringJourneyShareSnapshotWriter {
  Future<GatheringJourneyShareSnapshot> create(
    CreateGatheringJourneyShareInput input,
  );
}
