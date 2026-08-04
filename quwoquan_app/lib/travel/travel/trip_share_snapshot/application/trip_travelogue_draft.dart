import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TripTravelogueDaySource {
  TripTravelogueDaySource({
    required this.dayIndex,
    required Iterable<TripShareItemSlice> items,
    required Iterable<TripShareMomentSlice> moments,
    required Iterable<TripShareContentLinkSlice> contentLinks,
    required Iterable<TripShareRouteStopSlice> routeStops,
  }) : items = List<TripShareItemSlice>.unmodifiable(items),
       moments = List<TripShareMomentSlice>.unmodifiable(moments),
       contentLinks = List<TripShareContentLinkSlice>.unmodifiable(
         contentLinks,
       ),
       routeStops = List<TripShareRouteStopSlice>.unmodifiable(routeStops);

  final int dayIndex;
  final List<TripShareItemSlice> items;
  final List<TripShareMomentSlice> moments;
  final List<TripShareContentLinkSlice> contentLinks;
  final List<TripShareRouteStopSlice> routeStops;
}

/// Content 本地草稿适配器可消费的隐私安全旅行来源。
///
/// 它只包含服务端 [TripShareSnapshot] 已裁剪并冻结的字段，不允许从实时 Trip、
/// 群消息、成员名单或个人 Connector 重新补数据。
final class TripTravelogueDraftSource {
  TripTravelogueDraftSource({
    required this.localDraftId,
    required this.snapshotId,
    required this.snapshotVersion,
    required this.tripId,
    required this.sourceRevisionId,
    required this.sourceRevisionNumber,
    required this.sourceDigest,
    required this.privacyPolicyDigest,
    required this.scope,
    required this.visibility,
    required Iterable<TripTravelogueDaySource> days,
  }) : days = List<TripTravelogueDaySource>.unmodifiable(days);

  final String localDraftId;
  final String snapshotId;
  final int snapshotVersion;
  final String tripId;
  final String sourceRevisionId;
  final int sourceRevisionNumber;
  final String sourceDigest;
  final String privacyPolicyDigest;
  final TripShareSnapshotScope scope;
  final TripShareSnapshotVisibility visibility;
  final List<TripTravelogueDaySource> days;

  String get sourceEntityRef =>
      'travel.TripShareSnapshot:$snapshotId@$snapshotVersion';
}

enum TripTravelogueDraftBlockKind {
  heading,
  paragraph,
  orderedItem,
  bulletItem,
}

final class TripTravelogueDraftBlock {
  const TripTravelogueDraftBlock({required this.kind, required this.text});

  final TripTravelogueDraftBlockKind kind;
  final String text;
}

final class TripTravelogueDraftContent {
  TripTravelogueDraftContent({
    required this.title,
    required this.summary,
    required Iterable<TripTravelogueDraftBlock> blocks,
  }) : blocks = List<TripTravelogueDraftBlock>.unmodifiable(blocks);

  final String title;
  final String summary;
  final List<TripTravelogueDraftBlock> blocks;
}

abstract interface class TripTravelogueDraftComposer {
  TripTravelogueDraftContent compose(TripTravelogueDraftSource source);
}

abstract interface class TripTravelogueDraftWriter {
  Future<String> save(
    TripTravelogueDraftSource source,
    TripTravelogueDraftContent content,
  );
}

typedef TripTravelogueDraftIdFactory = String Function(String snapshotId);

/// 将隐私快照投影为确定性本地草稿输入；用户进入 Content 编辑器后才能发布。
final class TripTravelogueDraftCoordinator {
  const TripTravelogueDraftCoordinator({
    required this.composer,
    required this.writer,
    required this.draftIdFactory,
  });

  final TripTravelogueDraftComposer composer;
  final TripTravelogueDraftWriter writer;
  final TripTravelogueDraftIdFactory draftIdFactory;

  Future<String> create(TripShareSnapshot snapshot) async {
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

  TripTravelogueDraftSource buildSource(TripShareSnapshot snapshot) {
    _validateSnapshot(snapshot);
    final localDraftId = draftIdFactory(snapshot.id).trim();
    if (localDraftId.isEmpty) {
      throw StateError('Travelogue local draft id must not be blank');
    }

    final dayIndexes = <int>{
      ...snapshot.items.map((item) => item.dayIndex),
      ...snapshot.moments.map((moment) => moment.dayIndex),
      ...snapshot.contentLinks.map((link) => link.dayIndex).whereType<int>(),
      ...snapshot.routeStops.map((stop) => stop.dayIndex),
    }.toList(growable: false)..sort();
    final days = dayIndexes.map((dayIndex) {
      final items =
          snapshot.items
              .where((item) => item.dayIndex == dayIndex)
              .toList(growable: false)
            ..sort(
              (left, right) => left.orderInDay.compareTo(right.orderInDay),
            );
      final moments =
          snapshot.moments
              .where((moment) => moment.dayIndex == dayIndex)
              .toList(growable: false)
            ..sort((left, right) => left.momentId.compareTo(right.momentId));
      final links =
          snapshot.contentLinks
              .where((link) => link.dayIndex == dayIndex)
              .toList(growable: false)
            ..sort((left, right) => left.linkId.compareTo(right.linkId));
      final stops =
          snapshot.routeStops
              .where((stop) => stop.dayIndex == dayIndex)
              .toList(growable: false)
            ..sort((left, right) => left.sequence.compareTo(right.sequence));
      return TripTravelogueDaySource(
        dayIndex: dayIndex,
        items: items,
        moments: moments,
        contentLinks: links,
        routeStops: stops,
      );
    });

    return TripTravelogueDraftSource(
      localDraftId: localDraftId,
      snapshotId: snapshot.id,
      snapshotVersion: snapshot.version,
      tripId: snapshot.tripId,
      sourceRevisionId: snapshot.sourceRevisionId,
      sourceRevisionNumber: snapshot.sourceRevisionNumber,
      sourceDigest: snapshot.sourceDigest,
      privacyPolicyDigest: snapshot.privacyPolicyDigest,
      scope: snapshot.scope,
      visibility: snapshot.visibility,
      days: days,
    );
  }
}

void _validateSnapshot(TripShareSnapshot snapshot) {
  if (snapshot.id.trim().isEmpty ||
      snapshot.version <= 0 ||
      snapshot.tripId.trim().isEmpty ||
      snapshot.sourceRevisionId.trim().isEmpty ||
      snapshot.sourceRevisionNumber <= 0 ||
      snapshot.sourceDigest.trim().isEmpty ||
      snapshot.privacyPolicyDigest.trim().isEmpty ||
      snapshot.status != TripShareSnapshotStatus.active) {
    throw ArgumentError('Active, frozen Trip share snapshot is required');
  }
  if (snapshot.items.isEmpty &&
      snapshot.moments.isEmpty &&
      snapshot.contentLinks.isEmpty &&
      snapshot.routeStops.isEmpty) {
    throw ArgumentError('Trip share snapshot has no editable travel facts');
  }
}
