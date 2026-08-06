import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_share_capability.dart';

final class GatheringJourneyTravelogueDaySource {
  GatheringJourneyTravelogueDaySource({
    required this.dayIndex,
    required Iterable<GatheringJourneyShareEntry> entries,
  }) : entries = List<GatheringJourneyShareEntry>.unmodifiable(entries);

  final int dayIndex;
  final List<GatheringJourneyShareEntry> entries;
}

/// Content 本地草稿适配器可消费的隐私安全 Gathering Journey 来源。
///
/// 这里只接受 Circle owner 已裁剪并冻结的分享快照，不从实时计划、群消息、
/// 参与者名单或个人 Connector 补数据。
final class GatheringJourneyTravelogueDraftSource {
  GatheringJourneyTravelogueDraftSource({
    required this.localDraftId,
    required this.snapshotId,
    required this.snapshotVersion,
    required this.gatheringId,
    required this.sourceDigest,
    required this.privacyPolicyDigest,
    required this.scope,
    required this.visibility,
    required Iterable<GatheringJourneyTravelogueDaySource> days,
  }) : days = List<GatheringJourneyTravelogueDaySource>.unmodifiable(days);

  final String localDraftId;
  final String snapshotId;
  final int snapshotVersion;
  final String gatheringId;
  final String sourceDigest;
  final String privacyPolicyDigest;
  final GatheringJourneyShareScope scope;
  final GatheringJourneyShareVisibility visibility;
  final List<GatheringJourneyTravelogueDaySource> days;

  String get sourceEntityRef =>
      'circle.GatheringJourneyShareSnapshot:$snapshotId@$snapshotVersion';
}

enum GatheringJourneyTravelogueDraftBlockKind {
  heading,
  paragraph,
  orderedItem,
  bulletItem,
}

final class GatheringJourneyTravelogueDraftBlock {
  const GatheringJourneyTravelogueDraftBlock({
    required this.kind,
    required this.text,
  });

  final GatheringJourneyTravelogueDraftBlockKind kind;
  final String text;
}

final class GatheringJourneyTravelogueDraftContent {
  GatheringJourneyTravelogueDraftContent({
    required this.title,
    required this.summary,
    required Iterable<GatheringJourneyTravelogueDraftBlock> blocks,
  }) : blocks = List<GatheringJourneyTravelogueDraftBlock>.unmodifiable(blocks);

  final String title;
  final String summary;
  final List<GatheringJourneyTravelogueDraftBlock> blocks;
}

abstract interface class GatheringJourneyTravelogueDraftComposer {
  GatheringJourneyTravelogueDraftContent compose(
    GatheringJourneyTravelogueDraftSource source,
  );
}

abstract interface class GatheringJourneyTravelogueDraftWriter {
  Future<String> save(
    GatheringJourneyTravelogueDraftSource source,
    GatheringJourneyTravelogueDraftContent content,
  );
}

typedef GatheringJourneyTravelogueDraftIdFactory =
    String Function(String snapshotId);

/// 隐私快照只生成可编辑本地草稿；用户进入 Content 编辑器确认后才能发布。
final class GatheringJourneyTravelogueDraftCoordinator {
  const GatheringJourneyTravelogueDraftCoordinator({
    required this.composer,
    required this.writer,
    required this.draftIdFactory,
  });

  final GatheringJourneyTravelogueDraftComposer composer;
  final GatheringJourneyTravelogueDraftWriter writer;
  final GatheringJourneyTravelogueDraftIdFactory draftIdFactory;

  Future<String> create(GatheringJourneyShareSnapshot snapshot) async {
    final source = buildSource(snapshot);
    final content = composer.compose(source);
    if (content.title.trim().isEmpty ||
        content.summary.trim().isEmpty ||
        content.blocks.isEmpty ||
        content.blocks.any((block) => block.text.trim().isEmpty)) {
      throw StateError('Travelogue draft content must be complete');
    }
    final savedDraftId = (await writer.save(source, content)).trim();
    if (savedDraftId != source.localDraftId) {
      throw StateError('Travelogue writer returned a different local draft');
    }
    return savedDraftId;
  }

  GatheringJourneyTravelogueDraftSource buildSource(
    GatheringJourneyShareSnapshot snapshot,
  ) {
    _validateSnapshot(snapshot);
    final localDraftId = draftIdFactory(snapshot.snapshotId).trim();
    if (localDraftId.isEmpty) {
      throw StateError('Travelogue local draft id must not be blank');
    }

    final dayIndexes = <int>{};
    for (final entry in snapshot.entries) {
      final dayIndex = entry.dayIndex;
      if (dayIndex != null) {
        dayIndexes.add(dayIndex);
      }
    }
    final sortedDayIndexes = dayIndexes.toList(growable: false)..sort();
    final days = sortedDayIndexes.map((dayIndex) {
      final entries =
          snapshot.entries
              .where((entry) => entry.dayIndex == dayIndex)
              .toList(growable: false)
            ..sort(
              (left, right) =>
                  left.sourceRef.objectId.compareTo(right.sourceRef.objectId),
            );
      return GatheringJourneyTravelogueDaySource(
        dayIndex: dayIndex,
        entries: entries,
      );
    });

    return GatheringJourneyTravelogueDraftSource(
      localDraftId: localDraftId,
      snapshotId: snapshot.snapshotId,
      snapshotVersion: snapshot.version,
      gatheringId: snapshot.gatheringId,
      sourceDigest: snapshot.sourceDigest,
      privacyPolicyDigest: snapshot.privacyPolicyDigest,
      scope: snapshot.selection.scope,
      visibility: snapshot.selection.visibility,
      days: days,
    );
  }
}

void _validateSnapshot(GatheringJourneyShareSnapshot snapshot) {
  if (snapshot.snapshotId.trim().isEmpty ||
      snapshot.version <= 0 ||
      snapshot.gatheringId.trim().isEmpty ||
      snapshot.sourceDigest.trim().isEmpty ||
      snapshot.privacyPolicyDigest.trim().isEmpty) {
    throw ArgumentError('Active frozen Gathering share snapshot is required');
  }
  if (snapshot.entries.isEmpty) {
    throw ArgumentError('Gathering share snapshot has no editable facts');
  }
}
